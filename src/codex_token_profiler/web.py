"""Loopback service; dashboard routes are added in M6."""
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo
import hmac
import json
from pathlib import Path
import secrets
import socket
import threading
from urllib.parse import urlencode

from flask import Flask, Response,abort,jsonify,redirect,render_template,request,session,url_for

from .dashboard_queries import Filters,dataset,overview,prepare
from .exports import export_data
from .sources.sqlite import readonly


def create_app(config, state, stop_event, control_token, port, mutation_queue=None, lan=False):
    app = Flask(__name__)
    app.secret_key=control_token
    app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Strict")
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if lan:
        allowed.add(f"{socket.gethostname().lower()}:{port}")
        for address in socket.getaddrinfo(socket.gethostname(),port,family=socket.AF_INET,type=socket.SOCK_STREAM):
            allowed.add(f"{address[4][0]}:{port}")

    @app.before_request
    def local_only():
        if request.host.lower() not in allowed:
            abort(400)
        origin = request.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in allowed}:
            abort(403)

    @app.after_request
    def private_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; object-src 'none'"
        return response

    @app.get("/health")
    def health():
        return jsonify(dict(state))

    @app.post("/control/stop")
    def stop():
        if not hmac.compare_digest(request.headers.get("X-Profiler-Control", ""),control_token):
            abort(403)
        stop_event.set()
        return jsonify(status="stopping",instance=state["instance"])

    def filters():
        try:
            return Filters.parse(request.args)
        except (ValueError,KeyError):
            abort(400)

    @app.template_filter("metric")
    def metric(value):
        if value is None:
            return "Not recorded"
        if isinstance(value,int):
            return f"{value:,}"
        if isinstance(value,float):
            return f"{value:,.2f}"
        return {'unknown':'Not recorded','unknown_outcome':'Outcome not recorded',
                'no_verified_local_tokenizer':'Model tokenizer not configured','unavailable':'Content unavailable'}.get(str(value),str(value))

    @app.template_filter("cell")
    def cell(value,column):
        if value is None and column in ('argument_tokens','result_tokens','estimated_result_tokens'):
            return 'No model-tokenizer estimate'
        if value is None and column in ('rough_argument_tokens','rough_result_tokens'):
            return 'Text size unavailable'
        return metric(value)

    @app.template_filter("localtime")
    def localtime(value,zone):
        if not value:
            return "unknown"
        try:
            return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo(zone)).strftime('%Y-%m-%d %H:%M:%S %Z')
        except (ValueError,AttributeError):
            return str(value)

    @app.get("/")
    def home():
        return page("overview")

    @app.get("/view/<name>")
    def page(name):
        if name not in ("overview","usage","tools","rankings","results","patterns","sessions","timeline","comparisons"):
            abort(404)
        selected=filters()
        try:
            offset=max(0,int(request.args.get("offset",0)))
        except ValueError:
            abort(400)
        with readonly(config.data_dir/"profiler.sqlite") as connection:
            prepare(connection,selected)
            data=overview(connection,selected) if name=="overview" else None
            rows=dataset(connection,name,selected,limit=100,offset=offset) if name!="overview" else []
            models=[r[0] for r in connection.execute("SELECT DISTINCT coalesce(model,'unknown') FROM usage_facts ORDER BY 1")]
            projects=[r[0] for r in connection.execute("SELECT DISTINCT project_key(project) FROM usage_facts ORDER BY 1")]
        session.setdefault("csrf",secrets.token_hex(24))
        columns=[key for key in rows[0] if key!='rough_estimate_method'] if rows else []
        priority={
            'tools':['id','name','rough_result_tokens','result_bytes','status','session_id'],
            'results':['id','name','rough_result_tokens','result_bytes','completeness','session_id'],
            'rankings':['name','calls','rough_result_tokens','rough_results_known','result_bytes','failures','unknown_outcomes'],
            'sessions':['session_id','label','reported_total_tokens','noncached_input_tokens','cached_input_tokens','output_tokens','recorded_responses'],
        }.get(name,[])
        columns=[key for key in priority if key in columns]+[key for key in columns if key not in priority]
        return render_template("dashboard.html",name=name,filters=selected,query=urlencode(asdict(selected)),rows=rows,
            columns=columns,overview=data,state=dict(state),models=models,projects=projects,
            offset=offset,csrf=session["csrf"],notice=request.args.get("notice",""))

    @app.get("/export/<name>.<format>")
    def export(name,format):
        selected=filters()
        try:
            with readonly(config.data_dir/"profiler.sqlite") as connection:
                content=export_data(connection,name,selected,format)
        except ValueError:
            abort(400)
        return Response(content,mimetype="application/json" if format=="json" else "text/csv",
                        headers={"Content-Disposition":f'attachment; filename="{name}.{format}"'})

    @app.get("/provenance/<int:record_id>")
    def provenance(record_id):
        with readonly(config.data_dir/"profiler.sqlite") as connection:
            record=connection.execute("""SELECT r.id,r.byte_start,r.byte_end,r.digest,r.table_name,r.row_key,r.parser_version,
                s.original_path,s.kind FROM source_records r JOIN source_generations g ON g.id=r.generation_id
                JOIN sources s ON s.id=g.source_id WHERE r.id=?""",(record_id,)).fetchone()
        if not record:
            abort(404)
        result=dict(record)
        try:
            path=Path(result["original_path"])
            if result["table_name"] is None:
                from .ingest import hash_range
                with path.open("rb") as stream:
                    current=hash_range(stream,result["byte_start"],result["byte_end"]-result["byte_start"])
                result["verification"]="digest_matches" if current==result["digest"] else "source_changed"
            else:
                result["verification"]="database_row_locator; revision checked during ingestion" if path.exists() else "unavailable"
        except OSError:
            result["verification"]="unavailable"
        return render_template("provenance.html",record=result)

    @app.get("/pattern/<fingerprint>")
    def pattern(fingerprint):
        selected=filters()
        with readonly(config.data_dir/"profiler.sqlite") as connection:
            prepare(connection,selected)
            from .dashboard_queries import where
            condition,params=where(connection,selected,"t")
            rows=[dict(r) for r in connection.execute(f"SELECT t.id,t.session_id,t.name,t.timestamp,t.status,p.kind,p.likely_retry,(SELECT group_concat(record_id) FROM tool_sources WHERE tool_id=t.id) AS provenance_ids FROM pattern_occurrences p JOIN tool_calls t ON t.id=p.tool_id WHERE p.pattern_hash=? AND {condition} ORDER BY t.timestamp,t.id LIMIT 500",[fingerprint,*params])]
        return render_template("detail.html",title="Pattern occurrences",rows=rows,columns=list(rows[0]) if rows else [])

    @app.get('/tool/<tool_id>')
    def tool_detail(tool_id):
        from .previews import command_preview
        from .dashboard_queries import ROUGH_ARGUMENT,ROUGH_RESULT
        with readonly(config.data_dir/'profiler.sqlite') as connection:
            tool=connection.execute(f'SELECT t.*,{ROUGH_ARGUMENT} AS rough_argument_tokens,{ROUGH_RESULT} AS rough_result_tokens FROM tool_calls t WHERE t.id=?',(tool_id,)).fetchone()
            if tool is None:
                abort(404)
            preview=command_preview(connection,tool_id)
            references=[r[0] for r in connection.execute('SELECT record_id FROM tool_sources WHERE tool_id=?',(tool_id,))]
        return render_template('tool.html',tool=dict(tool),preview=preview,references=references)

    @app.post("/labels")
    def label():
        if not hmac.compare_digest(request.form.get("csrf",""),session.get("csrf","missing")):
            abort(403)
        value=request.form.get("label","").strip()
        identity=request.form.get("session_id","")
        if len(value)>200:
            abort(400)
        with readonly(config.data_dir/"profiler.sqlite") as connection:
            if not connection.execute("SELECT 1 FROM sessions WHERE id=?",(identity,)).fetchone():
                abort(404)
        if mutation_queue is None:
            abort(503)
        done=threading.Event()
        result={}
        mutation_queue.put(dict(operation="label",session_id=identity,label=value,done=done,result=result))
        if not done.wait(5):
            return "Saving label. Refresh the sessions view shortly.",202
        if result.get("error"):
            abort(500)
        return redirect(url_for("page",name="sessions",notice="Label saved"),code=303)

    return app

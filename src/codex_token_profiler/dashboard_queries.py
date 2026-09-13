from dataclasses import asdict,dataclass,replace
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo

from .config import canonical
from .normalize import TOKEN_FIELDS
from .queries import session_scope

NONCACHED = "CASE WHEN f.input_tokens>=f.cached_input_tokens THEN f.input_tokens-f.cached_input_tokens END"
RESPONSE_METRICS = f"sum(f.method='reported_response') AS recorded_responses,sum(f.method<>'reported_response') AS other_usage_intervals,sum(f.cached_input_tokens) AS cached_input_tokens,sum({NONCACHED}) AS noncached_input_tokens,count({NONCACHED}) AS noncached_known_facts"
ROUGH_RESULT = "CAST((json_extract(t.details_json,'$.result.characters')+3)/4 AS INTEGER)"
ROUGH_ARGUMENT = "CAST((json_extract(t.details_json,'$.argument.characters')+3)/4 AS INTEGER)"



@dataclass
class Filters:
    session: str = ""
    project: str = ""
    model: str = ""
    start: str = ""
    end: str = ""
    timezone: str = "Europe/London"
    scope: str = "own"
    sort: str = "calls"

    @classmethod
    def parse(cls, values):
        result=cls(**{key:str(values.get(key,default)) for key,default in asdict(cls()).items()})
        ZoneInfo(result.timezone)
        for value in (result.start,result.end):
            if value:
                date.fromisoformat(value)
        if result.start and result.end and result.start>result.end:
            raise ValueError("Start date must not follow end date")
        if result.scope not in ("own","descendants"):
            raise ValueError("Invalid session scope")
        if result.sort not in ("calls","failures","duration_ms","result_bytes","estimated_result_tokens","rough_result_tokens"):
            raise ValueError("Invalid ranking sort")
        return result


def prepare(connection,filters):
    zone=ZoneInfo(filters.timezone)
    roots=sorted([(canonical(r["root"]),r["id"]) for r in connection.execute("SELECT id,root FROM projects")],key=lambda r:len(r[0]),reverse=True)
    def project(value):
        if not value:
            return "unknown"
        path=canonical(value)
        for root,identity in roots:
            if path==root or path.startswith(root.rstrip("/\\")+ ("\\" if "\\" in root else "/")):
                return identity
        return path
    def local_day(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(zone).date().isoformat()
        except ValueError:
            return None
    connection.create_function("project_key",1,project,deterministic=True)
    connection.create_function("local_day",1,local_day,deterministic=True)


def where(connection,filters,alias):
    terms,parameters=[],[]
    if filters.session:
        sessions=session_scope(connection,filters.session,filters.scope=="descendants")
        terms.append(f"{alias}.session_id IN ("+",".join("?" for _ in sessions)+")")
        parameters.extend(sessions)
    if filters.project:
        terms.append(f"project_key({alias}.project)=?")
        parameters.append(filters.project)
    if filters.model:
        terms.append(f"coalesce({alias}.model,'unknown')=?")
        parameters.append(filters.model)
    zone=ZoneInfo(filters.timezone)
    for value,operator,extra in ((filters.start,">=",0),(filters.end,"<",1)):
        if value:
            day=date.fromisoformat(value)+timedelta(days=extra)
            bound=datetime.combine(day,datetime.min.time(),zone).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            terms.append(f"{alias}.timestamp{operator}?")
            parameters.append(bound)
    return " AND ".join(terms) or "1",parameters


def dataset(connection,name,filters,limit=100,offset=0):
    prepare(connection,filters)
    fw,fp=where(connection,filters,"f")
    tw,tp=where(connection,filters,"t")
    if name=="usage":
        query=f"""SELECT f.id,f.session_id,f.turn_id,f.timestamp,f.interval_start,f.interval_end,
            coalesce(f.model,'unknown') AS model,project_key(f.project) AS project,{','.join('f.'+k for k in TOKEN_FIELDS)},
            f.method,f.coverage,{NONCACHED} AS noncached_input_tokens,(SELECT group_concat(record_id) FROM fact_sources WHERE fact_id=f.id) AS provenance_ids
            FROM usage_facts f WHERE {fw} ORDER BY f.timestamp DESC,f.id"""
        parameters=fp
    elif name in ("tools","results"):
        query=f"""SELECT t.id,t.session_id,t.native_id,t.name,t.timestamp,t.completed_at,t.status,t.duration_ms,t.wall_ms,
            t.argument_bytes,t.result_bytes,t.argument_tokens,t.result_tokens,t.estimate_method,t.completeness,t.level,t.coverage,
            {ROUGH_ARGUMENT} AS rough_argument_tokens,{ROUGH_RESULT} AS rough_result_tokens,
            'characters_divided_by_4; rough text-size heuristic, not model-tokenizer or billed usage' AS rough_estimate_method,
            coalesce(t.model,'unknown') AS model,project_key(t.project) AS project,
            (SELECT group_concat(record_id) FROM tool_sources WHERE tool_id=t.id) AS provenance_ids
            FROM tool_calls t WHERE {tw} ORDER BY """+("t.result_bytes DESC,t.id" if name=="results" else "t.timestamp DESC,t.id")
        parameters=tp
    elif name=="rankings":
        query=f"""SELECT t.name,count(*) AS calls,sum(t.status='failed') AS failures,
            sum(t.status IN ('unknown','unknown_outcome','pending')) AS unknown_outcomes,
            sum(t.duration_ms) AS duration_ms,count(t.duration_ms) AS durations_known,
            sum(t.result_bytes) AS result_bytes,sum(t.result_tokens) AS estimated_result_tokens,
            count(t.result_tokens) AS result_estimates_known,
            sum({ROUGH_RESULT}) AS rough_result_tokens,count({ROUGH_RESULT}) AS rough_results_known,
            'characters_divided_by_4; rough text-size heuristic, not model-tokenizer or billed usage' AS rough_estimate_method FROM tool_calls t WHERE {tw}
            GROUP BY t.name ORDER BY {filters.sort} DESC,t.name"""
        parameters=tp
    elif name=="patterns":
        query=f"""SELECT p.pattern_hash,p.kind,count(*) AS occurrences,count(DISTINCT t.session_id) AS sessions,
            sum(p.likely_retry) AS likely_retries,min(t.timestamp) AS first_seen,max(t.timestamp) AS last_seen
            FROM pattern_occurrences p JOIN tool_calls t ON t.id=p.tool_id WHERE {tw}
            GROUP BY p.pattern_hash,p.kind HAVING count(*)>1 ORDER BY occurrences DESC,p.pattern_hash"""
        parameters=tp
    elif name=="sessions":
        restriction=""
        parameters=fp+tp
        if any((filters.session,filters.project,filters.model,filters.start,filters.end)):
            restriction="WHERE u.session_id IS NOT NULL OR tools.session_id IS NOT NULL"
        if filters.session and not any((filters.project,filters.model,filters.start,filters.end)):
            scope=session_scope(connection,filters.session,filters.scope=='descendants')
            restriction+=' OR s.id IN ('+','.join('?' for _ in scope)+')'
            parameters+=scope
        query=f"""WITH u AS (SELECT f.session_id,count(*) AS facts,sum(f.total_tokens) AS reported_total_tokens,
            sum(f.input_tokens) AS input_tokens,sum(f.output_tokens) AS output_tokens,{RESPONSE_METRICS},
            sum(f.method='unallocated_historical') AS unallocated_facts FROM usage_facts f WHERE {fw} GROUP BY f.session_id),
            tools AS (SELECT t.session_id,count(*) AS tool_calls,sum(t.status='failed') AS failures,
            sum(t.duration_ms) AS duration_ms,sum(t.result_bytes) AS result_bytes FROM tool_calls t WHERE {tw} GROUP BY t.session_id)
            SELECT s.id AS session_id,b.label,s.cwd,s.coverage,u.facts,u.reported_total_tokens,u.input_tokens,u.output_tokens,
            u.recorded_responses,u.other_usage_intervals,u.cached_input_tokens,u.noncached_input_tokens,u.noncached_known_facts,u.unallocated_facts,tools.tool_calls,tools.failures,tools.duration_ms,tools.result_bytes,
            (SELECT count(*) FROM accounting_gaps g WHERE g.session_id=s.id) AS accounting_gaps
            FROM sessions s LEFT JOIN u ON u.session_id=s.id LEFT JOIN tools ON tools.session_id=s.id
            LEFT JOIN benchmark_labels b ON b.session_id=s.id {restriction}
            ORDER BY u.reported_total_tokens DESC,s.id"""
    elif name=="timeline":
        nw,np=where(connection,filters,"n")
        # Fact/tool rows are canonical; context markers retain source provenance.
        query=f"""SELECT f.timestamp,f.session_id,'usage' AS kind,f.method AS description,f.total_tokens AS reported_tokens,
            f.id AS fact_id,(SELECT group_concat(record_id) FROM fact_sources WHERE fact_id=f.id) AS provenance_ids
            FROM usage_facts f WHERE {fw}
            UNION ALL SELECT t.timestamp,t.session_id,'tool',t.name,NULL,t.id,
            (SELECT group_concat(record_id) FROM tool_sources WHERE tool_id=t.id) FROM tool_calls t WHERE {tw}
            UNION ALL SELECT n.timestamp,n.session_id,'context',n.kind,NULL,cast(n.id AS TEXT),cast(n.record_id AS TEXT)
            FROM normalized_events n JOIN record_interpretations i ON i.record_id=n.record_id
            WHERE {nw} AND n.kind IN ('compacted','turn_context','session_meta','thread_settings_applied','task_started','task_complete','turn_aborted')
            ORDER BY timestamp DESC,fact_id"""
        parameters=fp+tp+np
    elif name=="comparisons":
        selected=[s.strip() for s in filters.session.split(',') if s.strip()]
        if not selected:
            selected=[r[0] for r in connection.execute("SELECT session_id FROM usage_facts GROUP BY session_id ORDER BY sum(total_tokens) DESC LIMIT 5")]
        rows=[]
        for identity in selected[:20]:
            for scope in ("own","descendants"):
                selection=replace(filters,session=identity,scope=scope)
                condition,values=where(connection,selection,"f")
                tool_condition,tool_values=where(connection,selection,"t")
                row=dict(connection.execute(f"SELECT {RESPONSE_METRICS},sum(f.input_tokens) AS input_tokens,sum(f.output_tokens) AS output_tokens,sum(total_tokens) AS reported_total_tokens,count(*) AS reported_facts,count(total_tokens) AS facts_with_known_total FROM usage_facts f WHERE {condition}",values).fetchone())
                row.update(dict(connection.execute(f"SELECT count(*) AS calls,sum(status='failed') AS failures,sum(duration_ms) AS duration_ms,sum(result_bytes) AS result_bytes FROM tool_calls t WHERE {tool_condition}",tool_values).fetchone()))
                label=connection.execute("SELECT label FROM benchmark_labels WHERE session_id=?",(identity,)).fetchone()
                scope_ids=session_scope(connection,identity,scope=="descendants")
                placeholders=','.join('?' for _ in scope_ids)
                row['accounting_gaps_all_dates']=connection.execute(f"SELECT count(*) FROM accounting_gaps WHERE session_id IN ({placeholders})",scope_ids).fetchone()[0]
                row['coverage']='known subtotal; inspect accounting gaps' if row['reported_facts'] else 'unknown usage'
                rows.append(dict(session_id=identity,label=label[0] if label else None,scope="own_thread" if scope=="own" else "unique_descendants",sessions_in_scope=len(session_scope(connection,identity,scope=="descendants")),**row))
        return rows if limit is None else rows[offset:offset+limit]
    else:
        raise ValueError("Unknown dataset")
    if limit is not None:
        query+=" LIMIT ? OFFSET ?"
        parameters=[*parameters,min(max(int(limit),1),500),max(int(offset),0)]
    return [dict(row) for row in connection.execute(query,parameters)]


def overview(connection,filters):
    prepare(connection,filters)
    condition,params=where(connection,filters,"f")
    fields=",".join(f"sum({k}) AS {k},count({k}) AS {k}_known" for k in TOKEN_FIELDS)
    totals=dict(connection.execute(f"SELECT count(*) AS facts,{fields},{RESPONSE_METRICS} FROM usage_facts f WHERE {condition}",params).fetchone())
    days=[dict(r) for r in connection.execute(f"SELECT local_day(f.timestamp) AS day,sum(total_tokens) AS total_tokens FROM usage_facts f WHERE {condition} GROUP BY day ORDER BY day",params)]
    sources=[dict(r) for r in connection.execute("SELECT disposition,count(*) AS sources FROM sources GROUP BY disposition")]
    gaps=[dict(r) for r in connection.execute("SELECT code,count(*) AS intervals FROM accounting_gaps GROUP BY code")]
    coverage=dict(connection.execute("SELECT min(timestamp) AS first_record,max(timestamp) AS last_record FROM source_records").fetchone())
    attribution=[dict(r) for r in connection.execute(f"SELECT coalesce(f.model,'unknown') AS model,f.method,count(*) AS facts,sum(f.total_tokens) AS total_tokens FROM usage_facts f WHERE {condition} GROUP BY f.model,f.method ORDER BY total_tokens DESC",params)]
    unknown=connection.execute("SELECT count(*) FROM sessions s WHERE coalesce(s.host_kind,'local')='local' AND NOT EXISTS(SELECT 1 FROM usage_facts f WHERE f.session_id=s.id)").fetchone()[0]
    maximum=max([day["total_tokens"] or 0 for day in days]+[1])
    for day in days:
        day["height"]=140*(day["total_tokens"] or 0)/maximum
    return dict(totals=totals,days=days,sources=sources,gaps=gaps,coverage=coverage,unknown_sessions=unknown,attribution=attribution)

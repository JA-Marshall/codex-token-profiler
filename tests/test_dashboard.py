import csv
import io
import json
import threading

import pytest

from codex_token_profiler.accounting import reconcile
from codex_token_profiler.config import Config
from codex_token_profiler.dashboard_queries import Filters,dataset,overview
from codex_token_profiler.db import connect
from codex_token_profiler.exports import export_data
from codex_token_profiler.ingest import import_sources
from codex_token_profiler.tools import rebuild_tools
from codex_token_profiler.web import create_app
from .fixtures.families import usage


@pytest.fixture
def dashboard(tmp_path):
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    folder=config.codex_home/"sessions"
    folder.mkdir(parents=True)
    records=[dict(timestamp="2026-03-29T00:00:00Z",type="session_meta",payload=dict(id="s",cwd="C:/synthetic")),
             dict(timestamp="2026-03-29T00:00:00Z",type="turn_context",payload=dict(turn_id="t",model="=malicious-model"))]
    for n,timestamp in enumerate(("2026-03-29T22:59:59Z","2026-03-29T23:00:00Z"),1):
        records.append(dict(timestamp=timestamp,type="token_usage_record",payload=dict(response_id=f"r{n}",thread_id="s",turn_id="t",usage=usage(),thread_token_usage=usage(100*n,20*n,40*n,5*n))))
    (folder/"s.jsonl").write_text("".join(json.dumps(r)+"\n" for r in records))
    connection=connect(config.data_dir)
    import_sources(connection,config)
    reconcile(connection)
    rebuild_tools(connection)
    connection.execute("INSERT INTO benchmark_labels VALUES ('s','<script>alert(1)</script>','now')")
    connection.commit()
    yield config,connection
    connection.close()


def test_dst_filters_tables_totals_and_exports_agree(dashboard):
    config,connection=dashboard
    filters=Filters(start="2026-03-29",end="2026-03-29")
    rows=dataset(connection,"usage",filters)
    assert len(rows)==1 and rows[0]["total_tokens"]==120
    assert overview(connection,filters)["totals"]["total_tokens"]==120
    exported=json.loads(export_data(connection,"usage",filters,"json"))
    assert exported["rows"]==rows
    csv_rows=list(csv.DictReader(io.StringIO(export_data(connection,"usage",filters,"csv"))))
    assert csv_rows[0]["model"].startswith("'=malicious")
    assert csv_rows[0]["total_tokens"]=="120"


def test_pagination_and_comparison_scope(dashboard):
    _,connection=dashboard
    first=dataset(connection,"usage",Filters(),limit=1)
    second=dataset(connection,"usage",Filters(),limit=1,offset=1)
    assert first[0]["id"]!=second[0]["id"]
    rows=dataset(connection,"comparisons",Filters(session="s"))
    assert len(rows)==2 and all(r["reported_total_tokens"]==240 for r in rows)
    exported=json.loads(export_data(connection,'comparisons',Filters(session='s'),'json'))
    assert len(exported['rows'][0]['usage_fact_ids'].split(','))==2


def test_cli_export_uses_shared_filters_and_protects_sources(dashboard,tmp_path,capsys):
    from codex_token_profiler.cli import main
    config,connection=dashboard
    output=tmp_path/'out.csv'
    args=['export','--codex-home',str(config.codex_home),'--data-dir',str(config.data_dir),'--format','csv','--start','2026-03-29','--end','2026-03-29']
    assert main([*args,'--output',str(output)])==0
    assert len(list(csv.DictReader(io.StringIO(output.read_text()))))==1
    with pytest.raises(SystemExit):
        main([*args,'--output',str(config.codex_home/'unsafe.csv')])
    assert not (config.codex_home/'unsafe.csv').exists()


def test_selected_metadata_only_session_keeps_unknown_usage(dashboard):
    _,connection=dashboard
    connection.execute("INSERT INTO sessions(id) VALUES ('metadata-only')")
    rows=dataset(connection,'sessions',Filters(session='metadata-only'))
    assert len(rows)==1 and rows[0]['reported_total_tokens'] is None
    exported=json.loads(export_data(connection,'sessions',Filters(session='metadata-only'),'json'))
    assert exported['rows'][0]['reported_total_tokens'] is None


def test_rankings_sort_and_aggregate_export_references(dashboard):
    _,connection=dashboard
    for identity,name,status,duration in [('a1','A','succeeded',10),('a2','A','succeeded',10),('b1','B','failed',100)]:
        connection.execute("""INSERT INTO tool_calls(id,session_id,name,status,duration_ms,result_bytes,estimate_method,completeness,level,coverage,details_json)
            VALUES (?,'s',?,?,?,0,'no_verified_local_tokenizer','retained_content','outer','observed','{}')""",(identity,name,status,duration))
    assert dataset(connection,'rankings',Filters(sort='calls'))[0]['name']=='A'
    assert dataset(connection,'rankings',Filters(sort='failures'))[0]['name']=='B'
    assert dataset(connection,'rankings',Filters(sort='duration_ms'))[0]['name']=='B'
    result=json.loads(export_data(connection,'rankings',Filters(sort='calls'),'json'))['rows']
    assert result[0]['tool_fact_ids']=='a1,a2'
    assert result[0]['result_bytes']==0 and result[0]['estimated_result_tokens'] is None
    csv_rows=list(csv.DictReader(io.StringIO(export_data(connection,'rankings',Filters(),'csv'))))
    assert csv_rows[0]['result_bytes']=='0' and csv_rows[0]['estimated_result_tokens']==''


def test_dashboard_escapes_labels_serves_local_assets_and_provenance(dashboard):
    config,connection=dashboard
    app=create_app(config,dict(instance="test",status="running"),threading.Event(),"test-secret",8765)
    client=app.test_client()
    for view in ("overview","usage","tools","rankings","results","patterns","sessions","timeline","comparisons"):
        response=client.get(f"/view/{view}",base_url="http://127.0.0.1:8765")
        assert response.status_code==200,(view,response.data[:100])
        assert b'<script>alert(1)</script>' not in response.data
    page=client.get("/view/sessions",base_url="http://127.0.0.1:8765").data
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in page
    assert b'src="https://' not in page and b'href="https://' not in page
    reference=connection.execute("SELECT record_id FROM fact_sources LIMIT 1").fetchone()[0]
    assert b'digest_matches' in client.get(f"/provenance/{reference}",base_url="http://127.0.0.1:8765").data
    assert client.post("/labels",base_url="http://127.0.0.1:8765",data=dict(session_id="s",label="bad")).status_code==403
    assert client.get("/view/usage?timezone=Invalid",base_url="http://127.0.0.1:8765").status_code==400

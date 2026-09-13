import json
import threading

from codex_token_profiler.dashboard_queries import Filters,dataset,overview
from codex_token_profiler.ingest import import_sources
from codex_token_profiler.tools import rebuild_tools
from codex_token_profiler.previews import command_preview,redact
from codex_token_profiler.web import create_app
from .test_dashboard import dashboard


def add_call(config,connection):
    path=config.codex_home/'sessions'/'s.jsonl'
    records=[dict(timestamp='2026-03-29T23:00:01Z',type='response_item',payload=dict(type='function_call',call_id='c',name='exec_command',arguments=json.dumps({'cmd':'echo <script>hello</script>; run --password hidden-secret'}))),
        dict(timestamp='2026-03-29T23:00:02Z',type='response_item',payload=dict(type='function_call_output',call_id='c',output='abcdefgh')),
        dict(timestamp='2026-03-29T23:00:03Z',type='response_item',payload=dict(type='function_call_output',call_id='c',output='ijkl'))]
    with path.open('a',encoding='utf-8') as stream:
        for row in records: stream.write(json.dumps(row)+'\n')
    import_sources(connection,config); rebuild_tools(connection)
    return path,connection.execute('SELECT id FROM tool_calls').fetchone()[0]


def test_rough_sizes_use_text_characters_and_preserve_reported_estimates(dashboard):
    config,connection=dashboard
    add_call(config,connection)
    tool=dataset(connection,'tools',Filters())[0]
    assert tool['rough_result_tokens']==3  # Two chunks, twelve retained characters.
    assert tool['result_tokens'] is None
    ranking=dataset(connection,'rankings',Filters(sort='rough_result_tokens'))[0]
    assert ranking['rough_result_tokens']==3 and ranking['rough_results_known']==1
    assert 'characters_divided_by_4' in ranking['rough_estimate_method']


def test_response_counts_and_noncached_input_follow_date_filters(dashboard):
    _,connection=dashboard
    selection=Filters(start='2026-03-29',end='2026-03-29')
    result=overview(connection,selection)['totals']
    assert result['recorded_responses']==1
    assert result['noncached_input_tokens']==60
    rows=dataset(connection,'sessions',selection)
    assert rows[0]['recorded_responses']==1 and rows[0]['noncached_input_tokens']==60
    comparisons=dataset(connection,'comparisons',Filters(session='s'))
    assert comparisons[0]['recorded_responses']==2 and comparisons[0]['noncached_input_tokens']==120


def test_preview_is_redacted_escaped_and_refuses_changed_source(dashboard):
    config,connection=dashboard
    path,identity=add_call(config,connection)
    preview=command_preview(connection,identity)
    assert 'hidden-secret' not in preview['text'] and '[redacted]' in preview['text']
    app=create_app(config,{'status':'running'},threading.Event(),'secret',8765)
    response=app.test_client().get('/tool/'+identity,base_url='http://127.0.0.1:8765')
    assert response.status_code==200
    assert b'<script>hello</script>' not in response.data and b'&lt;script&gt;hello&lt;/script&gt;' in response.data
    path.write_text(path.read_text().replace('hidden-secret','changed-secret'))
    assert command_preview(connection,identity)['text'] is None
    assert 'hidden-secret' not in redact('Authorization=hidden-secret')


def test_completion_preview_exposes_command_without_result(dashboard):
    config,connection=dashboard
    path=config.codex_home/'sessions'/'s.jsonl'
    record=dict(timestamp='2026-03-29T23:00:01Z',type='event_msg',payload=dict(
        type='item_completed',thread_id='s',turn_id='t',item=dict(
            type='CommandExecution',id='completion',command=['echo','hello'],
            cwd='C:/work',status='completed',exit_code=0,
            aggregated_output='private result must never appear')))
    with path.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(record)+'\n')
    import_sources(connection,config); rebuild_tools(connection)
    identity=connection.execute('SELECT id FROM tool_calls').fetchone()[0]
    preview=command_preview(connection,identity)
    assert 'hello' in preview['text'] and 'C:/work' in preview['text']
    assert 'private result' not in preview['text']

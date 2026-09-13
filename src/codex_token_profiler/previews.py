"""On-demand, bounded command previews from digest-verified rollout records.

No raw preview text is persisted or executed. Full results/messages are not served.
"""
import hashlib
import json
import re
from pathlib import Path

MAX_PREVIEW_RECORD = 1024 * 1024


def redact(text):
    text=re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+',r'\1[redacted]',text)
    text=re.sub(r'\bsk-[A-Za-z0-9_-]+', '[redacted]', text)
    text=re.sub(r'''(?i)(--(?:api-key|token|password|secret)\s+)("[^"]*"|'[^']*'|\S+)''',r'\1[redacted]',text)
    text=re.sub(r'''(?ix)(["']?(?:api[_-]?key|access[_-]?token|authorization|password|secret)["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;}]+)''',r'\1[redacted]',text)
    return text[:2000] + ('\n[preview truncated]' if len(text)>2000 else '')


def command_preview(connection, tool_id):
    records=connection.execute("""SELECT r.byte_start,r.byte_end,r.digest,s.original_path
        FROM tool_sources ts CROSS JOIN source_records r ON r.id=ts.record_id
        JOIN source_generations g ON g.id=r.generation_id JOIN sources s ON s.id=g.source_id
        WHERE ts.tool_id=? AND r.table_name IS NULL
        AND EXISTS (SELECT 1 FROM normalized_events n INDEXED BY normalized_record
                    WHERE n.record_id=r.id AND n.kind IN ('tool_call','item_completed'))
        ORDER BY r.id DESC LIMIT 8""",(tool_id,))
    reason='No supported original call record available'
    for record in records:
        length=record['byte_end']-record['byte_start']
        if length>MAX_PREVIEW_RECORD:
            reason='Source record exceeds preview size limit'; continue
        try:
            with Path(record['original_path']).open('rb') as stream:
                stream.seek(record['byte_start']); raw=stream.read(length)
            if hashlib.sha256(raw).hexdigest()!=record['digest']:
                reason='Source changed since ingestion'; continue
            payload=json.loads(raw).get('payload',{})
            if payload.get('type') == 'item_completed':
                item=payload.get('item',{})
                if item.get('type') in ('CommandExecution','commandExecution'):
                    value={'command':item.get('command'), 'workdir':item.get('cwd')}
                elif item.get('type') in ('McpToolCall','mcpToolCall','DynamicToolCall','dynamicToolCall'):
                    value=item.get('arguments')
                else:
                    continue
            elif payload.get('type') in ('function_call','custom_tool_call'):
                value=payload.get('arguments',payload.get('input'))
            else:
                continue
            if value is None:
                continue
            if isinstance(value,str):
                try: value=json.loads(value)
                except ValueError: pass
            if isinstance(value,dict):
                value={k:v for k,v in value.items() if k in ('cmd','command','code','path','file_path','offset','limit','start_line','end_line','workdir')}
                if not value:
                    return dict(status='No command/path fields in this call',text=None)
                value=json.dumps(value,ensure_ascii=False,indent=2)
            if not isinstance(value,str):
                return dict(status='Unsupported command shape',text=None)
            return dict(status='Digest verified; common secrets redacted; preview only',text=redact(value))
        except (OSError,ValueError,TypeError):
            reason='Original call could not be read'
    return dict(status=reason,text=None)

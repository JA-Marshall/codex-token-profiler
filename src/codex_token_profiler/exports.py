import csv
from dataclasses import asdict
import io
import json

from .dashboard_queries import dataset


def export_data(connection,name,filters,format):
    rows=dataset(connection,name,filters,limit=None)
    # Aggregate rows identify the canonical facts behind their totals. Those facts
    # carry exact source-record references in the usage/tools exports and UI.
    if name in ('rankings','patterns','sessions','comparisons'):
        from .dashboard_queries import where
        from dataclasses import replace
        for row in rows:
            selection=filters
            if name in ('sessions','comparisons'):
                selection=replace(filters,session=row['session_id'],scope='descendants' if row.get('scope')=='unique_descendants' else 'own')
                fw,fp=where(connection,selection,'f')
                row['usage_fact_ids']=','.join(r[0] for r in connection.execute(f'SELECT f.id FROM usage_facts f WHERE {fw} ORDER BY f.id',fp))
            tw,tp=where(connection,selection,'t')
            extra=''
            if name=='rankings':
                extra=' AND t.name=?'; tp.append(row['name'])
            elif name=='patterns':
                extra=' AND EXISTS(SELECT 1 FROM pattern_occurrences p WHERE p.tool_id=t.id AND p.pattern_hash=? AND p.kind=?)'; tp.extend((row['pattern_hash'],row['kind']))
            row['tool_fact_ids']=','.join(r[0] for r in connection.execute(f'SELECT t.id FROM tool_calls t WHERE {tw}{extra} ORDER BY t.id',tp))
    metadata=dict(dataset=name,filters=asdict(filters),timezone=filters.timezone,timestamps="UTC ISO 8601",
                  units="tokens; bytes; milliseconds where column ends _ms",unknown="null/empty is unknown; zero is measured",
                  accounting="cached input and reasoning output are subsets; tool token sizes are estimates, not billed cost")
    metadata['provenance']='provenance_ids identify raw records; aggregate usage_fact_ids/tool_fact_ids resolve through usage/tools exports'
    if format=="json":
        return json.dumps(dict(metadata=metadata,rows=rows),ensure_ascii=False,indent=2)
    if format!="csv":
        raise ValueError("Unknown export format")
    output=io.StringIO(newline="")
    def safe(value):
        if isinstance(value,str) and (value.lstrip().startswith(("=","+","-","@")) or value.startswith(("\t","\r"))):
            return "'"+value
        return value
    keys=list(rows[0]) if rows else ["dataset"]
    writer=csv.DictWriter(output,fieldnames=[*keys,"display_timezone","units","measurement_note"])
    writer.writeheader()
    for row in rows:
        writer.writerow({**{k:safe(v) for k,v in row.items()},"display_timezone":filters.timezone,"units":metadata["units"],"measurement_note":metadata["accounting"]})
    return output.getvalue()

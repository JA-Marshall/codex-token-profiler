"""Coverage-aware read queries over canonical facts."""
from .normalize import TOKEN_FIELDS


def session_scope(connection, root, descendants=False):
    seen, pending = {root}, [root]
    if descendants:
        while pending:
            parent = pending.pop()
            for row in connection.execute("SELECT DISTINCT child_id FROM session_edges WHERE parent_id=?", (parent,)):
                if row[0] not in seen:
                    seen.add(row[0])
                    pending.append(row[0])
    return sorted(seen)


def usage_summary(connection, root, descendants=False):
    scope = session_scope(connection, root, descendants)
    placeholders = ",".join("?" for _ in scope)
    fields = ",".join(f"sum({key}) AS {key},count({key}) AS {key}_known_facts" for key in TOKEN_FIELDS)
    row = dict(connection.execute(f"SELECT count(*) AS facts,count(DISTINCT session_id) AS sessions_with_reported_usage,{fields} FROM usage_facts WHERE session_id IN ({placeholders})", scope).fetchone())
    row["scope"] = "unique_descendants" if descendants else "own_thread"
    row["sessions_in_scope"] = len(scope)
    row["accounting_gaps"] = connection.execute(f"SELECT count(*) FROM accounting_gaps WHERE session_id IN ({placeholders})", scope).fetchone()[0]
    row["unallocated_facts"] = connection.execute(f"SELECT count(*) FROM usage_facts WHERE session_id IN ({placeholders}) AND method='unallocated_historical'", scope).fetchone()[0]
    return row

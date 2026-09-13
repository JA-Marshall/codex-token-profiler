from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def readonly(path: Path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")  # One consistent read snapshot for all related queries.
        yield connection
    finally:
        connection.close()


def schema(connection):
    tables = {}
    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        name = row[0]
        # Names originate in SQLite schema, not command input; quote identifiers.
        quoted = name.replace('"', '""')
        tables[name] = [dict(r) for r in connection.execute(f'PRAGMA table_info("{quoted}")')]
    return tables

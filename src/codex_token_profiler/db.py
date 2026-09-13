from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import secrets
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "profiler.sqlite"
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    migrations = sorted((Path(__file__).parent / "migrations").glob("*.sql"))
    if version > len(migrations):
        connection.close()
        raise ValueError("Profiler schema newer than this application")
    for index, migration in enumerate(migrations, 1):
        if index <= version:
            continue
        if version:
            backup_path = data_dir / f"profiler-before-v{index}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}.sqlite"
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()
        try:
            connection.executescript("BEGIN IMMEDIATE;\n" + migration.read_text() + f"\nPRAGMA user_version={index};\nCOMMIT;")
        except Exception:
            connection.rollback()
            connection.close()
            raise
    connection.execute("INSERT OR IGNORE INTO settings VALUES ('pattern_salt',?)", (secrets.token_hex(32),))
    connection.commit()
    return connection


@contextmanager
def writer_lock(data_dir: Path):
    """OS-held lock; stale files do not establish a live writer."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "writer.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        import os
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("A profiler writer is already running for this data directory") from None
        else:
            import fcntl
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError("A profiler writer is already running for this data directory") from None
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

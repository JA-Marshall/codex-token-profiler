import argparse
import json
from pathlib import Path

from .config import Config
from .discovery import discover


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local read-only Codex token profiler")
    parser.add_argument("command", choices=["discover", "import", "reconcile", "audit", "run", "start", "stop", "status", "export"])
    parser.add_argument("--dataset", choices=["usage","tools","results","rankings","patterns","sessions","timeline","comparisons"], default="usage")
    parser.add_argument("--format", choices=["json","csv"], default="json")
    from .dashboard_queries import Filters
    from dataclasses import asdict
    for key,default in asdict(Filters()).items():
        parser.add_argument("--"+key,default=default)
    parser.add_argument("--codex-home")
    parser.add_argument("--data-dir")
    parser.add_argument("--source-root", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inspect", action="store_true", help="Scan record shapes and numeric counter behavior")
    parser.add_argument("--finalized-source", action="append", default=[], help="Explicitly validate a stable closed source's final non-newline record")
    parser.add_argument("--retry-window", type=float, default=600, help="Likely-retry window in seconds")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--lan",action="store_true",help="Serve without a password on local network interfaces")
    parser.add_argument("--poll-interval",type=float,default=2)
    parser.add_argument("--discovery-interval",type=float,default=30)
    parser.add_argument("--reconcile-interval",type=float,default=300)
    parser.add_argument("--json",action="store_true",help="Machine-readable status (all commands already emit JSON)")
    args = parser.parse_args(argv)
    if args.inspect and args.command != 'discover':
        parser.error('--inspect applies only to discover')
    if args.retry_window <= 0:
        parser.error("--retry-window must be positive")
    if not 1 <= args.port <= 65535 or min(args.poll_interval,args.discovery_interval,args.reconcile_interval)<=0:
        parser.error("Port or polling intervals are invalid")
    config = Config.resolve(args.codex_home, args.data_dir, args.source_root)
    if args.command == "export":
        from .sources.sqlite import readonly
        from .exports import export_data
        try:
            selected=Filters.parse(vars(args))
        except (ValueError,KeyError) as exc:
            parser.error(str(exc))
        with readonly(config.data_dir / "profiler.sqlite") as connection:
            rendered=export_data(connection,args.dataset,selected,args.format)
        result={"dataset":args.dataset,"format":args.format}
    elif args.command in ("run","start","stop","status"):
        from . import lifecycle
        if args.command in ("run","start"):
            result = getattr(lifecycle,args.command)(config,args.port,args.poll_interval,args.discovery_interval,args.reconcile_interval,args.retry_window,lan=args.lan)
        else:
            result = getattr(lifecycle,args.command)(config)
    elif args.command == "audit":
        from .sources.sqlite import readonly
        from .audit import audit_sources
        with readonly(config.data_dir / "profiler.sqlite") as connection:
            result = audit_sources(connection)
    elif args.command in ("import", "reconcile"):
        from .db import connect, writer_lock
        from .ingest import import_sources
        with writer_lock(config.data_dir):
            connection = connect(config.data_dir)
            try:
                result = import_sources(connection, config, full=args.command == "reconcile", finalized_sources=args.finalized_source)
                if args.command == "reconcile":
                    from .accounting import reconcile
                    result["accounting"] = reconcile(connection)
                    from .tools import rebuild_tools
                    result["tools"] = rebuild_tools(connection, retry_window_seconds=args.retry_window)
            finally:
                connection.close()
    else:
        result = discover(config)
    if args.inspect:
        from .inspection import inspect_inventory
        result["inspection"] = inspect_inventory(result)
    if args.command != "export":
        rendered = json.dumps(result, indent=2)
    if args.output:
        output = args.output.resolve()
        if any(output.is_relative_to(p) for p in [config.codex_home, *config.extra_roots, *[p for p in (config.sqlite_home, config.log_dir) if p]]):
            parser.error("Output cannot be written under a source root")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(json.dumps({"output": str(output), "counts": result.get("counts", {k: v for k, v in result.items() if k != "sources"})}))
    else:
        print(rendered)
    return int(bool(result.get("diagnostics")) or bool(result.get("failed")) or bool(result.get("response_oracle", {}).get("mismatches")) or any(s.get("disposition") in ("failed", "mismatch") for s in result.get("sources",[])))

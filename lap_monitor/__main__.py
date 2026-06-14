# -*- coding: utf-8 -*-
"""Command-line entry point for the lap-monitor package.

This file is what Python runs for `python3 -m lap_monitor`. (We use __main__.py,
not __init__.py: __init__.py runs on every import and marks the package, while
__main__.py is the idiomatic place for the runnable CLI.)

Modes:
    run        scan AND display (default) - good for a quick local look.
    serve      headless daemon - scan + alert + store, no UI (for systemd).
    dashboard  read-only viewer of the data store.

Target management (targets live in the data store, not a file):
    add <type> <value>   add a target  (type: http | ping | tcp)
    list                 list targets
    remove <id>          remove a target by id
    enable/disable <id>  toggle a target
    import <file>        bulk-import targets from a JSON/YAML file
"""

import argparse

from . import __version__
from . import app
from . import manage


def build_parser():
    p = argparse.ArgumentParser(
        prog="lap-monitor",
        description="lap-monitor - website / VPS / service status dashboard.",
    )
    p.add_argument("-v", "--version", action="version",
                   version=f"lap-monitor v{__version__}")
    p.add_argument("-c", "--config", metavar="FILE", default=None,
                   help="path to a config file (default: config.yaml in the "
                        "project root)")

    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("run", help="scan and display (default)")
    sub.add_parser("serve", help="headless daemon (for systemd)")
    sub.add_parser("dashboard", help="read-only viewer of the store")

    pa = sub.add_parser("add", help="add a target")
    pa.add_argument("type", choices=["http", "ping", "tcp"])
    pa.add_argument("value", help="url (http) | host (ping) | host:port (tcp)")
    pa.add_argument("--name", help="custom display name")
    pa.add_argument("--port", type=int, help="port for tcp (if not in value)")
    pa.add_argument("--expect", type=int, metavar="CODE",
                    help="http: only this status code counts as UP")
    pa.add_argument("--timeout", type=int, metavar="SEC",
                    help="override the default timeout for this target")

    sub.add_parser("list", aliases=["ls"], help="list targets")

    pr = sub.add_parser("remove", aliases=["rm"], help="remove a target by id")
    pr.add_argument("id", type=int)

    pe = sub.add_parser("enable", help="enable a target by id")
    pe.add_argument("id", type=int)
    pd = sub.add_parser("disable", help="disable a target by id")
    pd.add_argument("id", type=int)

    pi = sub.add_parser("import", help="bulk-import targets from a file")
    pi.add_argument("file")

    return p


def cli():
    args = build_parser().parse_args()
    cmd = args.cmd or "run"
    cfg = args.config

    if cmd == "run":
        app.run(config_path=cfg)
    elif cmd == "serve":
        app.serve(config_path=cfg)
    elif cmd == "dashboard":
        app.dashboard(config_path=cfg)
    elif cmd == "add":
        manage.add(args.type, args.value, name=args.name, port=args.port,
                   expect=args.expect, timeout=args.timeout, config_path=cfg)
    elif cmd in ("list", "ls"):
        manage.list_targets(config_path=cfg)
    elif cmd in ("remove", "rm"):
        manage.remove(args.id, config_path=cfg)
    elif cmd == "enable":
        manage.set_enabled(args.id, True, config_path=cfg)
    elif cmd == "disable":
        manage.set_enabled(args.id, False, config_path=cfg)
    elif cmd == "import":
        manage.import_file(args.file, config_path=cfg)


if __name__ == "__main__":
    cli()

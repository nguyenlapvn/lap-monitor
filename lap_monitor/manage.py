# -*- coding: utf-8 -*-
"""Target management commands (add / list / remove / enable / import).

Targets live in the data store (see storage.py), not in a file. These handlers
back the `lap-monitor add|list|remove|enable|disable|import` CLI commands.
"""

import sys

from rich.console import Console
from rich.table import Table
from rich import box

from .config import load_config, normalize_targets, _name_from_url, _read_data_file
from .storage import build_storage

_console = Console()


def _open_store(config_path):
    cfg = load_config(config_path) if config_path else load_config()
    store = build_storage(cfg["storage"])
    if not getattr(store, "enabled", False):
        sys.exit("Storage is disabled. Enable 'storage' in config.yaml to "
                 "manage targets.")
    return store


def _endpoint(t):
    """Human-readable endpoint for a target dict."""
    ttype = t.get("type")
    if ttype == "http":
        return t.get("url", "?")
    if ttype == "ping":
        return t.get("host", "?")
    if ttype == "tcp":
        return f"{t.get('host', '?')}:{t.get('port', '?')}"
    return "?"


def _build_target(ttype, value, name=None, port=None, expect=None, timeout=None):
    """Turn CLI arguments into a full target dict."""
    t = {"type": ttype}
    if ttype == "http":
        url = value if "://" in value else "https://" + value
        t["url"] = url
        t["name"] = name or _name_from_url(url)
        if expect is not None:
            t["expect_code"] = int(expect)
    elif ttype == "ping":
        t["host"] = value
        t["name"] = name or value
    elif ttype == "tcp":
        host, _, parsed_port = value.rpartition(":")
        host = host or value
        prt = port if port is not None else parsed_port
        if not prt:
            sys.exit("TCP target needs a port: use 'host:port' or --port.")
        t["host"] = host
        t["port"] = int(prt)
        t["name"] = name or f"{host}:{prt}"
    else:
        sys.exit(f"Unknown type: {ttype}")
    if timeout is not None:
        t["timeout"] = int(timeout)
    return t


# ---------------------------------------------------------------------
#  Commands
# ---------------------------------------------------------------------
def add(ttype, value, name=None, port=None, expect=None, timeout=None,
        config_path=None):
    store = _open_store(config_path)
    target = _build_target(ttype, value, name, port, expect, timeout)
    tid = store.add_target(target)
    store.close()
    if tid is None:
        sys.exit("Failed to add target.")
    _console.print(f"[green]Added[/green] #{tid}: [bold]{target['name']}[/bold] "
                   f"({ttype} → {_endpoint(target)})")
    _console.print("[dim]Restart the service to pick it up:  "
                   "sudo systemctl restart lap-monitor[/dim]")


def list_targets(config_path=None):
    store = _open_store(config_path)
    targets = store.list_targets()
    store.close()

    if not targets:
        _console.print("[dim]No targets yet. Add one, e.g.:[/dim]")
        _console.print("  lap-monitor add http https://example.com")
        _console.print("  lap-monitor add ping 1.1.1.1")
        _console.print("  lap-monitor add tcp 10.0.0.5:22")
        return

    table = Table(box=box.ROUNDED, header_style="bold magenta")
    table.add_column("ID", justify="right")
    table.add_column("Name")
    table.add_column("Type", justify="center")
    table.add_column("Endpoint")
    table.add_column("Enabled", justify="center")
    for t in targets:
        on = t.get("enabled", True)
        table.add_row(
            str(t.get("id", "?")),
            t.get("name", "?"),
            t.get("type", "?"),
            _endpoint(t),
            "[green]yes[/green]" if on else "[red]no[/red]",
        )
    _console.print(table)


def remove(target_id, config_path=None):
    store = _open_store(config_path)
    ok = store.remove_target(int(target_id))
    store.close()
    if ok:
        _console.print(f"[green]Removed[/green] target #{target_id}")
    else:
        sys.exit(f"No target with id #{target_id}.")


def set_enabled(target_id, enabled, config_path=None):
    store = _open_store(config_path)
    ok = store.set_enabled(int(target_id), enabled)
    store.close()
    if ok:
        word = "enabled" if enabled else "disabled"
        _console.print(f"[green]{word.capitalize()}[/green] target #{target_id}")
    else:
        sys.exit(f"No target with id #{target_id}.")


def import_file(path, config_path=None):
    """Bulk-import targets from a JSON/YAML file (shorthand or full format)."""
    raw = _read_data_file(path)
    targets = normalize_targets(raw)
    if not targets:
        sys.exit(f"No targets found in {path}.")
    store = _open_store(config_path)
    count = 0
    for t in targets:
        if store.add_target(t) is not None:
            count += 1
    store.close()
    _console.print(f"[green]Imported[/green] {count} target(s) from {path}.")

# -*- coding: utf-8 -*-
"""Target management commands (add / list / edit / remove / enable / import).

Targets live in the data store (see storage.py), not in a file. These handlers
back the `lap-monitor add|list|edit|remove|enable|disable|import` CLI commands.
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


def _host_changes(value):
    """--host takes a bare host or the 'host:port' shorthand `add tcp` accepts.
    A single trailing ':<digits>' is the port; anything else (an IPv6 literal,
    which is all colons) is kept whole."""
    host, sep, port = value.rpartition(":")
    if sep and port.isdigit() and ":" not in host:
        return {"host": host, "port": int(port)}
    return {"host": value}


def edit(target_id, host=None, port=None, url=None, name=None, expect=None,
         timeout=None, config_path=None):
    """Change fields of an existing target in place, keeping its id."""
    store = _open_store(config_path)
    target_id = int(target_id)

    current = next((t for t in store.list_targets()
                    if t.get("id") == target_id), None)
    if current is None:
        store.close()
        sys.exit(f"No target with id #{target_id}.")

    ttype = current.get("type")

    def wrong_type(flag, wanted, hint=""):
        store.close()
        sys.exit(f"{flag} applies to {wanted} targets, but #{target_id} is "
                 f"'{ttype}'.{hint}")

    changes = {}
    if host is not None:
        if ttype not in ("ping", "tcp"):
            wrong_type("--host", "ping/tcp", " Use --url instead.")
        changes.update(_host_changes(host))
    if port is not None:
        if ttype != "tcp":
            wrong_type("--port", "tcp")
        changes["port"] = int(port)
    if url is not None:
        if ttype != "http":
            wrong_type("--url", "http", " Use --host instead.")
        changes["url"] = url if "://" in url else "https://" + url
    if expect is not None:
        if ttype != "http":
            wrong_type("--expect", "http")
        changes["expect_code"] = int(expect)
    if timeout is not None:
        changes["timeout"] = int(timeout)
    if name is not None:
        changes["name"] = name

    if not changes:
        store.close()
        sys.exit("Nothing to change. Pass at least one of "
                 "--host / --port / --url / --name / --expect / --timeout.")

    old_name = current.get("name")
    old_endpoint = _endpoint(current)

    updated = store.update_target(target_id, changes)
    if updated is None:
        store.close()
        sys.exit(f"Failed to update target #{target_id}.")

    # History and events are stored per name, so a rename has to take them
    # along - otherwise the target looks brand new and loses its uptime %.
    renamed = name is not None and name != old_name
    if renamed:
        store.rename_history(old_name, name)
    store.close()

    _console.print(f"[green]Updated[/green] #{target_id}: "
                   f"[bold]{updated.get('name')}[/bold] "
                   f"({ttype} → {_endpoint(updated)})")
    if _endpoint(updated) != old_endpoint:
        _console.print(f"[dim]  endpoint: {old_endpoint} → "
                       f"{_endpoint(updated)}[/dim]")
    if renamed:
        _console.print(f"[dim]  name: {old_name} → {name} "
                       f"(history and events moved with it)[/dim]")
    _console.print("[dim]Restart the service to pick it up:  "
                   "sudo systemctl restart lap-monitor[/dim]")


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

# -*- coding: utf-8 -*-
"""Scan engine and run modes.

Modes:
    run        - all-in-one TUI: scans AND displays (good for quick local use).
    serve      - headless daemon: scans + alerts + storage, no UI (for systemd).
    dashboard  - read-only TUI viewer: renders data written by 'serve'.

Run either ONE 'serve' (the background service) plus 'dashboard' viewers, OR a
single standalone 'run'. Don't run 'serve' and 'run' at the same time - they
would both scan and write to the same store.
"""

import time
import signal
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from rich.console import Console
from rich.live import Live

from .config import load_config
from .checks import run_check
from .state import TargetState
from .system import SystemMonitor
from .alerts import build_alerters, notify_change
from .storage import build_storage
from .market import MarketData
from .ui import build_layout

# How many recent events to show in quadrant 4.
EVENTS_SHOWN = 15
# Viewer refresh cadence (seconds) for 'dashboard' mode.
VIEWER_REFRESH = 2


def scan_once(states, default_timeout, parallel, workers):
    """Scan all targets once and update state.

    Returns the list of state changes as (state, old, new, detail) tuples so the
    caller (main thread) can dispatch alerts and persist them - keeping all
    alert/storage writes off the worker threads.
    """
    changes = []
    lock = threading.Lock()

    def do(s):
        is_up, ms, detail = run_check(s.target, default_timeout)
        changed, old, new = s.update(is_up, ms, detail)
        if changed:
            with lock:
                changes.append((s, old, new, detail))

    if parallel and len(states) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(do, states))
    else:
        for s in states:
            do(s)

    return changes


class Engine:
    """Shared monitoring engine: holds config, targets, storage, alerters."""

    def __init__(self, cfg):
        s = cfg["settings"]
        self.interval = int(s["interval"])
        self.timeout = int(s["timeout"])
        self.history_len = int(s["history"])
        self.parallel = bool(s["parallel"])
        self.workers = max(1, int(s["workers"]))
        self.sort_down_first = bool(s.get("sort_down_first", True))

        self.alerters = build_alerters(cfg["alerts"])
        self.storage = build_storage(cfg["storage"])
        # Targets now come from the data store, not a file.
        targets = self.storage.list_targets(enabled_only=True)
        self.states = [TargetState(t, self.history_len) for t in targets]
        self.sysmon = SystemMonitor()

        self._seed_from_snapshot()

    def _seed_from_snapshot(self):
        """Restore last known state so a restart isn't blank and cross-restart
        state-change alerts work."""
        snap = self.storage.load_snapshot()
        for s in self.states:
            info = snap.get(s.name)
            if not info:
                continue
            if info.get("state") in ("UP", "DOWN"):
                s.state = info["state"]
            s.last_ms = info.get("ms")
            if info.get("detail"):
                s.detail = info["detail"]
            for entry in info.get("history") or []:
                try:
                    s.history.append((bool(entry[0]), entry[1]))
                except (IndexError, TypeError):
                    pass

    def scan(self):
        """One scan cycle: check, alert on change, persist. Returns changes."""
        changes = scan_once(self.states, self.timeout, self.parallel, self.workers)
        for tgt, old, new, detail in changes:
            notify_change(self.alerters, tgt.name, old, new, detail)
            self.storage.record_event(tgt.name, tgt.type, old, new, detail)
        self.storage.save_snapshot(self.states)
        return changes


def _install_signal_handlers():
    """Turn SIGTERM (systemd stop) into KeyboardInterrupt for a clean shutdown."""
    def handler(signum, frame):
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, handler)
    except (ValueError, AttributeError, OSError):
        pass  # not available (e.g. non-main thread / Windows)


# =====================================================================
#  Mode: run (all-in-one TUI)
# =====================================================================
def run(config_path=None):
    cfg = load_config(config_path) if config_path else load_config()
    eng = Engine(cfg)
    _install_signal_handlers()

    console = Console()
    console.print("[dim]Starting lap-monitor... (Ctrl+C to quit)[/dim]")
    if not eng.states:
        console.print("[yellow]No targets yet.[/yellow] Add some with: "
                      "[bold]lap-monitor add http https://example.com[/bold]")

    market = MarketData(cfg)
    market.start()
    try:
        with Live(
            build_layout(eng.states, eng.sysmon, market, eng.interval,
                         eng.sort_down_first),
            console=console, screen=True, refresh_per_second=4,
        ) as live:
            while True:
                eng.scan()              # records events to storage regardless of UI
                for left in range(eng.interval, 0, -1):
                    live.update(build_layout(eng.states, eng.sysmon, market,
                                             left, eng.sort_down_first))
                    time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        market.stop()
        eng.storage.close()
        console.print("\n[bold]Monitor stopped. Goodbye![/bold]")


# =====================================================================
#  Mode: serve (headless daemon for systemd)
# =====================================================================
def serve(config_path=None):
    cfg = load_config(config_path) if config_path else load_config()
    eng = Engine(cfg)
    _install_signal_handlers()

    def log(msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)

    log(f"lap-monitor serve started "
        f"({len(eng.states)} targets, interval {eng.interval}s)")
    if not eng.states:
        log("no targets configured - add some with: lap-monitor add <type> <value>")
    try:
        while True:
            changes = eng.scan()
            for tgt, old, new, detail in changes:
                log(f"{tgt.name}: {old} -> {new} ({detail})")
            time.sleep(eng.interval)
    except KeyboardInterrupt:
        pass
    finally:
        eng.storage.close()
        log("lap-monitor serve stopped")


# =====================================================================
#  Mode: dashboard (read-only viewer of the store)
# =====================================================================
def _viewer_states(storage, history_len):
    """Build view states from the configured targets, overlaying the latest
    snapshot the daemon wrote (so targets show even before the first scan)."""
    snap = storage.load_snapshot()
    states = []
    for t in storage.list_targets(enabled_only=True):
        st = TargetState(t, history_len)
        info = snap.get(st.name)
        if info:
            if info.get("state") in ("UP", "DOWN"):
                st.state = info["state"]
            st.last_ms = info.get("ms")
            if info.get("detail"):
                st.detail = info["detail"]
            for entry in info.get("history") or []:
                try:
                    st.history.append((bool(entry[0]), entry[1]))
                except (IndexError, TypeError):
                    pass
        states.append(st)
    return states


def dashboard(config_path=None):
    cfg = load_config(config_path) if config_path else load_config()
    s = cfg["settings"]
    history_len = int(s["history"])
    sort_down_first = bool(s.get("sort_down_first", True))

    storage = build_storage(cfg["storage"])
    sysmon = SystemMonitor()
    market = MarketData(cfg)
    market.start()
    _install_signal_handlers()

    console = Console()
    try:
        with Live(console=console, screen=True, refresh_per_second=4) as live:
            while True:
                states = _viewer_states(storage, history_len)
                live.update(build_layout(states, sysmon, market, None,
                                         sort_down_first))
                time.sleep(VIEWER_REFRESH)
    except KeyboardInterrupt:
        pass
    finally:
        market.stop()
        storage.close()
        console.print("\n[bold]Dashboard closed.[/bold]")


# Backwards-compatible default entry.
def main(config_path=None):
    run(config_path)

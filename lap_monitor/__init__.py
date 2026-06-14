"""lap-monitor - terminal dashboard for website / VPS / service status.

Run it with:  python3 -m lap_monitor [run|serve|dashboard]

Modules:
    config  - load config.yaml and the targets file
    checks  - http / ping / tcp check functions
    state   - per-target runtime state (history, uptime)
    system  - local machine stats (CPU/RAM/disk/load/uptime)
    alerts  - alert channels (Telegram) + state-change dispatch
    storage - SQLite / JSON persistence
    ui      - 4-quadrant terminal rendering
    app     - engine + run/serve/dashboard modes
"""

__app_name__ = "lap-monitor"
__version__ = "3.1.0"

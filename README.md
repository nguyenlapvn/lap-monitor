# lap-monitor

A terminal (TUI) dashboard that monitors the **UP/DOWN** status of websites, VPS, and services. Lightweight, suited for low-spec devices (target < 50MB RAM).

The screen is split into **6 cells** (3 top, 3 bottom):

```
+-------------------------------------------------------------------+
|  header: overview + clock + countdown                             |
+------------------+------------------------+----------------------+
|  This machine    |  Websites (http)       |  VPS / hosts         |
|                  |                        |  (ping + tcp)        |
+------------------+------------------------+----------------------+
|  Recent events   |  Summary               |  Attention           |
|  (from storage)  |  (counts, avg uptime)  |  (targets DOWN now)  |
+------------------+------------------------+----------------------+
```

## Features
- Checks **HTTP/HTTPS**, **Ping (ICMP)**, and **TCP port**.
- **This machine:** live CPU / RAM / disk / load / uptime of the host (read from `/proc`, no extra deps).
- **Websites / VPS:** color (green = UP, red = DOWN), **type icons**, response time (ms) colored by latency, **uptime %**, and a **history sparkline**. DOWN targets float to the top.
- **Recent events:** a log of state changes read from the data store.
- **Summary** (counts, avg uptime/latency) and **Attention** (everything currently DOWN at a glance).
- **Targets managed via CLI** (`lap-monitor add|list|remove|import`) — stored in the data store, no file to edit.
- **Persistence:** targets + events + last-known state saved to **SQLite or a JSON file** (configurable); state is restored on restart.
- **Telegram** alerts when a target **changes state** (no spam). Easy to add more channels.
- **Concurrent** checks (optional) when there are many targets.
- Organized as a small `lap_monitor/` package (run via `python3 -m lap_monitor`).

## Install as a service (Debian / Linux)

One command installs dependencies, creates your config from templates, sets up
the data directory, and registers a **systemd service that auto-starts on boot**
and restarts on crash:

```bash
sudo apt update
sudo apt install -y python3 python3-pip iputils-ping git
git clone <your-repo-url> lap-monitor      # or copy the folder over
cd lap-monitor
bash install.sh
```

After install, add your targets (the `lap-monitor` command is now on your PATH)
and restart the service:
```bash
lap-monitor add http https://example.com
lap-monitor add ping 1.1.1.1
lap-monitor add tcp 10.0.0.5:22
sudo systemctl restart lap-monitor
```

Service management:
```bash
systemctl status lap-monitor      # is it running?
journalctl -u lap-monitor -f      # live logs (state changes)
sudo systemctl stop lap-monitor   # stop
```

To remove the service (keeps your config + data): `bash uninstall.sh`

## Run modes

Run from the project root (where the `lap_monitor/` folder lives):

| Command | What it does |
|---|---|
| `python3 -m lap_monitor` (or `run`) | All-in-one TUI: scans **and** displays. Good for a quick look. |
| `python3 -m lap_monitor serve` | Headless daemon: scans + alerts + stores data, no UI. This is what the service runs. |
| `python3 -m lap_monitor dashboard` | Read-only TUI that shows the data `serve` writes. Open it anytime over SSH. |

```bash
python3 -m lap_monitor --version            # print version
python3 -m lap_monitor serve --config FILE  # alternate config file
```

> Run **either** the service (`serve`) **or** a standalone `run` — not both at
> once, since both would scan and write to the same store. `dashboard` is always
> safe to open alongside the service.

### Quick view over SSH
While the service runs in the background, watch the live dashboard with:
```bash
cd ~/lap-monitor && python3 -m lap_monitor dashboard      # quit: Ctrl + C
```
(or run `serve` yourself inside `tmux` if you prefer not to use systemd).

> Windows (for testing): `pip install pyyaml rich`. Machine stats (Q1) read from
> Linux `/proc`, so they show `N/A` on Windows but populate on Debian.

## Versioning & updating

The version is shown in the dashboard header and via `--version`. It lives in
[`lap_monitor/__init__.py`](lap_monitor/__init__.py) (`__version__`); see
[CHANGELOG.md](CHANGELOG.md) for the history. The project follows Semantic
Versioning (MAJOR.MINOR.PATCH).

To update an installed copy on the target machine:
```bash
cd ~/lap-monitor
bash update.sh
```
`update.sh` pulls the latest code (`git pull`), updates dependencies from
`requirements.txt`, and restarts the `lap-monitor` service if present.

## Managing targets

Targets (the sites/VPS/services to monitor) live in the **data store**, not in a
file. Manage them with the CLI:

```bash
lap-monitor add http https://example.com           # name derived from the domain
lap-monitor add http https://api.example.com --name "Main API" --expect 200
lap-monitor add ping 1.1.1.1 --name "VPS Singapore"
lap-monitor add tcp 10.0.0.5:22 --name "SSH VPS"   # or: add tcp 10.0.0.5 --port 22

lap-monitor list                                   # show targets + ids
lap-monitor disable 3                              # stop checking #3 (keep it)
lap-monitor enable 3
lap-monitor remove 3                               # delete #3

lap-monitor import mylist.json                     # bulk-import (see below)
```

After changing targets, restart the service so it picks them up:
```bash
sudo systemctl restart lap-monitor
```

Options: `--name` (custom label), `--timeout SEC` (override default), and for
http `--expect CODE` (only that status counts as UP).

### Bulk import
`import` reads a JSON/YAML file (same two styles as the old targets file) and
adds everything to the store — handy for migrating a big list:
```json
{
  "http": ["https://a.com", "https://b.com"],
  "ping": ["8.8.8.8", "1.1.1.1"],
  "tcp":  ["10.0.0.5:22", { "name": "DB", "host": "10.0.0.9", "port": 3306 }]
}
```
```bash
lap-monitor import mylist.json
```

## Configuration — `config.yaml`
- `settings.interval` — seconds between scans.
- `settings.timeout` — default timeout per check (seconds).
- `settings.history` — number of samples kept for the sparkline / uptime %.
- `settings.parallel` / `settings.workers` — enable concurrent checks and thread count.
- `settings.sort_down_first` — `true` pushes DOWN targets to the top of the table.

### Status rules
- **HTTP:** 2xx–3xx = UP; 4xx = UP (server still alive); 5xx or connect error = DOWN. `expect_code` makes it stricter.
- **Ping:** a reply = UP.
- **TCP:** a successful connection = UP.

### Enable Telegram alerts
In `config.yaml`:
```yaml
alerts:
  telegram:
    enabled: true
    bot_token: "TOKEN_FROM_BOTFATHER"
    chat_id: "CHAT_ID"
```

### Storage (persistence)
The data store holds your **targets**, the **events** log, and a per-target
**snapshot** (so the dashboard has history and the last known state is restored
after a restart). Configure it in `config.yaml`:
```yaml
storage:
  enabled: true
  backend: sqlite          # sqlite | json
  path: "data/monitor.db"  # for json use e.g. "data/monitor.json"
  keep_events: 200         # max recent events to retain
```
- **sqlite** (default): compact, efficient; good for long uptimes.
- **json**: human-readable plain file; easy to inspect/edit.

The `data/` folder is created automatically and is git-ignored.

## Running 24/7

`install.sh` already sets this up via systemd (auto-start on boot, auto-restart
on crash) — see [Install as a service](#install-as-a-service-debian--linux).
The background daemon is `python3 -m lap_monitor serve`; watch it live with
`python3 -m lap_monitor dashboard`.

Prefer not to use systemd? Run the daemon inside tmux instead:
```bash
sudo apt install -y tmux
tmux new -s lap-monitor      # then: python3 -m lap_monitor serve
# detach: Ctrl+B then D  |  reattach: tmux attach -t lap-monitor
```

## Structure
```
lap-monitor/                 # project root (clone folder, name it as you like)
├── lap_monitor/             # the Python package (import name uses '_')
│   ├── __init__.py          # package marker + version (runs on import)
│   ├── __main__.py          # CLI entry — `python3 -m lap_monitor`
│   ├── config.py            # load config.yaml (+ target helpers)
│   ├── checks.py            # http / ping / tcp checks
│   ├── state.py             # per-target runtime state (history, uptime)
│   ├── system.py            # local machine stats (Q1)
│   ├── alerts.py            # Telegram + alert dispatch
│   ├── storage.py           # SQLite / JSON persistence (targets+events+snapshot)
│   ├── manage.py            # target CLI: add/list/remove/import
│   ├── ui.py                # 4-quadrant rendering
│   └── app.py               # engine + run/serve/dashboard modes
├── config.example.yaml      # config template (tracked in git)
├── config.yaml              # your settings        (git-ignored)
├── requirements.txt         # pinned Python dependencies
├── install.sh               # deps + 'lap-monitor' command + systemd service
├── uninstall.sh             # remove the service + command
├── update.sh                # git pull + deps + restart
├── CHANGELOG.md             # version history
├── .gitignore / .gitattributes
├── data/                    # runtime store: targets + history (git-ignored)
└── README.md
```

> **Why `__main__.py` and not `__init__.py`?** `__init__.py` runs every time the
> package is imported and is meant to *mark* the package, not to run it.
> `__main__.py` is the file Python executes for `python3 -m lap_monitor`, so it's
> the correct home for the CLI. (Module names can't contain `-`, so the import
> name is `lap_monitor` while the product/service is `lap-monitor`.)

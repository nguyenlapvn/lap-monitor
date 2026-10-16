# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the
project uses [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH).

The current version lives in [`lap_monitor/__init__.py`](lap_monitor/__init__.py)
(`__version__`) and is shown in the dashboard header and via
`python3 -m lap_monitor --version`.

## [3.6.0] - 2026-10-16
### Added
- **`cmd` target type** - run a shell command, exit code 0 = UP. This is how to
  watch a service that only listens on `127.0.0.1` (MySQL, MongoDB, Redis):
  ask the host over SSH rather than exposing the port to the network.
  ```bash
  lap-monitor add cmd "ssh -o BatchMode=yes root@10.0.0.5 systemctl is-active mysql" \
              --name "MySQL - VPS2"
  ```
  `--expect CODE` requires a different exit code and `--contains TEXT` also
  requires that text in the output (for commands that exit 0 while reporting a
  problem). The first output line becomes the status detail, so a failure shows
  as `exit 3: inactive`. Retries apply to `cmd` like any other type.
- `edit` gained `--command` and `--contains`; `--expect` now also covers `cmd`.

### Changed
- `cmd` targets render in the **VPS / hosts** cell (icon 🔧) and are counted in
  the Summary "By type" row, which only widens when such targets exist.
- A wrong-type `edit` flag now points at the right one per type
  (`--command` for cmd, `--url` for http, `--host` for ping/tcp).

## [3.5.0] - 2026-10-16
### Added
- **Retries before declaring DOWN** (`settings.retries`, default 2, and
  `settings.retry_delay`, default 3s). A failed check is repeated and only
  counts as DOWN when every attempt fails; the detail then reads
  `... (3 attempts)`. Fixes the flapping DOWN → UP alert pairs caused by a
  single slow response on shared hosting. `retries: 0` restores the old
  single-attempt behaviour.
- A broken target definition (missing `url` / `host` / `port`) is detected in
  `run_check()` and **not** retried - the scan would just stall on a result
  that cannot change.

### Changed
- Default `settings.timeout` raised **8 → 15** seconds. This is a default:
  an existing `config.yaml` that spells out `timeout: 8` keeps 8 until edited.

## [3.4.0] - 2026-10-16
### Added
- **`lap-monitor edit <id>`** - change a target in place instead of
  remove + add. Flags: `--host` (accepts `host:port`), `--port`, `--url`,
  `--name`, `--expect`, `--timeout`. The id is kept, and each flag is validated
  against the target's type (`--url` http only, `--host` ping/tcp, `--port` tcp).
- `storage.update_target(id, changes)` and `storage.rename_history(old, new)`
  on both backends. Snapshot and events are keyed by name, so `--name` carries
  the history and the event log over rather than orphaning them.

## [3.3.0] - 2026-10-16
### Added
- **IP column** in the **VPS / hosts** cell: the host/IP each target is checked
  against, between Name and Type. Fixed at 15 cells so a full IPv4 always fits;
  the port is left out (it still shows in the DOWN detail and `lap-monitor
  list`). On a cell narrower than 56 columns the IP is dropped automatically so
  the name stays readable.
- `TargetState.address()` - the host for ping/tcp, the URL hostname for http.

### Changed
- The VPS cell gets a slightly wider share of the top row (4:3 against the other
  two) to make room for the new column.
- `_Scroller` calls its `make_table(rows, width)` callback with the cell width.

## [3.2.0] - 2026-06-15
### Added
- **Market cells** (`market.py`): bottom-left now shows **₿ Crypto** prices with
  **1h / 24h / 7d** change (CoinGecko `/coins/markets`) and **🥇 Vietnam gold**
  buy/sell with up/down arrows (PNJ). Both are free, key-less public APIs - no
  secrets/`.env` needed. Fetched on a background thread every `market.refresh`
  seconds (default 60, min 15) and cached, so the API isn't hit on every repaint.
- Column headers are English; gold product names are shown in **accent-free
  Vietnamese** (e.g. "Vang mieng SJC 999.9").
- **Emoji toggle** (`settings.emoji: auto|true|false`). `auto` turns emoji off on
  the Linux framebuffer console (`TERM=linux`, which renders them as tofu and
  misaligns columns like "By type") and keeps them on over SSH. ASCII fallbacks
  are used when off.
- Crypto list ships with **22 popular coins** (BTC, ETH, BNB, SOL, XRP, ADA,
  DOGE, TRX, AVAX, LINK, DOT, LTC, SHIB, UNI, ATOM, XLM, XMR, BCH, NEAR, APT,
  ARB, OP); edit `market.crypto.coins` to taste.
- **Auto-scrolling** target/price tables: when a list is taller than its cell,
  the visible window scrolls upward over time (DOWN targets stay pinned). No
  more silently cropped rows.
- **`lapm`** short alias for the `lap-monitor` CLI (symlink installed by
  `install.sh`, removed by `uninstall.sh`).

### Changed
- First cell now stacks **This machine** (top) and **Summary** (bottom) in one
  cell, freeing the bottom row for the Crypto and Gold cells. The "Recent events"
  cell was removed from the dashboard (events are still recorded to storage).
- `build_layout()` takes a `market` object instead of `events`.

## [3.1.0] - 2026-06-14
### Changed
- Dashboard is now a **6-cell grid** (3 top, 3 bottom) instead of 4 quadrants.
  Top: This machine | Websites | VPS/hosts. Bottom: Recent events | Summary |
  Attention. Edit the two `split_row()` calls in `ui.build_layout()` to rearrange.

### Added
- **Summary** cell: total/UP/DOWN, average uptime and latency, counts by type.
- **Attention** cell: lists every target currently DOWN (or "All targets UP").

## [3.0.0] - 2026-06-14
### Changed (breaking)
- **Targets now live in the data store, not a file.** Removed `targets.json` /
  `targets.example.json` and the `targets_file` / inline `targets:` config.
  Manage targets with the CLI instead:
  `lap-monitor add|list|remove|enable|disable|import`.
- The engine, `serve`, and `dashboard` read targets from the store; `dashboard`
  shows all enabled targets even before the first scan.

### Added
- `storage.py`: a `targets` table/section with add/list/remove/enable APIs
  (SQLite and JSON backends).
- `manage.py`: target-management command handlers, incl. `import` for bulk
  migrating a JSON/YAML list.
- `install.sh` installs a **`lap-monitor` command** to `/usr/local/bin` so you
  run `lap-monitor ...` instead of `python3 -m lap_monitor ...`.
  `uninstall.sh` removes it.

### Migration
- Re-add your hosts with `lap-monitor add ...`, or `lap-monitor import old.json`
  using your previous targets file.

## [2.2.0] - 2026-06-14
### Changed
- **Renamed to `lap-monitor`.** The package is now `lap_monitor/` and is run with
  `python3 -m lap_monitor` (the systemd service and scripts use the name
  `lap-monitor`). The standalone `monitor.py` launcher was removed.
- Added `lap_monitor/__main__.py` as the CLI entry point (the idiomatic place for
  a runnable package, vs `__init__.py` which only runs on import).
- Dashboard header, log lines, HTTP User-Agent, and config headers rebranded.

## [2.1.0] - 2026-06-14
### Added
- **Installable software / service.** `install.sh` sets up dependencies, config,
  the data directory, and a systemd service (`terminal-monitor`) that runs
  headless and **auto-starts on boot** (auto-restarts on crash, capped at 80MB).
  `uninstall.sh` removes the service.
- **Run modes** via `monitor.py <mode>`:
  - `serve` - headless daemon (no UI), for the service.
  - `dashboard` - read-only TUI viewer that renders data written by `serve`.
  - `run` (default) - all-in-one TUI that scans and displays.
- Snapshot now persists per-target **history**, so the viewer can draw sparklines.
- Example templates `config.example.yaml` / `targets.example.json`; the real
  `config.yaml` / `targets.json` are now git-ignored to keep hosts/secrets local.
- Clean shutdown on SIGTERM (systemd stop) - flushes the store.

### Changed
- `monitor.py` gained a positional `mode` argument; default behavior unchanged.

## [2.0.0] - 2026-06-14
### Added
- **4-quadrant layout**: Q1 host machine stats (CPU/RAM/disk/load/uptime),
  Q2 websites, Q3 VPS/hosts, Q4 recent events.
- **Persistence** (`core/storage.py`): SQLite or JSON backend, configurable in
  `config.yaml`. Stores a state-change event log and a per-target snapshot;
  last known state is restored on restart.
- Modular `core/` package (config, checks, state, system, alerts, storage, ui, app).
- CLI: `--version` and `--config FILE`.
- `requirements.txt`, `CHANGELOG.md`, `update.sh`, `.gitignore`.

### Changed
- `monitor.py` is now a thin entry point delegating to `core.app`.
- Alert/storage writes happen on the main thread (workers only collect changes).

## [1.1.0] - 2026-06-14
### Added
- Separate `targets.json` file with shorthand + full target formats for fast
  bulk entry of many sites/VPS.
- Prettier UI: type icons, latency-colored ms, uptime %, DOWN-first sorting,
  status overview header, and a live countdown to the next scan.

## [1.0.0] - 2026-06-14
### Added
- Initial single-file `monitor.py` dashboard.
- HTTP/HTTPS, Ping (ICMP), and TCP port checks.
- Auto-refreshing table with colors and a response-time sparkline.
- Telegram alerts on state change (opt-in via config).
- Optional concurrent checks; `config.yaml` configuration.

[3.2.0]: #320---2026-06-15
[3.1.0]: #310---2026-06-14
[3.0.0]: #300---2026-06-14
[2.2.0]: #220---2026-06-14
[2.1.0]: #210---2026-06-14
[2.0.0]: #200---2026-06-14
[1.1.0]: #110---2026-06-14
[1.0.0]: #100---2026-06-14

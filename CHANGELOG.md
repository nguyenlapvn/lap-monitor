# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the
project uses [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH).

The current version lives in [`lap_monitor/__init__.py`](lap_monitor/__init__.py)
(`__version__`) and is shown in the dashboard header and via
`python3 -m lap_monitor --version`.

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

[3.1.0]: #310---2026-06-14
[3.0.0]: #300---2026-06-14
[2.2.0]: #220---2026-06-14
[2.1.0]: #210---2026-06-14
[2.0.0]: #200---2026-06-14
[1.1.0]: #110---2026-06-14
[1.0.0]: #100---2026-06-14

# -*- coding: utf-8 -*-
"""Persistence backends: store data in SQLite or a JSON file (configurable).

Nothing is hardcoded - the backend and path come from config.yaml:

    storage:
      enabled: true
      backend: sqlite      # sqlite | json
      path: "data/monitor.db"
      keep_events: 200     # max state-change events to retain

What is stored:
  - targets   : the monitored sites/VPS/services (managed via the CLI:
                `lap-monitor add|list|remove|import`). This replaces the old
                targets.json file - targets now live in the data store.
  - events    : a log of state changes (UP<->DOWN) with timestamp + detail.
  - snapshot  : the latest status per target, upserted each scan, so a restart
                restores the last known state (and cross-restart alerts work).

Storage failures must never crash the dashboard - methods swallow errors.
"""

import os
import json
import sqlite3
from datetime import datetime

# Project root = parent of this 'lap_monitor' package. Relative paths resolve here.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve(path):
    return path if os.path.isabs(path) else os.path.join(_ROOT, path)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_storage(conf):
    """Create a storage backend from the 'storage' config section."""
    conf = conf or {}
    if not conf.get("enabled", False):
        return NullStorage()
    backend = (conf.get("backend") or "sqlite").lower()
    keep = int(conf.get("keep_events", 200))
    path = conf.get("path")
    try:
        if backend == "json":
            return JsonStorage(path or "data/monitor.json", keep)
        return SqliteStorage(path or "data/monitor.db", keep)
    except Exception:
        # If storage can't be initialized, fall back to no-op rather than crash.
        return NullStorage()


# ---------------------------------------------------------------------
#  No-op backend (used when storage is disabled or fails to init)
# ---------------------------------------------------------------------
class NullStorage:
    enabled = False

    def add_target(self, target):
        return None

    def list_targets(self, enabled_only=False):
        return []

    def remove_target(self, target_id):
        return False

    def set_enabled(self, target_id, enabled):
        return False

    def record_event(self, *a, **k):
        pass

    def recent_events(self, limit=20):
        return []

    def save_snapshot(self, states):
        pass

    def load_snapshot(self):
        return {}

    def close(self):
        pass


# ---------------------------------------------------------------------
#  SQLite backend
# ---------------------------------------------------------------------
class SqliteStorage:
    enabled = True

    def __init__(self, path, keep_events):
        self.keep = keep_events
        self.path = _resolve(path)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Used only from the main thread, so the default connection is fine.
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS events(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts TEXT, name TEXT, type TEXT,
                   old_state TEXT, new_state TEXT, detail TEXT)"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS snapshot(
                   name TEXT PRIMARY KEY, type TEXT, state TEXT,
                   ms REAL, detail TEXT, ts TEXT, history TEXT)"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS targets(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT, type TEXT, data TEXT, enabled INTEGER DEFAULT 1)"""
        )
        self.conn.commit()

    # --- targets ---
    def add_target(self, target):
        try:
            cur = self.conn.execute(
                "INSERT INTO targets(name,type,data,enabled) VALUES(?,?,?,1)",
                (target.get("name"), target.get("type"), json.dumps(target)),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.Error:
            return None

    def list_targets(self, enabled_only=False):
        try:
            sql = "SELECT id,data,enabled FROM targets"
            if enabled_only:
                sql += " WHERE enabled=1"
            sql += " ORDER BY id"
            out = []
            for tid, data, enabled in self.conn.execute(sql).fetchall():
                try:
                    t = json.loads(data)
                except (ValueError, TypeError):
                    continue
                t["id"] = tid
                t["enabled"] = bool(enabled)
                out.append(t)
            return out
        except sqlite3.Error:
            return []

    def remove_target(self, target_id):
        try:
            cur = self.conn.execute("DELETE FROM targets WHERE id=?", (target_id,))
            self.conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error:
            return False

    def set_enabled(self, target_id, enabled):
        try:
            cur = self.conn.execute(
                "UPDATE targets SET enabled=? WHERE id=?",
                (1 if enabled else 0, target_id),
            )
            self.conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error:
            return False

    def record_event(self, name, ttype, old, new, detail):
        try:
            self.conn.execute(
                "INSERT INTO events(ts,name,type,old_state,new_state,detail) "
                "VALUES(?,?,?,?,?,?)",
                (_now(), name, ttype, old, new, detail),
            )
            # Trim to the most recent N events.
            self.conn.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                (self.keep,),
            )
            self.conn.commit()
        except sqlite3.Error:
            pass

    def recent_events(self, limit=20):
        try:
            cur = self.conn.execute(
                "SELECT ts,name,type,old_state,new_state,detail "
                "FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            keys = ("ts", "name", "type", "old", "new", "detail")
            return [dict(zip(keys, row)) for row in cur.fetchall()]
        except sqlite3.Error:
            return []

    def save_snapshot(self, states):
        try:
            for s in states:
                history = json.dumps(list(s.history))
                self.conn.execute(
                    "INSERT INTO snapshot(name,type,state,ms,detail,ts,history) "
                    "VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(name) DO UPDATE SET type=excluded.type, "
                    "state=excluded.state, ms=excluded.ms, "
                    "detail=excluded.detail, ts=excluded.ts, history=excluded.history",
                    (s.name, s.type, s.state, s.last_ms, s.detail, _now(), history),
                )
            self.conn.commit()
        except sqlite3.Error:
            pass

    def load_snapshot(self):
        try:
            cur = self.conn.execute(
                "SELECT name,type,state,ms,detail,history FROM snapshot")
            out = {}
            for name, ttype, state, ms, detail, history in cur.fetchall():
                try:
                    hist = json.loads(history) if history else []
                except (ValueError, TypeError):
                    hist = []
                out[name] = {"type": ttype, "state": state, "ms": ms,
                             "detail": detail, "history": hist}
            return out
        except sqlite3.Error:
            return {}

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
#  JSON-file backend
# ---------------------------------------------------------------------
class JsonStorage:
    enabled = True

    def __init__(self, path, keep_events):
        self.keep = keep_events
        self.path = _resolve(path)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.data = {"events": [], "snapshot": {}}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data = loaded
            except Exception:
                pass
        self.data.setdefault("events", [])
        self.data.setdefault("snapshot", {})
        self.data.setdefault("targets", [])

    # --- targets ---
    def add_target(self, target):
        targets = self.data.setdefault("targets", [])
        next_id = max((t.get("id", 0) for t in targets), default=0) + 1
        entry = dict(target)
        entry["id"] = next_id
        entry["enabled"] = True
        targets.append(entry)
        self._flush()
        return next_id

    def list_targets(self, enabled_only=False):
        targets = self.data.get("targets", [])
        if enabled_only:
            return [dict(t) for t in targets if t.get("enabled", True)]
        return [dict(t) for t in targets]

    def remove_target(self, target_id):
        targets = self.data.get("targets", [])
        kept = [t for t in targets if t.get("id") != target_id]
        if len(kept) == len(targets):
            return False
        self.data["targets"] = kept
        self._flush()
        return True

    def set_enabled(self, target_id, enabled):
        for t in self.data.get("targets", []):
            if t.get("id") == target_id:
                t["enabled"] = bool(enabled)
                self._flush()
                return True
        return False

    def _flush(self):
        # Atomic write: temp file then replace, so a crash can't corrupt it.
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def record_event(self, name, ttype, old, new, detail):
        self.data["events"].append({
            "ts": _now(), "name": name, "type": ttype,
            "old": old, "new": new, "detail": detail,
        })
        self.data["events"] = self.data["events"][-self.keep:]
        self._flush()

    def recent_events(self, limit=20):
        return list(reversed(self.data.get("events", [])))[:limit]

    def save_snapshot(self, states):
        self.data["snapshot"] = {
            s.name: {"type": s.type, "state": s.state, "ms": s.last_ms,
                     "detail": s.detail, "ts": _now(), "history": list(s.history)}
            for s in states
        }
        self._flush()

    def load_snapshot(self):
        snap = self.data.get("snapshot", {})
        return {name: {"type": v.get("type"), "state": v.get("state"),
                       "ms": v.get("ms"), "detail": v.get("detail"),
                       "history": v.get("history") or []}
                for name, v in snap.items()}

    def close(self):
        self._flush()

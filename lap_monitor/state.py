# -*- coding: utf-8 -*-
"""Per-target runtime state: current status, last latency, rolling history."""

from collections import deque

# How target types map to dashboard quadrants.
WEBSITE_TYPES = ("http",)
VPS_TYPES = ("ping", "tcp")


class TargetState:
    def __init__(self, target, history_len):
        self.target = target
        self.name = target.get("name", "(unnamed)")
        self.type = (target.get("type") or "?").lower()
        self.state = "UNKNOWN"        # UP | DOWN | UNKNOWN
        self.last_ms = None
        self.detail = "waiting..."
        self.history = deque(maxlen=history_len)  # stores (is_up, ms)

    def update(self, is_up, ms, detail):
        """Apply a check result. Returns (changed, old_state, new_state)."""
        self.last_ms = ms
        self.detail = detail
        self.history.append((is_up, ms))
        new_state = "UP" if is_up else "DOWN"
        changed = (self.state in ("UP", "DOWN")) and (new_state != self.state)
        old_state = self.state
        self.state = new_state
        return changed, old_state, new_state

    def uptime_pct(self):
        """Percentage of UP results in recent history - None if no data yet."""
        if not self.history:
            return None
        ups = sum(1 for up, _ in self.history if up)
        return ups * 100.0 / len(self.history)

    def is_website(self):
        return self.type in WEBSITE_TYPES

    def is_vps(self):
        return self.type in VPS_TYPES

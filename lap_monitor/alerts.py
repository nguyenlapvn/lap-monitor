# -*- coding: utf-8 -*-
"""Alert channels and state-change dispatch.

Alerts fire ONLY when a target changes state (UP->DOWN or DOWN->UP), never
on every scan. To add a channel, implement a class with a .send(text) method
and an .enabled flag, then register it in build_alerters().
"""

import json
import urllib.request
from datetime import datetime


class TelegramAlerter:
    """Send a Telegram message on state change. Send errors never crash the app."""

    name = "telegram"

    def __init__(self, conf):
        self.enabled = bool(conf.get("enabled"))
        self.bot_token = conf.get("bot_token", "")
        self.chat_id = conf.get("chat_id", "")
        if self.enabled and (not self.bot_token or not self.chat_id):
            self.enabled = False  # missing credentials -> auto-disable

    def send(self, text):
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = json.dumps({"chat_id": self.chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            # Don't surface to the UI to avoid noise; just skip this failed send.
            pass


def build_alerters(alerts_conf):
    """Build the list of enabled alerters. To add a channel, append it here."""
    alerters = []
    tg = alerts_conf.get("telegram")
    if tg:
        a = TelegramAlerter(tg)
        if a.enabled:
            alerters.append(a)
    return alerters


def notify_change(alerters, name, old_state, new_state, detail):
    """Dispatch a state-change message to all enabled alerters."""
    if not alerters:
        return
    emoji = "✅" if new_state == "UP" else "🔴"
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"{emoji} {name}: {old_state} → {new_state}\n{detail}\n{when}"
    for a in alerters:
        a.send(msg)

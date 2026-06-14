# -*- coding: utf-8 -*-
"""Configuration loading: config.yaml + a separate targets file (JSON/YAML)."""

import os
import sys
import json
import urllib.parse

try:
    import yaml
except ImportError:
    sys.exit("Missing 'pyyaml'. Install with: pip3 install pyyaml --break-system-packages")

# Project root = parent of this 'lap_monitor' package.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_ROOT, "config.yaml")


def _read_data_file(path):
    """Read a single .json or .yaml/.yml file and return Python data."""
    if not os.path.exists(path):
        sys.exit(f"File not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "r", encoding="utf-8") as f:
            if ext == ".json":
                return json.load(f)
            return yaml.safe_load(f)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        sys.exit(f"Error reading {os.path.basename(path)}: {e}")


def _name_from_url(url):
    """Derive a short display name from a URL (strip scheme and www)."""
    host = urllib.parse.urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host


def normalize_targets(raw):
    """
    Normalize a target list from several formats into a list of full dicts.

    Two writing styles are supported (works in both JSON and YAML):

    1) FULL form - a list of objects (when you need expect_code, timeout, name):
       [ {"name": "...", "type": "http", "url": "..."}, ... ]

    2) SHORTHAND form - an object grouped by type, very fast for many hosts:
       {
         "http": ["https://web99vn.com", "https://webvn.top"],
         "ping": ["8.8.8.8", "1.1.1.1"],
         "tcp":  ["127.0.0.1:3306", "10.0.0.5:22"]
       }
       (name is derived from url/host; you can still mix full objects in)
    """
    out = []

    if isinstance(raw, dict):
        for ttype in ("http", "ping", "tcp"):
            for item in raw.get(ttype, []) or []:
                if isinstance(item, dict):              # mixed-in full object
                    item.setdefault("type", ttype)
                    out.append(item)
                    continue
                item = str(item).strip()
                if ttype == "http":
                    url = item if "://" in item else "https://" + item
                    out.append({"name": _name_from_url(url), "type": "http", "url": url})
                elif ttype == "ping":
                    out.append({"name": item, "type": "ping", "host": item})
                elif ttype == "tcp":
                    host, _, port = item.rpartition(":")
                    out.append({"name": item, "type": "tcp",
                                "host": host or item, "port": port})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.append(item)
    return out


def load_config(path=CONFIG_PATH):
    """Read config.yaml and return a dict with settings/alerts/storage.

    Targets are NOT read here anymore - they live in the data store and are
    managed via the CLI (`lap-monitor add|list|remove|import`).
    """
    cfg = _read_data_file(path) or {}

    cfg.setdefault("settings", {})
    cfg.setdefault("alerts", {})
    cfg.setdefault("storage", {})

    s = cfg["settings"]
    s.setdefault("interval", 30)
    s.setdefault("timeout", 8)
    s.setdefault("history", 20)
    s.setdefault("parallel", True)
    s.setdefault("workers", 8)
    s.setdefault("sort_down_first", True)

    return cfg

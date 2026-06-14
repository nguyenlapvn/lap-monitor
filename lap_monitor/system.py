# -*- coding: utf-8 -*-
"""Local machine stats for quadrant 1 (the device running the monitor).

Reads /proc and os.statvfs on Linux (the target platform) with no extra
dependencies. On non-Linux (e.g. Windows dev box) values gracefully return
None and the UI shows 'N/A'.
"""

import os
import socket


class SystemMonitor:
    """Collects CPU / RAM / disk / load / uptime for the host machine.

    CPU% needs two samples; call cpu_percent() repeatedly and it computes the
    delta since the previous call (first call returns None).
    """

    def __init__(self, disk_path="/"):
        self._prev_cpu = None
        self._disk_path = disk_path if os.path.exists(disk_path) else os.getcwd()

    @staticmethod
    def hostname():
        try:
            return socket.gethostname()
        except Exception:
            return "?"

    def cpu_percent(self):
        """Overall CPU usage % since the previous call (None on first call/error)."""
        try:
            with open("/proc/stat") as f:
                fields = f.readline().split()[1:]
            vals = [float(x) for x in fields]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0.0)  # idle + iowait
            total = sum(vals)
        except Exception:
            return None

        prev = self._prev_cpu
        self._prev_cpu = (idle, total)
        if prev:
            di = idle - prev[0]
            dt = total - prev[1]
            if dt > 0:
                return max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))
        return None

    @staticmethod
    def mem():
        """Return (used_bytes, total_bytes, pct) or (None, None, None)."""
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    key, _, val = line.partition(":")
                    info[key] = float(val.strip().split()[0]) * 1024.0  # kB -> B
            total = info.get("MemTotal", 0.0)
            avail = info.get("MemAvailable", info.get("MemFree", 0.0))
            used = total - avail
            pct = (used / total * 100.0) if total else None
            return used, total, pct
        except Exception:
            return None, None, None

    def disk(self):
        """Return (used_bytes, total_bytes, pct) for the configured path."""
        try:
            st = os.statvfs(self._disk_path)
            total = st.f_blocks * st.f_frsize
            free = st.f_bfree * st.f_frsize
            used = total - free
            pct = (used / total * 100.0) if total else None
            return used, total, pct
        except (AttributeError, OSError):
            return None, None, None

    @staticmethod
    def loadavg():
        """Return (1m, 5m, 15m) load averages or None."""
        try:
            return os.getloadavg()
        except (OSError, AttributeError):
            return None

    @staticmethod
    def uptime():
        """Return system uptime in seconds or None."""
        try:
            with open("/proc/uptime") as f:
                return float(f.read().split()[0])
        except Exception:
            return None

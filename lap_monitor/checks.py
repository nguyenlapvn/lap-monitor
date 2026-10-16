# -*- coding: utf-8 -*-
"""Check functions for each target type.

Every function returns a tuple (is_up, response_ms, detail) and catches its
own errors - an exception must NEVER escape and crash the dashboard.
"""

import os
import ssl
import time
import socket
import subprocess
import urllib.request
import urllib.error


def check_http(target, default_timeout):
    """
    HTTP/HTTPS:
      2xx-3xx             = UP
      4xx                 = UP (server is alive, it responded)
      5xx / connect error = DOWN
    If 'expect_code' is set, ONLY that code counts as UP.
    """
    url = target.get("url")
    if not url:
        return (False, None, "missing 'url'")
    timeout = target.get("timeout", default_timeout)
    expect = target.get("expect_code")

    # Skip SSL verification to avoid a certifi dependency (we only need up/down).
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={"User-Agent": "lap-monitor/3.0"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        # The server answered, just with an error code.
        code = e.code
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError) as e:
        reason = getattr(e, "reason", e)
        return (False, None, f"error: {reason}")
    except Exception as e:  # absolute safety net
        return (False, None, f"error: {e}")

    ms = (time.monotonic() - start) * 1000.0

    if expect is not None:
        is_up = (code == int(expect))
    else:
        is_up = code < 500  # 2xx-4xx means the server is still alive
    return (is_up, ms, f"HTTP {code}")


def check_ping(target, default_timeout):
    """ICMP ping: exit code 0 = UP. Picks the syntax based on the OS."""
    host = target.get("host")
    if not host:
        return (False, None, "missing 'host'")
    timeout = int(target.get("timeout", default_timeout))

    if os.name == "nt":  # Windows
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else:                # Linux / Debian
        cmd = ["ping", "-c", "1", "-W", str(timeout), host]

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 2,
        )
    except subprocess.TimeoutExpired:
        return (False, None, "ping timeout")
    except FileNotFoundError:
        return (False, None, "'ping' command not found")
    except Exception as e:
        return (False, None, f"error: {e}")

    ms = (time.monotonic() - start) * 1000.0
    if proc.returncode == 0:
        return (True, ms, "reply received")
    return (False, None, "no reply")


def check_tcp(target, default_timeout):
    """TCP: a successful connection to host:port = UP."""
    host = target.get("host")
    port = target.get("port")
    if not host or not port:
        return (False, None, "missing 'host' or 'port'")
    timeout = target.get("timeout", default_timeout)

    start = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            ms = (time.monotonic() - start) * 1000.0
            return (True, ms, f"port {port} open")
    except socket.timeout:
        return (False, None, f"port {port} timeout")
    except (ConnectionRefusedError, OSError) as e:
        return (False, None, f"port {port}: {getattr(e, 'strerror', e)}")
    except Exception as e:
        return (False, None, f"error: {e}")


CHECKERS = {
    "http": check_http,
    "ping": check_ping,
    "tcp": check_tcp,
}

# What each target type needs before a check is worth running at all.
REQUIRED_FIELDS = {"http": ("url",), "ping": ("host",), "tcp": ("host", "port")}


def _missing_fields(target, ttype):
    return [f for f in REQUIRED_FIELDS.get(ttype, ()) if not target.get(f)]


def run_check(target, default_timeout, retries=0, retry_delay=0.0):
    """Run the right check for the type, wrapped so it can't crash the dashboard.

    A failed check is retried up to ``retries`` times, ``retry_delay`` seconds
    apart, and only counts as DOWN when every attempt fails. One slow response
    is the normal cause of a false DOWN (shared hosting with a spiky TTFB), and
    a single bad sample used to flip the state and fire an alert both ways.

    A broken target definition is NOT retried - waiting on it would just stall
    the scan for a result that cannot change.
    """
    ttype = (target.get("type") or "").lower()
    fn = CHECKERS.get(ttype)
    if fn is None:
        return (False, None, f"invalid type: '{ttype}'")
    missing = _missing_fields(target, ttype)
    if missing:
        return (False, None, "missing " + " and ".join(f"'{f}'" for f in missing))

    attempts = max(0, int(retries)) + 1
    for attempt in range(attempts):
        try:
            is_up, ms, detail = fn(target, default_timeout)
        except Exception as e:  # absolute safety net
            is_up, ms, detail = (False, None, f"error: {e}")
        if is_up:
            return (is_up, ms, detail)
        if attempt + 1 < attempts:
            time.sleep(max(0.0, float(retry_delay)))

    if attempts > 1:
        detail = f"{detail} ({attempts} attempts)"
    return (False, ms, detail)

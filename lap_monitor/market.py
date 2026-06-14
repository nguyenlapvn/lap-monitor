# -*- coding: utf-8 -*-
"""Background market-data fetcher: crypto prices (CoinGecko) + Vietnam gold
prices (PNJ).

Both are free, key-less public endpoints (verified working):
    crypto : https://api.coingecko.com/api/v3/simple/price
    gold   : https://edge-api.pnj.io/ecom-frontend/v1/get-gold-price

The fetcher runs on its own daemon thread and refreshes only every
``refresh`` seconds - the dashboard repaints several times a second, so it must
NOT hit these APIs on every frame. Panels read the cached snapshot, which is
swapped atomically. Any network/parse error is swallowed and the last good
value is kept (the panel shows it as slightly stale rather than crashing).
"""

import json
import ssl
import threading
import urllib.request
import urllib.error

_CG_URL = "https://api.coingecko.com/api/v3/simple/price"
_PNJ_URL = "https://edge-api.pnj.io/ecom-frontend/v1/get-gold-price?zone=00"

# CoinGecko ids -> short ticker shown in the table.
_SYMBOLS = {
    "bitcoin": "BTC", "ethereum": "ETH", "binancecoin": "BNB",
    "tether": "USDT", "solana": "SOL", "ripple": "XRP",
    "cardano": "ADA", "dogecoin": "DOGE", "tron": "TRX",
}


def _get_json(url, timeout):
    """GET a URL and parse JSON. Returns None on any error (never raises)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (lap-monitor)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, ssl.SSLError):
        return None
    except Exception:                       # absolute safety net for the thread
        return None


class MarketData:
    """Polls crypto + gold APIs on a background thread and caches the result.

    Read ``self.crypto`` (dict keyed by ticker) and ``self.gold`` (list of
    dicts) from the render thread - both are plain attributes swapped wholesale,
    so reads are safe without locking. ``None`` means "not fetched yet".
    """

    def __init__(self, cfg):
        m = cfg.get("market", {}) or {}
        self.enabled = bool(m.get("enabled", True))
        self.refresh = max(15, int(m.get("refresh", 60)))
        self.timeout = int(m.get("timeout", 10))

        c = m.get("crypto", {}) or {}
        self.crypto_enabled = bool(c.get("enabled", True))
        self.vs = str(c.get("vs_currency", "usd")).lower()
        self.coins = list(c.get("coins") or ["bitcoin", "ethereum"])

        g = m.get("gold", {}) or {}
        self.gold_enabled = bool(g.get("enabled", True))
        # PNJ product codes (masp) to keep; empty list = show all.
        self.gold_products = [str(p) for p in (g.get("products") or [])]

        self.crypto = None
        self.gold = None
        self._prev_gold = {}                 # masp -> last sell price, for deltas
        self._stop = threading.Event()
        self._thread = None

    # -- lifecycle -----------------------------------------------------
    def start(self):
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="market-fetch")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            if self.crypto_enabled:
                got = self._fetch_crypto()
                if got is not None:
                    self.crypto = got
            if self.gold_enabled:
                got = self._fetch_gold()
                if got is not None:
                    self.gold = got
            self._stop.wait(self.refresh)

    # -- fetchers ------------------------------------------------------
    def _fetch_crypto(self):
        ids = ",".join(self.coins)
        url = f"{_CG_URL}?ids={ids}&vs_currencies={self.vs}&include_24hr_change=true"
        data = _get_json(url, self.timeout)
        if not isinstance(data, dict):
            return None
        out = {}
        for cid in self.coins:
            row = data.get(cid)
            if not isinstance(row, dict):
                continue
            ticker = _SYMBOLS.get(cid, cid[:4].upper())
            out[ticker] = {
                "price": row.get(self.vs),
                "change": row.get(f"{self.vs}_24h_change"),
            }
        return out or None

    def _fetch_gold(self):
        data = _get_json(_PNJ_URL, self.timeout)
        if not isinstance(data, dict):
            return None
        items = data.get("data")
        if not isinstance(items, list):
            return None
        out = []
        for it in items:
            masp = str(it.get("masp", ""))
            if self.gold_products and masp not in self.gold_products:
                continue
            sell = _to_num(it.get("giaban"))
            buy = _to_num(it.get("giamua"))
            prev = self._prev_gold.get(masp)
            delta = (sell - prev) if (sell is not None and prev is not None) else None
            if sell is not None:
                self._prev_gold[masp] = sell
            out.append({
                "code": masp,
                "name": str(it.get("tensp", masp)),
                "buy": buy,
                "sell": sell,
                "delta": delta,
            })
        return out or None


def _to_num(v):
    """PNJ sometimes sends prices as '' or strings; coerce to float or None."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

# -*- coding: utf-8 -*-
"""Terminal rendering: a header plus a 2x2 quadrant dashboard.

Layout:
    +-----------------------------------------------------+
    |  header: overview + clock + countdown               |
    +---------------------------+-------------------------+
    |  Q1  This machine         |  Q2  Websites           |
    +---------------------------+-------------------------+
    |  Q3  VPS / hosts          |  Q4  (reserved)         |
    +---------------------------+-------------------------+
"""

import time
from datetime import datetime

from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.layout import Layout
from rich.align import Align
from rich import box

from . import __version__

# Sparkline characters (low -> high) for the response-time history.
SPARK_CHARS = "▁▂▃▄▅▆▇█"
TYPE_ICON = {"http": "🌐", "ping": "📡", "tcp": "🔌"}
STATE_RANK = {"DOWN": 0, "UNKNOWN": 1, "UP": 2}

# Auto-scroll: when a target list is taller than its cell, the visible window
# advances one row every SCROLL_SECONDS_PER_ROW seconds (wrapping around),
# driven by the Live refresh thread. DOWN targets are pinned so they stay put.
SCROLL_SECONDS_PER_ROW = 2.0


# ---------------------------------------------------------------------
#  Small formatting helpers
# ---------------------------------------------------------------------
def _gb(n):
    return f"{n / 1024 ** 3:.1f}" if n is not None else "?"


def _pct_style(pct, warn=70, crit=85):
    if pct is None:
        return "dim"
    if pct >= crit:
        return "red"
    if pct >= warn:
        return "yellow"
    return "green"


def latency_text(ms):
    """ms colored by latency: fast=green, medium=yellow, slow=red."""
    if ms is None:
        return Text("—", style="dim")
    style = "green" if ms < 200 else ("yellow" if ms < 500 else "red")
    return Text(f"{ms:.0f}", style=style)


def uptime_text(pct):
    """Uptime % with color."""
    if pct is None:
        return Text("—", style="dim")
    style = "green" if pct >= 99 else ("yellow" if pct >= 90 else "red")
    return Text(f"{pct:.0f}%", style=style)


def status_text(state):
    if state == "UP":
        return Text("● UP", style="bold green")
    if state == "DOWN":
        return Text("● DOWN", style="bold red")
    return Text("● …", style="dim")


def sparkline(history):
    """Draw a sparkline from the response-time history. DOWN shows a '·'."""
    if not history:
        return Text("")
    ms_values = [ms for (up, ms) in history if up and ms is not None]
    lo = min(ms_values) if ms_values else 0.0
    hi = max(ms_values) if ms_values else 1.0
    span = (hi - lo) or 1.0

    out = Text()
    for up, ms in history:
        if not up or ms is None:
            out.append("·", style="red")
        else:
            idx = int((ms - lo) / span * (len(SPARK_CHARS) - 1))
            out.append(SPARK_CHARS[idx], style="green")
    return out


def _fmt_uptime(seconds):
    if seconds is None:
        return "N/A"
    secs = int(seconds)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}:{mins:02d}"
    return f"{hours:02d}:{mins:02d}"


# ---------------------------------------------------------------------
#  Quadrant 1: this machine
# ---------------------------------------------------------------------
def render_system_panel(sysmon):
    grid = Table.grid(padding=(0, 1), expand=True)
    grid.add_column(justify="left", no_wrap=True, ratio=1)
    grid.add_column(justify="left", ratio=3)

    def row(label, value):
        grid.add_row(Text(label, style="bold cyan"), value)

    cpu = sysmon.cpu_percent()
    if cpu is None:
        cpu_val = Text("N/A", style="dim")
    else:
        cpu_val = Text(f"{cpu:.0f}%", style=_pct_style(cpu, 60, 85))

    mu, mt, mp = sysmon.mem()
    if mt:
        mem_val = Text(f"{_gb(mu)}/{_gb(mt)} GB ({mp:.0f}%)", style=_pct_style(mp))
    else:
        mem_val = Text("N/A", style="dim")

    du, dt, dp = sysmon.disk()
    if dt:
        disk_val = Text(f"{_gb(du)}/{_gb(dt)} GB ({dp:.0f}%)", style=_pct_style(dp))
    else:
        disk_val = Text("N/A", style="dim")

    la = sysmon.loadavg()
    load_val = (Text(f"{la[0]:.2f}  {la[1]:.2f}  {la[2]:.2f}")
                if la else Text("N/A", style="dim"))

    row("Host", Text(sysmon.hostname(), style="white"))
    row("CPU", cpu_val)
    row("RAM", mem_val)
    row("Disk", disk_val)
    row("Load", load_val)
    row("Uptime", Text(_fmt_uptime(sysmon.uptime())))

    return Panel(grid, title="🖥  This machine", border_style="cyan",
                 box=box.ROUNDED, padding=(0, 1))


# ---------------------------------------------------------------------
#  Quadrants 2 & 3: target tables
# ---------------------------------------------------------------------
class _Scroller:
    """Renderable that fits a list of target rows into whatever cell height it
    is given. If the list fits, the whole table is shown. If not, a window of
    rows scrolls upward over time (wrapping), with the first ``pin`` rows kept
    fixed at the top so currently-DOWN targets never scroll out of view.

    The scroll position is derived from the wall clock, so the animation is
    driven by Live's own refresh thread - no frame counter has to be threaded
    through the render loop.
    """

    # A SIMPLE_HEAD table costs 4 lines around its data rows: a leading blank,
    # the column header, the rule beneath it, and a trailing blank.
    _HEADER_LINES = 4

    def __init__(self, rows, make_table, pin=0):
        self.rows = rows
        self.make_table = make_table
        self.pin = pin

    def __rich_console__(self, console, options):
        height = options.height or options.max_height
        n = len(self.rows)
        capacity = max(1, height - self._HEADER_LINES)

        if n <= capacity:
            yield self.make_table(self.rows)
            return

        usable = max(1, capacity - 1)          # leave one line for the indicator
        pins = self.rows[:self.pin]
        scroll = self.rows[self.pin:]
        if len(pins) >= usable:                # too many pinned rows to fit: scroll all
            pins, scroll = [], self.rows

        slots = usable - len(pins)
        start = int(time.monotonic() / SCROLL_SECONDS_PER_ROW) % len(scroll)
        window = [scroll[(start + i) % len(scroll)] for i in range(min(slots, len(scroll)))]
        visible = pins + window

        yield self.make_table(visible)
        hidden = n - len(visible)
        yield Text(f"  ↕ auto-scrolling · {hidden} more of {n}",
                   style="dim", overflow="ellipsis", no_wrap=True)


def _targets_table(states, sort_down_first, show_type=False):
    rows = states
    if sort_down_first:
        rows = sorted(states, key=lambda s: STATE_RANK.get(s.state, 1))

    if not rows:
        return Align.center(Text("(no targets)", style="dim"), vertical="middle")

    def make_table(visible):
        table = Table(expand=True, box=box.SIMPLE_HEAD, header_style="bold magenta",
                      pad_edge=False, row_styles=["", "on grey7"])
        table.add_column("Name", no_wrap=True, ratio=3, overflow="ellipsis")
        if show_type:
            table.add_column("Type", justify="center", no_wrap=True)
        table.add_column("Status", justify="center", no_wrap=True)
        table.add_column("ms", justify="right", no_wrap=True)
        table.add_column("Up%", justify="right", no_wrap=True)
        table.add_column("History", no_wrap=True, ratio=2)
        for s in visible:
            cells = [s.name]
            if show_type:
                cells.append(f"{TYPE_ICON.get(s.type, '')} {s.type}")
            cells += [
                status_text(s.state),
                latency_text(s.last_ms),
                uptime_text(s.uptime_pct()),
                sparkline(s.history),
            ]
            table.add_row(*cells)
        return table

    # Pin the DOWN targets (they sort first) so they never scroll off-screen.
    pin = sum(1 for s in rows if s.state == "DOWN") if sort_down_first else 0
    return _Scroller(rows, make_table, pin=pin)


def _panel_title(label, states):
    up = sum(1 for s in states if s.state == "UP")
    down = sum(1 for s in states if s.state == "DOWN")
    t = Text()
    t.append(f"{label}  ", style="bold")
    t.append(f"✅{up}", style="green")
    t.append(" ")
    t.append(f"🔴{down}", style="red" if down else "dim")
    t.append(f" /{len(states)}", style="dim")
    return t


def render_websites_panel(states, sort_down_first):
    body = _targets_table(states, sort_down_first, show_type=False)
    border = "red" if any(s.state == "DOWN" for s in states) else "green"
    return Panel(body, title=_panel_title("🌐 Websites", states),
                 border_style=border, box=box.ROUNDED, padding=(0, 1))


def render_vps_panel(states, sort_down_first):
    body = _targets_table(states, sort_down_first, show_type=True)
    border = "red" if any(s.state == "DOWN" for s in states) else "green"
    return Panel(body, title=_panel_title("📡 VPS / hosts", states),
                 border_style=border, box=box.ROUNDED, padding=(0, 1))


# ---------------------------------------------------------------------
#  Quadrant 4: recent events (state changes) from storage
# ---------------------------------------------------------------------
def render_events_panel(events):
    if not events:
        body = Align.center(
            Text("No events recorded yet.\nState changes will appear here.",
                 justify="center", style="dim"),
            vertical="middle",
        )
        return Panel(body, title="📜 Recent events", border_style="bright_black",
                     box=box.ROUNDED, padding=(0, 1))

    table = Table(expand=True, box=box.SIMPLE_HEAD, header_style="bold magenta",
                  pad_edge=False, row_styles=["", "on grey7"])
    table.add_column("Time", no_wrap=True)
    table.add_column("Target", no_wrap=True, ratio=2, overflow="ellipsis")
    table.add_column("Change", no_wrap=True)

    for ev in events:
        ts = (ev.get("ts") or "")[-8:]          # HH:MM:SS
        new = ev.get("new")
        change = Text()
        change.append(str(ev.get("old", "?")), style="dim")
        change.append(" → ")
        change.append(str(new), style="bold green" if new == "UP" else "bold red")
        table.add_row(ts, ev.get("name", "?"), change)

    return Panel(table, title="📜 Recent events", border_style="bright_black",
                 box=box.ROUNDED, padding=(0, 1))


# ---------------------------------------------------------------------
#  Cell: summary / overview
# ---------------------------------------------------------------------
def render_summary_panel(states):
    grid = Table.grid(padding=(0, 1), expand=True)
    grid.add_column(justify="left", no_wrap=True, ratio=2)
    grid.add_column(justify="right", ratio=1)

    def row(label, value):
        grid.add_row(Text(label, style="bold cyan"), value)

    total = len(states)
    up = sum(1 for s in states if s.state == "UP")
    down = sum(1 for s in states if s.state == "DOWN")
    unknown = total - up - down

    ups = [s.uptime_pct() for s in states if s.uptime_pct() is not None]
    avg_uptime = sum(ups) / len(ups) if ups else None
    lat = [s.last_ms for s in states if s.state == "UP" and s.last_ms is not None]
    avg_lat = sum(lat) / len(lat) if lat else None

    n_http = sum(1 for s in states if s.type == "http")
    n_ping = sum(1 for s in states if s.type == "ping")
    n_tcp = sum(1 for s in states if s.type == "tcp")

    row("Targets", Text(str(total)))
    row("UP", Text(str(up), style="green"))
    row("DOWN", Text(str(down), style="red" if down else "dim"))
    if unknown:
        row("Unknown", Text(str(unknown), style="dim"))
    row("Avg uptime", uptime_text(avg_uptime))
    row("Avg latency", latency_text(avg_lat))
    row("By type", Text(f"{n_http}🌐 {n_ping}📡 {n_tcp}🔌", style="dim"))

    return Panel(grid, title="📊 Summary", border_style="blue",
                 box=box.ROUNDED, padding=(0, 1))


# ---------------------------------------------------------------------
#  Cell: attention (targets currently DOWN)
# ---------------------------------------------------------------------
def render_attention_panel(states):
    down = [s for s in states if s.state == "DOWN"]
    if not down:
        body = Align.center(
            Text("✓ All targets UP", justify="center", style="bold green"),
            vertical="middle",
        )
        return Panel(body, title="⚠ Attention", border_style="green",
                     box=box.ROUNDED, padding=(0, 1))

    table = Table(expand=True, box=box.SIMPLE_HEAD, header_style="bold magenta",
                  pad_edge=False, row_styles=["", "on grey7"])
    table.add_column("Target", no_wrap=True, ratio=2, overflow="ellipsis")
    table.add_column("Detail", overflow="ellipsis", ratio=3)
    for s in down:
        table.add_row(Text(s.name, style="bold red"), s.detail)

    return Panel(table, title=f"⚠ Attention  🔴{len(down)}",
                 border_style="red", box=box.ROUNDED, padding=(0, 1))


# ---------------------------------------------------------------------
#  Cell: Bitcoin / crypto prices (from market.MarketData)
# ---------------------------------------------------------------------
def _usd(v):
    if v is None:
        return Text("—", style="dim")
    return Text(f"${v:,.0f}" if v >= 1000 else f"${v:,.2f}")


def _change_text(pct):
    if pct is None:
        return Text("—", style="dim")
    arrow = "▲" if pct >= 0 else "▼"
    return Text(f"{arrow} {pct:+.2f}%", style="green" if pct >= 0 else "red")


def render_bitcoin_panel(crypto):
    """crypto: {ticker: {"price": float, "change": float}} or None."""
    if not crypto:
        body = Align.center(Text("Đang tải giá crypto…", style="dim"),
                            vertical="middle")
        return Panel(body, title="₿ Crypto", border_style="bright_black",
                     box=box.ROUNDED, padding=(0, 1))

    rows = list(crypto.items())

    def make_table(visible):
        table = Table(expand=True, box=box.SIMPLE_HEAD, header_style="bold magenta",
                      pad_edge=False, row_styles=["", "on grey7"])
        table.add_column("Coin", no_wrap=True, ratio=2)
        table.add_column("Giá (USD)", justify="right", no_wrap=True, ratio=3)
        table.add_column("24h", justify="right", no_wrap=True, ratio=2)
        for ticker, d in visible:
            table.add_row(Text(ticker, style="bold yellow"),
                          _usd(d.get("price")), _change_text(d.get("change")))
        return table

    btc = crypto.get("BTC") or next(iter(crypto.values()), {})
    chg = btc.get("change")
    border = "green" if (chg is None or chg >= 0) else "red"
    return Panel(_Scroller(rows, make_table), title="₿ Crypto",
                 border_style=border, box=box.ROUNDED, padding=(0, 1))


# ---------------------------------------------------------------------
#  Cell: Vietnam gold prices (PNJ, from market.MarketData)
# ---------------------------------------------------------------------
def _gold_price(v):
    """PNJ price is in thousand VND; show it in millions (triệu)."""
    if v is None:
        return Text("—", style="dim")
    return Text(f"{v / 1000:,.2f}")


def render_gold_panel(gold):
    """gold: [{"name","buy","sell","delta"}] or None."""
    if not gold:
        body = Align.center(Text("Đang tải giá vàng…", style="dim"),
                            vertical="middle")
        return Panel(body, title="🥇 Vàng VN", border_style="bright_black",
                     box=box.ROUNDED, padding=(0, 1))

    def make_table(visible):
        table = Table(expand=True, box=box.SIMPLE_HEAD, header_style="bold magenta",
                      pad_edge=False, row_styles=["", "on grey7"])
        table.add_column("Loại", no_wrap=True, ratio=3, overflow="ellipsis")
        table.add_column("Mua", justify="right", no_wrap=True)
        table.add_column("Bán", justify="right", no_wrap=True)
        for g in visible:
            sell = _gold_price(g.get("sell"))
            d = g.get("delta")
            if d:
                sell.append(" ▲" if d > 0 else " ▼", style="green" if d > 0 else "red")
            table.add_row(g.get("name", "?"), _gold_price(g.get("buy")), sell)
        return table

    return Panel(_Scroller(gold, make_table), title="🥇 Vàng VN (triệu đ)",
                 border_style="yellow", box=box.ROUNDED, padding=(0, 1))


# ---------------------------------------------------------------------
#  Header + full layout
# ---------------------------------------------------------------------
def render_header(states, countdown):
    up = sum(1 for s in states if s.state == "UP")
    down = sum(1 for s in states if s.state == "DOWN")
    total = len(states)
    overall = "green" if down == 0 else ("red" if up == 0 else "yellow")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    t = Text()
    t.append(" 🖥  Lap Monitor ", style="bold white on blue")
    t.append(f" v{__version__}", style="dim")
    t.append("   ")
    t.append(f"✅ {up} UP", style="bold green")
    t.append("   ")
    t.append(f"🔴 {down} DOWN", style="bold red" if down else "dim")
    t.append(f"  / {total} targets", style="dim")
    t.append("      ")
    t.append(f"🕐 {now}", style="cyan")
    if countdown is not None:
        t.append(f"   ⏳ next scan in {countdown:>2}s", style="dim")
    t.append("   ·  Ctrl+C to quit", style="dim")

    return Panel(Align.center(t, vertical="middle"),
                 border_style=overall, box=box.HEAVY, padding=0)


def build_layout(states, sysmon, market=None, countdown=None, sort_down_first=True):
    """Assemble the header + 3x2 (six-cell) layout into a single renderable.

    Grid (change the split_row()/split_column() calls below to rearrange):
        top:    [This machine / Summary] | Websites | VPS / hosts
        bottom: ₿ Crypto                 | 🥇 Vàng VN | Attention

    The first cell is split into two stacked sections (machine stats on top,
    target summary below). ``market`` is a market.MarketData (or None) whose
    cached ``crypto`` / ``gold`` snapshots feed the two bottom-left cells.
    """
    websites = [s for s in states if s.is_website()]
    vps = [s for s in states if s.is_vps()]
    crypto = market.crypto if market else None
    gold = market.gold if market else None

    root = Layout()
    root.split_column(
        Layout(render_header(states, countdown), name="header", size=3),
        Layout(name="body"),
    )
    root["body"].split_column(
        Layout(name="top"),
        Layout(name="bottom"),
    )
    root["top"].split_row(
        Layout(name="q1"),
        Layout(render_websites_panel(websites, sort_down_first), name="q2"),
        Layout(render_vps_panel(vps, sort_down_first), name="q3"),
    )
    # Cell 1: two stacked sections - machine stats above, target summary below.
    root["q1"].split_column(
        Layout(render_system_panel(sysmon), name="q1a"),
        Layout(render_summary_panel(states), name="q1b"),
    )
    root["bottom"].split_row(
        Layout(render_bitcoin_panel(crypto), name="q4"),
        Layout(render_gold_panel(gold), name="q5"),
        Layout(render_attention_panel(states), name="q6"),
    )
    return root

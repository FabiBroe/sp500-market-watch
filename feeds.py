"""Tägliche US-Schlusskurse und lokaler Cache. Benötigt Python 3.9+, keine API-Schlüssel."""
import csv
import datetime as dt
import io
import json
import math
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from http.client import HTTPException
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


START = dt.date(2000, 1, 3)
NAMES = {"spx": "S&P 500", "vix": "VIX", "qqq": "QQQ", "iwm": "IWM"}
SYMBOLS = {"spx": "^GSPC", "vix": "^VIX", "qqq": "QQQ", "iwm": "IWM"}
DAY = dt.timedelta(days=1)
UTC = dt.timezone.utc
EXTRA_CLOSURES = {
    dt.date(2001, 9, 11), dt.date(2001, 9, 12), dt.date(2001, 9, 13),
    dt.date(2001, 9, 14), dt.date(2004, 6, 11), dt.date(2007, 1, 2),
    dt.date(2012, 10, 29), dt.date(2012, 10, 30), dt.date(2018, 12, 5),
    dt.date(2025, 1, 9),
}
FEED_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, csv.Error, HTTPException)
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/"


def _date(value):
    return dt.date.fromisoformat(value) if isinstance(value, str) else value


def _weekday(year, month, weekday, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _ny(now):
    """Aware UTC input; Windows installations without IANA files use US DST rules."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    try:
        return now.astimezone(ZoneInfo("America/New_York"))
    except ZoneInfoNotFoundError:
        u = now.astimezone(UTC)
        if u.year >= 2007:
            start = _weekday(u.year, 3, 6, 2)
            end = _weekday(u.year, 11, 6, 1)
        else:
            start = _weekday(u.year, 4, 6, 1)
            end = dt.date(u.year, 10, 31)
            end -= dt.timedelta(days=(end.weekday() - 6) % 7)
        start = dt.datetime.combine(start, dt.time(7), UTC)
        end = dt.datetime.combine(end, dt.time(6), UTC)
        offset = -4 if start <= u < end else -5
        return u.astimezone(dt.timezone(dt.timedelta(hours=offset)))


def _easter(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, rem = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, rem + 1)


@lru_cache(maxsize=128)
def _holidays(year):
    jan = dt.date(year, 1, 1)
    may = dt.date(year, 5, 31)
    # NYSE leaves Dec 31 open when the following Jan 1 is a Saturday.
    holidays = {
        jan + DAY if jan.weekday() == 6 else jan,
        _weekday(year, 1, 0, 3), _weekday(year, 2, 0, 3), _easter(year) - 2 * DAY,
        may - dt.timedelta(days=may.weekday()), _weekday(year, 9, 0, 1),
        _weekday(year, 11, 3, 4),
    }
    fixed = [dt.date(year, 7, 4), dt.date(year, 12, 25)]
    if year >= 2022:
        fixed.append(dt.date(year, 6, 19))
    for item in fixed:
        delta = {5: -1, 6: 1}.get(item.weekday(), 0)
        holidays.add(item + delta * DAY)
    return holidays | EXTRA_CLOSURES


def is_session(day):
    day = _date(day)
    return day.weekday() < 5 and day not in _holidays(day.year)


def expected_session(now=None):
    """Latest scheduled US session ready for EOD use, conservatively after 16:35 ET."""
    local = _ny(now or dt.datetime.now(UTC))
    day = local.date()
    if (local.hour, local.minute) < (16, 35):
        day -= DAY
    while not is_session(day):
        day -= DAY
    return day.isoformat()


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _request(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketWatch-EOD/1.0)",
                                "Accept": "application/json,text/csv,*/*"})
    with urlopen(req, timeout=12) as response:
        content = response.read(12_000_001)
    if len(content) > 12_000_000:
        raise ValueError("Antwort überschreitet Größenlimit")
    return content.decode("utf-8-sig")


def yahoo_closes(symbol, start, end, host="query2.finance.yahoo.com", adjusted=False):
    """Daily Yahoo Finance close (split-adjusted) or adjclose; end date inclusive.

    The caller selects a completed end date. No intraday data from today's session
    are accepted before 16:35 ET, or if the feed still timestamps the regular quote
    in mid-session. Historical regular candles carry *opening* timestamps.
    """
    start, end = _date(start), _date(end)
    if host not in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        raise ValueError("Unbekannter Kursanbieter")
    if start > end:
        return {}
    to_epoch = lambda d: int(dt.datetime.combine(d, dt.time(), UTC).timestamp())
    query = urlencode({"period1": to_epoch(start), "period2": to_epoch(end + DAY), "interval": "1d"})
    payload = json.loads(_request("https://" + host + "/v8/finance/chart/" + quote(symbol, safe="") + "?" + query))
    result = payload["chart"]["result"][0]
    meta = result["meta"]
    if meta.get("symbol", "").upper() != symbol.upper() or meta.get("dataGranularity") != "1d":
        raise ValueError("Symbol oder Tagesintervall stimmt nicht überein")
    prices = (result["indicators"]["adjclose"][0]["adjclose"] if adjusted
              else result["indicators"]["quote"][0]["close"])
    stamps = result["timestamp"]
    if len(stamps) != len(prices):
        raise ValueError("Zeit- und Kursreihe unterschiedlich lang")
    values = {}
    now = dt.datetime.now(UTC)
    today = _ny(now).date()
    quote_time = meta.get("regularMarketTime")
    quote_et = _ny(dt.datetime.fromtimestamp(quote_time, UTC)) if quote_time else None
    for ts, raw in zip(stamps, prices):
        # In US daily ETFs/equity indices the UTC date equals the exchange date.
        day = dt.datetime.fromtimestamp(ts, UTC).date()
        value = _number(raw)
        if value is None or not start <= day <= end:
            continue
        if day == today:
            if day.isoformat() != expected_session(now) or not quote_et or quote_et.date() != day:
                continue
            # Yahoo's regularMarketTime can lag when a cached response is served.
            # Stale intraday closes must not turn into a same-day alert. On shortened
            # sessions wait until the following day if exact hours are unknown.
            if (quote_et.hour, quote_et.minute) < (16, 0):
                early = (day == _weekday(day.year, 11, 3, 4) + DAY or
                         (day.month, day.day) in ((7, 3), (12, 24)))
                if not early or (quote_et.hour, quote_et.minute) < (13, 0):
                    continue
        values[day.isoformat()] = value
    if not values:
        raise ValueError("Keine gültigen Tagesschlusskurse")
    return values


def _cboe(key, end):
    name, column = ("SPX", "SPX") if key == "spx" else ("VIX", "CLOSE")
    rows = csv.DictReader(io.StringIO(_request(CBOE + name + "_History.csv")))
    if not {"DATE", column}.issubset(rows.fieldnames or []):
        raise ValueError("Unerwartete CSV-Spalten")
    prices = {}
    for row in rows:
        day = dt.datetime.strptime(row["DATE"], "%m/%d/%Y").date()
        value = _number(row[column])
        if START <= day <= end and value is not None:
            prices[day.isoformat()] = value
    return prices


def _fred(key, end):
    series = "SP500" if key == "spx" else "VIXCLS"
    content = _request("https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series)
    rows = csv.DictReader(io.StringIO(content))
    date_column = "observation_date" if "observation_date" in (rows.fieldnames or []) else "DATE"
    prices = {}
    for row in rows:
        day = dt.date.fromisoformat(row[date_column])
        value = _number(row[series])
        if START <= day <= end and value is not None:
            prices[day.isoformat()] = value
    return prices


def _fetch(key, end):
    methods = []
    if key in ("spx", "vix"):
        methods.append(("Cboe", lambda: _cboe(key, end)))
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        methods.append(("Yahoo Finance", lambda h=host: yahoo_closes(SYMBOLS[key], START, end, h)))
    if key in ("spx", "vix"):
        methods.append(("FRED", lambda: _fred(key, end)))
    wanted = end.isoformat()
    result, used, failures = {}, [], []
    for name, fetch in methods:
        try:
            history = fetch()
            if not history:
                raise ValueError("Keine gültigen Schlusskurse")
            # Dates absent from the higher-priority feed may be supplied by a fallback.
            extra = {d: v for d, v in history.items() if d not in result}
            if extra:
                result.update(extra)
                if name not in used:
                    used.append(name)
            if wanted in result and len(result) >= 200:
                break
        except FEED_ERRORS as exc:
            failures.append(name + " (" + type(exc).__name__ + ")")
    return result, " + ".join(used), ", ".join(dict.fromkeys(failures))


def _read_cache(path):
    if not path.exists():
        return {}, None, None, None
    try:
        with path.open(encoding="utf-8") as file:
            obj = json.load(file)
        if obj["version"] != 1 or not isinstance(obj["closes"], dict):
            raise ValueError("Cacheformat")
        rows = {}
        for day, raw in obj["closes"].items():
            value = _number(raw)
            if value is not None:
                rows[dt.date.fromisoformat(day).isoformat()] = value
        return rows, str(obj["source"]), str(obj["at"]), None
    except FEED_ERRORS:
        return {}, None, None, "Lokaler Kursspeicher konnte nicht gelesen werden."


def _write_cache(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8",
                                         prefix="." + path.name, delete=False) as f:
            temp = Path(f.name)
            json.dump(obj, f, allow_nan=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass


def _asset(key, cache_dir, refresh, now, end):
    filename = cache_dir / (key + ".json")
    cache, source, at, read_error = _read_cache(filename)
    warnings = [NAMES[key] + " • " + read_error] if read_error else []
    online = False
    if refresh:
        incoming, new_source, failures = _fetch(key, end)
        if incoming:
            # Fresh ETF history must stay internally consistent across splits.
            # FRED and any truncated histories can safely extend the existing index series.
            if key in ("qqq", "iwm") and cache:
                overlap = max((d for d in incoming if d in cache), default=None)
                if overlap and abs(incoming[overlap] / cache[overlap] - 1) > 0.05:
                    cache = {}
            cache.update(incoming)
            source = new_source
            at = now.astimezone(UTC).isoformat(timespec="seconds")
            online = True
            try:
                _write_cache(filename, {"version": 1, "source": source, "at": at, "closes": cache})
            except OSError:
                warnings.append(NAMES[key] + " • Aktualisierung konnte nicht lokal gespeichert werden.")
        else:
            warnings.append(NAMES[key] + " • Kursabruf fehlgeschlagen. " + failures)
    upper = end.isoformat()
    cache = {day: value for day, value in cache.items() if START.isoformat() <= day <= upper}
    if cache and max(cache) < upper:
        warnings.append(NAMES[key] + " • Letzter verfügbarer Schlusskurs vom " + max(cache) + ".")
    if not cache:
        warnings.append(NAMES[key] + " • Keine Schlusskurse verfügbar.")
    return key, cache, source, at, online, warnings


def load_market_data(cache_dir, refresh=True, now=None):
    """Return (rows, metadata). Rows contain SPX/VIX/QQQ/IWM values or explicit None.

    Preserve missing scheduled sessions inside observed coverage. Trailing sessions
    entirely missing are identified by expected_session vs. the last observed date.
    """
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    last = expected_session(now)
    end = _date(last)
    folder = Path(cache_dir).expanduser()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_asset, k, folder, refresh, now, end) for k in NAMES]
        results = [f.result() for f in futures]
    series = {k: prices for k, prices, *_ in results}
    bounds = [p for p in series.values() if p]
    rows = []
    if bounds:
        first = _date(min(min(p) for p in bounds))
        observed = _date(max(max(p) for p in bounds))
        day = first
        while day <= observed:
            if is_session(day):
                iso = day.isoformat()
                rows.append({"date": iso, **{k: prices.get(iso) for k, prices in series.items()}})
            day += DAY
    common = next((r["date"] for r in reversed(rows) if all(r[k] is not None for k in NAMES)), None)
    spx_day = next((r["date"] for r in reversed(rows) if r["spx"] is not None), None)
    dates = [at for _, _, _, at, _, _ in results if at is not None]
    return rows, {
        "expected_session": last, "common_session": common, "spx_session": spx_day,
        "fresh": common == last, "cache_only": not any(item[4] for item in results),
        "sources": {k: src or "–" for k, _, src, _, _, _ in results},
        "warnings": [warning for item in results for warning in item[5]],
        "latest_by_asset": {k: max(p, default=None) for k, p in series.items()},
        "fetched_by_asset": {k: at for k, _, _, at, _, _ in results},
        "fetched_at": max(dates, default=None),
    }

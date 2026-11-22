"""A source-labelled, date-aligned 34-indicator cross-asset reconstruction."""

import csv
import io
import itertools
import json
import math
import statistics as st
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from cross_asset_catalog import INDICATORS, PILLARS
from feeds import CBOE, FEED_ERRORS, _request, _write_cache, expected_session, yahoo_closes

CBOE_SERIES = {
    "VIX",
    "VVIX",
    "VIX9D",
    "VIX3M",
    "VIX6M",
    "VXN",
    "SKEW",
    "COR1M",
    "COR3M",
    "COR6M",
    "COR1Y",
    "DSPX",
    "VXTLT",
}
FRED_SERIES = {"BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A3HYC", "BAMLH0A1HYBB", "DGS2", "DGS10", "DFII10"}
N = len(INDICATORS)
VERSION = 2
LOOKBACK = 252
BASE_MIN = 210
SCORE_PERIOD = 120


def _source(symbol):
    if symbol in CBOE_SERIES:
        return {"name": "Cboe " + symbol, "url": CBOE + symbol + "_History.csv"}
    if symbol in FRED_SERIES:
        return {"name": "FRED " + symbol, "url": "https://fred.stlouisfed.org/series/" + symbol}
    return {
        "name": "Yahoo Finance " + symbol,
        "url": "https://finance.yahoo.com/quote/" + quote(symbol, safe="") + "/history/",
    }


def _read(path):
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path, result):
    try:
        _write_cache(path, result)
    except OSError:
        pass  # The in-memory report remains usable if the cache is read-only.


def _num(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _fetch_series(symbol, start, end):
    if symbol in FRED_SERIES:
        url = (
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
            + symbol
            + "&cosd="
            + start
            + "&coed="
            + end
        )
        reader = csv.DictReader(io.StringIO(_request(url)))
        datecol = "observation_date" if "observation_date" in (reader.fieldnames or []) else "DATE"
        pairs = ((r[datecol], r[symbol]) for r in reader)
    elif symbol in CBOE_SERIES:
        reader = csv.DictReader(io.StringIO(_request(_source(symbol)["url"])))
        valuecol = "CLOSE" if "CLOSE" in (reader.fieldnames or []) else symbol
        pairs = ((datetime.strptime(r["DATE"], "%m/%d/%Y").date().isoformat(), r[valuecol]) for r in reader)
    else:
        for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
            try:
                return yahoo_closes(symbol, start, end, host, adjusted=not symbol.startswith("^"))
            except FEED_ERRORS:
                if host == "query1.finance.yahoo.com":
                    raise
    data = {}
    for d, value in pairs:
        number = _num(value)
        if start <= d <= end and number is not None:
            data[d] = number
    if not data:
        raise ValueError("Keine Messwerte für " + symbol)
    return data


def _series(symbol, folder, start, end, refresh):
    # Each response covers the full requested window. Preserve an earlier, more recent
    # file if a stale upstream mirror responds; never splice adjusted ETF histories.
    filename = folder / (symbol.replace("^", "index_") + ".json")
    cache = _read(filename)
    stored = cache.get("data", {})
    if not isinstance(stored, dict):
        stored = {}
    stored = {k: n for k, v in stored.items() if start <= k <= end and (n := _num(v)) is not None}
    now = datetime.now(timezone.utc).timestamp()
    last_fetch = _num(cache.get("fetched")) or 0
    if refresh and not (cache.get("end") == end and 0 <= now - last_fetch < 1800 and stored):
        try:
            data = _fetch_series(symbol, start, end)
            if not stored or max(data) >= max(stored):
                stored = data
                _save(filename, {"data": data, "end": end, "fetched": now})
        except FEED_ERRORS:
            pass
    return symbol, stored


def _change(a, b):
    return 100 * (a / b - 1) if a is not None and b is not None and b != 0 else None


def _correlation(x, y, minimum):
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < minimum:
        return None
    mx = sum(a for a, b in pairs) / len(pairs)
    my = sum(b for a, b in pairs) / len(pairs)
    num = sum((a - mx) * (b - my) for a, b in pairs)
    xx = sum((a - mx) ** 2 for a, b in pairs)
    yy = sum((b - my) ** 2 for a, b in pairs)
    return max(-1.0, min(1.0, num / math.sqrt(xx * yy))) if xx > 0 and yy > 0 else None


def _raw(spec, cols):
    series = [cols[s] for s in spec.symbols]
    first = series[0]
    op = spec.operation
    if op == "level":
        return first[:]
    if op in ("ratio", "spread", "relative20"):
        a, b = series
        base = [
            (
                (x - y if op == "spread" else x / y)
                if x is not None and y is not None and (op == "spread" or y != 0)
                else None
            )
            for x, y in zip(a, b)
        ]
        if op != "relative20":
            return base
        return [_change(v, base[i - 20]) if i >= 20 else None for i, v in enumerate(base)]
    if op in ("ret20", "change_bps"):
        return [
            (
                (_change(v, first[i - 20]) if op == "ret20" else (v - first[i - 20]) * 100)
                if i >= 20 and v is not None and first[i - 20] is not None
                else None
            )
            for i, v in enumerate(first)
        ]
    if op == "curve_vol":
        spreads, out = [], []
        for i, (x, y) in enumerate(zip(*series)):
            if x is None or y is None:
                out.append(None)
                continue
            spreads.append((i, 100 * (x - y)))
            latest = spreads[-21:]
            if len(latest) == 21 and i - latest[0][0] <= 25:
                out.append(st.stdev(b[1] - a[1] for a, b in zip(latest, latest[1:])))
            else:
                out.append(None)
        return out
    if op in ("down_sectors", "sectors_above"):
        out = []
        for i in range(len(first)):
            flags = []
            for values in series:
                if op == "down_sectors" and i >= 5:
                    move = _change(values[i], values[i - 5])
                    if move is not None:
                        flags.append(move < 0)
                elif op == "sectors_above" and i >= 199:
                    win = values[i - 199 : i + 1]
                    if None not in win:
                        flags.append(win[-1] > sum(win) / 200)
            out.append(100 * sum(flags) / len(flags) if len(flags) == len(series) else None)
        return out
    if op in ("corr60", "sector_corr"):
        n_days = 60 if op == "corr60" else 20
        returns = [[None] + [_change(x, y) for x, y in zip(s[1:], s)] for s in series]
        out = [None] * len(first)
        for i in range(n_days, len(first)):
            windows = [v[i - n_days + 1 : i + 1] for v in returns]
            if any(None in w for w in windows):
                continue
            r = [_correlation(a, b, n_days) for a, b in itertools.combinations(windows, 2)]
            if r and None not in r:
                out[i] = sum(r) / len(r)
        return out
    raise ValueError("Unbekannte Kennzahloperation " + op)


def _standardize(raw, risk_up):
    # Leave a missing endpoint missing. A macro publication holiday does not erase
    # the other 250 reference observations; the denominator is the valid count.
    z = [None] * len(raw)
    for i in range(max(LOOKBACK, len(raw) - SCORE_PERIOD), len(raw)):
        if raw[i] is None:
            continue
        window = [v for v in raw[i - LOOKBACK : i] if v is not None]
        if len(window) < BASE_MIN:
            continue
        mean = sum(window) / len(window)
        variance = sum((v - mean) ** 2 for v in window) / (len(window) - 1)
        if variance > 1e-15:
            signed = (raw[i] - mean) / math.sqrt(variance) * (-1 if risk_up else 1)
            z[i] = min(3.0, max(-3.0, signed))
    return z


def _de(x):
    if x is None:
        return "–"
    return f"{x:+.2f}".replace(".", ",").replace("-", "−")


def _label(z):
    if z is None:
        return "Daten fehlen"
    if z < -1:
        return "Alarm"
    if z <= -0.5:
        return "Beobachten"
    if z >= 0.5:
        return "Risikoappetit"
    return "Neutral"


def _aggregate(scores):
    pillar_values = []
    coverage = 0
    for j in range(len(PILLARS)):
        group = [v for m, v in zip(INDICATORS, scores) if m.pillar == j]
        known = [v for v in group if v is not None]
        coverage += len(known)
        pillar_values.append(sum(known) / len(known) if len(known) * 2 >= len(group) else None)
    partial = (
        sum(pillar_values) / len(pillar_values)
        if None not in pillar_values and coverage >= math.ceil(0.78 * N)
        else None
    )
    return pillar_values, coverage, partial


def _contagion(score_rows, pos):
    diffs = []
    for series in score_rows:
        part = series[max(0, pos - 60) : pos + 1]
        diffs.append([b - a if a is not None and b is not None else None for a, b in zip(part, part[1:])])
    correlations = []
    for x, y in itertools.combinations(diffs, 2):
        r = _correlation(x, y, 50)
        if r is not None:
            correlations.append(r)
    return (sum(correlations) / len(correlations) if correlations else None, len(correlations))


def _calculate(rows, data, end):
    dates = [r["date"] for r in rows]
    n = len(dates)
    cols = {s: [values.get(d) for d in dates] for s, values in data.items()}
    cols["VIX"] = [r.get("vix") for r in rows]
    raw_rows = [_raw(m, cols) for m in INDICATORS]
    scores = [_standardize(raw, m.risk_up) for m, raw in zip(INDICATORS, raw_rows)]
    current = [s[-1] for s in scores]
    pvalues, coverage, provisional = _aggregate(current)
    full_idx = next(
        (
            i
            for i in range(n - 1, max(-1, n - SCORE_PERIOD - 1), -1)
            if all(s[i] is not None for s in scores)
        ),
        None,
    )
    full_values = [s[full_idx] for s in scores] if full_idx is not None else []
    _, _, full_composite = _aggregate(full_values) if full_values else (None, 0, None)
    correlation, pairs = _contagion(scores, n - 1)
    summary = {
        "as_of": end,
        "total": N,
        "coverage": coverage,
        "composite": provisional if coverage == N else None,
        "partial_composite": provisional if coverage != N else None,
        "flashing": sum(_label(z) == "Alarm" for z in current),
        "watch": sum(_label(z) == "Beobachten" for z in current),
        "correlation": correlation,
        "correlation_pairs": pairs,
        "full_session": dates[full_idx] if full_idx is not None else None,
        "full_composite": full_composite,
        "full_flashing": sum(_label(z) == "Alarm" for z in full_values) if full_values else None,
        "full_watch": sum(_label(z) == "Beobachten" for z in full_values) if full_values else None,
    }
    items = []
    for j, name in enumerate(PILLARS):
        indices = [i for i, m in enumerate(INDICATORS) if m.pillar == j]
        known = [current[i] for i in indices if current[i] is not None]
        flash = sum(_label(z) == "Alarm" for z in known)
        watch = sum(_label(z) == "Beobachten" for z in known)
        spark = []
        for t in range(max(0, n - 60), n):
            obs = [scores[i][t] for i in indices]
            # Do not connect across missing measurements of a constituent.
            spark.append(sum(obs) / len(obs) if None not in obs else None)
        items.append(
            {
                "name": name,
                "value": _de(pvalues[j]) + " σ" if pvalues[j] is not None else "Daten fehlen",
                "note": f"{len(known)}/{len(indices)} aktuell · {flash} Alarm · {watch} beobachten",
                "spark": spark,
                "score": pvalues[j],
                "coverage": len(known),
                "total": len(indices),
            }
        )
    indicators = []
    for m, raw, z in zip(INDICATORS, raw_rows, scores):
        last = next((i for i in range(n - 1, -1, -1) if raw[i] is not None), None)
        score_day = next((i for i in range(n - 1, -1, -1) if z[i] is not None), None)
        sources = []
        for symbol in m.symbols:
            source = _source(symbol)
            recent = next((i for i in range(n - 1, -1, -1) if cols[symbol][i] is not None), None)
            source["as_of"] = dates[recent] if recent is not None else None
            sources.append(source)
        indicators.append(
            {
                "id": m.id,
                "pillar": PILLARS[m.pillar],
                "name": m.name,
                "evidence": m.evidence,
                "evidence_note": m.evidence_note,
                "implementation": m.implementation,
                "formula": m.formula,
                "raw": raw[last] if last is not None else None,
                "unit": m.unit,
                "score": z[-1],
                "status": _label(z[-1]),
                "as_of": dates[last] if last is not None else None,
                "current": z[-1] is not None,
                "direction": (
                    "Höher bedeutet mehr Stress" if m.risk_up else "Niedriger bedeutet mehr Stress"
                ),
                "last_score": z[score_day] if score_day is not None else None,
                "score_as_of": dates[score_day] if score_day is not None else None,
                "sources": sources,
            }
        )
    desc = (
        "34 Kennzahlen in sechs gleichgewichteten Bereichen. "
        + f"{coverage}/34 sind für den {date.fromisoformat(end).strftime('%d.%m.%Y')} auswertbar."
    )
    return {
        "title": "Cross-Asset-Risikomonitor",
        "description": desc,
        "as_of": end,
        "complete": coverage == N,
        "items": items,
        "indicators": indicators,
        "summary": summary,
        "method": "Eigene Rekonstruktion. Jede Kennzahl wird gegen die vorherigen 252 US-Aktienhandelstage standardisiert (mindestens 210 Messwerte, Stichprobenstreuung). "
        "Das Vorzeichen wird so gewählt, dass tiefere Werte mehr Stress anzeigen. Jeder z-Wert wird auf −3 bis +3 begrenzt. Alarm gilt bei z < −1, Beobachten bei −1 ≤ z ≤ −0,5. "
        "Die Kennzahlen zählen innerhalb ihres Bereichs gleich. Der vollständige Gesamtwert ist der Mittelwert der sechs Bereiche und verlangt 34 aktuelle Werte. "
        "Ein vorläufiger Wert verlangt mindestens 27 aktuelle Werte und mindestens die Hälfte je Bereich. Fehlende Beobachtungen werden nie fortgeschrieben. "
        "Die Korrelation misst gemeinsame tägliche Änderungen der ausgerichteten z-Werte über 60 Sitzungen, mit mindestens 50 gemeinsamen Änderungen je Paar. "
        "Bei 34 Kennzahlen sind 561 Paare möglich. Die Zuordnung einzelner sichtbarer Zeilen zu den sechs Bereichen, die genaue Normalisierung, die Rekonstruktionsformeln und Datenquellen sind eigene Festlegungen. "
        "Die Prozententwicklung eines Fondsverhältnisses berechnet sich als heutiges Verhältnis geteilt durch das Verhältnis vor 20 Sitzungen, minus eins. "
        "Die Marktdaten stammen von Cboe, FRED und Yahoo Finance. Fonds nutzen ausschüttungsbereinigte Kurse. "
        "Daten werden nachträglich aktualisiert und dienen einer Schlusskursauswertung. Der Vergleich gibt dem Washout-Score keine zusätzlichen Punkte.",
    }


def context_panel(all_rows, cache_dir, refresh=True):
    if not all_rows:
        # The catalogue remains readable on a first launch without any market data.
        end = expected_session()
        symbols = {s for m in INDICATORS for s in m.symbols}
        return _calculate([{"date": end, "vix": None}], {s: {} for s in symbols}, end)
    rows = all_rows[-580:]
    end = rows[-1]["date"]
    folder = Path(cache_dir) / "cross-asset-34"
    report_path = folder / ("report-v" + str(VERSION) + ".json")
    cache = _read(report_path)
    if not refresh and cache.get("as_of") == end and len(cache.get("indicators", [])) == N:
        return cache
    start = (date.fromisoformat(rows[0]["date"]) - timedelta(days=3)).isoformat()
    symbols = sorted({s for m in INDICATORS for s in m.symbols if s != "VIX"})

    def fetch(s):
        return _series(s, folder / "series", start, end, refresh)

    with ThreadPoolExecutor(max_workers=8) as workers:
        histories = dict(workers.map(fetch, symbols))
    result = _calculate(rows, histories, end)
    if refresh:
        _save(report_path, result)
    return result

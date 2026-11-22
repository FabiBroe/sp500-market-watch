"""Close-to-close S&P 500 washout monitor. No external dependencies."""

import math
import statistics
from collections import deque
from datetime import date


MARKETS = ("spx", "qqq", "iwm")
SQRT_YEAR = math.sqrt(252)
METHODOLOGY = {
    "rsi": "Wilder-RSI über 14 Handelstage. Die ersten 14 Kursänderungen liefern die Startmittelwerte. Bei unverändertem Kurs über die gesamte Startperiode gilt RSI 50.",
    "volatility": "Eigene Fensterwahl für die realisierte Volatilität: Stichproben-Standardabweichung über 20 tägliche logarithmische S&P-Renditen, annualisiert mit √252 und in Prozent ausgewiesen.",
    "sigma": "Tages-Sigma = einfache S&P-Tagesänderung in Prozent ÷ (VIX vom vorherigen Handelstag ÷ √252). Die Fünf-Tage-Regel summiert fünf Tages-Sigmas. Der Cluster zählt Tages-Sigmas ≤ −2 in den letzten 20 Sitzungen.",
    "setup": "Ein Anstieg von unter 4 auf mindestens 4 Punkte eröffnet eine Beobachtung. Pro laufender Beobachtung gibt es eine Washout-Meldung. Nach 252 Sitzungen ohne einen weiteren Tag mit mindestens 4 Punkten läuft die Beobachtung aus.",
    "recovery": "Die Erholung folgt auf eine eröffnete Beobachtung. Mindestens einer der drei Märkte muss ab dem Setup an oder unter seinem SMA200 gelegen haben. An einem späteren Schluss wechseln die drei gemeinsam von weniger als drei auf drei Märkte über ihrem jeweiligen SMA200. Eine spätere Unterschreitung beendet den aktuellen Erholungsstatus.",
    "backtest": "Auswertungsbeginn 1. November 2001. Vorlaufdaten dienen zur Initialisierung der Indikatoren. Je Gruppe zählen erste Aufwärtsüberschreitungen bzw. Erholungsmeldungen mit einem Mindestabstand von 63 Handelstagen zum zuletzt berücksichtigten Ereignis derselben Gruppe. Gruppen können sich überschneiden. 21/63-Tage-Ertrag = prozentuale Indexveränderung ab Signalschluss. Treffer = Ertrag > 0. Rückgang = niedrigster Schluss relativ zum Signalschluss innerhalb der nächsten 63 Sitzungen (höchstens 0 %). Angezeigt wird der Median der Rückgänge. Offene Zeitfenster und Zeitfenster mit fehlenden S&P-Schlusskursen entfallen für den jeweiligen Horizont.",
    "gaps": "Jede Zeile entspricht einer erwarteten US-Handelssitzung. Fehlende Werte werden nicht fortgeschrieben. Gleitende Fenster verlangen lückenlose Beobachtungen. Der Gesamtwert erscheint nur bei sechs auswertbaren Regeln. Für Schwellenmeldungen werden zwei aufeinanderfolgende gültige Score-Tage benötigt.",
}


def _price(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _at_most(value, limit):
    if value is None:
        return None
    return value <= limit or math.isclose(value, limit, rel_tol=1e-12, abs_tol=1e-12)


class _Window:
    """A fixed number of sessions; a missing member invalidates the window."""

    def __init__(self, size):
        self.values = deque(maxlen=size)
        self.missing = 0

    def add(self, value):
        if len(self.values) == self.values.maxlen and self.values[0] is None:
            self.missing -= 1
        self.values.append(value)
        if value is None:
            self.missing += 1

    @property
    def ready(self):
        return len(self.values) == self.values.maxlen and not self.missing

    def mean(self):
        return math.fsum(self.values) / self.values.maxlen if self.ready else None


class _Wilder:
    def __init__(self):
        self.seed = []
        self.gain = None
        self.loss = None

    def update(self, change):
        if change is None:
            self.seed.clear()
            self.gain = self.loss = None
            return None
        gain, loss = max(0.0, change), max(0.0, -change)
        if self.gain is None:
            self.seed.append((gain, loss))
            if len(self.seed) < 14:
                return None
            self.gain = math.fsum(v[0] for v in self.seed) / 14
            self.loss = math.fsum(v[1] for v in self.seed) / 14
            self.seed.clear()
        else:
            self.gain = (self.gain * 13 + gain) / 14
            self.loss = (self.loss * 13 + loss) / 14
        total = self.gain + self.loss
        return 50.0 if total == 0 else 100 * self.gain / total


def _backtest(timeline, candidates):
    groups, episodes = [], []
    for label, indices in candidates.items():
        group = []
        last_index = None
        for i in indices:
            if timeline[i]["date"] < "2001-11-01":
                continue
            if last_index is not None and i - last_index < 63:
                continue
            last_index = i
            day = timeline[i]
            ep = {
                "date": day["date"], "group": label, "score": day["score"],
                "return21": None, "return63": None, "drawdown63": None,
            }
            for horizon in (21, 63):
                if i + horizon >= len(timeline):
                    continue
                path = [d["spx"] for d in timeline[i + 1:i + horizon + 1]]
                if any(price is None for price in path):
                    continue
                ep["return" + str(horizon)] = (path[-1] / day["spx"] - 1) * 100
                if horizon == 63:
                    ep["drawdown63"] = min(0.0, (min(path) / day["spx"] - 1) * 100)
            group.append(ep)
        result = {"label": label, "n": len(group)}
        for horizon in ("21", "63"):
            returns = [ep["return" + horizon] for ep in group if ep["return" + horizon] is not None]
            result["n" + horizon] = len(returns)
            result["median" + horizon] = statistics.median(returns) if returns else None
            result["hit" + horizon] = 100 * sum(v > 0 for v in returns) / len(returns) if returns else None
        drawdowns = [ep["drawdown63"] for ep in group if ep["drawdown63"] is not None]
        result["drawdown63"] = statistics.median(drawdowns) if drawdowns else None
        result["worst63"] = min(drawdowns) if drawdowns else None
        groups.append(result)
        episodes.extend(group)
    return groups, sorted(episodes, key=lambda ep: ep["date"])


def analyze(rows):
    """Evaluate sorted, date-aligned US sessions. All series are causal up to each close."""
    averages = {key: _Window(200) for key in MARKETS}
    sigmas5, extreme20, log20 = _Window(5), _Window(20), _Window(20)
    wilder = _Wilder()
    timeline, events = [], []
    candidates = {"≥3": [], "≥4": [], "Erholung": []}
    previous_date = None
    previous_spx = previous_vix = previous_score = previous_above = None
    setup_date = recovery_date = None
    active = witnessed_below = recovery_live = False
    last_strong = None

    for i, raw in enumerate(rows):
        day_date = raw["date"]
        if not isinstance(day_date, str) or date.fromisoformat(day_date).isoformat() != day_date:
            raise ValueError("Erwartetes Datum im Format YYYY-MM-DD.")
        if previous_date and day_date <= previous_date:
            raise ValueError("Handelstage müssen eindeutig und aufsteigend sortiert sein.")
        day = {key: _price(raw.get(key)) for key in ("spx", "vix", "iwm", "qqq")}
        spx, vix = day["spx"], day["vix"]
        sma, above = {}, {}
        for key, window in averages.items():
            window.add(day[key])
            sma[key] = window.mean()
            above[key] = None if sma[key] is None else not _at_most(day[key], sma[key])
        basket = None if None in above.values() else all(above.values())

        change = None if previous_spx is None or spx is None else spx - previous_spx
        rsi = wilder.update(change)
        daily_return = None if change is None else change / previous_spx
        log20.add(None if daily_return is None else math.log(spx / previous_spx))
        sigma = None if daily_return is None or previous_vix is None else daily_return * 100 / (previous_vix / SQRT_YEAR)
        sigmas5.add(sigma)
        extreme20.add(_at_most(sigma, -2))
        sigma5 = math.fsum(sigmas5.values) if sigmas5.ready else None
        cluster = sum(extreme20.values) if extreme20.ready else None
        rv20 = statistics.stdev(log20.values) * SQRT_YEAR * 100 if log20.ready else None
        ratio = rv20 / vix if rv20 is not None and vix is not None else None
        gap = (spx / sma["spx"] - 1) * 100 if sma["spx"] is not None else None
        vix_high = None if vix is None else vix >= 30
        rules = [
            _at_most(rsi, 30),
            _at_most(gap, -10),
            vix_high,
            _at_most(sigma5, -2.5),
            None if cluster is None else cluster >= 3,
            None if ratio is None else vix_high and _at_most(ratio, 0.7),
        ]
        score = None if None in rules else sum(rules)
        crossed3 = score is not None and previous_score is not None and previous_score < 3 <= score
        crossed4 = score is not None and previous_score is not None and previous_score < 4 <= score
        if crossed3:
            candidates["≥3"].append(i)
        if crossed4:
            candidates["≥4"].append(i)

        if active and score is not None and score >= 4:
            last_strong = i
        if active and i - last_strong >= 252:
            active = False
        if recovery_live and basket is not True:
            recovery_live = False

        event_kind = None
        if crossed4 and not active:
            active, witnessed_below, recovery_live = True, False, False
            setup_date, recovery_date, last_strong = day_date, None, i
            event_kind = "washout"
        elif crossed3 and score == 3 and not active:
            event_kind = "watch"
        if active:
            if basket is False:
                witnessed_below = True
            if basket is None:
                # A gap makes any unobserved crossing impossible to date.
                witnessed_below = False
            if witnessed_below and basket is True and previous_above is False and day_date != setup_date:
                active, recovery_live = False, True
                recovery_date = day_date
                event_kind = "recovery"
                candidates["Erholung"].append(i)

        if score is None:
            phase = "unknown"
        elif active or score >= 4:
            phase = "washout"
        elif score == 3:
            phase = "watch"
        elif recovery_live:
            phase = "recovery"
        else:
            phase = "idle"
        if event_kind:
            events.append({
                "date": day_date, "kind": event_kind, "score": score,
                "setup_date": None if event_kind == "watch" else setup_date,
            })
        day.update({
            "date": day_date, "rules": rules, "score": score, "rsi": rsi,
            "spx_gap": gap, "sigma": sigma, "sigma5": sigma5, "cluster": cluster,
            "rv20": rv20, "vol_ratio": ratio, "sma": sma, "above": above,
            "phase": phase, "setup_date": setup_date, "recovery_date": recovery_date,
            "setup_active": active, "recovery_live": recovery_live,
        })
        timeline.append(day)
        previous_date, previous_spx, previous_vix = day_date, spx, vix
        previous_score, previous_above = score, basket

    summary, episodes = _backtest(timeline, candidates)
    return {
        "last": timeline[-1] if timeline else None, "timeline": timeline,
        "events": events, "backtest": summary, "backtestEpisodes": episodes, "method": METHODOLOGY.copy(),
    }

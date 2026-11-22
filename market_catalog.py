"""Shared, offline-readable research view for the 34 indicators."""
from html import escape
from math import isfinite

REPORT_URL = "https://ai.22vresearch.com/reports/when-stocks-break-and-yields-rise-reading-the-cross-asset-risk-monitor/"
VIDEO_URL = "https://www.youtube.com/watch?v=nMoiy-Mba_4&t=1380s"

READINGS = {
    "high_yield": "Verlangen Käufer riskanter Unternehmensanleihen mehr Entschädigung für Ausfälle?",
    "ig": "Erfasst der Finanzierungsdruck auch Unternehmen mit guter Bonität?",
    "credit_quality": "Weitet sich der Risikoaufschlag der schwächsten Schuldner überproportional aus?",
    "liquid_credit": "Geraten liquide Hochzinsfonds relativ zu Anleihen guter Bonität unter Verkaufsdruck?",
    "loans": "Ziehen Anleger kurzfristig sichere US-Staatspapiere gegenüber Unternehmenskrediten vor?",
    "regional": "Verlieren zinssensitive Regionalbanken gegenüber dem breiten Markt an Boden?",
    "vix": "Wie viel Schwankung preisen S&P-500-Optionen für die nächsten 30 Tage ein?",
    "vvix": "Wie teuer wird die Absicherung gegen Sprünge im VIX selbst?",
    "short_vol": "Konzentriert sich der Absicherungsbedarf besonders auf die nächsten neun Tage?",
    "front_curve": "Ist kurzfristige Absicherung inzwischen teurer als dreimonatige?",
    "back_curve": "Reicht der Absicherungsdruck bis in den Bereich zwischen drei und sechs Monaten?",
    "tech_vol": "Wie stark ist die erwartete Schwankung im technologielastigen Nasdaq-100?",
    "skew": "Wie teuer bewertet der Optionsmarkt besonders ungünstige S&P-500-Ausgänge?",
    "cor1m": "Erwarten die Optionsmärkte, dass große Aktien stärker gemeinsam schwanken?",
    "cor_shock": "Steigt die erwartete kurzfristige Korrelation schneller als die längerfristige?",
    "sector_corr": "Wie viel Diversifikation bleibt zwischen den elf US-Aktiensektoren?",
    "dispersion": "Wie groß ist das gemeinsame Indexrisiko relativ zur erwarteten Streuung zwischen Einzelaktien?",
    "breadth_down": "Wie viele Sektoren erfasst der Verkauf gleichzeitig?",
    "move": "Wie stark schwanken laut Optionspreisen die erwarteten US-Staatsanleiherenditen?",
    "cross_vol": "Liegt der Stress im Verhältnis zum Aktienmarkt besonders stark im Anleihemarkt?",
    "long_bond_vol": "Wie nervös ist speziell der Markt für langlaufende US-Staatsanleihen?",
    "real_yields": "Wie schnell verändert sich der reale Diskontsatz für künftige Unternehmensgewinne?",
    "curve_vol": "Wie stark verändert sich die Steigung der Zinskurve von Tag zu Tag?",
    "equal": "Trägt die typische S&P-500-Aktie die Marktbewegung mit?",
    "small": "Halten kleinere, häufig finanzierungsabhängigere Firmen mit den großen mit?",
    "momentum": "Bleiben die bisherigen Kursgewinner relativ stabil, oder lösen Anleger diese Positionen auf?",
    "cyclical": "Bevorzugen Anleger zyklischen Konsum oder defensive Basiskonsumgüter?",
    "sector_sma": "Wie viele US-Sektoren haben ihren langfristigen Aufwärtstrend erhalten?",
    "high_beta": "Fließt Kapital aus besonders marktsensitiven Aktien in Qualitätsaktien?",
    "bitcoin": "Zeigt der Bitcoin-Markt zum US-Handelsschluss steigende oder fallende Risikobereitschaft?",
    "copper_gold": "Wie entwickelt sich zyklisches Industriemetall relativ zum defensiven Gold?",
    "dollar": "Verteuert ein stärkerer US-Dollar die Finanzierung für internationale Dollarschuldner?",
    "em": "Lassen Anleger Aktien aus Schwellenländern relativ zu US-Aktien fallen?",
    "stock_bond": "Bewegen sich US-Staatsanleihen und Aktien so ähnlich, dass der Diversifikationseffekt sinkt?",
}

STYLE = """
.mw34{color:#20372f;font:15px/1.5 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.mw34 h2,.mw34 h3,.mw34 p,.mw34 dl,.mw34 dd{margin:0}
.mw34 a{color:#146349;text-underline-offset:3px}
.mw34 .m-head{display:flex;justify-content:space-between;align-items:baseline;gap:16px}
.mw34 .m-head time{font-size:13px;white-space:nowrap;color:#52665d}
.mw34 h2{font:normal clamp(25px,3.2vw,36px)/1.15 Georgia,serif;letter-spacing:-.03em}
.mw34 .m-deck,.mw34 .m-copy{color:#435b50;margin-top:9px;text-wrap:pretty}
.mw34 .m-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:20px 0 12px;padding:15px 0;border-block:1px solid #cfd9ce}
.mw34 .m-summary>div{padding:0 12px;border-left:1px solid #dce3da}
.mw34 .m-summary>div:first-child{padding-left:0;border:0}
.mw34 .m-summary dt{font-size:12px;color:#506259}.mw34 .m-summary dd{font-size:23px;font-weight:650;font-variant-numeric:tabular-nums}
.mw34 .m-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(145px,100%),1fr));gap:6px;margin:16px 0}
.mw34 .m-tiles a{padding:8px;border:1px solid #dce3d8;border-radius:5px;display:grid;gap:2px;align-content:space-between;text-decoration:none;color:#283e32}
.mw34 .m-tiles a:hover{border-color:#80a68d}.mw34 .m-tiles span{font-size:12px}.mw34 .m-tiles b{font-size:17px}
.mw34 .m-tiles svg{width:100%;height:29px;display:block}.mw34 .m-pills{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}
.mw34 .m-pills a{border:1px solid #cdd8ce;border-radius:20px;padding:3px 10px;font-size:13px;text-decoration:none}
.mw34 .m-pills a:hover{background:#e4eee4}
.mw34 .m-group{margin-top:22px;scroll-margin-top:14px}
.mw34 .m-group-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:9px 12px;background:#eaf1e8;border-block:1px solid #d3ded2}
.mw34 h3{font:600 17px/1.3 Inter,-apple-system,sans-serif}.mw34 .m-group-state{font:13px/1.4 Inter,sans-serif;color:#3d564a;text-align:right}
.mw34 .m-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(90px,auto) minmax(90px,auto);gap:12px;padding:11px 12px;border-bottom:1px solid #e0e6dd;align-items:start}
.mw34 .m-name{font-weight:650}.mw34 .m-note{font-size:13px;color:#4d6255;margin-top:2px}
.mw34 .m-dim{font-size:11px;text-transform:uppercase;letter-spacing:.035em;color:#586d61}
.mw34 .m-value,.mw34 .m-state{font-variant-numeric:tabular-nums;text-align:right}.mw34 .m-value{font-weight:600}
.mw34 .m-unit{font-weight:400}.mw34 .m-state{font-size:13px}.mw34 .m-state strong{display:block}
.mw34 .m-missing{color:#6c7068}.mw34 .m-red{color:#a1412c}.mw34 .m-amber{color:#886211}.mw34 .m-green{color:#196447}
.mw34 .m-origin{display:inline-block;font-size:11px;vertical-align:middle;font-weight:500;border:1px solid #d5ded3;padding:0 5px;border-radius:4px;margin-left:5px;color:#4c6054}
.mw34 .m-row details{font-size:12px;color:#495d52;margin-top:3px}.mw34 details summary{cursor:pointer;color:#226346;min-height:0;font-size:12px;font-weight:normal;list-style:revert;padding:0}
.mw34 .m-row details p{margin:3px 0}.mw34 .m-method{margin-top:8px}.mw34 .m-method summary{cursor:pointer;color:#196447;font-size:13px}.mw34 .m-sources{margin:16px 0 0;font-size:13px;color:#52665d}
.mw34 .m-sources a{white-space:normal}.mw34 .m-copy{font-size:13px;line-height:1.55}
@media(max-width:700px){.mw34 .m-summary{grid-template-columns:repeat(2,1fr);row-gap:9px}.mw34 .m-summary>div:nth-child(3){padding-left:0;border-left:0}
.mw34 .m-head{display:block}.mw34 .m-head time{display:block;margin-top:5px}.mw34 .m-row{grid-template-columns:minmax(0,1fr) auto;gap:6px;padding:10px 4px}
.mw34 .m-meta{grid-row:1/3}.mw34 .m-value,.mw34 .m-state{grid-column:2}.mw34 .m-state strong{display:inline}.mw34 .m-state strong:after{content:' · '}.mw34 .m-dim{font-size:10px}.mw34 .m-origin{margin-left:0;margin-right:3px}.mw34 .m-group-head{align-items:center}}
@media print{.mw34 .m-pills,.mw34 details{display:none}.mw34 .m-row,.mw34 .m-group-head{break-inside:avoid}}
"""


def esc(value):
    return escape(str(value), quote=True)


def fmt(value, digits=2, signed=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return "–"
    sign = "+" if signed and value > 0 else ""
    return sign + f"{value:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".").replace("-", "−")


def date_de(value):
    if isinstance(value, str) and len(value) == 10:
        return ".".join(reversed(value.split("-")))
    return "–"


def source_link(label, url):
    if not isinstance(url, str) or not url.startswith("https://"):
        return esc(label)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>'


def _spark(points):
    if not isinstance(points, list):
        return ""
    values = [n for n in points if isinstance(n, (float, int)) and isfinite(n)]
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    parts, ready = [], False
    for i, n in enumerate(points):
        if not isinstance(n, (float, int)) or not isfinite(n):
            ready = False
            continue
        x = 1 + i * 160 / max(1, len(points) - 1)
        y = 14 if hi == lo else 2 + 24 * (hi - n) / (hi - lo)
        parts.append(f"{'L' if ready else 'M'}{x:.1f},{y:.1f}")
        ready = True
    return ('<svg viewBox="0 0 162 28" preserveAspectRatio="none" role="img" aria-label="Verlauf der Säule">'
            '<path stroke="#46765a" stroke-width="1.6" vector-effect="non-scaling-stroke" fill="none" d="'
            + ' '.join(parts) + '"/></svg>')


def _metric(label, value):
    return f'<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>'


def _indicator(row):
    status = row.get("status") or "Daten fehlen"
    state = {"Alarm": "m-red", "Beobachten": "m-amber", "Risikoappetit": "m-green"}.get(status, "")
    if row.get("score") is None:
        state = "m-missing"
    links = [source_link(s["name"], s.get("url")) for s in row.get("sources", []) if s.get("name")]
    sources = " · ".join(links)
    raw = row.get("raw")
    formatted = fmt(raw, 4 if isinstance(raw, (int, float)) and 0 < abs(raw) < 0.1 else 2)
    provenance = esc(row.get("evidence") or "")
    note = " ".join(str(row[k]) for k in ("evidence_note", "implementation") if row.get(k))
    return (
        '<div class="m-row"><div class="m-meta"><span class="m-name">' + esc(row["name"])
        + '</span> <span class="m-origin">' + provenance + '</span>'
        + '<p class="m-note">' + esc(row.get("formula", "")) + '</p>'
        + '<details><summary>Herkunft und Datenquellen</summary><p>' + esc(note)
        + '</p><p>' + esc(READINGS.get(row['id'], '')) + ' ' + esc(row.get('direction', '')) + '.</p><p>' + sources + '</p></details></div><div class="m-value">'
        + formatted + ' <span class="m-unit">' + (esc(row.get("unit") or "") if raw is not None else "")
        + '</span><div class="m-dim">' + esc(date_de(row.get("as_of"))) + '</div></div>'
        + '<div class="m-state ' + state + '"><strong>' + esc(status) + '</strong>'
        + fmt(row.get("score"), 2, True) + ' σ</div></div>'
    )


def render_context(ctx):
    start = '<section id="context" class="mw34 card inset section">'
    if not ctx or not ctx.get("indicators"):
        return (start + '<h2>34 Marktindikatoren</h2><p class="m-deck">Für diese Sitzung fehlen die Zusatzdaten. '
                'Die datierte Übersicht im ZIP lässt sich über Indikatoren.html öffnen.</p></section>')
    rows, summary = ctx["indicators"], ctx["summary"]
    date = esc(date_de(ctx.get("as_of")))
    partial = summary.get("composite") is None and summary.get("partial_composite") is not None
    observed = sum(ind.get("evidence") == "Auf der Folie erkennbar" for ind in rows)
    introduction = (f"{observed} Kennzahlen sind in Vissers Wochenbericht erkennbar. " +
                    f"{len(rows) - observed} weitere ergänzen die sechs Marktbereiche. Je negativer der Score, desto höher der Stress.")
    html = [start, '<div class="m-head"><h2>34 Marktindikatoren</h2><time>' + date + '</time></div>',
            '<p class="m-deck">' + esc(introduction) + '</p>',
            '<dl class="m-summary">',
            _metric("Teilscore" if partial else "Gesamtscore", fmt(summary.get("partial_composite") if partial else summary.get("composite"), 2, True)),
            _metric("Aktuelle Werte", str(summary.get("coverage", 0)) + " / 34"),
            _metric("Im Stressbereich", str(summary.get("flashing", 0)) if summary.get("coverage") else "–"),
            _metric("Unter Beobachtung", str(summary.get("watch", 0)) if summary.get("coverage") else "–"), '</dl>']
    if summary.get("full_session") and summary["full_session"] != ctx.get("as_of"):
        html.append('<p class="m-copy"><strong>Letzter vollständiger Stand · ' + esc(date_de(summary["full_session"]))
                    + '</strong> · Gesamtscore ' + fmt(summary.get("full_composite"), 2, True)
                    + ' σ · ' + esc(summary.get("full_flashing", "–")) + ' von 34 im Stressbereich.</p>')
    if summary.get("correlation") is not None:
        html.append('<p class="m-copy">Mittlere Korrelation über 60 Handelstage <strong>'
                    + fmt(summary['correlation']) + '</strong> · ' + esc(summary.get('correlation_pairs', 0))
                    + ' auswertbare Indikatorpaare.</p>')
    html.append('<details class="m-method"><summary>Wie werden Stress, Teilscore und Korrelation berechnet?</summary>'
                + '<p class="m-copy">' + esc(ctx.get("method") or "") + '</p></details>')
    groups = list(dict.fromkeys(row["pillar"] for row in rows))
    cards = {c["name"]: c for c in ctx.get("items", [])}
    html.append('<nav class="m-tiles" aria-label="Marktbereiche">')
    for i, name in enumerate(groups):
        card = cards.get(name, {})
        html.append(f'<a href="#mw-pillar-{i}"><span>{esc(name)}</span><b>'
                    + esc(card.get("value", "–")) + '</b>' + _spark(card.get("spark")) + '</a>')
    html.append('</nav>')
    for i, group in enumerate(groups):
        members = [row for row in rows if row["pillar"] == group]
        card = cards.get(group, {})
        details = str(card.get("value", "")) + (" · " + card["note"] if card.get("note") else "")
        html.append(f'<section class="m-group" id="mw-pillar-{i}"><div class="m-group-head"><h3>'
                    + esc(group) + f' ({len(members)})</h3><span class="m-group-state">'
                    + esc(details) + '</span></div>')
        html.extend(_indicator(row) for row in members)
        html.append('</section>')
    html.append('<p class="m-sources">Quellen zur Auswahl und Einordnung · '
                + source_link('Jordi Vissers Video', VIDEO_URL) + ' · '
                + source_link('22V Research, Bericht vom 19.11.2026 (Anmeldung)', REPORT_URL)
                + ' · ' + source_link('Cboe – Volatilitätslaufzeiten', 'https://www.cboe.com/tradable-products/vix/term-structure')
                + ' · ' + source_link('Cboe – implizite Korrelation', 'https://www.cboe.com/us/indices/implied')
                + ' · ' + source_link('Office of Financial Research – Stressindikatoren', 'https://www.financialresearch.gov/financial-stress-index/')
                + '. Die Zuordnung einzelner Kennzahlen zu den Säulen ist teilweise rekonstruiert. Die Spalte zur Herkunft bezieht sich auf die Auswahl der Kennzahl. '
                'Für die Standardisierung und das Zusammenfassen der Tageswerte gilt die hier beschriebene Berechnung.</p></section>')
    return ''.join(html)


def standalone(ctx):
    return ('<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>34 Marktindikatoren · Market Watch</title><style>*{box-sizing:border-box}body{margin:0;background:#f5f5ef}'
            'main{width:min(1060px,calc(100% - 28px));margin:30px auto;padding:clamp(12px,4vw,40px);background:#fffffc;border:1px solid #d8dfd5;border-radius:10px}'
            '.mark{font:600 15px/1.4 system-ui;color:#38654c;margin-bottom:14px}'
            + STYLE + '</style><main><div class="mark">Market Watch · Tagesansicht</div>'
            + render_context(ctx) + '<p class="mw34 m-copy">Gespeicherte Momentaufnahme. Aktuelle Tageswerte öffnest du über Start.command im ZIP.</p></main></html>')

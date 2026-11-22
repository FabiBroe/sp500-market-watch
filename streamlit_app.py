"""Browser-first deployment of the original S&P 500 Market Watch engine."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from market_watch import dashboard, snapshot

st.set_page_config(
    page_title="Market Watch | S&P-500-Bodenwächter",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container {max-width: 1450px; padding-top: 1.25rem; padding-bottom: 1rem;}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stVerticalBlock"] > div {min-width: 0;}
</style>
""", unsafe_allow_html=True)

st.title("S&P 500 · Market Watch")
st.caption("Cloud-Dashboard | Washout-Score (6 Bedingungen) + Trendbestätigung + 34 Cross-Asset-Kennzahlen")

CACHE_DIR = Path(os.environ.get("MARKETWATCH_CACHE_DIR", "/tmp/sp500_market_watch_cloud"))

@st.cache_data(ttl=1800, show_spinner=False)
def get_snapshot(with_context: bool, refresh_token: int):
    # The underlying stdlib-only code obtains EOD histories on the server.
    # Refresh token invalidates Streamlit's view cache without bypassing source checks.
    _ = refresh_token
    return snapshot(CACHE_DIR, refresh=True, with_context=with_context)

if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = 0

control_col, context_col, right_col = st.columns([1.1, 1.5, 3.2], vertical_alignment="center")
with control_col:
    if st.button("↻ Daten neu laden", use_container_width=True, type="primary"):
        st.session_state.refresh_token += 1
        st.cache_data.clear()
        st.rerun()
with context_col:
    load_34 = st.checkbox("34 Marktindikatoren laden", value=True)
with right_col:
    st.caption("Quellen: Cboe, FRED, Yahoo Finance | US-Handelsschlüsse; verzögerte Daten werden gekennzeichnet")

try:
    with st.spinner("Hole Schlusskurse und berechne Signale. Die erste Abfrage der 34 Indikatoren kann länger dauern …"):
        result = get_snapshot(load_34, st.session_state.refresh_token)
except Exception as exc:
    st.error("Der Datenabruf oder die Berechnung ist fehlgeschlagen. Es wird kein erfundener Signalwert angezeigt.")
    st.code(f"{type(exc).__name__}: {exc}")
    st.info("Bitte später erneut versuchen. Einzelne Datenquellen können zeitweise blockieren oder verzögert liefern.")
    st.stop()

meta = result.get("meta", {})
last = result.get("last") or {}
expected = meta.get("expected_session")
latest = meta.get("latest_by_asset", {})
score = last.get("score")

if not meta.get("fresh"):
    st.warning(
        f"Kursstand noch nicht vollständig aktuell. Erwartete US-Sitzung: {expected or 'unbekannt'}. "
        f"Letzte Abschlüsse: " + ", ".join(f"{k.upper()}: {v or 'fehlt'}" for k, v in latest.items())
        + ". Keine ungeprüften aktuellen Alarme."
    )
if not load_34:
    st.info("Der 34-Indikatoren-Bereich ist ausgeschaltet, um den Abruf zu beschleunigen. "
            "Die sechs Washout-Regeln und der Trendcheck bleiben aktiv.")
elif "context" not in result:
    st.warning("Die Zusatzindikatoren konnten nicht geladen werden; der Kernwächter bleibt unabhängig.")

report_html = dashboard(result)
# Non-embedded streamlit apps have no /refresh endpoint; the refresh button sits above the iframe.
# Keep the original JS charts / per-indicator provenance / methodological details intact.
report_html = report_html.replace('href="/refresh"', 'href="#"')
components.html(report_html, height=2250 if load_34 else 1420, scrolling=True)

with st.expander("Datenexport und Diagnostik"):
    a, b = st.columns(2)
    with a:
        st.download_button("HTML-Bericht herunterladen", report_html, file_name="SP500-Market-Watch-Bericht.html",
                           mime="text/html", use_container_width=True)
    with b:
        export = {key: result.get(key) for key in ("last", "events", "backtest", "meta", "context")}
        st.download_button("Daten als JSON herunterladen", json.dumps(export, ensure_ascii=False, indent=2, allow_nan=False),
                           file_name="SP500-Market-Watch-Daten.json", mime="application/json",
                           use_container_width=True)
    st.json({"expected_session": expected, "latest_by_asset": latest, "washout_fresh": meta.get("washout_fresh"),
             "trend_fresh": meta.get("trend_fresh"), "current_score": score, "data_sources": meta.get("sources")})

st.caption("Der Score erkennt außergewöhnlichen Verkaufsdruck, nicht den exakten Tiefpunkt. "
           "Die 34er-Rekonstruktion enthält eigene Indikatoren und ist nicht Vissers proprietäre Berechnung. "
           "Die Seite aktualisiert beim Öffnen bzw. auf Knopfdruck; sie sendet keine eigenen Push-Nachrichten.")

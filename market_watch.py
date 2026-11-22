"""S&P 500 Market Watch. Python 3.9+, local browser or one-shot CLI."""
import argparse
import json
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from context_panel import context_panel
from engine import analyze
from market_catalog import STYLE as CONTEXT_STYLE, render_context
from feeds import load_market_data

BASE = Path(__file__).resolve().parent
DEFAULT_CACHE = Path.home() / ".market-watch-sp500" / "v1"


def snapshot(cache_dir, refresh=True, with_context=True):
    rows, meta = load_market_data(cache_dir, refresh=refresh)
    result = analyze(rows)
    latest = meta.get("latest_by_asset", {})
    expected = meta["expected_session"]
    last = result["last"] or {}
    result["meta"] = dict(
        meta, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        washout_fresh=last.get("score") is not None and all(latest.get(k) == expected for k in ("spx", "vix")),
        trend_fresh=all(latest.get(k) == expected for k in ("spx", "qqq", "iwm"))
                   and all(last.get("above", {}).get(k) is not None for k in ("spx", "qqq", "iwm")),
    )
    # Optional markets must never prevent evaluation of the two core signals.
    if with_context:
        try:
            result["context"] = context_panel(rows, cache_dir, refresh)
        except (OSError, ValueError, RuntimeError) as exc:
            result["meta"]["warnings"].append("Zusatzdaten für den Marktvergleich fehlen. " + str(exc))
    return result


def dashboard(result):
    kinds = {"≥3": "watch", "≥4": "washout", "Erholung": "recovery"}
    recoveries = {event["setup_date"]: event["date"] for event in result["events"]
                  if event["kind"] == "recovery"}
    episodes = [
        dict(row, kind=kinds[row["group"]],
             endDate=recoveries.get(row["date"]) if row["group"] == "≥4" else None)
        for row in result.get("backtestEpisodes", [])
    ]
    # Only chart series travel to the browser. Keep last day's complete diagnostics.
    chart = [{"date": day["date"], "spx": day["spx"], "score": day["score"],
              "sma": {"spx": round(day["sma"]["spx"], 3) if day["sma"]["spx"] else None}}
             for day in result["timeline"]]
    payload = {k: result[k] for k in ("last", "events", "method", "backtest", "meta")}
    payload.update(timeline=chart, episodeRows=episodes, context=result.get("context"))
    quotes = {"spx": "%5EGSPC", "vix": "%5EVIX", "qqq": "QQQ", "iwm": "IWM"}
    sources = {}
    for key, label in result["meta"].get("sources", {}).items():
        url = None
        if label == "Cboe" and key in ("spx", "vix"):
            url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/" + key.upper() + "_History.csv"
        elif label == "FRED" and key in ("spx", "vix"):
            url = "https://fred.stlouisfed.org/series/" + ("SP500" if key == "spx" else "VIXCLS")
        elif label == "Yahoo Finance" and key in quotes:
            url = "https://finance.yahoo.com/quote/" + quotes[key] + "/history/"
        sources[key] = {"name": label, "url": url}
    payload["meta"] = dict(result["meta"], sources=sources)
    encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"), ensure_ascii=False)
    # Preserve arbitrary labels inside the script element as data.
    encoded = encoded.replace("&", r"\u0026").replace("<", r"\u003c").replace(">", r"\u003e")
    template = (BASE / "dashboard.html").read_text(encoding="utf-8")
    return (template.replace("__CONTEXT_STYLE__", CONTEXT_STYLE)
            .replace("__CONTEXT_BLOCK__", render_context(result.get("context")))
            .replace("__MARKET_DATA__", encoded))


def loading_page(error=None):
    from html import escape
    if error:
        status = "<p>" + escape(error) + "</p><a href='/refresh'>Erneut versuchen</a>"
        autoswitch = ""
    else:
        status = "<p>US-Schlusskurse werden geladen und die sechs Regeln berechnet …</p>"
        autoswitch = '<meta http-equiv="refresh" content="3">'
    return ("<!doctype html><html lang='de'><meta charset='utf-8'>" + autoswitch
            + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            + "<title>S&amp;P 500 · Market Watch</title><style>"
            + "body{margin:12vh auto;max-width:36rem;padding:24px;background:#f8f8f4;color:#153331;"
            + "font:17px/1.6 system-ui}h1{font:600 48px/1.1 Georgia,serif}a{color:#176e65}"
            + "</style><h1>S&amp;P 500<br>Market Watch</h1>" + status + "</html>")


class ReportState:
    def __init__(self, cache_dir, offline=False):
        self.cache_dir = cache_dir
        self.offline = offline
        self.lock = threading.Lock()
        self.busy = False
        self.last_attempt = 0
        self.html = None
        self.error = None

    def start(self):
        with self.lock:
            if self.busy or time.monotonic() - self.last_attempt < 5:
                return
            self.busy = True
            self.last_attempt = time.monotonic()
        threading.Thread(target=self.build, daemon=True).start()

    def build(self):
        try:
            page = dashboard(snapshot(self.cache_dir, refresh=not self.offline))
        except Exception as exc:
            with self.lock:
                self.error = "Die Daten konnten nicht verarbeitet werden. " + str(exc)
                self.busy = False
            print(self.error, file=sys.stderr, flush=True)
            return
        with self.lock:
            self.html = page
            self.error = None
            self.busy = False


def serve(cache_dir, offline, open_browser):
    state = ReportState(cache_dir, offline)

    class ReportHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            host = self.headers.get("Host", "")
            local = f"127.0.0.1:{self.server.server_port}"
            if host != local:
                self.send_error(403)
                return
            if self.path == "/refresh":
                state.start()
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if self.path != "/":
                self.send_error(404)
                return
            with state.lock:
                page = (loading_page() if state.busy else
                        loading_page(state.error) if state.error else state.html or loading_page())
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    with ThreadingHTTPServer(("127.0.0.1", 0), ReportHandler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print("Market Watch läuft unter " + url, flush=True)
        print("Zum Beenden dieses Terminalfenster schließen oder Strg+C drücken.", flush=True)
        state.start()
        if open_browser:
            threading.Timer(0.25, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description="S&P 500 Market Watch")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Aktuellen Stand und Ereignisse als JSON ausgeben.")
    mode.add_argument("--report", type=Path, metavar="HTML", help="Eigenständigen HTML-Bericht speichern.")
    parser.add_argument("--context", action="store_true", help="Bei --check auch die 34 Marktindikatoren ausgeben.")
    parser.add_argument("--offline", action="store_true", help="Nur den lokalen Kurszwischenspeicher verwenden.")
    parser.add_argument("--no-browser", action="store_true", help="Browser beim Start geschlossen lassen.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="Alternatives Datenverzeichnis.")
    args = parser.parse_args()
    if args.context and not args.check:
        parser.error("--context gehört zu --check.")
    if not args.check and args.report is None:
        serve(args.cache_dir, args.offline, not args.no_browser)
        return
    result = snapshot(args.cache_dir, refresh=not args.offline, with_context=not args.check or args.context)
    if args.check:
        fields = {k: result[k] for k in ("meta", "last", "events", "backtest")}
        if args.context:
            fields["context"] = result.get("context")
        print(json.dumps(fields,
                         ensure_ascii=False, allow_nan=False, indent=2))
    else:
        args.report.write_text(dashboard(result), encoding="utf-8")
        print(args.report.resolve())
    if result["last"] is None or result["last"]["score"] is None or not result["meta"]["fresh"]:
        sys.exit(2)


if __name__ == "__main__":
    main()

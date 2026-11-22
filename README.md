# S&P 500 Market Watch – Browser-Version

Diese Version übernimmt die Originalberechnungen aus dem bestehenden Market-Watch-Paket.
**Auf deinem Mac ist keine Python-Installation nötig.** Python läuft bei Streamlit Community Cloud.

## Online bringen (im Browser)

1. ZIP herunterladen und entpacken.
2. Auf https://github.com/new ein neues Repository erstellen, z. B. `sp500-market-watch`. Privat ist möglich, sofern Streamlit Zugriff darauf erhält.
3. Im Repository **Add file → Upload files** wählen. Den **Inhalt** von `MarketWatch-Browser` hochladen: `streamlit_app.py`, die sechs Python-Module, `dashboard.html`, `requirements.txt`, `README.md` und den Ordner `.streamlit` (falls der Upload versteckte Ordner nicht unterstützt, kann er entfallen). Darauf achten, dass `streamlit_app.py` im Hauptverzeichnis des Repositories liegt.
4. Auf https://share.streamlit.io anmelden (mit GitHub), **Create app → Deploy a public app from GitHub / Yup, I have an app**.
5. Repository und Branch `main` wählen. **Main file path:** `streamlit_app.py`. **Deploy** klicken.
6. Die erzeugte `*.streamlit.app`-Adresse im Browser öffnen und als Lesezeichen speichern.

Das Hosting ist laut Streamlit Community Cloud kostenlos, kann aber Ressourcengrenzen, Inaktivitätspausen und Zugriffsregeln haben. Für ein privates Repo GitHub-Verbindung/Zugriffsrechte prüfen.

## Bedienung

- Standardmäßig lädt das Dashboard den Washout-Score, die Trendbestätigung und 34 weitere Marktindikatoren.
- Mit **Daten neu laden** aktuelle verfügbare US-Schlusskurse anfordern. Der Server zwischenspeichert Abrufe für bis zu 30 Minuten; die ursprünglichen Quellen können verzögert sein.
- Den 34er-Vergleich zeitweilig ausschalten, wenn einzelne Datenquellen langsam sind.
- Die historischen Signale anklicken und die Berichte als HTML oder JSON herunterladen.
- Fehlende Kurse erscheinen mit Datenstand/Warnung, nicht als Schätzung.

## Wichtige Grenzen

- **Noch keine öffentliche URL**: Die Adresse entsteht erst durch deinen einmaligen Deploy in deinem GitHub/Streamlit-Account.
- Streamlit verschickt mit diesem Paket keine Push-Warnungen. Eine bereits bestehende ChatGPT-Watch-Aufgabe kann unabhängig davon arbeiten.
- Nur real verfügbare historische EOD-Kurse, keine garantierte Echtzeitversorgung.
- Zehn von Vissers 34 Kennzahlen sind auf den gezeigten Folien erkennbar, 24 sind eigene Ergänzungen. Berechnung, Z-Werte und Gewichtung sind eine Rekonstruktion.
- Kein Versprechen eines exakten Markttiefs und keine Anlageberatung.

Quellen: https://www.cboe.com/, https://fred.stlouisfed.org/, https://finance.yahoo.com/

## Falls später lokal verwendet

`pip install -r requirements.txt && streamlit run streamlit_app.py`

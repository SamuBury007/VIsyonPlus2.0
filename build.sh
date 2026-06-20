#!/usr/bin/env bash
set -e
pip install -r requirements.txt

# Installa dipendenze di sistema senza sudo (già disponibili su Render)
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/.cache/ms-playwright

# Scarica solo il browser, senza tentare install-deps
playwright install chromium

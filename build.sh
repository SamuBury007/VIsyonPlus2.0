#!/usr/bin/env bash
set -e

echo "[build] Installazione dipendenze Python..."
pip install -r requirements.txt

echo "[build] Installazione Chromium per Playwright..."
playwright install chromium

echo "[build] Done."

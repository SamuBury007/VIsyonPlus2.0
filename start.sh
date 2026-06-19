#!/bin/bash

# Installa Playwright e i browser
pip install -r requirements.txt
playwright install chromium
playwright install-deps

# Avvia l'applicazione
python main.py

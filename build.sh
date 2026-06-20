#!/usr/bin/env bash
set -e

export PLAYWRIGHT_BROWSERS_PATH=/opt/render/.cache/ms-playwright

pip install -r requirements.txt
playwright install chromium

#!/bin/bash
# Script de configuración inicial para Linux/VPS
echo "🚀 Iniciando configuración de entorno virtual..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
chmod +x run_bot.sh
echo "✅ Configuración lista. Usa ./run_bot.sh para iniciar el bot."

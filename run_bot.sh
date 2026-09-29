#!/bin/bash
# Script para ejecutar el bot de forma segura en Linux/VPS
source .venv/bin/activate
python3 amazon_deal_bot.py --schedule --headless

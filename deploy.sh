#!/bin/bash
# Script de deployment para GangasMX VPS
# Uso: ./deploy.sh

set -e  # Exit on error

echo "==============================================="
echo "🚀 DEPLOYMENT SCRIPT - GangasMX"
echo "==============================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para logging
log_step() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# PASO 1: Crear backups
echo ""
echo "PASO 1: Crear backups de estado actual..."
BACKUP_SUFFIX=$(date +%Y%m%d_%H%M%S)

if [ -f "products_list.json" ]; then
    cp products_list.json "products_list.json.backup.$BACKUP_SUFFIX"
    log_step "Backup de products_list.json"
else
    log_warning "products_list.json no encontrado"
fi

if [ -f "published_history.json" ]; then
    cp published_history.json "published_history.json.backup.$BACKUP_SUFFIX"
    log_step "Backup de published_history.json"
else
    log_warning "published_history.json no encontrado"
fi

if [ -f "user_state.json" ]; then
    cp user_state.json "user_state.json.backup.$BACKUP_SUFFIX"
    log_step "Backup de user_state.json"
else
    log_warning "user_state.json no encontrado"
fi

# PASO 2: Detener scheduler
echo ""
echo "PASO 2: Detener scheduler si está corriendo..."
if pgrep -f "amazon_deal_bot.py --schedule" > /dev/null; then
    pkill -f "amazon_deal_bot.py --schedule"
    log_step "Scheduler detenido"
    sleep 2
else
    log_warning "Scheduler no estaba corriendo"
fi

# PASO 3: Actualizar código
echo ""
echo "PASO 3: Actualizar código desde origin/master..."
git fetch origin
if git diff origin/master HEAD --quiet; then
    log_step "Código ya está actualizado"
else
    git pull origin master || log_error "Error al hacer git pull"
    log_step "Código actualizado"
fi

# PASO 4: Verificar compilación
echo ""
echo "PASO 4: Verificar que los archivos críticos compilan..."
python3 -m py_compile core/scheduler.py || log_error "Error compilando scheduler.py"
log_step "scheduler.py compila OK"

python3 -m py_compile publishers/facebook_publisher.py || log_error "Error compilando facebook_publisher.py"
log_step "facebook_publisher.py compila OK"

python3 -m py_compile core/telegram_bot.py || log_error "Error compilando telegram_bot.py"
log_step "telegram_bot.py compila OK"

# PASO 5: Verificar que la historia se carga
echo ""
echo "PASO 5: Verificar que la historia se carga correctamente..."
python3 << 'EOF'
import sys
try:
    from core.config import Config
    from core.storage import json_load

    history = json_load(Config.HISTORY_FILE, default=[])
    print(f"✅ Historia cargada: {len(history)} productos publicados")
    sys.exit(0)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    log_error "Error cargando historia"
fi
log_step "Historia OK"

# PASO 6: Reiniciar scheduler
echo ""
echo "PASO 6: Reiniciar scheduler..."

# Detectar cómo está siendo ejecutado
if systemctl is-active --quiet amazon_bot 2>/dev/null; then
    # Está en systemd
    sudo systemctl restart amazon_bot
    log_step "Scheduler reiniciado via systemd"
elif pgrep -f "screen.*amazon_bot" > /dev/null; then
    # Está en screen
    screen -S amazon_bot -X quit 2>/dev/null || true
    sleep 2
    screen -S amazon_bot -d -m python3 amazon_deal_bot.py --schedule
    log_step "Scheduler reiniciado via screen"
else
    # Usar nohup como fallback
    nohup python3 amazon_deal_bot.py --schedule > scheduler.log 2>&1 &
    log_step "Scheduler iniciado via nohup"
fi

sleep 3

# PASO 7: Verificar que scheduler está corriendo
echo ""
echo "PASO 7: Verificar que scheduler está corriendo..."
if pgrep -f "amazon_deal_bot.py --schedule" > /dev/null; then
    log_step "Scheduler está corriendo"
else
    log_error "Scheduler no inició"
fi

# PASO 8: Resumen
echo ""
echo "==============================================="
echo -e "${GREEN}✅ DEPLOYMENT COMPLETADO${NC}"
echo "==============================================="
echo ""
echo "Próximos pasos:"
echo "1. Monitorear logs: tail -f scheduler.log"
echo "2. Esperar al próximo slot (8, 10, 12, 14, 16, 18, 20, 22 hrs)"
echo "3. Verificar que se publica un producto SIN duplicados"
echo "4. Revisar Telegram notifications"
echo ""
echo "Cambios principales en este deployment:"
echo "- FIX #9 CRÍTICO: Historia se guarda a disco en cada slot"
echo "- FIX #5 IMPORTANTE: Validación consolidada"
echo "- P3-P5: Refactorización (23 métodos nuevos)"
echo ""
echo "Rollback si hay problemas:"
echo "  git reset --hard HEAD~1  # Revertir FIX #5"
echo "  git reset --hard HEAD~1  # Revertir FIX #9 (si aún hay problemas)"
echo ""

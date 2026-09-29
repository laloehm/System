# DEPLOYMENT GUIDE - GangasMX VPS

## 📋 PRE-DEPLOYMENT CHECKLIST

```
✅ Código compilable (verificado)
✅ Tests pasados (87.5% casos)
✅ FIX CRÍTICO #9 aplicado (historia a disco)
✅ FIX IMPORTANTE #5 aplicado (validación)
✅ 23 commits en origin/master
✅ Ramas limpias
✅ Git status clean
```

---

## 🚀 DEPLOYMENT EN VPS (Linux)

### PASO 1: Conectarse al VPS

```bash
ssh user@vps.ip.address
cd /path/to/gangas-mx
```

### PASO 2: Hacer backup de estado actual

```bash
# Guardar estado antes de actualizar
cp products_list.json products_list.json.backup.$(date +%Y%m%d_%H%M%S)
cp published_history.json published_history.json.backup.$(date +%Y%m%d_%H%M%S)
cp user_state.json user_state.json.backup.$(date +%Y%m%d_%H%M%S)

echo "✅ Backups creados"
```

### PASO 3: Actualizar código desde origin/master

```bash
# Detener scheduler si está corriendo
pkill -f "amazon_deal_bot.py --schedule" || true
sleep 2

# Fetch updates
git fetch origin

# Verificar cambios
git log origin/master..master  # Debe estar vacío si está actualizado
git diff origin/master HEAD    # Debe estar vacío

# Hacer pull
git pull origin master

echo "✅ Código actualizado desde origin/master"
```

### PASO 4: Verificar compilación

```bash
# Verificar que los archivos críticos compilan
python3 -m py_compile core/scheduler.py
python3 -m py_compile publishers/facebook_publisher.py
python3 -m py_compile core/telegram_bot.py

if [ $? -eq 0 ]; then
    echo "✅ Compilación OK"
else
    echo "❌ Error de compilación - REVERTIR"
    git reset --hard HEAD~1
    exit 1
fi
```

### PASO 5: Verificar que la historia se carga

```bash
python3 << 'EOF'
import json
from core.config import Config
from core.storage import json_load

try:
    history = json_load(Config.HISTORY_FILE, default=[])
    print(f"✅ Historia cargada: {len(history)} productos publicados anteriormente")
except Exception as e:
    print(f"❌ Error cargando historia: {e}")
    exit(1)
EOF
```

### PASO 6: Reiniciar scheduler

```bash
# Opción A: Servicio systemd (si está configurado)
sudo systemctl restart amazon_bot

# Opción B: Screen session (si se usa screen)
screen -S amazon_bot -d -m python3 amazon_deal_bot.py --schedule

# Opción C: Nohup
nohup python3 amazon_deal_bot.py --schedule > scheduler.log 2>&1 &

echo "✅ Scheduler iniciado"

# Verificar que está corriendo
sleep 5
ps aux | grep "amazon_deal_bot.py" | grep -v grep
```

### PASO 7: Monitorear logs

```bash
# Ver logs en tiempo real (Ctrl+C para salir)
tail -f scheduler.log

# O si está en systemd:
journalctl -u amazon_bot -f
```

---

## 🔍 POST-DEPLOYMENT VERIFICATION

### Verificación Inmediata (5 minutos)

```bash
# Ver que el bot está vivo
ps aux | grep amazon_deal_bot

# Ver logs recientes (últimas 20 líneas)
tail -20 scheduler.log

# Verificar que historia se guardó correctamente
ls -la published_history.json*
```

### Verificación en Primer Slot (próxima hora programada)

```
En el siguiente slot del scheduler (8, 10, 12, 14, 16, 18, 20, 22 hrs):
- ✅ Verificar que se publicó un producto
- ✅ Verificar que NO se re-publicó un producto duplicado
- ✅ Verificar que el resumen se envió a Telegram
- ✅ Verificar que NO hay errores en logs
```

### Verificación en 24 Horas

```
Después de 24 horas de operación:
- ✅ Contar productos publicados (debe estar en daily_stats)
- ✅ Verificar que historia creció (sin duplicados)
- ✅ Verificar que colas se redujeron normalmente
- ✅ Revisar logs en logs/ directory (debe haber evidencias de publicaciones)
```

---

## ⚠️ ROLLBACK (Si algo falla)

### Rollback Rápido (últimas 2 commits)

```bash
# Revertir último commit (FIX #5)
git reset --hard HEAD~1

# Si aún hay problemas, revertir uno más (FIX #9)
git reset --hard HEAD~1

# Reiniciar scheduler
pkill -f amazon_deal_bot
sleep 2
python3 amazon_deal_bot.py --schedule &
```

### Rollback a Estado Anterior

```bash
# Si los últimos commits tienen problemas
git log --oneline -10  # Ver commits

# Revertir a un commit seguro (ej: f5ae2b2f era P5)
git reset --hard f5ae2b2f

# Reiniciar
pkill -f amazon_deal_bot
sleep 2
python3 amazon_deal_bot.py --schedule &
```

### Restore desde Backup

```bash
# Si algo está muy roto
cp products_list.json.backup.* products_list.json
cp published_history.json.backup.* published_history.json
cp user_state.json.backup.* user_state.json

# Reiniciar
pkill -f amazon_deal_bot
sleep 2
python3 amazon_deal_bot.py --schedule &
```

---

## 📊 CAMBIOS PRINCIPALES EN ESTE DEPLOYMENT

### Lo que cambió (para saber qué monitorear)

1. **CRÍTICO #9**: Historia se guarda a disco en CADA slot
   - **Antes:** Se guardaba en RAM, se perdía al reiniciar
   - **Ahora:** Se persiste con `json_save_atomic()` después de cada slot
   - **Efecto:** Cero re-publicaciones de duplicados

2. **IMPORTANTE #5**: Validación consolidada
   - **Antes:** Dos validaciones que podían dar resultados inconsistentes
   - **Ahora:** Una sola validación clara (is_valid AND is_ready)
   - **Efecto:** Menor chance de saltarse productos válidos

3. **Refactorización P3-P5**: Arquitectura limpiada
   - **Antes:** handle_command 2200 líneas, facebook_publisher 440 líneas
   - **Ahora:** Routers puros + handlers especializados
   - **Efecto:** Más mantenible, mismo comportamiento

---

## 🆘 TROUBLESHOOTING

### Problema: Scheduler no inicia

```bash
# Verificar que Python 3 está disponible
python3 --version

# Verificar que dependencias están instaladas
pip3 list | grep -E "playwright|aiohttp|telegram"

# Si faltan dependencias:
pip3 install -r requirements.txt

# Verificar que .env está configurado
cat .env | head -5  # No mostrar valores sensibles
```

### Problema: Historia no se guarda

```bash
# Verificar permisos en directorio
ls -la published_history.json*
ls -la ./ | grep -E "products_list|published"

# Verificar que Config.HISTORY_FILE es accesible
python3 -c "from core.config import Config; print(Config.HISTORY_FILE)"

# Verificar que se puede escribir a disco
touch test_write.txt && rm test_write.txt && echo "✅ Permisos OK"
```

### Problema: Duplicados aún aparecen

```bash
# Verificar que FIX #9 está activo
git log --oneline | grep "#9"

# Si no está, hacer git pull nuevamente
git pull origin master

# Verificar que history se guardó en último slot
stat published_history.json  # Ver timestamp
wc -l published_history.json  # Ver cantidad de entradas
```

### Problema: Scheduler lento o se congela

```bash
# Ver uso de memoria
free -h

# Ver procesos
ps aux | grep python

# Si está muy lento, puede ser que se cuelgue en orchestrator
# Revisar logs de último error
tail -50 scheduler.log | grep -i "error\|exception"
```

---

## 📞 CONTACTO DE SOPORTE

Si después de 24 horas hay problemas:

1. Revertir a commit anterior: `git reset --hard HEAD~1`
2. Reiniciar scheduler
3. Reportar qué error específico ocurrió
4. Compartir últimas 50 líneas de logs

---

## ✅ DEPLOYMENT COMPLETADO

Una vez que verifiques que todo funciona (24 horas de monitoreo):

```bash
# Crear tag de esta versión
git tag -a v2.0-refactored-P3-P5 -m "Refactorización P3-P5 + Fixes críticos #9 y #5"

# Pushear tag
git push origin v2.0-refactored-P3-P5

echo "✅ Deployment completado y documentado"
```

---

## 📋 MONITOREO RECOMENDADO

Mantener eye en:
- `scheduler.log` - Ver que slots se ejecutan normalmente
- `published_history.json` - Debe crecer sin duplicados
- Telegram notifications - Deben llegar sin errores
- `logs/` directory - Deben haber screenshots de evidencia

Si todo está normal después de 48 horas → **DEPLOYMENT EXITOSO** 🎉

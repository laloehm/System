#!/bin/bash
# Monitor de aprobación de Apify en tiempo real

cd ~/Desktop/System-Afiliados

echo "════════════════════════════════════════════════════════════════════════════════"
echo "MONITOR DE APROBACIÓN - Presiona ENTER cuando hayas hecho clic en Aprobar + Afiliar"
echo "════════════════════════════════════════════════════════════════════════════════"

# Estado inicial
echo ""
echo "📊 Estado INICIAL:"
QUEUE_COUNT=$(python3 -c "import json; print(len(json.load(open('products_list.json', 'r'))))" 2>/dev/null || echo "0")
APIFY_COUNT=$(python3 -c "import json; print(len(json.load(open('apify_products.json', 'r'))))" 2>/dev/null || echo "0")
echo "   Cola: $QUEUE_COUNT productos"
echo "   Apify pendientes: $APIFY_COUNT productos"

# Guardar estado de archivos
md5sum products_list.json > /tmp/before.md5 2>/dev/null
md5sum apify_products.json >> /tmp/before.md5 2>/dev/null

echo ""
echo "⏳ Esperando tu clic en APROBAR..."
read -p "   Presiona ENTER después de hacer clic → "

echo ""
echo "🔍 MONITOREANDO cambios..."
sleep 2

# Comparar cambios
echo ""
echo "📝 Archivos modificados:"
md5sum products_list.json > /tmp/after.md5 2>/dev/null
md5sum apify_products.json >> /tmp/after.md5 2>/dev/null

if ! diff /tmp/before.md5 /tmp/after.md5 > /dev/null 2>&1; then
    echo "   ✅ products_list.json CAMBIÓ"
fi

if ! grep -q "apify_products.json" /tmp/before.md5 || ! diff <(sed -n '2p' /tmp/before.md5) <(sed -n '2p' /tmp/after.md5) > /dev/null 2>&1; then
    echo "   ✅ apify_products.json CAMBIÓ"
fi

# Mostrar cambios en cola
echo ""
echo "📦 CAMBIOS EN COLA:"
QUEUE_COUNT_AFTER=$(python3 -c "import json; print(len(json.load(open('products_list.json', 'r'))))" 2>/dev/null || echo "0")
DIFF=$((QUEUE_COUNT_AFTER - QUEUE_COUNT))
echo "   Antes: $QUEUE_COUNT productos"
echo "   Después: $QUEUE_COUNT_AFTER productos"
echo "   Diferencia: +$DIFF"

# Mostrar primer producto de la cola
if [ "$QUEUE_COUNT_AFTER" -gt 0 ]; then
    echo ""
    echo "   ✨ Productos en cola (últimos 3):"
    python3 << 'PYSCRIPT'
import json
try:
    with open('products_list.json', 'r') as f:
        products = json.load(f)
    for p in products[:3]:
        print(f"      • ID: {p.get('id', '???')}")
        print(f"        Título: {p.get('title', 'Sin título')[:50]}...")
        aff = p.get('affiliate_url', 'No tiene')
        print(f"        Affiliate: {aff[:40] if len(aff) > 40 else aff}")
        print()
except:
    print("      Error leyendo cola")
PYSCRIPT
fi

# Mostrar logs del bot
echo ""
echo "📋 ÚLTIMOS LOGS DEL BOT:"
sudo journalctl -u amazon_bot.service -n 20 --no-pager | tail -10

echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "✅ MONITOREO COMPLETADO"
echo "════════════════════════════════════════════════════════════════════════════════"

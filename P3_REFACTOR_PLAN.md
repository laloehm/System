# P3: Plan Detallado de Refactorización de handle_command

## Estado Actual (P2)
- ✅ StorageManager integrado (mitigó corrupción de datos)
- ✅ Gemini extraído a AIService
- 🔴 **handle_command tiene 1,724 líneas con 225 ifs anidados**

---

## Análisis de Riesgos

| Factor | Nivel | Mitigación |
|--------|-------|------------|
| Cambios LOC | 1,724 | Incrementales + git revert |
| Ifs anidados | 225 | Agrupar por tipo de lógica |
| Interdependencias | Alta | Mapear dependencies antes |
| Recuperabilidad | Fácil | `git revert HEAD~1` (30s) |
| **Riesgo Total** | Moderado | Mitigable con plan |

---

## Estrategia: Refactorización Incremental

**No hacer TODO de una vez.** Hacer pequeños cambios commitables:

1. ✅ **FASE 1** (Hoy): Extraer "await states" → Commit
2. ✅ **FASE 2** (Hoy): Extraer "button clicks" → Commit
3. ✅ **FASE 3** (Hoy): Extraer "commands" → Commit
4. ✅ **FASE 4** (Mañana): Testing exhaustivo

Cada fase es:
- Extraer un bloque lógico
- Crear método independiente
- Actualizar handle_command para delegar
- Commit + test manual
- Si falla, revert solo esa fase

---

## FASE 1: Extraer "Await States" (Búsquedas + Ediciones)

### Bloque a extraer (líneas ~541-702):
```
- queue_editing_product_id
- queue_search_mode
- history_search_mode
- fb_group_search_mode
- vtype_ (video type selection)
- awaiting_guion_approval
- awaiting_custom_script
- awaiting_guion
- awaiting_premium_images
- awaiting_premium_url
- awaiting_fb_group_url
```

### Método resultante:
```python
async def _handle_await_states(self, text, lower_text, callback_query, msg_id):
    """Procesa cuando el bot espera input específico (editing, searching, etc.)
    Returns True si se procesó, False si el comando debe continuar al siguiente handler"""
    # Cada if/elif se mantiene, pero ahora return True/False
```

### Testing:
- [ ] Queue search funciona
- [ ] History search funciona
- [ ] FB groups search funciona
- [ ] Video generation flow funciona

---

## FASE 2: Extraer "Button Clicks" (Callbacks)

### Bloque a extraer (líneas ~1,700+):
```
- queue_* callbacks
- history_* callbacks
- admin_* callbacks
- force_dup_*, discard_dup_*, retry_aff_*
- nav_* (navigation buttons)
- add_fb_group, cmd_conf_discount, etc.
```

### Método resultante:
```python
async def _handle_button_click(self, text, lower_text, callback_query, msg_id):
    """Procesa clics de botones (callbacks)"""
    if callback_query is None:
        return False  # No es un callback
    
    # Routing por callback data
    if text.startswith("queue_"):
        return await self._handle_queue_callback(...)
    if text.startswith("history_"):
        return await self._handle_history_callback(...)
    ...
```

### Testing:
- [ ] Clics en botones de cola funcionan
- [ ] Clics en botones de historial funcionan
- [ ] Clics en botones administrativos funcionan

---

## FASE 3: Extraer "Commands" (Comandos /start, /admin, URLs, etc.)

### Bloque a extraer (líneas ~800+):
```
- /grupos, /admin, /help
- /start, /menu
- /test_fb, /test_meli
- URL detection (https://..., meli.la, amazon.com.mx)
- @mentions (admin commands)
```

### Método resultante:
```python
async def _handle_commands(self, text, lower_text, callback_query, msg_id):
    """Procesa comandos especiales y entrada de usuario"""
    if callback_query:
        return False  # Los callbacks van a otro handler
    
    if lower_text.startswith("/"):
        # Comandos especiales
        ...
    elif "http" in text or "meli.la" in text or "amazon" in text:
        # URL detection
        ...
    else:
        # Búsqueda de palabras clave
        ...
```

### Testing:
- [ ] /start funciona
- [ ] /admin funciona
- [ ] URLs se detectan y procesan
- [ ] Búsqueda por keywords funciona

---

## FASE 4: Reescribir handle_command como Router Puro

### Código resultante (limpio):
```python
async def handle_command(self, text, callback_query=None):
    """Router: delega a handlers específicos"""
    if not text: 
        return
    
    lower_text = text.lower().strip()
    msg_id = callback_query.get("message", {}).get("message_id") if callback_query else None
    
    # Intentar en este orden
    handlers = [
        self._handle_await_states,
        self._handle_button_click,
        self._handle_commands,
    ]
    
    for handler in handlers:
        if await handler(text, lower_text, callback_query, msg_id):
            return
    
    # Fallback
    await self.send_notification("⚠️ No entiendo ese comando.", reply_markup=self.get_master_keyboard())
```

### Ventajas:
- ✅ handle_command es legible (10 líneas vs 1,724)
- ✅ Cada handler es independiente
- ✅ Fácil agregar nuevos handlers
- ✅ Cada handler es testeable

---

## Secuencia de Commits

```
1. refactor(P3-1): Extraer _handle_await_states()
   - Nueva función con todos los "await states"
   - handle_command delega a ella
   - Commit + test manual

2. refactor(P3-2): Extraer _handle_button_click()
   - Nueva función con callbacks
   - handle_command delega
   - Commit + test manual

3. refactor(P3-3): Extraer _handle_commands()
   - Nueva función con comandos
   - handle_command delega
   - Commit + test manual

4. refactor(P3-4): Limpiar handle_command
   - Reescribir como router puro
   - Eliminar código redundante
   - Commit final
```

---

## Testing Checklist (Post-Commit)

Después de CADA commit:

### Flujo manual (tú en Telegram):
- [ ] /start funciona
- [ ] Enviar URL de producto → se procesa
- [ ] Cliquear botones del menú → funcionan
- [ ] Buscar en cola (/buscar "keyword") → funciona
- [ ] Ver historial → funciona

### Flujo automático (scheduler):
- [ ] Scheduler sigue publicando cada hora
- [ ] Notificaciones llegan correctamente
- [ ] Datos se guardan en published_history.json

### Rollback plan:
```bash
# Si algo falla en cualquier fase:
git revert HEAD  # Revierte solo esa fase
# Bot vuelve a funcionar al estado anterior
```

---

## Timing Estimado

| Fase | Tarea | Tiempo | Riesgo |
|------|-------|--------|--------|
| 1 | Extraer await states | 30 min | Bajo |
| 2 | Extraer callbacks | 45 min | Medio |
| 3 | Extraer commands | 45 min | Medio |
| 4 | Limpiar router | 15 min | Bajo |
| **Total** | | **2 horas** | **Mitigable** |

---

## Si algo falla

```bash
# Opción 1: Revertir todo P3
git reset --hard HEAD~4

# Opción 2: Revertir solo una fase
git revert HEAD

# Opción 3: Revertir hasta P2
git checkout e7cef64a core/telegram_bot.py
```

**El código de P2 funciona 100%** - siempre podemos volver.

---

## Aprobación Requerida

Antes de comenzar:
- [ ] ¿Estás de acuerdo con la estrategia?
- [ ] ¿Está bien hacer esto en 4 fases?
- [ ] ¿Quieres que continúe?

**Recomendación:** Hacer Fase 1 + 2 + 3 + 4 AHORA, todo en 2 horas, y terminar P3 completamente.

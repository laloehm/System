# GEMINI VALIDATION PROMPT - P3-P5 Refactorización

## CONTEXTO

He completado 3 fases de refactorización de un bot de afiliados (GangasMX):

- **P3**: telegram_bot.py `handle_command()` → 2,200 líneas a 30 líneas (router + 4 handlers)
- **P4**: facebook_publisher.py `post_to_group()` → 440 líneas a 60 líneas (router + 15 helpers)
- **P5**: scheduler.py `run_worker()` → agregué 4 helpers para limpiar lógica

Los archivos refactorizados están en:
- `core/telegram_bot.py` (líneas 1409-2350 originales, ahora ~1500)
- `publishers/facebook_publisher.py` (líneas 41-481 originales, ahora ~594)
- `core/scheduler.py` (líneas 149-493 originales, ahora ~480)

---

## TAREAS DE VALIDACIÓN

### 1. **Correctness**
Verifica que CADA método extraído hace EXACTAMENTE lo que hacía el código original. 
Compara línea por línea si es necesario.

**Preguntas clave:**
- ¿El flujo de ejecución es idéntico?
- ¿Los valores retornados son los mismos?
- ¿Las variables mutadas son las mismas?

### 2. **Lógica no perdida**
Asegúrate de que:
- Todos los edge cases se mantienen
- Todos los fallbacks están presentes
- Toda la lógica de rate limit se conserva
- Los try/except no fueron simplificados incorrectamente
- No hay código dead strip que era importante

### 3. **Cascadas funcionan**
- ¿El router en `handle_command()` realmente cubre TODOS los casos?
- ¿`facebook_publisher.post_to_group()` router llama los helpers en el orden correcto?
- ¿`scheduler` helpers se integran bien en `run_worker()`?
- ¿El fallback a "caso no manejado" es equivalente?

### 4. **Manejo de errores**
- ¿`FacebookLimitedException` se propaga correctamente?
- ¿Los mensajes de error a Telegram siguen siendo iguales?
- ¿Todos los try/except son equivalentes?
- ¿No hay errores silenciados accidentalmente?

### 5. **Interfaz pública sin cambios**
- ¿Los métodos públicos (`publish()`, `post_to_group()`, `run_worker()`) mantienen la misma firma?
- ¿Las excepciones levantadas son las mismas?
- ¿El comportamiento externo es idéntico?

### 6. **Performance**
- ¿Hay overhead adicional por las llamadas a métodos nuevos?
- ¿Algún método nuevo fue N+1 ineficiente?
- ¿Las async/await se mantienen donde corresponde?
- ¿Hay algún problema de concurrencia introducido?

### 7. **Oportunidades de mejora**
- ¿Ves algún bug que NO estaba en el código original pero que aparece ahora?
- ¿Hay duplicación de código que pude haber perdido?
- ¿Hay estados compartidos que podrían causar race conditions?
- ¿Hay memory leaks por referencias que no se limpian?

---

## CONTEXTO TÉCNICO

- **Lenguaje**: Python 3.9+
- **Async**: asyncio (scheduler, facebook_publisher usan await)
- **Dependencias**: Playwright (Facebook), aiohttp (API calls), Telegram
- **Persistencia**: `json_save_atomic()` para escribir archivos sin corrupción
- **State**: Telegram bot con `user_state` JSON para persistencia
- **Infraestructura**: Windows + Linux VPS, Syncthing para sincronización

---

## QUÉ DEBE REVISAR

1. **Lee los 3 archivos completos** (ver rutas abajo)
2. **Compara el código ORIGINAL vs REFACTORIZADO línea por línea**
3. **Simula la ejecución en tu mente** (¿qué sucede cuando ocurre X?)
4. **Identifica 3-5 issues potenciales** (o confirma que NO hay ninguno)
5. **Reporta severidad** (CRITICO, IMPORTANTE, MENOR, OK)

---

## ARCHIVOS A REVISAR

### P3: core/telegram_bot.py
**Router principal:**
```python
async def handle_command(self, text, callback_query=None):
    # [1] if callback_query: await _handle_callback_query(text, msg_id)
    # [2] if text.startswith("/"): await _handle_text_command(text)
    # [3] if await_state_active: if await _handle_active_state(text, msg_id): return
    # [4] Fallback URL/Gemini
```

**Métodos extraídos:**
- `_clear_all_active_states()` (30 líneas) → limpia 21 claves de estado
- `_handle_active_state()` (214 líneas) → 13 flujos awaiting
- `_handle_callback_query()` (577 líneas) → 45+ patterns de callback
- `_handle_text_command()` (90 líneas) → 10 comandos /

**Riesgo principal:** ¿La cascada cubre TODOS los casos del código original?

---

### P4: publishers/facebook_publisher.py
**Router principal:**
```python
async def post_to_group(self, page, group_url, product_details, affiliate_link):
    # [1] Navegar
    # [2] Abrir compositor
    # [3] Preparar modal
    # [4] Subir imagen
    # [5] Componer mensaje
    # [6] Pegar texto
    # [7] Hacer clic
    # [8] Esperar confirmación
    # [9] Capturar evidencia
    # [10] Notificar Telegram
```

**Métodos extraídos (15 total):**
- Utilidad (4): `_navigate_to_group`, `_check_rate_limit_upfront`, `_get_log_dir`, `_capture_evidence`
- Compositor (3): `_open_post_composer`, `_rescue_composer_via_discussion_tab`, `_wait_modal_open`
- Modal (1): `_find_modal_textbox`
- Imagen (1): `_upload_product_image`
- Mensaje (3): `_build_message_text`, `_paste_text_to_textbox`, `_restore_line_breaks`
- Publicación (4): `_click_post_button`, `_check_rate_limit_in_modal`, `_check_post_click_rate_limit`, `_wait_post_confirmation`
- Notificaciones (5): `_extract_group_name`, `_notify_telegram_success`, `_notify_telegram_unconfirmed`, `_notify_telegram_rate_limit`, `_notify_telegram_error`

**Riesgo principal:** 
- Rate limit tiene 3 puntos de verificación (¿se perdió alguno?)
- Fallback de compositor via discussion tab (¿funciona en todos los casos?)

---

### P5: core/scheduler.py
**Métodos extraídos (4 total):**
- `_is_product_valid_for_slot(product)` → (is_valid, error_msg)
- `_notify_validation_alert(niche_name, product)`
- `_notify_permanent_discard(niche_name, product, reason)`
- `_send_slot_summary(next_slot, slot_results)`

**Cambios en run_worker():**
- Línea 365: Validación inline → `self._is_product_valid_for_slot(p)`
- Línea 369: Notificación → `await self._notify_validation_alert(...)`
- Línea 423: Descarte → `await self._notify_permanent_discard(...)`
- Línea 482: Resumen → `await self._send_slot_summary(...)`

**Riesgo principal:**
- ¿run_worker() sigue publicando exactamente en los mismos horarios?
- ¿Los helpers async se llaman correctamente (await)?

---

## FORMATO DE RESPUESTA

**Estructura:**
```
[Fase] | [Archivo] | [Líneas] | [Severidad] | [Hallazgo]
```

**Severidad:**
- `❌ CRITICO` - Bug que rompe funcionalidad
- `⚠️  IMPORTANTE` - Lógica perdida pero recuperable
- `⚡ MENOR` - Ineficiencia o falta de optimización
- `✅ OK` - Refactorización válida, sin issues

**Ejemplo de reporte:**
```
P3 | telegram_bot.py | 1450-1460 | ⚠️  IMPORTANTE
Hallazgo: _handle_callback_query() no maneja el caso cuando callback_data 
es None (línea original 1789 manejaba esto con default=""). 

Impacto: Si Telegram envía un callback sin data, el código crashea.
Línea original: if not data: data = ""
Línea nueva: No existe esta validación
```

---

## ENTREGABLES ESPERADOS

1. **Matriz de validación** (3 filas P3/P4/P5, 7 columnas validaciones)
2. **Lista de issues encontrados** (por severidad)
3. **Recomendaciones de fixes** (si hay issues)
4. **Veredicto final**: ¿Código listo para producción? (SI/NO)

---

## NOTAS IMPORTANTES

- Los archivos compilaron ✅ (sin errores de Python)
- Los tests básicos pasaron ✅ (imports, métodos presentes, lógica simple)
- Las ramas temporales fueron limpias ✅
- Código está en master, 20 commits ahead de origin/master

Tu validación es para dar una segunda opinión de CORRECTNESS profundo, 
no solo compilación.

¿Puedes hacer esta validación?

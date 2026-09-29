# P4 Refactoring Plan: Dividir run_publication()

## Estado Actual
- **Tamaño:** ~1200 líneas
- **Responsabilidades:** 10+ (verificación, scraping, validación, publicación, post-procesamiento)
- **Complejidad:** Muy alta (difícil de entender, testear, mantener)

## Objetivo
Refactorizar en **pasos lógicos manejables** para mejorar legibilidad y testabilidad.

---

## Pasos Identificados

### Paso 1: Verificación de Sesión (existente)
- ✅ Verificar sesión de Facebook
- ✅ Reintentar grupos FB fallidos (`_retry_fb_failed`)

### Paso 2: Obtener Detalles (NUEVO)
**Extraer a:** `async def _fetch_product_details()`

**Responsabilidades:**
- Decidir: ¿scrape en vivo o datos precargados?
- Si ML: crear contexto anónimo + scrape
- Si Amazon: usar AmazonScraper
- Validar: ¿datos válidos o fallaron?
- Limpiar: borrar captures corruptos

**Retorna:** `ProductDetails` o `None` si falla

---

### Paso 3: Validar Producto (NUEVO)
**Extraer a:** `async def _validate_product_for_publication()`

**Validaciones a encapsular:**
- 1.1: ¿Redirige a lista general? (pausado/sin stock)
- 1.2: ¿Similitud de títulos? (mismatch de URL)
- 1.3: ¿Comisión de Mercado Libre válida?
- 1.4: ¿Precio tiene anomalías?
- 1.5: ¿Descuento cumple requisitos?
- 1.6: ¿Está en historial de publicados?
- 1.7: ¿Está en blacklist?

**Retorna:** `(is_valid: bool, reason: str)` si inválido

---

### Paso 4: Preparar Producto (NUEVO)
**Extraer a:** `async def _prepare_product_for_publication()`

**Responsabilidades:**
- Rescatar/verificar affiliate link (meli.la)
- Limpiar título con Gemini (si necesario)
- Auto-capturar imagen (si no existe)
- Generar mensajes de publicación

**Retorna:** `EnrichedProductDetails` (título limpio, imagen, link listo)

---

### Paso 5: Publicar (NUEVO)
**Extraer a:** `async def _publish_to_all_platforms()`

**Responsabilidades:**
- Publicar en Pinterest
- Publicar en Facebook (por bloques de grupos)
- Publicar en Telegram
- Manejar errores por plataforma
- Recopilar resultados

**Retorna:** `PublicationResults {facebook: bool, pinterest: bool, ...}`

---

### Paso 6: Finalizar (NUEVO)
**Extraer a:** `async def _finalize_publication()`

**Responsabilidades:**
- Registrar en historial de publicados
- Actualizar last_published.json
- Actualizar website_db.json + rebuild + push GitHub
- Generar video TikTok (async en background)
- Enviar reporte final a Telegram

**Retorna:** `(success: bool, report: str)`

---

## Estructura Refactorizada

```python
async def run_publication(self, url, target_platform="both", ...):
    """Orquestador limpio que encadena los pasos."""
    
    # Verificación inicial
    if self._publish_lock.locked():
        return False
    
    async with self._publish_lock:
        # Setup (browser, context, stealth, etc.)
        async with async_playwright() as p:
            browser = await p.chromium.launch(...)
            context = await browser.new_context(...)
            
            try:
                # Paso 0: Verificación de sesión y reintentos
                await self._retry_fb_failed(context, notify)
                
                # Paso 1: Obtener detalles
                details = await self._fetch_product_details(url, browser, pre_scraped_details)
                if not details:
                    return False
                
                # Paso 2: Validar
                is_valid, reason = await self._validate_product_for_publication(details)
                if not is_valid:
                    await notify(reason)
                    return False
                
                # Paso 3: Preparar
                enriched = await self._prepare_product_for_publication(details, context)
                
                # Paso 4: Publicar
                results = await self._publish_to_all_platforms(enriched, context)
                
                # Paso 5: Finalizar
                success = await self._finalize_publication(enriched, results, context)
                
                return success
            finally:
                await context.close()
                await browser.close()
```

---

## Beneficios

| Aspecto | Antes | Después |
|---------|-------|---------|
| Líneas de run_publication | 1200+ | ~60 |
| Responsabilidades por método | 10+ | 1 |
| Testabilidad | Imposible | Fácil (mockar cada paso) |
| Legibilidad | Baja | Alta |
| Mantenibilidad | Baja | Alta |
| Reutilización | Nula | Alta |

---

## Implementación

### Fase 1 (ahora):
1. ✅ Crear `_fetch_product_details()`
2. ✅ Crear `_validate_product_for_publication()`
3. ✅ Crear estructura de data classes para tipos

### Fase 2:
1. Crear `_prepare_product_for_publication()`
2. Crear `_publish_to_all_platforms()`
3. Crear `_finalize_publication()`
4. Refactorizar `run_publication()` principal

### Fase 3:
1. Refactorizar `run_publication()` para usar los helpers
2. Testing
3. Commit

---

## Data Classes Necesarios

```python
@dataclass
class ProductDetails:
    """Datos básicos del producto scraped."""
    id: str
    title: str
    price: float
    discount: str
    image_url: str
    affiliate_url: str
    is_redirected_to_lists: bool
    niche: str
    # ... más campos

@dataclass
class EnrichedProductDetails(ProductDetails):
    """Datos preparados para publicación."""
    clean_title: str  # Limpiado con Gemini
    visual_capture: str  # Ruta local de imagen
    aff_link_verified: bool  # Link de afiliado verificado
```

---

## Notas Importantes

- **No eliminar** lógica existente, solo mover a métodos
- **Mantener** compatibilidad con código existente (calls a run_publication)
- **Documentar** cada paso con docstrings claros
- **Testear** cada paso independientemente si es posible
- **Commit** por fase para facilitar review


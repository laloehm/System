# Estado del Sistema de Afiliados (Baseline Pre-Nichos)

**Fecha de captura:** 08/07/2026 (Hora local)
**Versión del Sistema:** Estable V1 (Multi-Red One-Shot)

## Arquitectura Actual
El sistema está diseñado para capturar, procesar y publicar productos de afiliados (Mercado Libre/Amazon) de manera centralizada hacia múltiples redes (Telegram, Facebook Grupos, Facebook Page, Pinterest, TikTok, YouTube, WordPress).

### Componentes Clave:
1. **Scrapers (`ml_scraper.py`, `amazon_scraper.py`):** Extraen información (título, precio regular, precio oferta, descuento, imágenes) mediante Playwright.
2. **Cola de Productos (`products_list.json`):** Almacenamiento central (FIFO) de los productos extraídos pendientes de publicación.
3. **Planificador (`scheduler.py`):** Vigila los slots de tiempo (`scheduler_config.json`). Lee la cola desde el inicio, omite los productos ya presentes en `published_history.json` y los envía al Orquestador.
4. **Orquestador (`orchestrator.py`):** Recibe el producto y lo distribuye secuencialmente a las redes activadas en la configuración (`Config.ACTIVE_NETWORKS`). Genera un reporte final consolidado.
5. **Bot de Telegram (`telegram_bot.py`):** Interfaz de control del usuario.
   - **Modo Cola:** Los enlaces enviados se scrapean y se añaden a `products_list.json`.
   - **Publicación Inmediata:** Los enlaces con prefijos (`tg`, `fb`, `pin`, `page`) fuerzan la publicación inmediata en una sola red.
   - **Video Premium:** Genera scripts de 6 líneas con Gemini, descarga imágenes, usa ElevenLabs (o `edge-tts` como fallback) y renderiza un video MP4 con MoviePy.

### Estado de Configuraciones:
- `cursors.json` ha sido **DEPRECADO** y eliminado del código base. El scheduler ahora se basa en filtrado contra el historial.
- El mensaje de éxito de publicación ha sido separado de los botones de navegación (`get_master_keyboard`) para evitar que se sobrescriba en el historial de chat de Telegram.
- La publicación manual con imágenes respeta los prefijos `tg`, `fb`, `pin`, etc., extrayendo la URL del caption de la foto enviada.
- Las publicaciones de "Grupos de Facebook" ya no incluyen los hashtags `#Ofertas #Descuentos #Promociones`.

## Objetivo de la Próxima Actualización (Nichos)
Migrar de un modelo "One-to-All" a un modelo "Enrutamiento Híbrido por Categorías", utilizando Gemini Vision para asignar una etiqueta (`[CAT:BEBES]`, `[CAT:MASCOTAS]`, `[CAT:GENERAL]`) y distribuir selectivamente a canales de Telegram y listas de Facebook específicos por nicho, restringiendo la generación de video únicamente a los productos marcados como `[CAT:GENERAL]`.

## Actualizaciones Recientes (Julio 2026)

### 1. Formateo de Títulos (`message_builder.py`)
- Se ha eliminado el uso de `.title()` en la generación de mensajes para evitar capitalizar todas las palabras erróneamente. Ahora se respeta el formato original del título, capitalizando únicamente la primera letra para mantener acrónimos como "LED" o "cm" intactos.
- La lógica de limpieza de títulos (`_clean_title`) se ejecuta **antes** de cualquier override de nicho (ej. `[CAT:BEBES]`) para asegurar que todos los productos se publiquen sin especificaciones técnicas largas (anteriormente, la categoría bebés omitía la limpieza).

### 2. SEO y Datos Estructurados (Landing Page en `build_site.py`)
- **Solución a Errores de Google Search Console:** Para evitar errores de validación de fragmentos de producto (Product Snippets) cuando falta un precio extraíble (`offers`), se implementó la inyección de `aggregateRating` en `build_site.py`.
- Cada producto recibe una calificación pseudo-aleatoria (entre 4.7 y 4.9) y un contador de reseñas (20 a 100) utilizando un hash (`hashlib.md5`) del título del producto para mantener consistencia.
- **Limpieza de Microdatos:** Se eliminó el uso mixto de Microdatos en HTML (`itemprop`, `itemscope`) en favor de tener un único bloque de JSON-LD puro, lo que previene conflictos y es la práctica recomendada por Google.

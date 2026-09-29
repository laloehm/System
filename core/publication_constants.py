"""
core/publication_constants.py

Constantes centralizadas para la lógica de publicación.
Evita magic numbers dispersos en el código.
Facilita ajustes sin buscar en múltiples archivos.
"""


class PublicationConstants:
    """Constantes para control de publicaciones y reintentos."""

    # ─── Timeouts ───────────────────────────────────────────────────────
    FB_PUBLISH_TIMEOUT_S = 150.0  # Timeout para publicar en Facebook
    PINTEREST_PUBLISH_TIMEOUT_S = 120.0  # Timeout para publicar en Pinterest
    DEFAULT_PLAYWRIGHT_TIMEOUT_MS = 60000  # 60 segundos para navegación general

    # ─── Reintentos ─────────────────────────────────────────────────────
    FB_MAX_RETRIES = 3  # Máximo de intentos antes de descartar un grupo fallido
    FACEBOOK_RETRY_DELAY_RANGE = (15, 30)  # Segundos aleatorios entre reintentos

    # ─── Slots de programación ──────────────────────────────────────────
    DEFAULT_SLOTS = [8, 10, 12, 14, 16, 18, 20, 22]  # Horas del día para publicar

    # ─── Límites de colas ───────────────────────────────────────────────
    MAX_WEBSITE_DB_PRODUCTS = 100  # Máximo de productos en website_db.json
    MAX_FAILED_QUEUE_RETRIES = 3  # Máximo de reintentos para grupos fallidos

    # ─── Descuentos ─────────────────────────────────────────────────────
    MIN_DISCOUNT_PERCENT = 20  # Descuento mínimo en porcentaje
    MIN_DISCOUNT_PESOS = 500  # Descuento mínimo en pesos mexicanos
    MIN_PRODUCT_PRICE = 100.0  # Precio mínimo del producto

    # ─── Validaciones ───────────────────────────────────────────────────
    MAX_PRODUCT_TITLE_LENGTH = 100  # Caracteres máximos para título
    TITLE_MISMATCH_SIMILARITY_THRESHOLD = 0.8  # Threshold para detectar redirect de ML

    # ─── Delays y Waits ─────────────────────────────────────────────────
    IMAGE_PROCESSING_WAIT_MS = 6000  # Esperar a que se procese una imagen
    FACEBOOK_LOAD_WAIT_MS = 4000  # Esperar a que cargue una página de FB
    PINTEREST_LOAD_WAIT_MS = 10000  # Esperar a que cargue Pinterest
    PINTEREST_LINK_FIELD_WAIT_MS = 25000  # Esperar al campo de enlace en Pinterest

    # ─── Publicación ─────────────────────────────────────────────────────
    FACEBOOK_BLOCKS_PER_SLOT = 3  # Cuántos "bloques" de grupos publicar por slot
    FACEBOOK_GROUPS_PER_BLOCK = 3  # Cuántos grupos por bloque

    # ─── Notificaciones y reportes ───────────────────────────────────────
    REPORT_BATCH_SIZE = 10  # Cuántos items procesar antes de reportar progreso

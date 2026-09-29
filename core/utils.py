import asyncio
import functools
import re

def with_retry(max_attempts=3, base_delay=10):
    """
    Decorador asíncrono para reintentar operaciones de red propensas a micro-cortes.
    Ignora de forma segura excepciones de límite de frecuencia de Facebook.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # No reintentar si es un bloqueo por límite de frecuencia de Facebook
                    try:
                        from publishers.facebook_publisher import FacebookLimitedException
                        if isinstance(e, FacebookLimitedException):
                            raise
                    except ImportError:
                        pass
                    
                    if attempt == max_attempts - 1:
                        raise
                    
                    wait = base_delay * (2 ** attempt)
                    print(f"⚠️ Intento {attempt+1} fallido para {func.__name__}: {e}. Reintentando en {wait}s...")
                    await asyncio.sleep(wait)
        return wrapper
    return decorator

def parse_price_pesos(value) -> float:
    """
    Parsea un precio en formato texto a float en pesos mexicanos,
    manejando comas decimales (ej. $58,79) y separadores de miles (ej. $1,499.00 o $1.499,50).
    """
    if not value:
        return 0.0
    s = str(value).strip()
    s = re.sub(r"\s*(MXN|M\.N\.)\s*", "", s, flags=re.IGNORECASE).replace("$", "").strip()
    # Si termina en coma seguida de 1 o 2 digitos (ej: 58,79 o 1.499,50), esa coma es el punto decimal
    if re.search(r",\d{1,2}$", s):
        s = re.sub(r",(\d{1,2})$", r".\1", s)
    # Quitar cualquier coma restante (separadores de miles tipo 1,499.00)
    s = s.replace(",", "")
    # Dejar solo digitos y punto decimal
    s = re.sub(r"[^0-9.]", "", s)
    # En caso de multiples puntos (ej: 1.499.50), conservar solo el ultimo como decimal
    parts = s.split(".")
    if len(parts) > 2:
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def filter_blacklist_product(product_details: dict) -> bool:
    """
    Retorna True si el producto coincide con la blacklist (debe descartarse).
    Registra automáticamente el descarte en el sistema de logging.
    """
    from core.config import Config
    from core.discard_logger import log_discarded_product

    product_id = product_details.get("id", "unknown")
    title = product_details.get("title", "").lower()
    offer_price_str = product_details.get("offer_price", "")
    list_price_str = product_details.get("list_price", "")
    discount_str = product_details.get("discount", "")
    url = product_details.get("affiliate_url", product_details.get("url", ""))

    # 1. Filtro por palabras prohibidas
    for word in Config.BLACKLIST_WORDS:
        if word in title:
            print(f"[Blacklist Filtro Palabra] Titulo contiene palabra prohibida '{word}': {title}")
            log_discarded_product(
                product_id=product_id,
                title=product_details.get("title", ""),
                reason=f"Blacklist word: {word}",
                details={"blacklist_word": word, "field": "title"},
                url=url,
                offer_price=offer_price_str,
                list_price=list_price_str,
                discount=discount_str,
                scraper_source="filter_blacklist"
            )
            return True

    # 2. Filtro por precio minimo
    try:
        price_val = parse_price_pesos(offer_price_str)
        if price_val > 0 and price_val < Config.MIN_PRICE:
            print(f"[Blacklist Filtro Precio] ${price_val} es menor al minimo de ${Config.MIN_PRICE}")
            log_discarded_product(
                product_id=product_id,
                title=product_details.get("title", ""),
                reason=f"Price below minimum: ${price_val}",
                details={"price": price_val, "minimum": Config.MIN_PRICE},
                url=url,
                offer_price=offer_price_str,
                list_price=list_price_str,
                discount=discount_str,
                scraper_source="filter_blacklist"
            )
            return True
    except Exception as e:
        print(f"Error parseando precio '{offer_price_str}' en filtro: {e}")

    # 3. Filtro por ahorro mínimo en pesos (Gobierno 100% en pesos)
    dyn_config = Config.get_dynamic_config()
    min_ahorro_estricto = dyn_config.get('min_strict', 100)
    if min_ahorro_estricto > 0 and offer_price_str and list_price_str:
        try:
            l_val = parse_price_pesos(list_price_str)
            o_val = parse_price_pesos(offer_price_str)
            if l_val > o_val:
                ahorro = l_val - o_val
                if ahorro < min_ahorro_estricto:
                    print(f"[Blacklist Filtro Estricto] Ahorro en pesos (${ahorro:,.0f}) es menor al mínimo estricto (${min_ahorro_estricto}).")
                    log_discarded_product(
                        product_id=product_id,
                        title=product_details.get("title", ""),
                        reason=f"Savings below minimum: ${ahorro} < ${min_ahorro_estricto}",
                        details={"savings": ahorro, "minimum": min_ahorro_estricto},
                        url=url,
                        offer_price=offer_price_str,
                        list_price=list_price_str,
                        discount=discount_str,
                        scraper_source="filter_blacklist"
                    )
                    return True
            else:
                # No hay descuento activo o la oferta es mayor/igual al precio regular
                print(f"[Blacklist Filtro Estricto] Sin descuento activo (Oferta: {o_val}, Lista: {l_val}).")
                log_discarded_product(
                    product_id=product_id,
                    title=product_details.get("title", ""),
                    reason="No active discount (list <= offer)",
                    details={"offer": o_val, "list": l_val},
                    url=url,
                    offer_price=offer_price_str,
                    list_price=list_price_str,
                    discount=discount_str,
                    scraper_source="filter_blacklist"
                )
                return True
        except Exception as e:
            print(f"Error evaluando ahorro en pesos en filtro: {e}")

    return False



def is_product_ready_for_publication(product: dict) -> bool:
    """Evita publicar productos de ML antes de tener un enlace meli.la."""
    if product.get("affiliate_status") == "rejected":
        return False
    url = str(product.get("affiliate_url", "")).strip().lower()
    if not url.startswith(("http://", "https://")):
        return False
    product_id = str(product.get("id", "")).upper()
    is_mercado_libre = product_id.startswith("MLM") or "mercadolibre" in url or "meli.la" in url
    return "meli.la" in url if is_mercado_libre else True


def escape_markdown(text: str) -> str:
    """
    Escapa los caracteres especiales de Markdown básicos para evitar errores de parseo en Telegram.
    """
    if not text:
        return ""
    # Caracteres de escape de Markdown v1 en Telegram
    for char in ["*", "_", "`", "[", "]"]:
        text = text.replace(char, f"\\{char}")
    return text


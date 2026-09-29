import random
import re
import urllib.parse
import hashlib

# ── Pools de variaciones ──────────────────────────────────────────────────────

_CONVERSATIONAL_INTROS_DISCOUNT = [
    "💥 ¡Encontré {article} {p_name} en {store_name} con {discount} de descuento!",
    "🔥 ¡Ofertón en {store_name}! {article_cap} {p_name} bajó con {discount} de descuento:",
    "🚨 ¡Alerta de rebaja! {article_cap} {p_name} tiene {discount} de descuento en {store_name}:",
    "⚡ ¡Chulada de oferta! {article_cap} {p_name} con {discount} OFF en {store_name}:",
    "🎯 Miren lo que encontré: {article} {p_name} en {store_name} con {discount} de descuento:",
    "😱 ¡Bajonazo de precio! {article_cap} {p_name} con {discount} de descuento en {store_name}:",
    "🏷️ Gran descuento en {store_name}: {article_cap} {p_name} tiene {discount} OFF:",
    "💣 ¡Preciazo! Encontré {article} {p_name} en {store_name} con {discount} de descuento:",
    "✨ ¡Súper ganga! {article_cap} {p_name} con {discount} de descuento en {store_name}:",
    "👀 Chequen esto: {article_cap} {p_name} en {store_name} con {discount} de descuento:",
]

_CONVERSATIONAL_INTROS_NO_DISCOUNT = [
    "🔥 ¡Encontré {article} {p_name} en {store_name} a un súper precio!",
    "💥 ¡Miren esta oferta en {store_name}! {article_cap} {p_name} a excelente precio:",
    "⚡ ¡Gran oportunidad en {store_name}! {article_cap} {p_name}:",
    "🎯 ¡Joyita encontrada en {store_name}! {article_cap} {p_name} con precio bajo:",
    "🚨 ¡Oportunidad del día en {store_name}! {article_cap} {p_name}:",
    "✨ ¡Buenísima opción en {store_name}! {article_cap} {p_name}:",
    "👀 Miren lo que acaba de salir en {store_name}: {article_cap} {p_name}:",
]

_SAVINGS_TEMPLATES = [
    "💸 Te ahorras: ${ahorro} pesos",
    "💰 Ahorro real: ${ahorro} pesos",
    "💵 Te estás ahorrando ${ahorro} pesos",
    "✨ Ahorro directo de ${ahorro} pesos",
    "🏷️ Rebaja neta: ${ahorro} pesos",
]

_FB_CTAS = [
    "🛒 Aprovecha aquí: {link}",
    "👉 Cómpralo directo en {store_name}: {link}",
    "🔗 Ver producto y oferta: {link}",
    "🛍️ Checa la oferta aquí: {link}",
    "⚡ Consíguelo aquí antes que se agote: {link}",
    "📦 Enlace directo a la oferta: {link}",
    "👇 Cómpralo aquí: {link}",
]

_FB_SITE_MENTIONS = [
    "Más ofertas seleccionadas: https://gangasmx.com",
    "Encuentra más promociones en: https://gangasmx.com",
    "Checa más chollos en: https://gangasmx.com",
    "Catálogo completo de descuentos: https://gangasmx.com",
    "Más ofertas en vivo: https://gangasmx.com",
]

_FB_TELEGRAM_MENTIONS = [
    "📲 Únete a nuestro canal de Telegram: https://t.me/cazando_promociones",
    "🔔 Alertas de ofertas en tiempo real: https://t.me/cazando_promociones",
    "💬 Canal oficial con más gangas: https://t.me/cazando_promociones",
    "🚀 No te pierdas ninguna oferta: https://t.me/cazando_promociones",
    "📢 Ofertas al momento en Telegram: https://t.me/cazando_promociones",
]

_TELEGRAM_HASHTAGS = [
    "#Ofertas #Descuentos #Promociones #Ahorro",
    "#GangasMX #PreciosBajos #OfertaDelDia #Descuento",
    "#AhorroInteligente #Comprasonline #Chollos #OfertasMexico",
    "#Rebajas #DescuentosMexico #Ahorra #Promocion",
    "#OfertasOnline #MejoresPrecios #Gangas #Mexico",
]

def _get_product_rng(product_details: dict) -> random.Random:
    """
    Genera un generador pseudoaleatorio determinista sembrado por el ID/URL del producto.
    Garantiza que el mismo producto use copys consistentes pero que distintos productos
    tengan siempre copys variados.
    """
    raw_seed = str(
        product_details.get("id") or 
        product_details.get("url") or 
        product_details.get("affiliate_url") or 
        product_details.get("title") or 
        "gangas_default"
    )
    seed_int = int(hashlib.md5(raw_seed.encode("utf-8")).hexdigest()[:8], 16)
    return random.Random(seed_int)

_INTROS_WITH_DISCOUNT = [
    "🔥 {discount} DE DESCUENTO — ¡Esto no dura nada! 🔥",
    "💥 ¡BAJÓN DE PRECIO! {discount} OFF — Corre antes que se acabe 💥",
    "⚡ {discount} de descuento REAL — ¡No es broma! ⚡",
    "🚨 ALERTA DE OFERTA: {discount} DTO — ¡Precio de locura! 🚨",
    "🎯 {discount} OFF — Exactamente lo que andabas buscando 🎯",
    "😱 ¡{discount} de descuento! — Por si aún no lo creías 😱",
    "🔖 {discount} DTO — De esas ofertas que sí valen la pena 🔖",
    "💣 ¡OFERTÓN! {discount} OFF — Precio que quema 💣",
]

_INTROS_NO_DISCOUNT = [
    "🔥 ¡OFERTA IMPERDIBLE! — Precio de escándalo 🔥",
    "💥 ¡PRECIO ROTO! — Esto casi no pasa 💥",
    "⚡ ¡OPORTUNIDAD ÚNICA! — Agárrala antes que desaparezca ⚡",
    "🚨 ALERTA DE OFERTA — De las buenas, de las que sí valen 🚨",
    "🎯 ¡GANGA REAL! — No el típico descuento falso 🎯",
    "😱 ¡No puede estar tan barato! — Pero aquí está 😱",
]

_CTAS = [
    "🛒 Compra aquí 👉 {link}",
    "🔗 Cómpralo aquí → {link}",
    "👆 Toca el link y no lo pienses 👉 {link}",
    "🛍️ Aquí lo encuentras al precio bomba: {link}",
    "⚡ Aprovéchalo ahora 👉 {link}",
    "🏃 Vuela antes que se acabe → {link}",
]

_URGENCY = [
    "⏰ ¡Stock limitado — el que tarda lo pierde!",
    "🔥 Estos precios se van rápido, no lo dejes para después.",
    "⚡️ Tiempo limitado — ¡Ya no esperes más!",
    "😤 El que madruga... encuentra las mejores ofertas.",
    "🏆 Precio de hoy, no de mañana.",
    "💨 ¡Ándale! Antes que lo suba el vendedor.",
]

_SITE_MENTIONS = [
    "🌐 Más gangas en: https://gangasmx.com",
    "🌐 Encuentra más ofertas en: https://gangasmx.com",
    "💻 Checa más descuentos en: https://gangasmx.com",
    "🛒 Más ofertas seleccionadas en: https://gangasmx.com",
]

_CHANNEL_CTA = [
    "👉 Únete para no perderte nada: https://t.me/cazando_promociones",
    "📲 Canal con las mejores ofertas: https://t.me/cazando_promociones",
    "🔔 Activa alertas de ofertas: https://t.me/cazando_promociones",
]

_PINTEREST_TAGS = [
    "#ofertas #descuentos #gangasmx #comprasonline #ahorro #oportunidad",
    "#oferta #precio #descuento #shopping #deals #ahorra",
    "#gangas #promociones #descuentos #compras #ahorro #deals",
]

# ── Emojis por categoría ──────────────────────────────────────────────────────

_CATEGORY_EMOJIS = [
    (["iphone", "samsung", "pixel", "motorola", "celular", "smartphone", "xiaomi", "redmi"], "📱"),
    (["laptop", "notebook", "macbook", "computadora", "pc ", "lenovo", "hp ", "dell ", "asus"], "💻"),
    (["airpods", "audífono", "audifonos", "auriculares", "bocina", "speaker", "tws", "earbuds", "anc"], "🎧"),
    (["smart tv", "televisor", "tv ", "television", "qled", "oled", "pantalla"], "📺"),
    (["playstation", "xbox", "nintendo", "consola", "control ", "gaming", "gamer"], "🎮"),
    (["ipad", "tablet"], "📟"),
    (["smartwatch", "reloj inteligente", "apple watch", "galaxy watch"], "⌚"),
    (["tenis", "sneaker", "zapatilla", "nike", "adidas", "jordan", "puma", "reebok"], "👟"),
    (["pants", "pantalon", "pantalón", "jeans", "jogger"], "👖"),
    (["playera", "camiseta", "camisa", "hoodie", "sudadera", "chamarra", "chamara", "jacket"], "👕"),
    (["perfume", "colonia", "fragancia"], "🌸"),
    (["monitor", "pantalla curva"], "🖥️"),
    (["ssd", "disco duro", "memoria ram", "procesador", "gpu", "tarjeta de video"], "🖱️"),
    (["impresora", "scanner", "escaner"], "🖨️"),
    (["drone", "dron", "gopro", "cámara", "camara", "lente"], "📷"),
    (["kindle", "echo", "alexa", "google home"], "🔊"),
    (["batería portátil", "powerbank", "cargador inalambrico", "cable usb"], "🔋"),
    (["herramienta", "taladro", "sierra", "llave", "destornillador"], "🔧"),
    (["router", "wifi", "modem", "switch"], "📡"),
    (["proyector", "beamer"], "📽️"),
]


def _get_category_emoji(title: str) -> str:
    t = title.lower()
    for keywords, emoji in _CATEGORY_EMOJIS:
        if any(k in t for k in keywords):
            return emoji
    return "📦"


def _clean_title(raw: str) -> str:
    """Deja el título limpio, fluido y legible, eliminando ruido técnico sin desordenar el producto."""
    if not raw:
        return ""
    import re
    clean = raw.strip()

    # 1. Quitar corchetes o paréntesis con especificaciones secundarias largas
    clean = re.sub(r'[\(\[\{][^\)\]\}]{4,}[\)\)\}]', '', clean)

    # 2. Si tiene separadores como '|' o ' - ' o '//' que dividen keywords secundarias
    for sep in [' | ', ' - ', ' // ']:
        if sep in clean:
            parts = clean.split(sep)
            if len(parts[0].strip()) >= 25:
                clean = parts[0].strip()
                break

    # 3. Quitar comas con listas excesivas de keywords si la primera parte ya es sustancial
    if ',' in clean:
        parts = clean.split(',')
        if len(parts[0].strip()) >= 30:
            clean = parts[0].strip()

    # 4. Quitar especificaciones técnicas redundantes al final (QHD, 165Hz, 1ms, 4K, 1000R, etc.)
    clean = re.sub(r'\s+(QHD|FHD|4K|UHD|2K|1000R|1500R|1800R|1ms|0\.5ms|165Hz|144Hz|240Hz|120Hz|60Hz|HDR10\+?)\b', '', clean, flags=re.IGNORECASE)

    # 5. Normalizar espacios
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = re.sub(r'^[\s\-\:\,\.]+|[\s\-\:\,\.]+$', '', clean).strip()

    # 6. Límite de longitud lógico (hasta 75 caracteres) sin cortar palabras
    max_len = 75
    if len(clean) > max_len:
        clean = clean[:max_len].rsplit(' ', 1)[0]
        trailing_dangling = ['para', 'de', 'con', 'en', 'y', 'el', 'la', 'los', 'las', 'un', 'una', 'a']
        words = clean.split()
        while words and words[-1].lower() in trailing_dangling:
            words.pop()
        clean = ' '.join(words)
        clean = clean.rstrip(',-:')

    return clean.strip()


def _detect_article(title: str) -> str:
    """
    Detecta 'este', 'esta', 'estos', 'estas' basándose en el núcleo del sujeto (inicio del título).
    """
    first_words = title.strip().lower().split()[:3]
    if not first_words:
        return "este"

    # Sustantivos plurales masculinos y femeninos al inicio
    plurals_m = ["tenis", "audífonos", "audifonos", "auriculares", "sneakers", "jeans", "pants", "lentes", "guantes", "zapatos", "ventiladores"]
    plurals_f = ["zapatillas", "botas", "sandalias", "pantunflas", "calcetas", "baterías", "baterias"]

    # Sustantivos femeninos singulares al inicio
    feminine_nouns = [
        "laptop", "licuadora", "pantalla", "bocina", "chamarra", "playera", "cámara", "camara", 
        "impresora", "consola", "sudadera", "memoria", "batería", "bateria", "mesa", "silla", 
        "computadora", "mochila", "tablet", "tarjeta", "funda", "diadema", "barra de sonido", 
        "base", "lámpara", "lampara", "cafetera", "freidora", "aspiradora", "plancha"
    ]

    title_start = " ".join(first_words)

    for p in plurals_m:
        if title_start.startswith(p):
            return "estos"
    for p in plurals_f:
        if title_start.startswith(p):
            return "estas"
    for f in feminine_nouns:
        if title_start.startswith(f):
            return "esta"

    # Verificación por terminación de la primera palabra relevante
    w0 = first_words[0]
    if w0.endswith("as") and len(w0) > 4:
        return "estas"
    if w0.endswith("os") and len(w0) > 4 and w0 not in ("menos", "chaos"):
        return "estos"
    if w0.endswith("a") and len(w0) > 3 and w0 not in ("dia", "mapa", "sistema", "clima"):
        return "esta"

    return "este"


def _detect_store(product_details: dict, affiliate_link: str = "") -> tuple[str, str]:
    """
    Retorna (nombre_tienda, emoji_tienda), ej: ("Mercado Libre", "💛") o ("Amazon", "📦")
    """
    source = str(product_details.get("source", "")).lower()
    url = str(product_details.get("affiliate_url") or product_details.get("url") or affiliate_link).lower()
    p_id = str(product_details.get("id", "")).upper()

    if "amazon" in source or "amazon" in url or "amzn" in url:
        return "Amazon", "📦"
    if "meli.la" in url or "mercadolibre" in url or p_id.startswith("MLM") or source in ("apify", "ml", "mercadolibre"):
        return "Mercado Libre", "💛"

    return "Tienda en Línea", "🛍️"


def build_post_message(product_details, affiliate_link, platform="facebook"):
    """
    Genera lista de renglones con texto variado para evitar detección de spam.
    platform: "facebook" | "telegram" | "pinterest" | "fb_page"
    """
    niche = product_details.get("niche", "[CAT:GENERAL]")
    discount = str(product_details.get('discount', '')).strip()
    # Limpiar signos negativos (-33% -> 33%), mas/menos y palabras repetidas
    discount = re.sub(r'^[+\-\s]+', '', discount)
    discount = re.sub(r'\s*(off|dto|descuento|de descuento)\s*', '', discount, flags=re.IGNORECASE).strip()
    has_discount = discount and discount not in ('0%', '0', '')

    # Priorizar título limpio de IA si ya existe y es coherente
    raw_title = product_details.get("title", "Oferta Especial")
    ai_clean = (product_details.get("clean_title") or "").strip()

    if ai_clean and ai_clean != raw_title and len(ai_clean) <= 85:
        clean = ai_clean
    else:
        clean = _clean_title(ai_clean or raw_title)

    emoji = _get_category_emoji(clean or raw_title)
    product_title = f"{emoji} {clean}"

    # Detección de tienda (Mercado Libre vs Amazon)
    store_name, store_emoji = _detect_store(product_details, affiliate_link)

    # Detección inteligente de artículo gramatical (este / esta / estos / estas)
    article = _detect_article(clean)

    rng = _get_product_rng(product_details)
    p_name = clean[0].upper() + clean[1:] if clean else ""
    article_cap = article.capitalize()

    if has_discount:
        intro_tmpl = rng.choice(_CONVERSATIONAL_INTROS_DISCOUNT)
        conversational_title = intro_tmpl.format(
            article=article,
            article_cap=article_cap,
            p_name=p_name,
            store_name=store_name,
            discount=discount
        )
    else:
        intro_tmpl = rng.choice(_CONVERSATIONAL_INTROS_NO_DISCOUNT)
        conversational_title = intro_tmpl.format(
            article=article,
            article_cap=article_cap,
            p_name=p_name,
            store_name=store_name
        )

    # Precio
    offer_price = product_details.get('offer_price', '').strip()
    list_price  = product_details.get('list_price', '').strip()
    
    # Calcular ahorro absoluto en pesos
    savings_text = ""
    ahorro = 0.0
    if offer_price and list_price:
        try:
            o_val = float(''.join(c for c in offer_price if c.isdigit() or c == '.'))
            l_val = float(''.join(c for c in list_price if c.isdigit() or c == '.'))
            ahorro = l_val - o_val
            if ahorro > 0:
                ahorro_str = f"{int(ahorro):,}" if ahorro.is_integer() else f"{ahorro:,.2f}"
                savings_tmpl = rng.choice(_SAVINGS_TEMPLATES)
                savings_text = "\n" + savings_tmpl.format(ahorro=ahorro_str)
        except Exception:
            pass

    # ==========================================
    # OVERRIDE: FORMATO ESTRICTO PARA BEBÉS
    # ==========================================
    if niche == "[CAT:BEBES]":
        from core.config import Config
        wa_url = getattr(Config, 'WHATSAPP_CHANNEL_BABY_URL', 'https://gangasmx.com/bebes')
        tg_url = 'https://t.me/Gangas_para_Bebes_MX'
        
        baby_lines = [conversational_title]
        
        if offer_price and list_price:
            discount_str = f" ({discount} OFF)" if has_discount else ""
            baby_lines.append(f"💰 {list_price} ➡️ {offer_price}{discount_str}")
            if ahorro > 0:
                if ahorro.is_integer():
                    baby_lines.append(f"💰 Te ahorras ${int(ahorro):,}.00")
                else:
                    baby_lines.append(f"💰 Te ahorras ${ahorro:,.2f}")
        elif offer_price:
            baby_lines.append(f"💰 {offer_price}")
            
        baby_lines.append(f"📍 Comprar en {store_name}: {affiliate_link}")
        if wa_url:
            baby_lines.append(f"💬 Únete al WhatsApp VIP de Bebés: {wa_url}")
        baby_lines.append(f"🍼 Únete al Telegram exclusivo de Bebés: {tg_url}")
        
        return baby_lines
    # ==========================================

    if offer_price and list_price:
        # Salvaguarda: Verificar que el precio de oferta sea estrictamente menor al original
        try:
            num_o = float(str(offer_price).replace("$", "").replace(",", "").strip())
            num_l = float(str(list_price).replace("$", "").replace(",", "").strip())
            if num_o >= num_l:
                # Datos invertidos o inválidos: descartar list_price para no mostrar precio original menor
                list_price = None
        except Exception:
            pass

    if offer_price and list_price:
        if platform == "telegram":
            striked_price = ''.join(c + '\u0336' for c in str(list_price))
            price_section = f"❌ Precio original: {striked_price}\n🔥 Precio oferta: {offer_price}{savings_text}"
        else:
            price_section = f"❌ Precio original: {list_price}\n🔥 Precio oferta: {offer_price}{savings_text}"
    elif offer_price and offer_price != "Ver precio en el enlace":
        price_section = f"🔥 Precio oferta: {offer_price}"
    else:
        price_section = "🔥 Ver precio especial en el enlace"

    # CTA variado con seed determinista
    cta = rng.choice(_CTAS).format(link=affiliate_link)

    # Urgencia variada
    urgency = rng.choice(_URGENCY)

    # Mención al sitio variada
    site = rng.choice(_SITE_MENTIONS)

    if platform == "telegram":
        tg_tags = rng.choice(_TELEGRAM_HASHTAGS)
        lines = [
            conversational_title,
            "",
            price_section,
            "",
            tg_tags
        ]
    elif platform == "facebook":
        fb_cta = rng.choice(_FB_CTAS).format(link=affiliate_link, store_name=store_name)
        fb_site = rng.choice(_FB_SITE_MENTIONS)
        fb_tg = rng.choice(_FB_TELEGRAM_MENTIONS)
        lines = [
            conversational_title,
            "",
            price_section,
            "",
            fb_cta,
            fb_site,
            fb_tg
        ]
    elif platform == "fb_page":
        fb_cta = rng.choice(_FB_CTAS).format(link=affiliate_link, store_name=store_name)
        fb_site = rng.choice(_FB_SITE_MENTIONS)
        lines = [
            conversational_title,
            "",
            price_section,
            "",
            fb_cta,
            "",
            "👇 ¿Tú qué opinas, lo comprarías? ¡Déjanos tu comentario y etiqueta a quien lo necesita! 👇",
            "",
            fb_site,
        ]
    else:
        lines = [
            conversational_title,
            "",
            price_section,
            "",
            cta,
            "",
            urgency,
            site,
        ]

    # Agregar canal de Telegram y WhatsApp dependiendo de la plataforma y el nicho
    if platform not in ("telegram", "facebook"):
        lines += [
            "",
            rng.choice(_CHANNEL_CTA),
        ]
        
    # Inyectar canales VIP si es nicho Bebés
    if niche == "[CAT:BEBES]":
        from core.config import Config
        wa_url = getattr(Config, 'WHATSAPP_CHANNEL_BABY_URL', 'https://whatsapp.com/channel/0029VbDGpo76BIEnWUILzU1D')
        tg_url = 'https://t.me/Gangas_para_Bebes_MX'
        
        if wa_url:
            lines += ["", f"💬 Únete al WhatsApp VIP de Bebés: {wa_url}"]
        lines += ["", f"🍼 Únete al Telegram exclusivo de Bebés: {tg_url}"]

    if platform == "pinterest":
        lines += ["", rng.choice(_PINTEREST_TAGS)]

    return lines


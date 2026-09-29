import os
import platform
from dotenv import load_dotenv

class ConfigMeta(type):
    """Metaclass con caché de variables de entorno dinámicas."""

    _cache = {}
    _env_loaded = False

    @classmethod
    def _ensure_env_loaded(mcs):
        """Carga .env solo una vez."""
        if not mcs._env_loaded:
            load_dotenv(override=True)
            mcs._env_loaded = True

    @classmethod
    def invalidate_cache(mcs, key=None):
        """Invalida caché (completo o para una clave específica)."""
        if key:
            mcs._cache.pop(key, None)
        else:
            mcs._cache.clear()
        mcs._env_loaded = False

    @staticmethod
    def _parse_group_urls(env_var_name):
        """Helper para parsear lista de URLs de grupos, filtrando PAUSEDs."""
        value = os.getenv(env_var_name, "")
        return list(dict.fromkeys([
            g.strip() for g in value.split(",")
            if g.strip() and not g.strip().upper().startswith("PAUSED")
        ]))

    @property
    def FB_GROUPS(cls):
        ConfigMeta._ensure_env_loaded()
        if "FB_GROUPS" not in ConfigMeta._cache:
            ConfigMeta._cache["FB_GROUPS"] = ConfigMeta._parse_group_urls("FB_GROUP_URLS")
        return ConfigMeta._cache["FB_GROUPS"]

    @property
    def FB_GROUPS_BABY(cls):
        ConfigMeta._ensure_env_loaded()
        if "FB_GROUPS_BABY" not in ConfigMeta._cache:
            ConfigMeta._cache["FB_GROUPS_BABY"] = ConfigMeta._parse_group_urls("FB_GROUPS_BABY_URLS")
        return ConfigMeta._cache["FB_GROUPS_BABY"]

    @property
    def FB_GROUPS_PETS(cls):
        ConfigMeta._ensure_env_loaded()
        if "FB_GROUPS_PETS" not in ConfigMeta._cache:
            ConfigMeta._cache["FB_GROUPS_PETS"] = ConfigMeta._parse_group_urls("FB_GROUPS_PETS_URLS")
        return ConfigMeta._cache["FB_GROUPS_PETS"]

    @property
    def FB_GROUPS_TENIS(cls):
        ConfigMeta._ensure_env_loaded()
        if "FB_GROUPS_TENIS" not in ConfigMeta._cache:
            ConfigMeta._cache["FB_GROUPS_TENIS"] = ConfigMeta._parse_group_urls("FB_GROUPS_TENIS_URLS")
        return ConfigMeta._cache["FB_GROUPS_TENIS"]

    @property
    def FB_GROUPS_MODA(cls):
        ConfigMeta._ensure_env_loaded()
        if "FB_GROUPS_MODA" not in ConfigMeta._cache:
            ConfigMeta._cache["FB_GROUPS_MODA"] = ConfigMeta._parse_group_urls("FB_GROUPS_MODA_URLS")
        return ConfigMeta._cache["FB_GROUPS_MODA"]

    @property
    def FB_PAGE_ID(cls):
        ConfigMeta._ensure_env_loaded()
        if "FB_PAGE_ID" not in ConfigMeta._cache:
            ConfigMeta._cache["FB_PAGE_ID"] = os.getenv("FB_PAGE_ID")
        return ConfigMeta._cache["FB_PAGE_ID"]

    @property
    def FB_PAGE_TOKEN(cls):
        ConfigMeta._ensure_env_loaded()
        if "FB_PAGE_TOKEN" not in ConfigMeta._cache:
            ConfigMeta._cache["FB_PAGE_TOKEN"] = os.getenv("FB_PAGE_TOKEN")
        return ConfigMeta._cache["FB_PAGE_TOKEN"]

    @property
    def SCRAPING_CONFIG(cls):
        """
        Carga scraping_config.json desde el disco en cada acceso (sin caché).

        El panel web y el bot corren en procesos de Linux distintos
        (gangas_api.service / amazon_bot.service); un caché en memoria aquí
        nunca se enteraría de los cambios hechos desde el otro proceso, así
        que se lee siempre del disco para reflejar ediciones del panel
        (ej. max_price) sin necesitar reiniciar el bot.
        """
        from core.storage import json_load
        scraping_config_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scraping_config.json"
        )
        return json_load(scraping_config_file, default={})

class Config(metaclass=ConfigMeta):
    # Cargar variables de entorno iniciales
    load_dotenv(override=True)

    # Telegram
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
    CHANNEL_BABY_ID = os.getenv("TELEGRAM_CHANNEL_BABY_ID")
    CHANNEL_PETS_ID = os.getenv("TELEGRAM_CHANNEL_PETS_ID")
    CHANNEL_TENIS_ID = os.getenv("TELEGRAM_CHANNEL_TENIS_ID")
    CHANNEL_MODA_ID = os.getenv("TELEGRAM_CHANNEL_MODA_ID")
    WHATSAPP_CHANNEL_BABY_URL = os.getenv("WHATSAPP_CHANNEL_BABY_URL")

    # Facebook API (ahora cargadas dinámicamente desde ConfigMeta)

    # Amazon Creators API
    AMAZON_CREATORS_CREDENTIAL_ID = os.getenv("AMAZON_CREATORS_CREDENTIAL_ID")
    AMAZON_CREATORS_CREDENTIAL_SECRET = os.getenv("AMAZON_CREATORS_CREDENTIAL_SECRET")
    AMAZON_CREATORS_CREDENTIAL_VERSION = os.getenv("AMAZON_CREATORS_CREDENTIAL_VERSION")
    AMAZON_CREATORS_MARKETPLACE = os.getenv("AMAZON_CREATORS_MARKETPLACE", "www.amazon.com.mx")
    AMAZON_PARTNER_TAG = os.getenv("AMAZON_PARTNER_TAG")

    # Rutas
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Linux usa su propio archivo de sesión para no compartir cookies de ML con Windows vía OneDrive.
    # Windows conserva storage_state.json que incluye la sesión de ML para el scraper masivo.
    _session_file = "storage_state_linux.json" if platform.system() == "Linux" else "storage_state.json"
    STORAGE_PATH = os.path.join(BASE_DIR, _session_file)
    JSON_QUEUE_FILE = os.path.join(BASE_DIR, "products_list.json")
    JSON_QUEUE_BABY_FILE = os.path.join(BASE_DIR, "products_list_baby.json")
    JSON_QUEUE_PETS_FILE = os.path.join(BASE_DIR, "products_list_pets.json")
    JSON_QUEUE_TENIS_FILE = os.path.join(BASE_DIR, "queue_tenis.json")
    JSON_QUEUE_MODA_FILE = os.path.join(BASE_DIR, "queue_moda.json")
    JSON_DRAFT_FILE = os.path.join(BASE_DIR, "products_draft.json")
    HISTORY_FILE = os.path.join(BASE_DIR, "published_history.json")
    CAPTURES_DIR = os.path.join(BASE_DIR, "captures")
    SCRAPING_CONFIG_FILE = os.path.join(BASE_DIR, "scraping_config.json")

    # Apify
    APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
    APIFY_API_TOKEN1 = os.getenv("APIFY_API_TOKEN1")
    APIFY_API_TOKEN2 = os.getenv("APIFY_API_TOKEN2")

    @classmethod
    def get_apify_tokens(cls):
        import os
        tokens = []
        for key, value in os.environ.items():
            if key.startswith("APIFY_API_TOKEN") and value:
                if value not in tokens:
                    tokens.append(value)
        # Sort them basically by key name length to have APIFY_API_TOKEN first, then 1, 2, 3...
        return sorted(tokens)

    @classmethod
    def get_gemini_keys(cls):
        import os
        pairs = [
            (name, value) for name, value in os.environ.items()
            if name.startswith("GEMINI_API_KEY") and value
        ]
        # GEMINI_API_KEY primero, luego GEMINI_API_KEY1, GEMINI_API_KEY2... (orden por nombre de variable)
        pairs.sort(key=lambda p: p[0])
        keys = []
        for _, value in pairs:
            if value not in keys:
                keys.append(value)
        return keys

    # Filtros de Blacklist (Lista de Exclusión) por Evento
    BLACKLIST_WORDS = [w.strip().lower() for w in os.getenv("BLACKLIST_WORDS", "funda,mica,case,protector,cable,llavero,silicona").split(",") if w.strip()]
    MIN_PRICE = float(os.getenv("MIN_PRICE", "100.0"))
    MIN_DISCOUNT = 20
    MIN_DISCOUNT_PESOS = 500
    MIN_AHORRO_ESTRICTO_PESOS = 150

    @classmethod
    def get_dynamic_config(cls):
        import json, os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraping_config.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "min_discount_pesos": int(data.get("min_discount_pesos", cls.MIN_DISCOUNT_PESOS)),
                    "min_discount": int(data.get("min_discount_pct", cls.MIN_DISCOUNT)),
                    "min_strict": int(data.get("min_strict_savings", cls.MIN_AHORRO_ESTRICTO_PESOS)),
                    "history_ttl_days": int(data.get("history_ttl_days", 21)),
                    "max_price": float(data.get("max_price", 10000.0))
                }
        except Exception:
            return {
                "min_discount_pesos": cls.MIN_DISCOUNT_PESOS,
                "min_discount": cls.MIN_DISCOUNT,
                "min_strict": cls.MIN_AHORRO_ESTRICTO_PESOS,
                "history_ttl_days": 21,
                "max_price": 10000.0
            }


    # Tiempos
    QUEUE_INTERVAL_MINS = 90
    HUMAN_PAUSE_MIN = 5
    HUMAN_PAUSE_MAX = 10


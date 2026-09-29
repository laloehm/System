import json
import os
from core.storage import json_load, json_save_atomic

# Archivos de entrada y salida
RAW_COOKIES_FILE = "raw_tiktok_cookies.json"
TIKTOK_STATE_FILE = "tiktok_state.json"

def main():
    if not os.path.exists(RAW_COOKIES_FILE):
        print(f"❌ Error: No se encontró el archivo '{RAW_COOKIES_FILE}'.")
        print("Asegúrate de haber exportado tus cookies usando la extensión 'Cookie-Editor' y guardarlas en este archivo.")
        return

    try:
        raw_cookies = json_load(RAW_COOKIES_FILE, default=[])
    except Exception as e:
        print(f"❌ Error leyendo el archivo JSON: {e}")
        return

    # Formato que exige Playwright
    playwright_state = {
        "cookies": [],
        "origins": [
            {
                "origin": "https://www.tiktok.com",
                "localStorage": [
                    {
                        "name": "tt-target-idc-sign",
                        "value": "1"
                    }
                ]
            }
        ]
    }

    # Adaptar cada cookie
    for cookie in raw_cookies:
        p_cookie = {
            "name": cookie.get("name", ""),
            "value": cookie.get("value", ""),
            "domain": cookie.get("domain", ""),
            "path": cookie.get("path", "/"),
            "expires": cookie.get("expirationDate", -1),
            "httpOnly": cookie.get("httpOnly", False),
            "secure": cookie.get("secure", False),
            "sameSite": cookie.get("sameSite", "None")
        }
        
        # En Cookie-Editor, SameSite a veces viene como null, "no_restriction" o "unspecified"
        s_site = cookie.get("sameSite")
        if not s_site or s_site == "no_restriction":
            p_cookie["sameSite"] = "None"
        elif s_site == "unspecified":
            p_cookie["sameSite"] = "Lax"
        else:
            # Asegurar que empieza con mayúscula (ej. "lax" -> "Lax", "strict" -> "Strict")
            p_cookie["sameSite"] = s_site.capitalize()

        playwright_state["cookies"].append(p_cookie)

    try:
        json_save_atomic(TIKTOK_STATE_FILE, playwright_state, indent=4)
        print(f"✅ ¡Éxito! Se han convertido {len(raw_cookies)} cookies.")
        print(f"🎉 El archivo '{TIKTOK_STATE_FILE}' ha sido generado correctamente y está listo para usarse.")
    except Exception as e:
        print(f"❌ Error guardando el estado: {e}")

if __name__ == "__main__":
    main()

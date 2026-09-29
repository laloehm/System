import os
import sys
import json
from core.config import Config

def create_twitter_storage_state(auth_token: str, ct0: str = ""):
    auth_token = auth_token.strip()
    ct0 = ct0.strip()

    cookies = [
        {
            "name": "auth_token",
            "value": auth_token,
            "domain": ".x.com",
            "path": "/",
            "expires": 1900000000,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        },
        {
            "name": "auth_token",
            "value": auth_token,
            "domain": ".twitter.com",
            "path": "/",
            "expires": 1900000000,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        }
    ]

    if ct0:
        cookies.extend([
            {
                "name": "ct0",
                "value": ct0,
                "domain": ".x.com",
                "path": "/",
                "expires": 1900000000,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax"
            },
            {
                "name": "ct0",
                "value": ct0,
                "domain": ".twitter.com",
                "path": "/",
                "expires": 1900000000,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax"
            }
        ])

    state_data = {
        "cookies": cookies,
        "origins": []
    }

    tw_path = os.path.join(Config.BASE_DIR, "storage_state_twitter.json")
    with open(tw_path, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)
    print(f"✅ Archivo de sesión creado: {tw_path}")

    main_path = Config.STORAGE_PATH
    if os.path.exists(main_path):
        try:
            with open(main_path, "r", encoding="utf-8") as f:
                main_data = json.load(f)

            existing_cookies = [c for c in main_data.get("cookies", []) if "x.com" not in c.get("domain", "") and "twitter.com" not in c.get("domain", "")]
            existing_cookies.extend(cookies)
            main_data["cookies"] = existing_cookies

            with open(main_path, "w", encoding="utf-8") as f:
                json.dump(main_data, f, indent=2)
            print(f"✅ Cookies de Twitter fusionadas exitosamente en: {main_path}")
        except Exception as e:
            print(f"⚠️ No se pudo fusionar en {main_path}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python import_twitter_cookies.py <auth_token> [ct0]")
        sys.exit(1)

    tok = sys.argv[1]
    ct = sys.argv[2] if len(sys.argv) > 2 else ""
    create_twitter_storage_state(tok, ct)

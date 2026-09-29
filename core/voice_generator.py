import os
import json
import asyncio
import urllib.request
import urllib.error
import re


def number_to_words_es(n: int) -> str:
    if n == 0:
        return "cero"
    
    def _convert_group(val: int, is_mil: bool = False) -> str:
        c = val // 100
        d = (val % 100) // 10
        u = val % 10
        
        parts = []
        
        # Centenas
        if c == 1:
            if d == 0 and u == 0:
                parts.append("cien")
            else:
                parts.append("ciento")
        elif c == 2:
            parts.append("doscientos")
        elif c == 3:
            parts.append("trescientos")
        elif c == 4:
            parts.append("cuatrocientos")
        elif c == 5:
            parts.append("quinientos")
        elif c == 6:
            parts.append("seiscientos")
        elif c == 7:
            parts.append("setecientos")
        elif c == 8:
            parts.append("ochocientos")
        elif c == 9:
            parts.append("novecientos")
            
        # Decenas y unidades
        rest = val % 100
        if rest > 0:
            if rest == 10:
                parts.append("diez")
            elif rest == 20:
                parts.append("veinte")
            elif 11 <= rest <= 19:
                esp = {
                    11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
                    16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve"
                }
                parts.append(esp[rest])
            elif 21 <= rest <= 29:
                nombres = ["veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"]
                name = nombres[rest - 20]
                if is_mil and rest == 21:
                    name = "veintiún"
                parts.append(name)
            else:
                dec_names = ["", "diez", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
                uni_names = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
                if d == 0:
                    if is_mil and u == 1:
                        parts.append("un")
                    else:
                        parts.append(uni_names[u])
                else:
                    if u == 0:
                        parts.append(dec_names[d])
                    else:
                        if is_mil and u == 1:
                            parts.append(f"{dec_names[d]} y un")
                        else:
                            parts.append(f"{dec_names[d]} y {uni_names[u]}")
        
        res = " ".join(parts)
        if is_mil and res in ("un", "uno"):
            return ""
        return res

    miles = n // 1000
    unidades = n % 1000
    
    parts = []
    if miles > 0:
        miles_text = _convert_group(miles, is_mil=True)
        if miles_text:
            parts.append(f"{miles_text} mil")
        else:
            parts.append("mil")
            
    if unidades > 0:
        parts.append(_convert_group(unidades))
        
    return " ".join(parts).strip()


def normalize_prices_for_tts(text: str) -> str:
    # Quitar centavos .00 para evitar que la voz diga "punto cero cero"
    text = re.sub(r'\.00\b', '', text)
    
    # 1. Reemplazar "$ X" o "$X" por "X pesos"
    text = re.sub(r'\$\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)\s*(pesos?)?', r'\1 pesos', text, flags=re.IGNORECASE)
    
    # 2. Quitar la coma de miles, ej: "1,599" -> "1599"
    def clean_comma(match):
        return match.group(0).replace(",", "")
    text = re.sub(r'[0-9]+,[0-9]+', clean_comma, text)
    
    # 3. Convertir números de pesos a palabras
    def num_replacer(match):
        num_str = match.group(1)
        suffix = match.group(2) or ""
        try:
            val = int(num_str)
            if 1 <= val <= 999999:
                words = number_to_words_es(val)
                # Apócope de uno/veintiuno antes de "pesos"
                if "pesos" in suffix.lower():
                    if words.endswith("veintiuno"):
                        words = words[:-9] + "veintiún"
                    elif words.endswith("uno"):
                        words = words[:-3] + "un"
                return f"{words}{suffix}"
        except:
            pass
        return match.group(0)

    # Buscar cualquier número seguido de " pesos" o " peso"
    text = re.sub(r'\b([0-9]+)(\s*pesos?)\b', num_replacer, text, flags=re.IGNORECASE)
    
    # 4. Convertir porcentajes a palabras, ej: "52%" -> "cincuenta y dos por ciento"
    def pct_replacer(match):
        num_str = match.group(1)
        try:
            val = int(num_str)
            if 1 <= val <= 100:
                words = number_to_words_es(val)
                # Apócope de uno/veintiuno para porcentajes
                if words.endswith("veintiuno"):
                    words = words[:-9] + "veintiún"
                elif words.endswith("uno"):
                    words = words[:-3] + "un"
                return f"{words} por ciento"
        except:
            pass
        return match.group(0)
        
    text = re.sub(r'\b([0-9]+)\s*%', pct_replacer, text)
    
    return text


def _generate_elevenlabs(text: str, output_path: str, api_key: str) -> bool:
    voice_id = "pNInz6obpgDQGcFmaJgB"  # Adam — voz premade, disponible en plan gratuito
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    normalized = normalize_prices_for_tts(text)
    clean_text = " ".join(normalized.replace("\n", " ").split())
    data = {
        "text": clean_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.75,
            "similarity_boost": 0.85,
            "style": 0.0,
            "use_speaker_boost": True
        },
    }

    req = urllib.request.Request(
        url, headers=headers, data=json.dumps(data).encode("utf-8")
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            audio_bytes = response.read()

        if len(audio_bytes) < 100:
            print(f"[Voice] ElevenLabs: respuesta demasiado corta ({len(audio_bytes)} bytes)")
            return False

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        print(f"[Voice] ElevenLabs OK: {output_path} ({len(audio_bytes)} bytes)")
        return True

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"[Voice] ElevenLabs HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print(f"[Voice] ElevenLabs error: {e}")
        return False


def _generate_edge_tts(text: str, output_path: str) -> bool:
    try:
        import edge_tts

        normalized = normalize_prices_for_tts(text)
        clean_text = " ".join(normalized.replace("\n", " ").split())

        async def _run():
            communicate = edge_tts.Communicate(clean_text, "es-MX-JorgeNeural", rate="+12%")
            await communicate.save(output_path)

        # Corre en un thread (to_thread), así que no hay event loop activo aquí
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            print(f"[Voice] edge-tts OK: {output_path}")
            return True

        print("[Voice] edge-tts: archivo vacío o no generado")
        return False

    except ImportError:
        print("[Voice] edge-tts no instalado. Ejecuta: pip install edge-tts")
        return False
    except Exception as e:
        print(f"[Voice] edge-tts error: {e}")
        return False


def generate_scene_audio(text: str, output_path: str):
    """
    Genera audio para una escena.
    Intenta ElevenLabs con rotación de múltiples API keys.
    Si todas las API keys fallan o no hay ninguna configurada, usa edge-tts como fallback.
    Retorna el path si tuvo éxito, None si falló.
    """
    # 1. Recopilar todas las API keys de ElevenLabs de forma flexible
    api_keys = []
    
    # Buscar variables individuales ELEVENLABS_API_KEY, ELEVENLABS_API_KEY_1, ELEVENLABS_API_KEY_2, etc.
    for env_key in sorted(os.environ.keys()):
        if env_key == "ELEVENLABS_API_KEY" or env_key.startswith("ELEVENLABS_API_KEY_"):
            val = os.getenv(env_key, "").strip()
            if val:
                # Si el valor contiene comas, dividirlo
                if "," in val:
                    for k in val.split(","):
                        k_clean = k.strip()
                        if k_clean and k_clean not in api_keys:
                            api_keys.append(k_clean)
                else:
                    if val not in api_keys:
                        api_keys.append(val)

    # 2. Intentar generar con cada API key disponible
    if api_keys:
        print(f"[Voice] Encontradas {len(api_keys)} API keys de ElevenLabs. Iniciando intentos...")
        for idx, key in enumerate(api_keys):
            masked_key = key[:6] + "..." + key[-4:] if len(key) > 10 else "..."
            print(f"[Voice] Intentando ElevenLabs con Key #{idx+1} ({masked_key})...")
            if _generate_elevenlabs(text, output_path, key):
                return output_path
            print(f"[Voice] Key #{idx+1} falló o superó el límite.")
        print("[Voice] Todas las API keys de ElevenLabs fallaron — usando edge-tts como fallback...")
    else:
        print("[Voice] Sin ELEVENLABS_API_KEY configuradas — usando edge-tts...")

    # 3. Fallback a edge-tts
    if _generate_edge_tts(text, output_path):
        return output_path

    print(f"[Voice] No se pudo generar audio para: {text[:60]}")
    return None


def process_script(script_path: str, output_dir: str):
    """
    Lee guion.json y genera un archivo de audio por cada escena.
    Retorna lista de (key, path, text) solo de las escenas exitosas.
    """
    os.makedirs(output_dir, exist_ok=True)
    audio_paths = []

    if not os.path.exists(script_path):
        print(f"[Voice] Error: guion.json no encontrado en {script_path}")
        return []

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    scenes = {k: v for k, v in script_data.items() if k.startswith("escena")}

    for key, text in scenes.items():
        idx = key.replace("escena", "")
        out_path = os.path.join(output_dir, f"audio_{idx}.mp3")
        result = generate_scene_audio(text, out_path)
        if result:
            audio_paths.append((key, out_path, text))
        else:
            print(f"[Voice] Escena {key} omitida por error en generación")

    print(f"[Voice] {len(audio_paths)}/{len(scenes)} escenas generadas correctamente")
    return audio_paths

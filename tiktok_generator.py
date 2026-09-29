"""
TikTok Video Generator - UGC / Educativo
Usa Google Labs Flow para generar imágenes IA y el Advanced Video Maker para efectos.
"""
import os
import json
import asyncio
from core.voice_generator import generate_scene_audio
from core.advanced_video_maker import create_final_video
from core.flow_image_generator import generate_flow_images

VIDEOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

def _download_image(url, dest_path):
    """Descarga una imagen de URL a disco. Retorna True si tuvo éxito."""
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(dest_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"[IMG] Error descargando imagen: {e}")
    return False

def create_tiktok_video(product, music_path=None, output_path=None):
    """
    Genera un video TikTok educativo (UGC) usando imágenes de IA + producto real.
    """
    p_id        = product.get("id", "unknown")
    image_url   = product.get("image_url", "")
    screenshot  = product.get("screenshot", "")

    if not output_path:
        output_path = os.path.join(VIDEOS_DIR, f"{p_id}.mp4")

    # 0. Filtro estricto de viabilidad económica (Ahorro >= $250 y Precio >= $300)
    # Protege cuota de ElevenLabs y recursos de renderizado en publicaciones automáticas.
    try:
        p_price = float(product.get("price") or 0.0)
        p_orig = float(product.get("original_price") or 0.0)
        p_savings = (p_orig - p_price) if p_orig > p_price else 0.0
        is_forced = bool(product.get("force_publish") or product.get("force_video"))
        if not is_forced and (p_savings < 250.0 or p_price < 300.0):
            print(f"[VIDEO] ⏭️ Omitiendo video para {p_id}: No cumple umbral mínimo (Precio: ${p_price:.0f} >= $300, Ahorro: ${p_savings:.0f} >= $250)")
            return None
    except Exception as thresh_err:
        print(f"[VIDEO] ⚠️ Error evaluando umbral económico: {thresh_err}")

    print(f"[VIDEO] Generando UGC para: {p_id}")

    # 1. Cargar guion y prompt de imagen
    guion_lines = []
    image_prompts = []
    default_prompt = f"A high quality aesthetic lifestyle photo related to {product.get('title', 'product')}"
    
    # Prioridad 1: Si vienen directamente en el dict del producto
    if product.get("guion_lines"):
        guion_lines = product.get("guion_lines")
    if product.get("image_prompts"):
        image_prompts = product.get("image_prompts")
        
    if not guion_lines or not image_prompts:
        guion_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guion.json")
        if not os.path.exists(guion_path):
            guion_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guion.json")
            
        if os.path.exists(guion_path):
            try:
                with open(guion_path, "r", encoding="utf-8") as f:
                    guion_data = json.load(f)
                    if not guion_lines:
                        guion_lines = [guion_data.get(f"escena{i}", "") for i in range(1, 7)]
                        guion_lines = [l for l in guion_lines if l]
                    if not image_prompts:
                        if "image_prompt_1" in guion_data:
                            image_prompts.append(guion_data["image_prompt_1"])
                            image_prompts.append(guion_data.get("image_prompt_2", guion_data["image_prompt_1"]))
                            image_prompts.append(guion_data.get("image_prompt_3", guion_data["image_prompt_1"]))
                        elif "image_prompt" in guion_data:
                            image_prompts = [guion_data["image_prompt"]] * 3
            except Exception as e:
                print(f"[VIDEO] Error cargando guion.json: {e}")

    if not image_prompts:
        image_prompts = [default_prompt] * 3

    if not guion_lines:
        guion_lines = [
            "¿Sabías esto sobre tu mascota?",
            "El cuidado diario es súper importante.",
            "Muchos cometen este error básico.",
            "Por suerte, hay soluciones prácticas.",
            "Encontré esto en oferta hoy.",
            "Revisa el enlace en el perfil."
        ]

    # 2. Obtener la imagen real del producto
    product_img_path = None
    if image_url and image_url.startswith("http"):
        temp_img = os.path.join(VIDEOS_DIR, f"{p_id}_clean_img.jpg")
        if _download_image(image_url, temp_img):
            product_img_path = temp_img
    
    if not product_img_path and screenshot and os.path.exists(screenshot):
        product_img_path = screenshot
        
    if not product_img_path:
        # Fallback de emergencia
        product_img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "placeholder.jpg")
        # Asegurar que el placeholder existe o crearlo
        if not os.path.exists(product_img_path):
            from PIL import Image
            img = Image.new('RGB', (1080, 1920), color = 'black')
            img.save(product_img_path)

    # 3. Generar las imágenes hiperrealistas con IA (Google Flow via Playwright)
    ai_base_path = os.path.join(VIDEOS_DIR, f"{p_id}_ai_lifestyle")
    print(f"[FLOW] Llamando a Playwright para generar {len(image_prompts)} imágenes IA...")
    ai_images = asyncio.run(generate_flow_images(image_prompts, ai_base_path))
    
    if not ai_images:
        print("[FLOW] Falló la generación de IA. Usando la imagen del producto para todo el video.")

    # 4. Generar Voz (TTS) para cada escena
    audio_data = []
    print(f"[TTS] Generando voz para {len(guion_lines)} líneas...")
    for idx, line in enumerate(guion_lines):
        if not line.strip():
            continue
        temp_voice_path = output_path + f".voice_{idx}.mp3"
        try:
            result = generate_scene_audio(line, temp_voice_path)
            if result and os.path.exists(temp_voice_path):
                audio_data.append((idx, temp_voice_path, line))
                print(f"[TTS] Escena {idx+1} lista.")
            else:
                print(f"[TTS] Error generando audio escena {idx+1}")
        except Exception as e:
            print(f"[TTS] Exception en escena {idx+1}: {e}")

    if not audio_data:
        print("[VIDEO] Error crítico: No se generó ningún audio.")
        return None

    # 5. Ensamblar lista de imágenes para el motor de video avanzado
    # Mapeo: Las primeras 3 escenas usan IA 1, IA 2, IA 3.
    # Si hay una escena 4 educativa, repite IA 3.
    # Las últimas 2 (CTA / Producto) usan la imagen real de Amazon.
    images_paths = []
    total_scenes = len(audio_data)
    
    for i in range(total_scenes):
        if i >= total_scenes - 2: # Últimas 2 escenas muestran el producto
            images_paths.append(product_img_path)
        else:
            ai_idx = min(i, len(ai_images) - 1)
            if ai_images and os.path.exists(ai_images[ai_idx]):
                images_paths.append(ai_images[ai_idx])
            else:
                print(f"[VIDEO] Imagen IA {ai_idx} no disponible. Usando fallback.")
                images_paths.append(product_img_path)

    # 6. Renderizar Video Final
    print("[VIDEO] Delegando renderizado al motor avanzado...")
    final_video_path = create_final_video(images_paths, audio_data, output_path)
    
    # 7. Limpiar audios temporales
    for _, voice_path, _ in audio_data:
        if os.path.exists(voice_path):
            try: os.remove(voice_path)
            except: pass
            
    print(f"[OK] Video UGC listo: {final_video_path}")
    return final_video_path

if __name__ == "__main__":
    test_product = {
        "id": "TEST_UGC_001",
        "title": "Cama ortopédica para perro",
        "image_url": ""
    }
    create_tiktok_video(test_product)

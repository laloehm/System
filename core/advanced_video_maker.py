import os
import textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    from moviepy.editor import (
        ImageClip, CompositeVideoClip, AudioFileClip,
        concatenate_videoclips, VideoClip, CompositeAudioClip,
        concatenate_audioclips, AudioClip,
    )
except ImportError:
    pass

# TikTok acepta 720p; renderiza ~2.25x más rápido que 1080p
RESOLUTION = (720, 1280)

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
]


def _load_font(size: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _create_subtitle_overlay(text: str, duration: float, resolution=RESOLUTION):
    """Subtítulo PIL: texto blanco con sombra negra. Sin ImageMagick."""
    font_size = 46
    font = _load_font(font_size)
    line_height = font_size + 14
    max_chars = 24

    overlay = Image.new("RGBA", resolution, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    lines = textwrap.wrap(text, width=max_chars)
    total_h = len(lines) * line_height
    y_start = resolution[1] - total_h - 120

    stroke = [(-2,-2),(-2,0),(-2,2),(0,-2),(0,2),(2,-2),(2,0),(2,2)]

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (resolution[0] - w) // 2
        y = y_start + i * line_height
        for dx, dy in stroke:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 210))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    rgb_arr = np.array(overlay.convert("RGB"))
    alpha_arr = np.array(overlay.split()[3]).astype(float) / 255.0

    clip = ImageClip(rgb_arr).set_duration(duration)
    mask = ImageClip(alpha_arr, ismask=True).set_duration(duration)
    return clip.set_mask(mask)


def _fit_image(image_path: str, resolution=RESOLUTION, zoom: bool = False) -> np.ndarray:
    """
    Escala y recorta la imagen al centro.
    Si zoom=True aplica un 15% extra de escala (efecto estático, cero costo por frame).
    """
    img = Image.open(image_path).convert("RGB")
    img_ratio = img.width / img.height
    target_ratio = resolution[0] / resolution[1]

    if img_ratio > target_ratio:
        new_h = resolution[1]
        new_w = int(new_h * img_ratio)
    else:
        new_w = resolution[0]
        new_h = int(new_w / img_ratio)

    if zoom:
        new_w = int(new_w * 1.15)
        new_h = int(new_h * 1.15)

    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - resolution[0]) // 2
    top = (new_h - resolution[1]) // 2
    img = img.crop((left, top, left + resolution[0], top + resolution[1]))
    return np.array(img)


def build_scene_clip(image_path, audio_path, text, resolution=RESOLUTION, is_reused=False, scene_index=0):
    """Construye un clip de escena con efectos dinámicos (zoom/paneo) + subtítulo PIL + audio.
    Evita recortar el producto colocando la imagen completa centrada sobre un fondo difuminado.
    Añade una pequeña pausa al final para mejorar el ritmo de la locución."""
    audio_clip = AudioFileClip(audio_path)
    original_audio_duration = audio_clip.duration
    
    # Pausa de 0.1 segundos al final de cada escena (ritmo dinámico)
    pause_duration = 0.1
    total_duration = original_audio_duration + pause_duration

    # Crear un AudioClip de silencio y concatenarlo para rellenar de forma limpia
    # Esto evita el uso de CompositeAudioClip que genera stutters y clics digitales en MoviePy.
    silence_clip = AudioClip(lambda t: 0.0, duration=pause_duration)
    audio_padded = concatenate_audioclips([audio_clip, silence_clip])

    # 1. Cargar imagen original (con canal alfa si existe)
    img_obj = Image.open(image_path).convert("RGBA")
    img_w, img_h = img_obj.size
    img_ratio = img_w / img_h
    target_ratio = resolution[0] / resolution[1]

    # 2. Generar el fondo difuminado (Cover)
    if img_ratio > target_ratio:
        bg_h = resolution[1]
        bg_w = int(bg_h * img_ratio)
    else:
        bg_w = resolution[0]
        bg_h = int(bg_w / img_ratio)
        
    bg_resized = img_obj.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
    bg_left = (bg_w - resolution[0]) // 2
    bg_top = (bg_h - resolution[1]) // 2
    bg_cropped = bg_resized.crop((bg_left, bg_top, bg_left + resolution[0], bg_top + resolution[1]))
    
    # Aplicar desenfoque gaussiano y oscurecer el fondo para mejor contraste
    bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=30))
    bg_darkened = Image.new("RGBA", resolution, (0, 0, 0, 110)) # capa semitransparente negra
    bg_final = Image.alpha_composite(bg_blurred, bg_darkened)

    # 3. Generar el producto en primer plano sin recortar (Contain)
    # Dejamos un margen lateral de 40px y un margen vertical de 300px para que quepan subtítulos
    max_w = resolution[0] - 40
    max_h = resolution[1] - 300
    
    if img_ratio > (max_w / max_h):
        fg_w = max_w
        fg_h = int(fg_w / img_ratio)
    else:
        fg_h = max_h
        fg_w = int(fg_h * img_ratio)
        
    fg_resized = img_obj.resize((fg_w, fg_h), Image.Resampling.LANCZOS)
    
    # Pegar el producto centrado en el lienzo
    fg_x = (resolution[0] - fg_w) // 2
    fg_y = (resolution[1] - fg_h) // 2
    bg_final.paste(fg_resized, (fg_x, fg_y), fg_resized)
    
    # Lienzo final en modo RGB
    canvas = bg_final.convert("RGB")

    # 4. Escalar el lienzo un 25% extra para tener margen de zoom y paneo
    scale_factor = 1.25
    base_w = int(resolution[0] * scale_factor)
    base_h = int(resolution[1] * scale_factor)
    base_img = canvas.resize((base_w, base_h), Image.Resampling.LANCZOS)

    # Determinar el tipo de movimiento según el índice de la escena:
    # 0 = Zoom In (Acercamiento)
    # 1 = Pan Up (Desplazamiento hacia arriba)
    # 2 = Zoom Out (Alejamiento)
    # 3 = Pan Down (Desplazamiento hacia abajo)
    movement_type = scene_index % 4

    def get_frame(t):
        progress = min(t / total_duration, 1.0)
        
        if movement_type == 0:
            # Zoom In: factor aumenta de 1.0 a 1.15
            factor = 1.0 + 0.15 * progress
            curr_w = int(base_w * factor)
            curr_h = int(base_h * factor)
            resized = base_img.resize((curr_w, curr_h), Image.Resampling.BILINEAR)
            left = (curr_w - resolution[0]) // 2
            top = (curr_h - resolution[1]) // 2
            cropped = resized.crop((left, top, left + resolution[0], top + resolution[1]))
            
        elif movement_type == 1:
            # Pan Up: zoom fijo en 1.1x, paneo de abajo hacia arriba
            factor = 1.10
            curr_w = int(base_w * factor)
            curr_h = int(base_h * factor)
            resized = base_img.resize((curr_w, curr_h), Image.Resampling.BILINEAR)
            left = (curr_w - resolution[0]) // 2
            max_top = curr_h - resolution[1]
            top = int(max_top * (1.0 - 0.25 * progress))
            cropped = resized.crop((left, top, left + resolution[0], top + resolution[1]))
            
        elif movement_type == 2:
            # Zoom Out: factor disminuye de 1.15 a 1.0
            factor = 1.15 - 0.15 * progress
            curr_w = int(base_w * factor)
            curr_h = int(base_h * factor)
            resized = base_img.resize((curr_w, curr_h), Image.Resampling.BILINEAR)
            left = (curr_w - resolution[0]) // 2
            top = (curr_h - resolution[1]) // 2
            cropped = resized.crop((left, top, left + resolution[0], top + resolution[1]))
            
        else:
            # Pan Down: zoom fijo en 1.1x, paneo de arriba hacia abajo
            factor = 1.10
            curr_w = int(base_w * factor)
            curr_h = int(base_h * factor)
            resized = base_img.resize((curr_w, curr_h), Image.Resampling.BILINEAR)
            left = (curr_w - resolution[0]) // 2
            max_top = curr_h - resolution[1]
            top = int(max_top * (0.25 * progress))
            cropped = resized.crop((left, top, left + resolution[0], top + resolution[1]))

        return np.array(cropped)

    video_clip = VideoClip(make_frame=get_frame, duration=total_duration)
    subtitle_clip = _create_subtitle_overlay(text, original_audio_duration, resolution)
    final_clip = CompositeVideoClip([video_clip, subtitle_clip], size=resolution)
    final_clip = final_clip.set_audio(audio_padded)
    return final_clip


def create_final_video(images_paths, audio_data, output_path):
    """
    Ensambla todas las escenas en el video final.
    audio_data: lista de (escena_id, audio_path, text)
    """
    if not images_paths:
        print("[Video] Error: no hay imágenes.")
        return None

    print(f"[Video] Construyendo {len(audio_data)} escenas a {RESOLUTION[0]}x{RESOLUTION[1]}...")
    clips = []

    for i, (escena_id, aud_path, text) in enumerate(audio_data):
        is_reused = i >= len(images_paths)
        img_path = images_paths[i] if not is_reused else images_paths[i % len(images_paths)]
        print(f"[Video] Escena {i+1}/{len(audio_data)}: {os.path.basename(img_path)}")
        clips.append(build_scene_clip(img_path, aud_path, text, is_reused=is_reused, scene_index=i))

    print("[Video] Concatenando y exportando...")
    final_video = concatenate_videoclips(clips, method="chain")
    final_video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger=None,
    )
    print(f"[Video] Exportado: {output_path}")
    return output_path

"""
core/ai_service.py

Servicio centralizado para todas las operaciones de IA con Google Gemini.
Encapsula la lógica de generación de contenido, visión por IA, y procesamiento.
"""

import os
import json
import aiohttp
import asyncio
from typing import Optional, Dict, Any


def generate_with_gemini_rotation(contents, model_name: str = "gemini-flash-latest"):
    """
    Genera contenido con Gemini (SDK sincrono) rotando entre todas las
    GEMINI_API_KEY* configuradas en .env. Si una clave devuelve error de
    cuota (429/quota), reintenta la misma llamada con la siguiente clave.

    `contents` acepta lo mismo que GenerativeModel.generate_content(): un
    string, o una lista de partes (ej. [prompt, imagen] para vision).
    """
    import google.generativeai as genai
    from core.config import Config

    keys = Config.get_gemini_keys()
    if not keys:
        raise RuntimeError("No hay ninguna GEMINI_API_KEY configurada en .env")

    last_error = None
    for key in keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name)
            return model.generate_content(contents)
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if "429" in str(e) or "quota" in msg or "rate limit" in msg or "resourceexhausted" in msg:
                print(f"[GEMINI ROTATION] Clave agotada/limitada, probando siguiente...")
                continue
            raise
    raise last_error


async def generate_with_gemini_rotation_rest(url_template: str, payload: dict, timeout_seconds: int = 15):
    """
    Igual que generate_with_gemini_rotation pero via REST/aiohttp (para llamadas
    async que no usan el SDK). `url_template` debe contener "{key}" donde va la
    API key, ej: ".../generateContent?key={key}".
    Retorna el dict de respuesta JSON ya parseado, o lanza la ultima excepcion.
    """
    from core.config import Config

    keys = Config.get_gemini_keys()
    if not keys:
        raise RuntimeError("No hay ninguna GEMINI_API_KEY configurada en .env")

    last_error = None
    for key in keys:
        try:
            url = url_template.format(key=key)
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as resp:
                    if resp.status == 429:
                        print(f"[GEMINI ROTATION] Clave agotada/limitada (429), probando siguiente...")
                        last_error = RuntimeError(f"429 quota exceeded")
                        continue
                    resp.raise_for_status()
                    return await resp.json()
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if "429" in str(e) or "quota" in msg or "rate limit" in msg:
                continue
            raise
    raise last_error


async def generate_product_script(product: Dict[str, Any]) -> str:
    """
    Genera un guion de 6 líneas (Problema+Beneficio+CTA) para un producto,
    usando Gemini con rotación de claves. Si Gemini falla o no hay clave
    configurada, usa una plantilla de respaldo. Retorna el guion como un
    solo string (una línea por renglón, separadas por \\n).
    """
    from core.config import Config

    title = product.get("title", "este producto")
    offer = product.get("offer_price", "")
    original_p = product.get("list_price", "")
    category = product.get("category", "")
    price_info = "Tiene un gran descuento actualmente. (NO mencionar el precio exacto)"

    prompt = (
        f"Eres un experto en copywriting digital y creador de contenido viral de TikTok/Shorts en México, especializado en suplementos, tecnología y estilo de vida.\n"
        f"Tu objetivo es crear un video de OFERTA que identifica un problema, muestra beneficios y convoca a la acción inmediata para promocionar este producto.\n\n"
        f"Datos del producto:\n"
        f"- Producto: {title}\n"
        f"- Contexto de oferta: {price_info}\n"
        f"{'- Categoría: ' + category if category else ''}\n\n"
        f"ESTRUCTURA OBLIGATORIA (6 líneas):\n"
        f"LÍNEAS 1-2 (PROBLEMA): Identifica un dolor, frustración o necesidad real del usuario. SIN preguntas.\n"
        f"LÍNEAS 3-4 (BENEFICIO): Cómo este producto RESUELVE exactamente ese problema. Beneficios concretos.\n"
        f"LÍNEAS 5-6 (CTA): Línea 5 = invitación al link. Línea 6 = urgencia + refuerzo final.\n\n"
        f"REGLAS OBLIGATORIAS:\n"
        f"1. TONO: Natural, conversacional, maduro. SIN emojis, SIN '¿Buscas..?', SIN falsas introducciones.\n"
        f"2. PRECIOS: NUNCA menciones cifras exactas. Usa: 'costo increíblemente bajo', 'precio que vale la pena', 'descuento real'.\n"
        f"3. TIMING: Cada línea debe durar 5-8 segundos al leerla. Pensadas para video corto (30-45s total).\n"
        f"4. FORMATO: 6 líneas, UNA POR LÍNEA. SIN números, SIN puntos, SIN guiones al inicio.\n\n"
        f"Salida: Devuelve ÚNICAMENTE las 6 líneas exactas, nada más."
    )

    fallback_lines = [
        f"¿Buscas el mejor precio para {title}?",
        "Acabamos de encontrar esta increíble oferta.",
        f"De un precio original de {original_p or 'su costo regular'}, bajó considerablemente.",
        f"Llévatelo ahora por solo {offer or 'el mejor precio'} con un gran descuento.",
        "Consigue el tuyo en el enlace de la descripción de este video.",
    ]

    if not Config.get_gemini_keys():
        return "\n".join(fallback_lines)

    lines = []
    try:
        response = generate_with_gemini_rotation(prompt)
        if response and response.text:
            lines = [l.strip() for l in response.text.strip().splitlines() if l.strip()][:6]
    except Exception as e:
        print(f"[AI_SERVICE] Error generando guion de producto: {e}")

    return "\n".join(lines or fallback_lines)


class AIService:
    """Servicio centralizado de IA (Google Gemini)."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el servicio de IA.

        Args:
            api_key: Clave de API de Google Gemini. Si es None, se rota entre
                todas las GEMINI_API_KEY* configuradas en .env.
        """
        from core.config import Config

        self.api_keys = [api_key] if api_key else Config.get_gemini_keys()
        self.api_key = self.api_keys[0] if self.api_keys else None

        if self.api_keys:
            print(f"[AI_SERVICE] Gemini inicializado correctamente ({len(self.api_keys)} clave(s) disponibles)")
        else:
            print("[AI_SERVICE] GEMINI_API_KEY no configurada")

    async def generate_6_lines(self, product: Dict[str, Any]) -> Optional[str]:
        """
        Genera 6 líneas de descripción para un producto usando Gemini.

        Args:
            product: Diccionario con datos del producto (title, price, original_price, etc.)

        Returns:
            String con 6 líneas de descripción, o None si falla.
        """
        if not self.api_key:
            return None

        try:
            title = product.get("title", "")
            price = product.get("price", product.get("offer_price", ""))
            original = product.get("original_price", product.get("list_price", ""))
            discount = product.get("discount", "")

            prompt = f"""
Eres un copywriter de marketing para redes sociales. Genera EXACTAMENTE 6 líneas (una por línea) de descripción enganchante para este producto:

Producto: {title}
Precio: {price}
Precio Original: {original}
Descuento: {discount}

Requisitos:
- 6 líneas exactas
- Cada línea es una propuesta de valor o argumento de venta
- Sin emojis
- Sin hashtags
- Directo al punto
- Tono entusiasta pero profesional

Devuelve SOLO las 6 líneas, nada más."""

            try:
                response = generate_with_gemini_rotation(prompt)
                lines = response.text.strip().split('\n')
                lines = [l.strip() for l in lines if l.strip()]
                return "\n".join(lines[:6])  # Asegurar exactamente 6 líneas
            except Exception as e:
                print(f"[AI_SERVICE] SDK falló ({e}), probando via REST...")
                return await self._generate_6_lines_rest(prompt)

        except Exception as e:
            print(f"[AI_SERVICE] Error generando 6 líneas: {e}")
            return None

    async def _generate_6_lines_rest(self, prompt: str) -> Optional[str]:
        """Fallback a REST API de Gemini (con rotación de claves) si el SDK falla."""
        if not self.api_keys:
            return None

        try:
            url_template = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 256,
                }
            }
            data = await generate_with_gemini_rotation_rest(url_template, payload)
            content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            lines = content.strip().split('\n')
            lines = [l.strip() for l in lines if l.strip()]
            return "\n".join(lines[:6])
        except Exception as e:
            print(f"[AI_SERVICE] Error en REST fallback: {e}")
            return None


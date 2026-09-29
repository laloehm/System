import os
import asyncio
import glob
import aiohttp
import random
import sys
import re
import json
from datetime import datetime, timedelta
from core.config import Config
from core.storage import json_load, json_save_atomic
from core.utils import is_product_ready_for_publication
from core.ai_service import AIService

class TelegramBot:
    def __init__(self, token, chat_id, orchestrator):
        self.token = token
        self.chat_id = chat_id
        self.orchestrator = orchestrator
        self.offset = 0
        _default_state = {"paused": False, "fb_paused": False, "mode": "both", "queue_mode": False,
                          "active_networks": {"facebook": True, "facebook_bebes": True, "facebook_pets": True, "facebook_moda": True, "facebook_tenis": True, "fb_page": True, "telegram": True, "twitter": True, "web": True, "youtube": True, "pinterest": False, "tiktok": False},
                          "video_niches": {"general": True, "baby": False, "pets": True, "moda": True, "tenis": True},
                          "video_mode": "normal"}
        self._state_file = os.path.join(Config.BASE_DIR, "user_state.json")
        _loaded = json_load(self._state_file, default={})
        if _loaded:
            _default_state.update(_loaded)
            print("[STATE] user_state cargado desde disco.")
        self.user_state = _default_state
        self.ai_service = AIService()
        self._send_session = None
        self._poll_session = None
        self.chat_history = []

    def _clear_all_active_states(self):
        """Limpia TODOS los estados activos del usuario. Se llama al escapar con comandos /."""
        active_state_keys = [
            "queue_editing_product_id",
            "queue_editing_field",
            "queue_search_mode",
            "history_search_mode",
            "fb_group_search_mode",
            "awaiting_guion_approval",
            "awaiting_custom_script",
            "awaiting_custom_script_product_id",
            "awaiting_guion",
            "awaiting_premium_images",
            "awaiting_premium_url",
            "awaiting_fb_group_url",
            "editing_product_id",
            "editing_field",
            "admin_search_mode",
            "awaiting_discount_pesos",
            "pending_guion_lines",
            "pending_fb_group_url",
            "premium_images_collected",
            "show_force_menu",
            "show_network_menu"
        ]
        for key in active_state_keys:
            self.user_state.pop(key, None)
        self._save_user_state()
        print(f"[ROUTER] Estados activos limpiados. user_state guardado.")

    async def _handle_active_state(self, text, msg_id):
        """
        Maneja estados activos (cuando el bot espera input del usuario).
        Retorna True si consumió el mensaje, False si debe continuar la cascada.
        """
        print(f"[ROUTER] -> _handle_active_state | text: {text[:20]}...")
        lower_text = text.lower().strip()

        # 1. Edición de producto en cola
        if self.user_state.get("queue_editing_product_id"):
            await self._process_queue_edit_text(text)
            return True

        # 2. Búsqueda en cola
        if self.user_state.get("queue_search_mode"):
            self.user_state.pop("queue_search_mode", None)
            await self._search_queue(text.strip())
            return True

        # 3. Búsqueda en historial
        if self.user_state.get("history_search_mode"):
            self.user_state.pop("history_search_mode", None)
            await self._search_history(text.strip())
            return True

        # 4. Búsqueda de grupos FB
        if self.user_state.get("fb_group_search_mode"):
            self.user_state.pop("fb_group_search_mode", None)
            await self._search_fb_groups(text.strip())
            return True

        # 5. Aprobación de guión generado por Gemini
        if self.user_state.get("awaiting_guion_approval"):
            pending = self.user_state.pop("pending_guion_lines", [])
            work_dir = os.path.join(Config.BASE_DIR, "captures", "premium_temp")
            self.safe_makedirs(work_dir)
            self.user_state["premium_images_collected"] = []
            self.user_state.pop("awaiting_guion_approval", None)
            if lower_text.strip() == "ok" and pending:
                lines = pending
            else:
                lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            if not lines:
                await self.send_notification("No hay guion. Vuelve a intentarlo.", reply_markup=self.get_master_keyboard())
                return True
            guion = {f"escena{i+1}": line for i, line in enumerate(lines)}
            script_path = os.path.join(Config.BASE_DIR, "guion.json")
            json_save_atomic(script_path, guion, indent=2, ensure_ascii=False)
            self.user_state["awaiting_premium_images"] = True
            await self.send_notification(
                f"GUION GUARDADO: {len(guion)} escenas.\n\n"
                "Ahora manda las fotos del producto una por una.\n"
                "Minimo 3 fotos. Cuando termines escribe: LISTO"
            )
            return True

        # 6. Guión manual para video personalizado
        if self.user_state.get("awaiting_custom_script"):
            lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            if not lines:
                await self.send_notification("No recibí texto. Manda el guion con una escena por línea.")
                return True
            product_id = self.user_state.pop("awaiting_custom_script_product_id", None)
            self.user_state.pop("awaiting_custom_script", None)
            product = self._find_product_by_id(product_id)
            if not product:
                await self.send_notification(f"⚠️ El producto con ID `{product_id}` ya no se encuentra en el sistema.")
                return True
            guion = {f"escena{i+1}": line for i, line in enumerate(lines)}
            script_path = os.path.join(Config.BASE_DIR, "guion.json")
            json_save_atomic(script_path, guion, indent=2, ensure_ascii=False)
            img_path = product.get("visual_capture") or product.get("screenshot")
            if img_path and not os.path.isabs(img_path):
                img_path = os.path.join(Config.BASE_DIR, img_path)
            if not img_path or not os.path.exists(img_path):
                img_url = product.get("image_url")
                if img_url:
                    await self.send_notification("⏳ Descargando imagen del producto para el video...")
                    dest = os.path.join(Config.BASE_DIR, "captures", f"temp_{product_id}.jpg")
                    from publishers.pinterest_publisher import PinterestPublisher
                    pin = PinterestPublisher()
                    downloaded = await pin._download_image(img_url, dest)
                    if downloaded:
                        img_path = dest
            if not img_path or not os.path.exists(img_path):
                await self.send_notification("❌ Error: El producto no tiene captura de pantalla o imagen válida.")
                return True
            await self.send_notification("🎙️ Generando locución de voz y renderizando video personalizado... por favor espera.")
            asyncio.create_task(self._execute_custom_script_render(product, [img_path]))
            return True

        # 7. Guión por texto para video premium
        if self.user_state.get("awaiting_guion"):
            lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            if not lines:
                await self.send_notification("No recibi texto. Manda el guion con una escena por linea.")
                return True
            guion = {f"escena{i+1}": line for i, line in enumerate(lines)}
            script_path = os.path.join(Config.BASE_DIR, "guion.json")
            json_save_atomic(script_path, guion, indent=2, ensure_ascii=False)
            self.user_state.pop("awaiting_guion", None)
            self.user_state["awaiting_premium_images"] = True
            await self.send_notification(
                f"GUION GUARDADO: {len(guion)} escena(s).\n\n"
                "Paso 2/3: Ahora manda las fotos del producto una por una.\n"
                "Minimo 3 fotos. Cuando termines escribe: LISTO"
            )
            return True

        # 8. Fotos para video premium
        if self.user_state.get("awaiting_premium_images"):
            if lower_text == "listo":
                images = self.user_state.pop("premium_images_collected", [])
                work_dir = os.path.join(Config.BASE_DIR, "captures", "premium_temp")
                self.user_state.pop("awaiting_premium_images", None)
                if not images:
                    await self.send_notification("No recibi ninguna foto. Vuelve a activar VIDEO PREMIUM e intentalo de nuevo.", reply_markup=self.get_master_keyboard())
                else:
                    asyncio.create_task(self._execute_premium_render(images, work_dir))
                return True
            await self.send_notification(f"Esperando tus fotos. Manda las imagenes una por una y cuando termines escribe: LISTO")
            return True

        # 9. URL para video premium
        if self.user_state.get("awaiting_premium_url"):
            self.user_state.pop("awaiting_premium_url", None)
            asyncio.create_task(self._execute_premium_flow(text.strip()))
            return True

        # 10. URL de grupo Facebook a añadir
        if self.user_state.get("awaiting_fb_group_url"):
            self.user_state.pop("awaiting_fb_group_url", None)
            url_to_add = text.strip()
            if not url_to_add.startswith("http"):
                await self.send_notification("❌ URL inválido. Inténtalo de nuevo desde Redes > Añadir Grupo FB.", reply_markup=self.get_master_keyboard())
                return True
            self.user_state["pending_fb_group_url"] = url_to_add
            keyboard = {
                "inline_keyboard": [
                    [{"text": "General", "callback_data": "add_fb_niche_fb_groups"}],
                    [{"text": "Bebes", "callback_data": "add_fb_niche_fb_groups_baby"}],
                    [{"text": "Mascotas", "callback_data": "add_fb_niche_fb_groups_pets"}],
                    [{"text": "Tenis", "callback_data": "add_fb_niche_fb_groups_tenis"}],
                    [{"text": "Moda", "callback_data": "add_fb_niche_fb_groups_moda"}],
                    [{"text": "Cancelar", "callback_data": "nav_redes"}]
                ]
            }
            await self.send_notification(
                f"🔗 Grupo recibido:\n{url_to_add}\n\n"
                f"🎯 **Selecciona el nicho para este grupo:**",
                reply_markup=keyboard
            )
            return True

        # 11. Edición de producto en panel admin
        if self.user_state.get("editing_product_id") and self.user_state.get("editing_field"):
            await self._process_admin_edit_text(text)
            return True

        # 12. Búsqueda en panel admin
        if self.user_state.get("admin_search_mode"):
            self.user_state.pop("admin_search_mode", None)
            await self._search_web_database(text.strip())
            return True

        # 13. Ingreso de descuento mínimo
        if self.user_state.get("awaiting_discount_pesos"):
            try:
                new_val = int(text.strip())
                config_path = os.path.join(Config.BASE_DIR, "scraping_config.json")
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
                data["min_discount_pesos"] = new_val
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.user_state.pop("awaiting_discount_pesos", None)
                await self.send_notification(
                    f"✅ Configuración actualizada. Nuevo ahorro premium: ${new_val}\n"
                    "El cambio aplica inmediatamente.",
                    reply_markup=self.get_master_keyboard()
                )
            except ValueError:
                await self.send_notification(
                    "❌ Por favor ingresa un número entero válido (ej. 500).",
                    reply_markup=self.get_master_keyboard()
                )
            return True

        # No hay estado activo
        return False

    async def _handle_callback_query(self, data, msg_id, callback_query=None):
        """
        Rutea callbacks por prefijo a handlers especializados.
        Los callbacks llegan con estructura: "prefix_arg1_arg2"
        """
        print(f"[ROUTER] -> _handle_callback_query | data: {data[:20]}... | lower_data={data.lower()}")
        try:
            with open(os.path.join(Config.BASE_DIR, "captures", "last_callback.txt"), "w", encoding="utf-8") as _df:
                _df.write(f"CALLBACK RECEIVED: data={data}, time={datetime.now().isoformat()}\n")
        except Exception as _e:
            print(f"[DEBUG_CB] Error writing callback debug file: {_e}")
        lower_data = data.lower().strip()

        # Ruteo por prefijo (orden importa: más específicos primero)

        # Admin callbacks
        if lower_data.startswith("admin_"):
            await self._handle_admin_callback(data, {"message": {"message_id": msg_id}} if msg_id else None)
            return

        # Queue callbacks
        if lower_data.startswith("queue_"):
            await self._handle_queue_callback(data, {"message": {"message_id": msg_id}} if msg_id else None, msg_id=msg_id)
            return

        # History callbacks
        if lower_data.startswith("history_"):
            await self._handle_history_callback(data, {"message": {"message_id": msg_id}} if msg_id else None, msg_id=msg_id)
            return

        # Duplicate handling
        if lower_data.startswith("force_dup_"):
            temp_id = data[len("force_dup_"):]
            await self._handle_force_duplicate(temp_id, {"message": {"message_id": msg_id}} if msg_id else None)
            return

        if lower_data.startswith("discard_dup_"):
            temp_id = data[len("discard_dup_"):]
            await self._handle_discard_duplicate(temp_id, {"message": {"message_id": msg_id}} if msg_id else None)
            return

        if lower_data.startswith("retry_aff_"):
            parts = data[len("retry_aff_"):].split("_", 1)
            if len(parts) == 2:
                await self._handle_retry_affiliate(parts[0], parts[1], {"message": {"message_id": msg_id}} if msg_id else None)
            return

        # Video type selection
        if lower_data.startswith("vtype_"):
            parts = data.split("_", 2)
            if len(parts) == 3:
                vtype, product_id = parts[1].lower(), parts[2]
                products = self._load_queue_data()
                product = next((p for p in products if p.get("id") == product_id), None)
                if not product:
                    await self.send_notification("Producto no encontrado en la cola.", reply_markup=self.get_master_keyboard())
                    return
                await self.send_notification(
                    f"Generando guion de {vtype.upper()} con Gemini...\n"
                    f"Producto: {product.get('title','')[:60]}"
                )
                asyncio.create_task(self._generate_and_preview_script(product, vtype, msg_id))
            return

        # Navigation
        if lower_data.startswith("nav_"):
            nav_map = {
                "nav_main": "main", "nav_publicacion": "publicacion",
                "nav_contenido": "contenido", "nav_video_niches": "video_niches", "nav_redes": "redes",
                "nav_programacion": "programacion", "nav_mantenimiento": "mantenimiento",
            }
            self.user_state["current_menu"] = nav_map.get(lower_data, "main")
            titles = {
                "main": "🛠️ **Panel de Control Maestro**",
                "publicacion": "🚀 **Publicación**",
                "contenido": "🗂️ **Gestión de Contenido**",
                "redes": "🌐 **Redes Sociales**",
                "programacion": "⏰ **Programación**",
                "mantenimiento": "🔧 **Mantenimiento del Bot**",
            }
            title = titles.get(self.user_state["current_menu"], "🛠️ **Menú**")
            await self.send_notification(
                title + "\n" + "⠀" * 40,
                reply_markup=self.get_master_keyboard(),
                msg_id=msg_id
            )
            return

        # Network toggles
        if lower_data.startswith("toggle_net_"):
            net_key = lower_data[len("toggle_net_"):]
            active = self.user_state.get("active_networks", {
                "facebook": True, "facebook_bebes": True, "fb_page": True, "telegram": True,
                "pinterest": True, "tiktok": True, "youtube": True, "web": True
            })
            active[net_key] = not active.get(net_key, True)
            self.user_state["active_networks"] = active
            self._save_user_state()
            net_status = "ON" if active[net_key] else "OFF"
            await self._answer_callback({"id": "dummy"}, text=f"{net_key.upper()}: {net_status}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        # Facebook split blocks toggles
        if lower_data == "toggle_fb_split":
            current = self.user_state.get("fb_split_blocks", 1)
            self.user_state["fb_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback({"id": "dummy"}, text=f"Bloques FB General: {self.user_state['fb_split_blocks']}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        if lower_data == "toggle_fb_pets_split":
            current = self.user_state.get("fb_pets_split_blocks", 1)
            self.user_state["fb_pets_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback({"id": "dummy"}, text=f"Bloques FB Mascotas: {self.user_state['fb_pets_split_blocks']}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        if lower_data == "toggle_fb_moda_split":
            current = self.user_state.get("fb_moda_split_blocks", 1)
            self.user_state["fb_moda_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback({"id": "dummy"}, text=f"Bloques FB Moda: {self.user_state['fb_moda_split_blocks']}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        if lower_data == "toggle_fb_tenis_split":
            current = self.user_state.get("fb_tenis_split_blocks", 1)
            self.user_state["fb_tenis_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback({"id": "dummy"}, text=f"Bloques FB Tenis: {self.user_state['fb_tenis_split_blocks']}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        if lower_data == "toggle_fb_bebes_split":
            current = self.user_state.get("fb_bebes_split_blocks", 1)
            self.user_state["fb_bebes_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback({"id": "dummy"}, text=f"Bloques FB Bebés: {self.user_state['fb_bebes_split_blocks']}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        # Scheduler/Programming callbacks
        if lower_data.startswith("prog_net_"):
            net = lower_data.replace("prog_net_", "")
            self.user_state["current_menu"] = "prog_net_grid"
            self.user_state["prog_selected_net"] = net
            self._save_user_state()
            await self.send_notification(
                f"🕒 **Configurando horarios para: {net.upper()}**\n" + "⠀" * 40,
                reply_markup=self.get_master_keyboard(),
                msg_id=msg_id
            )
            return

        if lower_data.startswith("toggle_custom_"):
            net = lower_data.replace("toggle_custom_", "")
            from core.scheduler import Scheduler
            s = Scheduler(self.orchestrator)
            config = s.load_slots()
            use_custom = config.get("use_custom", {}).get(net, False)
            if "use_custom" not in config: config["use_custom"] = {}
            config["use_custom"][net] = not use_custom
            s.save_slots(config)
            estado = 'ACTIVADO' if not use_custom else 'DESACTIVADO'
            await self._answer_callback({"id": "dummy"}, text=f"Horario {net.upper()}: {estado}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        if lower_data.startswith("toggle_slot_"):
            try:
                parts = lower_data.split("_")
                slot = int(parts[-1])
                net = parts[2]
                from core.scheduler import Scheduler
                s = Scheduler(self.orchestrator)
                config = s.load_slots()
                if net == "general":
                    slots = config.get("general", [])
                    if slot in slots: slots.remove(slot)
                    else: slots.append(slot)
                    config["general"] = sorted(slots)
                else:
                    if "custom" not in config: config["custom"] = {}
                    if net not in config["custom"]: config["custom"][net] = []
                    slots = config["custom"][net]
                    if slot in slots: slots.remove(slot)
                    else: slots.append(slot)
                    config["custom"][net] = sorted(slots)
                s.save_slots(config)
                slot_estado = 'ON' if slot in slots else 'OFF'
                await self._answer_callback({"id": "dummy"}, text=f"{slot:02d}:00 {net.upper()}: {slot_estado}")
                if msg_id:
                    await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            except Exception as e:
                print(f"Error toggling slot: {e}")
            return

        # Video mode selection
        if lower_data.startswith("video_mode_"):
            mode = lower_data[len("video_mode_"):]
            self.user_state["video_mode"] = mode
            self._save_user_state()
            mode_names = {"normal": "Normal", "benefits": "Beneficios", "comparison": "Comparativa"}
            await self.send_notification(
                f"🎬 Modo de contenido: **{mode_names.get(mode, mode)}** ✅\n" + "⠀" * 40,
                reply_markup=self.get_master_keyboard(),
                msg_id=msg_id
            )
            return

        # Publish callbacks
        if lower_data == "publish_next_amazon":
            await self.send_notification("⚡ **Buscando siguiente producto de Amazon en la lista...**")
            asyncio.create_task(self._process_publish_next_amazon())
            return

        if lower_data == "publish_next_ml":
            await self.send_notification("⚡ **Buscando siguiente producto de Mercado Libre...**")
            asyncio.create_task(self._process_publish_next_ml())
            return

        if lower_data.startswith("publish_next_"):
            if lower_data == "publish_next_now":
                target_platform = [k for k, v in self.user_state.get("active_networks", {}).items() if v] if self.user_state.get("active_networks", {}) else "both"
            else:
                plat_map = {"tg": "telegram", "fb": "facebook", "pin": "pinterest", "tw": "twitter"}
                plat_key = lower_data.split("_")[-1]
                target_platform = plat_map.get(plat_key, "both")
            await self.send_notification("⚡ **Buscando siguiente producto en la lista...**")
            asyncio.create_task(self._process_publish_next(target_platform))
            return

        # Add FB group niche selection
        if lower_data.startswith("add_fb_niche_"):
            niche_map = {
                "add_fb_niche_fb_groups": "FB_GROUP_URLS",
                "add_fb_niche_fb_groups_baby": "FB_GROUPS_BABY_URLS",
                "add_fb_niche_fb_groups_pets": "FB_GROUPS_PETS_URLS",
                "add_fb_niche_fb_groups_tenis": "FB_GROUPS_TENIS_URLS",
                "add_fb_niche_fb_groups_moda": "FB_GROUPS_MODA_URLS",
            }
            target_env_var = niche_map.get(lower_data)
            if not target_env_var:
                await self.send_notification("Nicho no reconocido.", reply_markup=self.get_master_keyboard())
                return
            url_to_add = self.user_state.pop("pending_fb_group_url", None)
            if not url_to_add:
                await self.send_notification("❌ No se encontró el URL pendiente.", reply_markup=self.get_master_keyboard())
                return
            await self._add_fb_group_to_env(url_to_add, target_env_var)
            from dotenv import load_dotenv
            load_dotenv(override=True)
            return

        # FB Group management
        if lower_data == "omit_fb_failed":
            fb_failed_file = os.path.join(Config.BASE_DIR, "fb_failed_queue.json")
            try:
                count = self._count_fb_failed()
                if os.path.exists(fb_failed_file):
                    os.remove(fb_failed_file)
                await self.send_notification(
                    f"🗑️ *Cola de fallidos eliminada.*\n"
                    f"Se descartaron {count} publicaciones pendientes de FB.",
                    reply_markup=self.get_master_keyboard(),
                    msg_id=msg_id
                )
            except Exception as e:
                await self.send_notification(f"❌ Error: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_data == "fb_group_search":
            self.user_state["fb_group_search_mode"] = True
            await self.send_notification(
                "🔍 Envía una palabra clave o parte de la URL para buscar un grupo de Facebook:",
                reply_markup=self.get_master_keyboard()
            )
            return

        if lower_data == "fb_group_browser" or lower_data.startswith("fb_group_nav_"):
            groups = list(dict.fromkeys(
                Config.FB_GROUPS + getattr(Config, 'FB_GROUPS_BABY', []) +
                getattr(Config, 'FB_GROUPS_PETS', []) + getattr(Config, 'FB_GROUPS_TENIS', []) +
                getattr(Config, 'FB_GROUPS_MODA', [])
            ))
            if not groups:
                await self.send_notification("⚠️ No hay grupos de Facebook configurados.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
                return
            idx = 0
            if lower_data.startswith("fb_group_nav_"):
                try:
                    idx = int(lower_data.split("fb_group_nav_")[1])
                except ValueError:
                    idx = 0
            idx = max(0, min(idx, len(groups) - 1))
            group_url = groups[idx]
            group_name = group_url.split("/groups/")[-1].strip("/") if "/groups/" in group_url else group_url
            nav_row = []
            if idx > 0:
                nav_row.append({"text": "◀️ Anterior", "callback_data": f"fb_group_nav_{idx - 1}"})
            if idx < len(groups) - 1:
                nav_row.append({"text": "Siguiente ▶️", "callback_data": f"fb_group_nav_{idx + 1}"})
            keyboard = {
                "inline_keyboard": [
                    nav_row,
                    [{"text": f"🗑️ ELIMINAR ESTE GRUPO", "callback_data": f"fb_group_delete_{idx}"}],
                    [{"text": "🔍 Buscar Grupo", "callback_data": "fb_group_search"}],
                    [{"text": "↩️ Volver a Redes", "callback_data": "nav_redes"}]
                ]
            }
            await self.send_notification(
                f"📋 *Grupo {idx + 1} de {len(groups)}*\n\n🔗 [{group_name}]({group_url})",
                reply_markup=keyboard, msg_id=msg_id
            )
            return

        if lower_data.startswith("fb_group_delete_"):
            try:
                idx = int(lower_data.split("fb_group_delete_")[1])
            except ValueError:
                await self.send_notification("❌ Índice inválido.", reply_markup=self.get_master_keyboard())
                return
            groups = list(dict.fromkeys(
                Config.FB_GROUPS + getattr(Config, 'FB_GROUPS_BABY', []) +
                getattr(Config, 'FB_GROUPS_PETS', []) + getattr(Config, 'FB_GROUPS_TENIS', []) +
                getattr(Config, 'FB_GROUPS_MODA', [])
            ))
            if idx < 0 or idx >= len(groups):
                await self.send_notification("❌ Ese grupo ya no existe.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
                return
            group_url = groups[idx]
            group_name = group_url.split("/groups/")[-1].strip("/") if "/groups/" in group_url else group_url
            await self._remove_fb_group_from_env(group_url)
            from dotenv import load_dotenv
            load_dotenv(override=True)
            new_groups = list(dict.fromkeys(
                Config.FB_GROUPS + getattr(Config, 'FB_GROUPS_BABY', []) +
                getattr(Config, 'FB_GROUPS_PETS', []) + getattr(Config, 'FB_GROUPS_TENIS', []) +
                getattr(Config, 'FB_GROUPS_MODA', [])
            ))
            new_total = len(new_groups)
            if new_total == 0:
                await self.send_notification(f"🗑️ Grupo *{group_name}* eliminado.\nYa no quedan grupos.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
                return
            new_idx = max(0, min(idx, new_total - 1))
            new_url = new_groups[new_idx]
            new_name = new_url.split("/groups/")[-1].strip("/") if "/groups/" in new_url else new_url
            await self.send_notification(f"✅ Grupo *{group_name}* eliminado.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        # Mode selection callbacks
        if lower_data.startswith("mode_"):
            current_mode = self.user_state.get("mode", "both")
            mode_key = lower_data[5:]
            if current_mode == mode_key:
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = mode_key
                mode_msgs = {
                    "facebook": "📘 **Modo**: `Solo Grupos FB`.",
                    "fb_page": "📄 **Modo**: `Solo Página FB`.",
                    "telegram": "✈️ **Modo**: `Solo Telegram`.",
                    "pinterest": "📌 **Modo**: `Solo Pinterest`.",
                    "tiktok": "🎵 **Modo**: `Solo TikTok`.",
                    "youtube": "▶️ **Modo**: `Solo YouTube Shorts`.",
                    "video": "🎬 **Modo**: `Solo Video`.",
                    "web": "🌐 **Modo**: `Solo Web`.",
                }
                msg = mode_msgs.get(mode_key, f"**Modo**: `{mode_key}`.")
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        # Queue management
        if lower_data == "cola":
            history = set(self._load_history())
            q_gen = self._get_pending_queue(niche="general")
            q_baby = self._get_pending_queue(niche="baby")
            q_pets = self._get_pending_queue(niche="pets")
            q_moda = self._get_pending_queue(niche="moda")
            q_tenis = self._get_pending_queue(niche="tenis")
            total = len(q_gen) + len(q_baby) + len(q_pets) + len(q_moda) + len(q_tenis)
            if total == 0:
                await self.send_notification("📭 **Las colas están vacías.**", reply_markup=self.get_master_keyboard())
                return
            msg = f"📋 **Colas ({total} productos)**\nGeneral: **{len(q_gen)}** | Bebes: **{len(q_baby)}** | Mascotas: **{len(q_pets)}** | Moda: **{len(q_moda)}** | Tenis: **{len(q_tenis)}**"
            keyboard = {
                "inline_keyboard": [
                    [{"text": "Ver Cola General", "callback_data": "queue_nav_general"}],
                    [{"text": "Ver Cola Bebes", "callback_data": "queue_nav_baby"}],
                    [{"text": "Ver Cola Mascotas", "callback_data": "queue_nav_pets"}],
                    [{"text": "Ver Cola Moda", "callback_data": "queue_nav_moda"}],
                    [{"text": "Ver Cola Tenis", "callback_data": "queue_nav_tenis"}],
                    [{"text": "VOLVER", "callback_data": "nav_contenido"}]
                ]
            }
            await self.send_notification(msg, reply_markup=keyboard, msg_id=msg_id)
            return

        if lower_data == "clear_queue":
            pending = self._get_pending_queue()
            keyboard = {"inline_keyboard": [[
                {"text": "SI, VACIAR", "callback_data": "clear_queue_yes"},
                {"text": "CANCELAR", "callback_data": "clear_queue_no"},
            ]]}
            await self.send_notification(
                f"Tienes {len(pending)} producto(s). ¿Confirmas?",
                reply_markup=keyboard, msg_id=msg_id
            )
            return

        if lower_data == "clear_queue_yes":
            try:
                products = self._load_queue()
                history = set(self._load_history())
                for p in products:
                    p_id = p.get('id')
                    if p_id and p_id not in history:
                        history.add(p_id)
                self._save_history(history)
                self._save_queue([], niche="general")
                self._save_queue([], niche="baby")
                self._save_queue([], niche="pets")
                await self.send_notification("🗑️ **Cola Vaciada.**", reply_markup=self.get_master_keyboard())
            except Exception as e:
                await self.send_notification(f"❌ Error: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_data == "clear_queue_no":
            await self.send_notification("Operacion cancelada." + " " * 5, reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        # Simple callbacks
        if lower_data == "cmd_admin_web":
            await self._show_admin_browser(msg_id=msg_id)
            return

        if lower_data == "toggle_duplicates":
            current = self.user_state.get("allow_duplicate_products", False)
            self.user_state["allow_duplicate_products"] = not current
            self._save_user_state()
            status = "PERMITIDO" if self.user_state.get("allow_duplicate_products") else "RECHAZADO"
            await self.send_notification(f"✅ Duplicados: {status}", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        if lower_data == "show_fb_groups":
            await self._show_all_fb_groups(msg_id)
            return

        if lower_data == "video_premium_btn":
            self.user_state["awaiting_guion"] = True
            work_dir = os.path.join(Config.BASE_DIR, "captures", "premium_temp")
            self.safe_makedirs(work_dir)
            self.user_state["premium_images_collected"] = []
            await self.send_notification("VIDEO PREMIUM\n\nPaso 1/3: Escribe el guion.", msg_id=msg_id)
            return

        if lower_data == "last_published_show":
            details = self._load_last_published()
            if not details:
                await self.send_notification("⚠️ Sin datos.", reply_markup=self.get_master_keyboard())
                return
            await self._send_history_product_actions(details, msg_id=msg_id)
            return

        if lower_data == "force_video":
            await self.send_notification("🎬 **Generando video del último producto...**")
            asyncio.create_task(self._force_video_generation())
            return

        if lower_data == "force_web":
            await self.send_notification("Iniciando sincronización forzada...")
            asyncio.create_task(self._force_web_sync())
            return

        if lower_data == "toggle_force_menu":
            self.user_state["show_force_menu"] = not self.user_state.get("show_force_menu", False)
            await self.send_notification("⚡ **Menú de Forzado**\n" + "⠀" * 40, reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        if lower_data == "toggle_network_menu":
            self.user_state["show_network_menu"] = not self.user_state.get("show_network_menu", False)
            await self.send_notification("📡 **Menú de Redes**\n" + "⠀" * 40, reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        if lower_data == "get_status":
            await self._send_system_status(msg_id)
            return

        if lower_data == "toggle_queue_mode":
            current_queue = self.user_state.get("queue_mode", False)
            self.user_state["queue_mode"] = not current_queue
            self._save_user_state()
            status = "ACTIVO" if self.user_state["queue_mode"] else "DESACTIVADO"
            await self._answer_callback({"id": "dummy"}, text=f"Modo Cola: {status}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        if lower_data == "toggle_video_ia_mode":
            current_ia = self.user_state.get("video_ia_mode", False)
            self.user_state["video_ia_mode"] = not current_ia
            self._save_user_state()
            status = "ACTIVO" if self.user_state["video_ia_mode"] else "DESACTIVADO"
            await self._answer_callback({"id": "dummy"}, text=f"Modo Video IA: {status}")
            if msg_id:
                await self._edit_reply_markup(msg_id, self.get_master_keyboard())
            return

        if lower_data.startswith("user_guide"):
            await self._show_user_guide(msg_id)
            return

        if lower_data.startswith("guide_page_"):
            page = int(lower_data.replace("guide_page_", ""))
            await self._show_guide_page(page, msg_id=msg_id)
            return

        if lower_data.startswith("view_logs"):
            await self._send_logs(msg_id)
            return

        if lower_data == "toggle_fb_pause":
            is_paused = self.user_state.get("fb_paused", False)
            self.user_state["fb_paused"] = not is_paused
            msg = "⏸️ **Facebook PAUSADO.**" if self.user_state["fb_paused"] else "▶️ **Facebook ACTIVADO.**"
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        if lower_data == "trigger_scrape":
            flag_path = os.path.join(Config.BASE_DIR, "scrape_trigger.flag")
            try:
                import time
                with open(flag_path, "w", encoding="utf-8") as f:
                    f.write(str(time.time()))
                await self.send_notification("🔍 *Solicitud enviada a Windows.*", reply_markup=self.get_master_keyboard())
            except Exception as e:
                await self.send_notification(f"❌ Error: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_data.startswith("clear_logs"):
            await self.send_notification("🧹 **Limpiando...**")
            asyncio.create_task(self._clean_logs())
            return

        if lower_data.startswith("reboot_bot"):
            print("[ROUTER] MATCHED reboot_bot! Exiting via os._exit(0)...")
            try:
                if callback_query:
                    await self._answer_callback(callback_query, text="Reiniciando bot...")
            except Exception:
                pass
            try:
                await self.send_notification("🔄 REINICIANDO BOT...")
            except Exception:
                pass
            sys.stdout.flush()
            await asyncio.sleep(1)
            os._exit(0)

        if lower_data == "historial":
            await self._show_history_browser(msg_id=msg_id)
            return

        if lower_data.startswith("toggle_video_niche_"):
            niche = lower_data.replace("toggle_video_niche_", "")
            vn = self.user_state.setdefault("video_niches", {"general": True, "baby": False, "pets": True, "moda": True, "tenis": True})
            vn[niche] = not vn.get(niche, True)
            self._save_user_state()
            st = "[ON]" if vn[niche] else "[OFF]"
            await self.send_notification(
                f"🎬 Videos para nicho **{niche.upper()}**: {st}",
                reply_markup=self.get_master_keyboard(),
                msg_id=msg_id
            )
            return

        if lower_data == "cancel_custom_script":
            self.user_state.pop("awaiting_custom_script", None)
            self.user_state.pop("awaiting_custom_script_product_id", None)
            self.user_state.pop("pending_guion_lines", None)
            self._save_user_state()
            await self.send_notification("❌ Creación de guión cancelada.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        if lower_data == "ignore":
            return

        if lower_data == "rebuild_web_panel":
            await self.send_notification("🔨 **INICIANDO RECOMPILACIÓN DEL PANEL WEB...**\n\nEjecutando `npm run build` en `web-panel/`. Esto toma ~20-30 segundos. Te notificaré al terminar.")
            asyncio.create_task(self._async_rebuild_web_panel())
            return

        if lower_data.startswith("reboot_system"):
            print("[ROUTER] MATCHED reboot_system! Calling _execute_reboot_system...")
            await self._execute_reboot_system(callback_query=callback_query)
            return

        if lower_data == "start_review":
            await self.show_next_draft()
            return

        if lower_data.startswith("approve_draft_"):
            p_id = data[len("approve_draft_"):]
            await self.process_draft_action(p_id, approve=True, callback_query={"message": {"message_id": msg_id}} if msg_id else None)
            return

        if lower_data.startswith("discard_draft_"):
            p_id = data[len("discard_draft_"):]
            await self.process_draft_action(p_id, approve=False, callback_query={"message": {"message_id": msg_id}} if msg_id else None)
            return

        if lower_data.startswith("draft_video_"):
            p_id = data[len("draft_video_"):]
            await self._start_custom_script_flow(p_id, msg_id=msg_id)
            return

        if lower_data == "add_fb_group":
            self.user_state["awaiting_fb_group_url"] = True
            await self.send_notification("Envia el URL del grupo FB.", reply_markup=self.get_master_keyboard())
            return

        if lower_data == "cmd_conf_discount":
            self.user_state["awaiting_discount_pesos"] = True
            await self.send_notification("Ingresa el descuento mínimo (Pesos):", reply_markup=self.get_master_keyboard())
            return

    async def _send_system_status(self, msg_id=None):
        """Genera y envía el reporte de diagnóstico del estado del sistema en tiempo real."""
        try:
            from datetime import datetime as _dt
            _now = _dt.now()

            active = self.user_state.get("active_networks", {})
            net_names = {
                "facebook": "FB Grupos Gen", "facebook_bebes": "FB Bebes", "facebook_pets": "FB Mascotas",
                "facebook_tenis": "FB Tenis", "facebook_moda": "FB Moda", "fb_page": "FB Page",
                "telegram": "Telegram", "twitter": "Twitter", "youtube": "YouTube", "web": "Web"
            }
            redes_lines = " | ".join(
                f"{'🟢' if active.get(k) else '🔴'} {v}"
                for k, v in net_names.items()
            )

            try:
                from core.scheduler import Scheduler
                _s_config = Scheduler(self.orchestrator).load_slots()
                _slots = sorted(_s_config.get("general", []))
            except Exception:
                _slots = []
            if _slots:
                slots_str = "  ".join(f"{h:02d}:00" for h in _slots)
                _next = next((h for h in _slots if h > _now.hour), _slots[0] if _slots else None)
                next_str = f"{_next:02d}:00" if _next is not None else "?"
                if _next is not None and _next <= _now.hour:
                    next_str += " (mañana)"
            else:
                slots_str = "⚠️ Sin slots configurados"
                next_str = "?"

            try:
                q_gen = self._get_pending_queue(niche="general")
                q_baby = self._get_pending_queue(niche="baby")
                q_pets = self._get_pending_queue(niche="pets")
                q_tenis = self._get_pending_queue(niche="tenis")
                q_moda = self._get_pending_queue(niche="moda")

                total_pend = len(q_gen) + len(q_baby) + len(q_pets) + len(q_tenis) + len(q_moda)
                queue_str = f"**{total_pend} en espera**\n"
                queue_str += f"   • General: {len(q_gen)}\n"
                queue_str += f"   • Bebes: {len(q_baby)}\n"
                queue_str += f"   • Mascotas: {len(q_pets)}\n"
                queue_str += f"   • Tenis: {len(q_tenis)}\n"
                queue_str += f"   • Moda: {len(q_moda)}"
            except Exception:
                queue_str = "No disponible"

            try:
                _lp = self._load_last_published()
                _lp_title = _lp.get("title", "?")[:50]
                _lp_price = _lp.get("price", "?")
                last_pub_str = f"`{_lp_title}` — ${_lp_price}"
            except Exception:
                last_pub_str = "Sin datos"

            msg = (
                f"📊 **Estado del Sistema — {_now.strftime('%d/%m/%Y %H:%M:%S')}**\n\n"
                f"🌐 **Redes:**\n{redes_lines}\n\n"
                f"⏰ **Slots General:** `{slots_str}`\n"
                f"👉 Próxima publicación: `{next_str}`\n\n"
                f"📦 **Estado de Colas:**\n{queue_str}\n\n"
                f"🛍️ **Último publicado:**\n{last_pub_str}"
            )
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=msg_id)
        except Exception as _e:
            await self.send_notification(f"❌ Error al generar estado: {_e}", reply_markup=self.get_master_keyboard(), msg_id=msg_id)

    async def _clean_logs(self):
        """Limpia los archivos de logs del sistema (bot.log y nohup.out)."""
        try:
            for log_file in ["bot.log", "nohup.out"]:
                log_path = os.path.join(Config.BASE_DIR, log_file)
                if os.path.exists(log_path):
                    with open(log_path, "w", encoding="utf-8") as f:
                        f.write("")
            await self.send_notification("🧹 **LOGS LIMPIADOS EXITOSAMENTE**", reply_markup=self.get_master_keyboard())
        except Exception as e:
            await self.send_notification(f"❌ **Error al limpiar logs:** {e}", reply_markup=self.get_master_keyboard())

    async def _async_rebuild_web_panel(self):
        """Recompila la aplicación Next.js en web-panel/ y reinicia gangas.target."""
        web_dir = os.path.join(Config.BASE_DIR, "web-panel")
        if not os.path.exists(web_dir):
            await self.send_notification("❌ **Error:** No se encontró la carpeta `web-panel/`.", reply_markup=self.get_master_keyboard())
            return

        try:
            cmd = "npm run build"
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=web_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            out_str = (stdout.decode('utf-8', errors='ignore') + "\n" + stderr.decode('utf-8', errors='ignore')).strip()

            if proc.returncode == 0:
                await self.send_notification("✅ **PANEL WEB RECOMPILADO CON ÉXITO**\n\nReiniciando servicios (`gangas.target`) para aplicar cambios...")
                await asyncio.sleep(2)
                import subprocess
                cmd_reboot = "sudo -n systemctl restart gangas.target || systemctl restart gangas.target"
                subprocess.run(cmd_reboot, shell=True, capture_output=True)
                os._exit(0)
            else:
                log_snippet = out_str[-1500:] if len(out_str) > 1500 else out_str
                await self.send_notification(f"❌ **FALLÓ LA COMPILACIÓN DEL PANEL WEB**\n\nError (código {proc.returncode}):\n```\n{log_snippet}\n```", reply_markup=self.get_master_keyboard())
        except Exception as e:
            await self.send_notification(f"❌ **Error al recompilar el panel web:** {e}", reply_markup=self.get_master_keyboard())

        # Fallback: callback no manejado
        print(f"[ROUTER] ⚠️ Callback no manejado: {data}")

    async def _execute_reboot_system(self, callback_query=None):
        """Reinicia limpiamente Bot, API y Web Panel (gangas.target) de forma síncrona y garantizada."""
        if callback_query and callback_query.get("id"):
            await self._answer_callback(callback_query.get("id"), text="Reiniciando sistema...")
        await self.send_notification("🔄 **REINICIANDO SISTEMA COMPLETO...**\n\nReiniciando Bot, API y Panel Web (`gangas.target`). Estaré de vuelta en unos segundos.")
        await asyncio.sleep(1)

        import subprocess
        import signal

        # 1. Matar procesos de API (uvicorn) de forma síncrona
        for pat in ["uvicorn.*api.main:app", "api.main:app"]:
            try:
                subprocess.run(["pkill", "-9", "-f", pat], capture_output=True, timeout=3)
            except Exception:
                pass

        # 2. Matar procesos de Web Panel (Next.js / npm) de forma síncrona
        for pat in ["next.*dev", "web-panel.*next", "npm run dev", "next-server"]:
            try:
                subprocess.run(["pkill", "-9", "-f", pat], capture_output=True, timeout=3)
            except Exception:
                pass

        # 3. Intentar restart via systemctl si sudo sin contraseña está disponible
        try:
            subprocess.run(["sudo", "-n", "systemctl", "restart", "gangas.target"], capture_output=True, timeout=4)
        except Exception:
            pass

        # 4. Escaneo nativo en /proc para asegurar terminación de subprocesos huérfanos
        try:
            if hasattr(os, "listdir") and os.path.exists("/proc"):
                my_pid = os.getpid()
                for entry in os.listdir("/proc"):
                    if entry.isdigit() and int(entry) != my_pid:
                        try:
                            cmd_path = f"/proc/{entry}/cmdline"
                            if os.path.exists(cmd_path):
                                with open(cmd_path, "rb") as cf:
                                    raw_cmd = cf.read().decode("utf-8", errors="ignore").replace("\x00", " ")
                                if any(k in raw_cmd for k in ["api.main:app", "web-panel/node_modules"]):
                                    os.kill(int(entry), signal.SIGKILL)
                        except Exception:
                            pass
        except Exception:
            pass

        # 5. Pausa de 1.5s para que systemd registre la caída de API y Web e inicie su ciclo Restart=always
        await asyncio.sleep(1.5)

        # 6. Salir para que systemd reinicie amazon_bot.service
        os._exit(0)

    async def _handle_text_command(self, text):
        """
        Maneja comandos que comienzan con / y escapan de estados activos.
        Limpia todos los estados activos antes de procesar el comando.
        """
        print(f"[ROUTER] -> _handle_text_command | text: {text[:20]}...")
        lower_text = text.lower().strip()

        # Limpiar estados activos cuando hay comando /
        self._clear_all_active_states()

        # Routing de comandos
        if lower_text in ["/reboot", "/reiniciar", "/restart", "/reboot_system", "/reboot_bot"]:
            await self._execute_reboot_system()
            return

        if lower_text == "/grupos":
            msg = (
                f"📊 **GRUPOS DE FACEBOOK CONFIGURADOS**\n\n"
                f"📱 **General**: `{len(Config.FB_GROUPS)}` grupos activos\n"
                f"🧸 **Bebés**: `{len(Config.FB_GROUPS_BABY)}` grupos\n"
                f"🐶 **Mascotas**: `{len(Config.FB_GROUPS_PETS)}` grupos\n"
                f"👟 **Tenis**: `{len(Config.FB_GROUPS_TENIS)}` grupos\n"
                f"👗 **Moda**: `{len(Config.FB_GROUPS_MODA)}` grupos\n\n"
                f"_(Para modificar, edita el archivo .env)_"
            )
            await self.send_notification(msg)
            return

        if lower_text.startswith("/admin ") or lower_text == "/admin":
            term = text[len("/admin "):].strip() if lower_text.startswith("/admin ") else ""
            if not term:
                await self._show_admin_browser()
            else:
                await self._search_web_database(term)
            return

        if lower_text.startswith("/buscar ") or lower_text.startswith("buscar "):
            term = text[len("/buscar "):].strip() if lower_text.startswith("/buscar ") else text[len("buscar "):].strip()
            if not term:
                await self.send_notification("⚠️ Escribe el término que quieres buscar, por ejemplo: `/buscar tenis` o `buscar laptop`.")
                return
            asyncio.create_task(self.perform_search(term))
            return

        if lower_text == "/test_fb":
            await self.send_notification("⏳ Iniciando prueba de bloqueo de Facebook. Tardará unos segundos en verificar...")
            asyncio.create_task(self._run_fb_test_command())
            return

        if lower_text == "/test_meli":
            await self.send_notification("🕵️‍♂️ Iniciando test de Mercado Libre en el servidor Linux...")
            asyncio.create_task(self._run_meli_test_command())
            return

        if lower_text == "/start" or lower_text == "menu":
            await self.handle_command("cola", None)
            await self.send_notification(
                "🛠️ **Panel de Control Maestro**\n\nBienvenido, Eduardo. Elige una opción:\n" + "\u2800" * 40,
                reply_markup=self.get_master_keyboard()
            )
            return

        if lower_text == "/cola":
            await self.handle_command("cola", None)
            return

        if lower_text == "/historial" or lower_text == "/publicados":
            await self._show_history_browser()
            return

        if lower_text == "/revisar" or lower_text == "start_review":
            await self.show_next_draft()
            return

        # Comando desconocido
        print(f"[ROUTER] ⚠️ Comando desconocido: {text}")
        await self.send_notification(f"⚠️ Comando no reconocido: {text}", reply_markup=self.get_master_keyboard())

    def get_master_keyboard(self):
        """Genera el teclado dinámico según el menú actual y estado de redes."""
        menu = self.user_state.get("current_menu", "main")
        active = self.user_state.get("active_networks", {
            "facebook": True, "fb_page": True, "telegram": True,
            "pinterest": True, "tiktok": True, "youtube": True, "web": True
        })
        v_mode = self.user_state.get("video_mode", "normal")
        try:
            scheduler_config = json_load(os.path.join(Config.BASE_DIR, "scheduler_config.json"), default={})
            active_slots = scheduler_config.get("general", scheduler_config.get("slots", [8, 10, 12, 14, 16, 18, 20, 22]))
        except Exception:
            active_slots = [8, 10, 12, 14, 16, 18, 20, 22]

        keyboards = {
            "main": [
                [{"text": "PUBLICACION", "callback_data": "nav_publicacion"}],
                [{"text": "CONTENIDO", "callback_data": "nav_contenido"}],
                [{"text": "REDES", "callback_data": "nav_redes"}],
                [{"text": "PROGRAMACION", "callback_data": "nav_programacion"}],
                [{"text": "ESTADO", "callback_data": "get_status"}],
                [{"text": "MANTENIMIENTO", "callback_data": "nav_mantenimiento"}]
            ],
            "publicacion": [
                [
                    {"text": "PUBLICAR SIG (Global)", "callback_data": "publish_next_now"},
                ],
                [
                    {"text": "PUB SIG (SOLO TG)", "callback_data": "publish_next_tg"},
                    {"text": "PUB SIG (SOLO FB)", "callback_data": "publish_next_fb"},
                ],
                [
                    {"text": "PUB SIG (SOLO PINT)", "callback_data": "publish_next_pin"},
                    {"text": "PUB SIG (SOLO TW)", "callback_data": "publish_next_tw"},
                ],
                [
                    {"text": "VIDEO PREMIUM", "callback_data": "video_premium_btn"},
                ],
                [{"text": "VER ÚLTIMO PUBLICADO", "callback_data": "last_published_show"}],
                *([  # Solo aparece si hay grupos fallidos pendientes
                    [
                        {"text": f"🗑️ DESCARTAR FALLIDOS ({self._count_fb_failed()})", "callback_data": "omit_fb_failed"}
                    ]
                ] if self._count_fb_failed() > 0 else []),
                [{"text": "VOLVER", "callback_data": "nav_main"}]
            ],
            "video_niches": [
                [{"text": f"[{'ON' if self.user_state.get('video_niches', {}).get('general', True) else 'OFF'}] VIDEOS GENERAL", "callback_data": "toggle_video_niche_general"}],
                [{"text": f"[{'ON' if self.user_state.get('video_niches', {}).get('baby', False) else 'OFF'}] VIDEOS BEBES", "callback_data": "toggle_video_niche_baby"}],
                [{"text": f"[{'ON' if self.user_state.get('video_niches', {}).get('pets', True) else 'OFF'}] VIDEOS MASCOTAS", "callback_data": "toggle_video_niche_pets"}],
                [{"text": f"[{'ON' if self.user_state.get('video_niches', {}).get('moda', True) else 'OFF'}] VIDEOS MODA", "callback_data": "toggle_video_niche_moda"}],
                [{"text": f"[{'ON' if self.user_state.get('video_niches', {}).get('tenis', True) else 'OFF'}] VIDEOS TENIS", "callback_data": "toggle_video_niche_tenis"}],
                [{"text": "VOLVER AL MENU", "callback_data": "nav_contenido"}]
            ],
            "contenido": [
                [{"text": "CONFIGURAR VIDEOS", "callback_data": "nav_video_niches"}],
                [{"text": "VER COLA", "callback_data": "cola"}],
                [{"text": "VER HISTORIAL PUBLICADOS", "callback_data": "historial"}],
                [{"text": "MODO COLA: ACTIVO" if self.user_state.get("queue_mode") else "MODO COLA: DESACTIVADO", "callback_data": "toggle_queue_mode"}],
                [{"text": "MODO VIDEO IA: ACTIVO" if self.user_state.get("video_ia_mode") else "MODO VIDEO IA: DESACTIVADO", "callback_data": "toggle_video_ia_mode"}],
                [{"text": "VOLVER", "callback_data": "nav_main"}]
            ],
            "redes": [
                [
                    {"text": f"{'[ON]' if active.get('facebook', True) else '[OFF]'} FB GRUPOS GEN", "callback_data": "toggle_net_facebook"},
                    {"text": f"{'[ON]' if active.get('facebook_bebes', True) else '[OFF]'} FB GRUPOS BEBES", "callback_data": "toggle_net_facebook_bebes"}
                  ],
                  [
                      {"text": f"{'[ON]' if active.get('facebook_pets', True) else '[OFF]'} FB MASCOTAS", "callback_data": "toggle_net_facebook_pets"},
                      {"text": f"{'[ON]' if active.get('facebook_moda', True) else '[OFF]'} FB MODA", "callback_data": "toggle_net_facebook_moda"}
                  ],
                  [
                      {"text": f"{'[ON]' if active.get('facebook_tenis', True) else '[OFF]'} FB TENIS", "callback_data": "toggle_net_facebook_tenis"}
                ],
                [
                    {"text": f"BLOQUES FB GENERAL: [{self.user_state.get('fb_split_blocks', 1)}]", "callback_data": "toggle_fb_split"},
                    {"text": f"BLOQUES FB BEBES: [{self.user_state.get('fb_bebes_split_blocks', 1)}]", "callback_data": "toggle_fb_bebes_split"}
                  ],
                  [
                      {"text": f"BLOQUES MASCOTAS: [{self.user_state.get('fb_pets_split_blocks', 1)}]", "callback_data": "toggle_fb_pets_split"},
                      {"text": f"BLOQUES MODA: [{self.user_state.get('fb_moda_split_blocks', 1)}]", "callback_data": "toggle_fb_moda_split"}
                  ],
                  [
                      {"text": f"BLOQUES TENIS: [{self.user_state.get('fb_tenis_split_blocks', 1)}]", "callback_data": "toggle_fb_tenis_split"}
                ],
                [{"text": f"{'[ON]' if active.get('fb_page') else '[OFF]'} FB PAGE", "callback_data": "toggle_net_fb_page"}],
                [{"text": f"{'[ON]' if active.get('telegram') else '[OFF]'} TELEGRAM", "callback_data": "toggle_net_telegram"}],
                [{"text": f"{'[ON]' if active.get('pinterest') else '[OFF]'} PINTEREST", "callback_data": "toggle_net_pinterest"}],
                [{"text": f"{'[ON]' if active.get('tiktok') else '[OFF]'} TIKTOK", "callback_data": "toggle_net_tiktok"}],
                [{"text": f"{'[ON]' if active.get('youtube') else '[OFF]'} YOUTUBE", "callback_data": "toggle_net_youtube"}],
                [{"text": f"{'[ON]' if active.get('twitter') else '[OFF]'} TWITTER / X", "callback_data": "toggle_net_twitter"}],
                [
                    {"text": "📊 VER GRUPOS FB CONFIGURADOS", "callback_data": "show_fb_groups"}
                ],
                [
                    {"text": "ANIADIR GRUPO FB", "callback_data": "add_fb_group"},
                    {"text": "🗑️ BORRAR GRUPO FB", "callback_data": "fb_group_browser"}
                ],
                [{"text": "VOLVER", "callback_data": "nav_main"}]
            ],
            "programacion": [
                [{"text": "⚙️ Horario General", "callback_data": "prog_net_general"}],
                [{"text": "🐦 Horario Twitter / X", "callback_data": "prog_net_twitter"}],
                [{"text": "🎵 Horario TikTok", "callback_data": "prog_net_tiktok"}],
                [{"text": "🟥 Horario YouTube", "callback_data": "prog_net_youtube"}],
                [{"text": "VOLVER", "callback_data": "nav_main"}]
            ],
            "mantenimiento": [
                [{"text": "ADMINISTRAR WEB", "callback_data": "cmd_admin_web"}],
                [{"text": "🔨 RECOMPILAR PANEL WEB", "callback_data": "rebuild_web_panel"}],
                [{"text": "⚙️ CONF. DESCUENTO", "callback_data": "cmd_conf_discount"}],
                [{"text": f"📁 DUPLICADOS: {'PERMITIDO' if self.user_state.get('allow_duplicate_products', False) else 'RECHAZADO'}", "callback_data": "toggle_duplicates"}],
                [{"text": "REVISAR LOGS", "callback_data": "view_logs"}],
                [{"text": "LIMPIAR LOGS", "callback_data": "clear_logs"}],
                [{"text": "REINICIAR BOT", "callback_data": "reboot_bot"}],
                [{"text": "REINICIAR SISTEMA COMPLETO", "callback_data": "reboot_system"}],
                [{"text": "📖 GUÍA DE USUARIO", "callback_data": "user_guide"}],
                [{"text": "VOLVER", "callback_data": "nav_main"}]
            ]
        }

        keyboard = keyboards.get(menu, keyboards["main"])
        
        # Submenú dinámico para programación específica
        if menu == "prog_net_grid":
            net_sel = self.user_state.get("prog_selected_net", "general")
            from core.scheduler import Scheduler
            config = Scheduler(self.orchestrator).load_slots()
            
            if net_sel == "general":
                active_slots = config.get("general", [])
                keyboard = []
                keyboard.append([{"text": "HORARIOS GENERALES POR DEFECTO", "callback_data": "ignore"}])
            else:
                use_custom = config.get("use_custom", {}).get(net_sel, False)
                active_slots = config.get("custom", {}).get(net_sel, [])
                keyboard = []
                keyboard.append([{"text": f"{'[ACTIVADO]' if use_custom else '[DESACTIVADO]'} USAR HORARIO PERSONALIZADO", "callback_data": f"toggle_custom_{net_sel}"}])
            
            # Matriz de horas
            for h in range(8, 23, 3):
                row = []
                for i in range(3):
                    hr = h + i
                    row.append({"text": f"{'[ON]' if hr in active_slots else '[OFF]'} {hr:02d}:00", "callback_data": f"toggle_slot_{net_sel}_{hr}"})
                keyboard.append(row)
                
            keyboard.append([{"text": "VOLVER A PROGRAMACIÓN", "callback_data": "nav_programacion"}])
            
        return {"inline_keyboard": keyboard}

    async def _get_send_session(self):
        if self._send_session is None or self._send_session.closed:
            self._send_session = aiohttp.ClientSession()
        return self._send_session

    async def _get_poll_session(self):
        if self._poll_session is None or self._poll_session.closed:
            self._poll_session = aiohttp.ClientSession()
        return self._poll_session

    def _sync_user_state(self):
        """Lee el estado del disco y actualiza las claves persistentes sin borrar las efímeras."""
        try:
            if os.path.exists(self._state_file):
                with open(self._state_file, "r", encoding="utf-8") as _sf:
                    _loaded = json.load(_sf)
                    keys = ["active_networks", "video_mode", "paused", "fb_paused", "mode", "queue_mode", "fb_split_blocks", "fb_bebes_split_blocks", "fb_pets_split_blocks", "fb_tenis_split_blocks", "fb_moda_split_blocks", "fb_gen_block_index", "fb_bebes_block_index", "fb_pets_block_index", "fb_tenis_block_index", "fb_moda_block_index", "allow_duplicate_products", "video_niches", "video_ia_mode"]
                    for k in keys:
                        if k in _loaded:
                            self.user_state[k] = _loaded[k]
        except Exception:
            pass

    def _save_user_state(self):
        """Guarda active_networks y video_mode a disco para sobrevivir reinicios."""
        try:
            disk_state = json_load(self._state_file, default={})
            keys = ["active_networks", "video_mode", "paused", "fb_paused", "mode", "queue_mode", "fb_split_blocks", "fb_bebes_split_blocks", "fb_pets_split_blocks", "fb_tenis_split_blocks", "fb_moda_split_blocks", "fb_gen_block_index", "fb_bebes_block_index", "fb_pets_block_index", "fb_tenis_block_index", "fb_moda_block_index", "allow_duplicate_products", "video_niches", "video_ia_mode"]
            for k in keys:
                if k in self.user_state:
                    disk_state[k] = self.user_state[k]
            json_save_atomic(self._state_file, disk_state, indent=2, ensure_ascii=False)
        except Exception as _e:
            print(f"[STATE] Error guardando user_state: {_e}")

    def _count_fb_failed(self) -> int:
        """Retorna cuántos grupos de FB tienen publicaciones pendientes de reintento."""
        try:
            fb_failed_file = os.path.join(Config.BASE_DIR, "fb_failed_queue.json")
            data = json_load(fb_failed_file, default=[])
            return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0

    def _get_cursors(self) -> dict:
        """Retorna el estado actual de los cursores de publicación."""
        try:
            cursors_file = os.path.join(Config.BASE_DIR, "cursors.json")
            data = json_load(cursors_file, default={})
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_history(self):
        try:
            from core.history_manager import load_recent_history
            return list(load_recent_history())
        except Exception:
            return []

    def _save_history(self, history):
        try:
            from core.history_manager import load_history_map
            from core.storage import json_save_atomic
            from datetime import datetime
            h_map = load_history_map()
            now_iso = datetime.now().isoformat()
            for item in history:
                if item and str(item) not in h_map:
                    h_map[str(item)] = now_iso
            json_save_atomic(Config.HISTORY_FILE, h_map, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[STATE] Error guardando historial: {e}")

    def _get_queue_file(self, niche="general"):
        if niche == "baby": return Config.JSON_QUEUE_BABY_FILE
        if niche == "pets": return Config.JSON_QUEUE_PETS_FILE
        if niche == "moda": return Config.JSON_QUEUE_MODA_FILE
        if niche == "tenis": return getattr(Config, "JSON_QUEUE_TENIS_FILE", __import__("os").path.join(Config.BASE_DIR, "queue_tenis.json"))
        return Config.JSON_QUEUE_FILE

    def _load_queue(self, niche="general"):
        try:
            queue = json_load(self._get_queue_file(niche), default=[])
            return queue if isinstance(queue, list) else []
        except Exception:
            return []

    def _save_queue(self, products, niche="general"):
        try:
            json_save_atomic(self._get_queue_file(niche), products, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[STATE] Error guardando cola {niche}: {e}")

    def _load_last_published(self, default=None):
        try:
            data = json_load(os.path.join(Config.BASE_DIR, "last_published.json"), default=default if default is not None else {})
            return data if isinstance(data, dict) else (default if default is not None else {})
        except Exception:
            return default if default is not None else {}

    def _save_last_published(self, details):
        try:
            json_save_atomic(os.path.join(Config.BASE_DIR, "last_published.json"), details, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[STATE] Error guardando last_published: {e}")

    def _load_drafts(self):
        try:
            drafts = json_load(Config.JSON_DRAFT_FILE, default=[])
            return drafts if isinstance(drafts, list) else []
        except Exception:
            return []

    def _save_drafts(self, drafts):
        try:
            json_save_atomic(Config.JSON_DRAFT_FILE, drafts, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[STATE] Error guardando borradores: {e}")

    async def send_notification(self, message, reply_markup=None, msg_id=None):
        """Envía o edita un mensaje. Si msg_id, edita en lugar de crear."""
        # Forzar ancho máximo para estirar los botones si hay un teclado
        if reply_markup and "⠀" not in message:
            message += "\n" + "⠀" * 40

        if msg_id:
            url = f"https://api.telegram.org/bot{self.token}/editMessageText"
            payload = {"chat_id": self.chat_id, "message_id": msg_id, "text": message, "parse_mode": "Markdown"}
        else:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            session = await self._get_send_session()
            async with session.post(url, json=payload) as resp:
                res = await resp.json()
                if not res.get("ok"):
                    if "can't parse entities" in res.get("description", ""):
                        # Reintentar sin Markdown para evitar que el mensaje se pierda
                        payload.pop("parse_mode", None)
                        async with session.post(url, json=payload) as resp2:
                            res = await resp2.json()
                            if not res.get("ok"):
                                print(f"⚠️ Error Telegram API (sin Markdown): {res}")
                    else:
                        print(f"⚠️ Error Telegram API: {res}")
                return res
        except Exception as e:
            print(f"Error enviando a Telegram: {e}")
            return None

    async def send_video(self, video_path, caption=""):
        """Envía un video por Telegram al chat de control."""
        if not self.token or not self.chat_id:
            return False
        if not os.path.exists(video_path):
            print(f"Error: Video no encontrado en {video_path}")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendVideo"
        data = aiohttp.FormData()
        data.add_field('chat_id', self.chat_id)
        if caption:
            data.add_field('caption', caption)
            data.add_field('parse_mode', "Markdown")
        try:
            session = await self._get_send_session()
            with open(video_path, 'rb') as f:
                data.add_field('video', f)
                # timeout alto porque los videos pesan
                async with session.post(url, data=data, timeout=60) as resp:
                    res = await resp.json()
                    ok = res.get("ok", False)
                    if not ok:
                        print(f"Error enviando video a Telegram: {res}")
                    return ok
        except Exception as e:
            print(f"Excepcion enviando video a Telegram: {e}")
            return False

    async def send_photo(self, photo_path, caption="", parse_mode="Markdown", reply_markup=None):
        """Envía una foto local o remota. Devuelve el message_id del mensaje enviado, o None si falla."""
        if not self.token or not self.chat_id: return None
        is_http = photo_path.startswith("http")
        if not is_http and not os.path.exists(photo_path): return None
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        
        try:
            session = await self._get_send_session()
            data = aiohttp.FormData()
            data.add_field("chat_id", str(self.chat_id))
            if caption:
                data.add_field("caption", caption)
                data.add_field("parse_mode", parse_mode)
            if reply_markup:
                import json as _json
                data.add_field("reply_markup", _json.dumps(reply_markup))
            
            if is_http:
                data.add_field("photo", photo_path)
            else:
                with open(photo_path, 'rb') as f:
                    data.add_field("photo", f.read(), filename="photo.png", content_type="image/png")
                
            async with session.post(url, data=data) as resp:
                result = await resp.json()
                if result.get("ok"):
                    return result["result"]["message_id"]
                print(f"Error enviando foto: {result}")
                return None
        except Exception as e:
            print(f"Excepcion enviando foto: {e}")
            return None

    async def _edit_photo_message(self, msg_id, photo_path, caption="", parse_mode="Markdown", reply_markup=None):
        """Edita un mensaje de foto existente usando editMessageMedia."""
        is_http = photo_path.startswith("http")
        if not is_http and not os.path.exists(photo_path):
            return False
        url = f"https://api.telegram.org/bot{self.token}/editMessageMedia"
        try:
            session = await self._get_send_session()
            import json as _json
            data = aiohttp.FormData()
            data.add_field("chat_id", str(self.chat_id))
            data.add_field("message_id", str(msg_id))
            
            if is_http:
                media = {"type": "photo", "media": photo_path, "caption": caption, "parse_mode": parse_mode}
                data.add_field("media", _json.dumps(media))
                if reply_markup:
                    data.add_field("reply_markup", _json.dumps(reply_markup))
            else:
                media = {"type": "photo", "media": "attach://photo", "caption": caption, "parse_mode": parse_mode}
                data.add_field("media", _json.dumps(media))
                if reply_markup:
                    data.add_field("reply_markup", _json.dumps(reply_markup))
                with open(photo_path, 'rb') as f:
                    data.add_field("photo", f.read(), filename="photo.png", content_type="image/png")
            
            async with session.post(url, data=data) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    print(f"Error editando foto: {result}")
                return result.get("ok", False)
        except Exception as e:
            print(f"Excepcion editando foto: {e}")
            return False

    async def delete_message(self, message_id):
        """Elimina un mensaje específico del chat de Telegram."""
        url = f"https://api.telegram.org/bot{self.token}/deleteMessage"
        payload = {"chat_id": self.chat_id, "message_id": message_id}
        try:
            session = await self._get_send_session()
            async with session.post(url, json=payload) as resp:
                result = await resp.json()
                return result.get("ok", False)
        except Exception as e:
            print(f"Error deleting message: {e}")
            return False

    async def _edit_reply_markup(self, msg_id: int, reply_markup: dict) -> bool:
        """Actualiza solo el teclado inline de un mensaje sin tocar el texto."""
        url = f"https://api.telegram.org/bot{self.token}/editMessageReplyMarkup"
        payload = {"chat_id": self.chat_id, "message_id": msg_id, "reply_markup": reply_markup}
        try:
            session = await self._get_send_session()
            async with session.post(url, json=payload) as resp:
                result = await resp.json()
                return result.get("ok", False)
        except Exception as e:
            print(f"Error editando reply markup: {e}")
            return False

    async def _answer_callback(self, callback_query, text: str = ""):
        """Responde el callback query con un toast de texto (feedback inmediato al usuario)."""
        if isinstance(callback_query, dict):
            cb_id = callback_query.get("id")
        elif isinstance(callback_query, str):
            cb_id = callback_query
        else:
            cb_id = None
        if not cb_id or cb_id == "dummy":
            return
        url = f"https://api.telegram.org/bot{self.token}/answerCallbackQuery"
        payload = {"callback_query_id": cb_id}
        if text:
            payload["text"] = text[:200]
        try:
            session = await self._get_send_session()
            await session.post(url, json=payload)
        except Exception:
            pass

    async def send_to_channel(self, message, image_path=None):
        """Publica la oferta en el canal de Telegram con imagen y botón de compra."""
        channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
        if not self.token or not channel_id:
            print("Error: Token de bot o TELEGRAM_CHANNEL_ID no configurados.")
            return False

        # Extraer el link de compra del mensaje para el botón
        url_match = re.search(r'https?://[^\s]+', message)
        buy_url = url_match.group(0) if url_match else None

        reply_markup = None
        if buy_url:
            url_low = buy_url.lower()
            if "amazon" in url_low or "amzn" in url_low:
                btn_text = "🛒 VER OFERTA EN AMAZON"
            elif "meli.la" in url_low or "mercadolibre" in url_low:
                btn_text = "🛒 VER EN MERCADO LIBRE"
            else:
                btn_text = "🛒 VER OFERTA AHORA"
            reply_markup = {
                "inline_keyboard": [[{"text": btn_text, "url": buy_url}]]
            }

        try:
            session = await self._get_send_session()
            if image_path and os.path.exists(image_path):
                url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                data = aiohttp.FormData()
                data.add_field('chat_id', channel_id)
                data.add_field('caption', message)
                if reply_markup:
                    data.add_field('reply_markup', json.dumps(reply_markup))
                
                with open(image_path, 'rb') as f:
                    data.add_field('photo', f)
                    async with session.post(url, data=data) as resp:
                        res = await resp.json()
                        ok = res.get("ok", False)
                        if not ok:
                            print(f"Error enviando foto a canal Telegram: {res}")
                        return ok
            else:
                # Si no hay imagen, enviar solo texto con botón
                target_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                payload = {
                    "chat_id": channel_id,
                    "text": message
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                async with session.post(target_url, json=payload) as resp:
                    res = await resp.json()
                    ok = res.get("ok", False)
                    if not ok:
                        print(f"Error enviando mensaje a canal Telegram: {res}")
                    return ok
        except Exception as e:
            print(f"Error enviando al canal: {e}")
            return False

    async def _get_updates(self, offset=None, timeout=30):
        self._sync_user_state()
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        params = {"timeout": timeout}
        if offset:
            params["offset"] = offset
            
        try:
            session = await self._get_poll_session()
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                return data.get("result", [])
        except Exception as e:
            print(f"Error obteniendo updates: {e}")
            return []

    async def handle_command(self, text, callback_query=None):
        """Router puro: delega a handlers especializados por tipo de input"""
        if not text:
            return

        lower_text = text.lower().strip()
        _cb_msg_id = callback_query.get("message", {}).get("message_id") if callback_query else None

        print(f"[HANDLE_COMMAND] Entra: type={'callback' if callback_query else 'text'} | text: {text[:25]}...")

        # ===== CASCADA DE ROUTING =====
        # [1] Callbacks (botones inline)
        if callback_query:
            print(f"[ROUTE] → _handle_callback_query()")
            await self._handle_callback_query(text, _cb_msg_id, callback_query=callback_query)
            return

        # [2] Comandos / (escapan de estados activos)
        if lower_text.startswith("/"):
            print(f"[ROUTE] → _handle_text_command()")
            await self._handle_text_command(text)
            return

        # [3] Estados activos (usuario espera input específico)
        print(f"[ROUTE] → _handle_active_state()")
        if await self._handle_active_state(text, _cb_msg_id):
            return  # El estado consumió el mensaje

        # 0.5 DETECTAR URL PARA VIDEO PREMIUM
        # Seleccion de tipo para CREAR VIDEO desde la cola
        if lower_text.startswith("vtype_") and callback_query:
            parts = text.split("_", 2)  # usar text original para preservar mayusculas del ID
            if len(parts) == 3:
                vtype, product_id = parts[1].lower(), parts[2]
                products = self._load_queue_data()
                product = next((p for p in products if p.get("id") == product_id), None)
                if not product:
                    await self.send_notification("Producto no encontrado en la cola.", reply_markup=self.get_master_keyboard())
                    return
                await self.send_notification(
                    f"Generando guion de {vtype.upper()} con Gemini...\n"
                    f"Producto: {product.get('title','')[:60]}"
                )
                asyncio.create_task(self._generate_and_preview_script(product, vtype, _cb_msg_id))
            return

        # [Estados activos duplicados REMOVIDOS - ahora en _handle_active_state()]

        # 1. DETECTAR ENLACES
        urls = re.findall(r'https?://[^\s]+', text)
        
        if urls:
            is_queue_forced = self.user_state.get("queue_mode") or lower_text.startswith("/cola") or lower_text.startswith("/queue") or len(urls) > 1
            is_video_ia_forced = self.user_state.get("video_ia_mode")
            
            if is_video_ia_forced:
                await self.send_notification(f"🎬 **Modo Video IA Detectado.** Procesando `{len(urls)}` enlace(s)...")
                for u in urls:
                    status_resp = await self.send_notification(f"⏳ **Scrapeando y generando video IA para:**\n{u}")
                    status_msg_id = status_resp["result"]["message_id"] if status_resp and status_resp.get("ok") else None
                    asyncio.create_task(self._generate_video_ia_direct(u, msg_id=status_msg_id))
                return
            elif is_queue_forced:
                await self.send_notification(f"📥 **Modo Cola Detectado.** Procesando `{len(urls)}` enlace(s)...")
                for u in urls:
                    status_resp = await self.send_notification(f"⏳ **Extrayendo datos de:**\n{u}")
                    status_msg_id = status_resp["result"]["message_id"] if status_resp and status_resp.get("ok") else None
                    asyncio.create_task(self._process_queue_command(u, affiliate_override=None, msg_id=status_msg_id))
                return
            
            # Si tiene prefijo de test, lo manda a captura de prueba
            if lower_text.startswith("/test"):
                url = urls[0]
                affiliate_override = urls[1] if len(urls) > 1 else None
                await self.send_notification(f"📸 **Generando captura de prueba...**\n`{url}`")
                asyncio.create_task(self._process_test_command(url, affiliate_override))
                return

            url = urls[0]

            # ---------------------------------------------------------------
            # AUTO-ASIGNACIÓN DE LINK AFILIADO
            # Solo si el usuario manda un link YA AFILIADO (meli.la o amzn.to)
            # y hay productos en cola con pending_affiliate → asignarlo.
            # Links normales de mercadolibre.com o amazon van al flujo normal.
            # ---------------------------------------------------------------
            is_meli_affiliate = "meli.la" in url
            is_amazon_affiliate = "amzn.to" in url or ("amazon.com" in url and "tag=" in url)

            if is_meli_affiliate or is_amazon_affiliate:
                ALL_NICHES = ["general", "baby", "pets", "tenis", "moda"]
                assigned = False
                for niche_key in ALL_NICHES:
                    queue = self._load_queue(niche=niche_key)
                    for product in queue:
                        if product.get("review_status") == "pending_affiliate":
                            product["affiliate_url"] = url
                            product.pop("review_status", None)
                            self._save_queue(queue, niche=niche_key)
                            title = product.get("title", product.get("id", "Desconocido"))[:50]
                            await self.send_notification(
                                f"✅ *Link asignado automáticamente*\n"
                                f"📦 `{title}`\n"
                                f"🔗 `{url}`\n"
                                f"🎯 Cola: *{niche_key.upper()}*\n\n"
                                f"El producto ya está listo para publicarse en el siguiente slot."
                            )
                            assigned = True
                            break
                    if assigned:
                        break

                if assigned:
                    return  # No publicar inmediatamente, solo asignar
                # Si no había pending, cae al flujo normal de publicación
            # ---------------------------------------------------------------


            # Detectar prefijo manual para forzar red
            override_plat = None
            if lower_text.startswith("tg "): override_plat = "telegram"
            elif lower_text.startswith("fb "): override_plat = "facebook"
            elif lower_text.startswith("pin "): override_plat = "pinterest"
            elif lower_text.startswith("page "): override_plat = "fb_page"

            # Si no, lo publica inmediatamente (Solo toma el primer URL, asume que es el único)
            affiliate_override = urls[1] if len(urls) > 1 else None
            
            if override_plat:
                target_platform = override_plat
                platform_str = f"Solo {override_plat.capitalize()}"
            else:
                active = self.user_state.get("active_networks", {})
                target_platform = [k for k, v in active.items() if v] if active else "both"
                platform_str = "Todas las Redes"
                if target_platform == "facebook": platform_str = "Solo Facebook"
                elif target_platform == "pinterest": platform_str = "Solo Pinterest"
                elif target_platform == "telegram": platform_str = "Solo Telegram"
            
            # Enviar notificación de "Procesando..."
            status_resp = await self.send_notification(
                f"⏳ **Scrapeando y agregando a la cola...**\n`{url}`"
            )
            msg_id = status_resp["result"]["message_id"] if status_resp and status_resp.get("ok") else None

            # Procesar como cola (agregar a la cola, NO publicar directo)
            asyncio.create_task(
                self._process_manual_publication(url, target_platform, affiliate_override)
            )
            return




        lower_text = text.lower().strip()

        # [Comandos / duplicados REMOVIDOS - ahora en _handle_text_command()]

        if lower_text.startswith("force_dup_"):
            temp_id = text[len("force_dup_"):]
            await self._handle_force_duplicate(temp_id, callback_query)
            return

        if lower_text.startswith("discard_dup_"):
            temp_id = text[len("discard_dup_"):]
            await self._handle_discard_duplicate(temp_id, callback_query)
            return

        if lower_text.startswith("retry_aff_"):
            parts = text[len("retry_aff_"):].split("_", 1)
            if len(parts) == 2:
                await self._handle_retry_affiliate(parts[0], parts[1], callback_query)
            return

        # --- NAVEGACIÓN DE MENÚ JERÁRQUICO ---
        if lower_text.startswith("nav_"):
            _msg_id = _cb_msg_id
            nav_map = {
                "nav_main": "main", "nav_publicacion": "publicacion",
                "nav_contenido": "contenido", "nav_video_niches": "video_niches", "nav_redes": "redes",
                "nav_programacion": "programacion",
                "nav_mantenimiento": "mantenimiento",
            }
            self.user_state["current_menu"] = nav_map.get(lower_text, "main")
            titles = {
                "main": "🛠️ **Panel de Control Maestro**",
                "publicacion": "🚀 **Publicación**",
                "contenido": "🗂️ **Gestión de Contenido**",
                "redes": "🌐 **Redes Sociales**",
                "programacion": "⏰ **Programación**",
                "mantenimiento": "🔧 **Mantenimiento del Bot**",
            }
            title = titles.get(self.user_state["current_menu"], "🛠️ **Menú**")
            await self.send_notification(
                title + "\n" + "⠀" * 40,
                reply_markup=self.get_master_keyboard(),
                msg_id=_msg_id
            )
            return

        if lower_text == "add_fb_group":
            self.user_state["awaiting_fb_group_url"] = True
            await self.send_notification(
                "Envia el URL del grupo de Facebook que quieres anadir.",
                reply_markup=self.get_master_keyboard()
            )
            return

        if lower_text == "cmd_conf_discount":
            self.user_state["awaiting_discount_pesos"] = True
            await self.send_notification(
                "Ingresa el nuevo Descuento Mínimo (Ahorro Premium) en Pesos (ej. 500):",
                reply_markup=self.get_master_keyboard()
            )
            return

        if lower_text == "toggle_duplicates":
            current = self.user_state.get("allow_duplicate_products", False)
            self.user_state["allow_duplicate_products"] = not current
            self._save_user_state()
            new_state = self.user_state.get("allow_duplicate_products", False)
            status = "PERMITIDO" if new_state else "RECHAZADO"
            await self.send_notification(
                f"✅ Productos Duplicados: {status}\n"
                "Los scrapers ahora {'aceptarán' if new_state else 'rechazarán'} productos ya publicados.",
                reply_markup=self.get_master_keyboard()
            )
            return

        if lower_text == "show_fb_groups":
            all_groups = list(dict.fromkeys(
                Config.FB_GROUPS + 
                getattr(Config, 'FB_GROUPS_BABY', []) + 
                getattr(Config, 'FB_GROUPS_PETS', []) + 
                getattr(Config, 'FB_GROUPS_TENIS', []) + 
                getattr(Config, 'FB_GROUPS_MODA', [])
            ))

            def format_links(title, links):
                if not links: return f"**{title}**: Ninguno\n"
                formatted = "\n".join([f"• [{link.split('/groups/')[-1].strip('/')}]({link})" for link in links])
                return f"**{title}** ({len(links)}):\n{formatted}\n\n"

            msg = "📊 **TUS GRUPOS (Toca el enlace para abrir)**\n\n"
            msg += format_links("📱 General", Config.FB_GROUPS)
            msg += format_links("🧸 Bebés", Config.FB_GROUPS_BABY)
            msg += format_links("🐶 Mascotas", Config.FB_GROUPS_PETS)
            msg += format_links("👟 Tenis", Config.FB_GROUPS_TENIS)
            msg += format_links("👗 Moda", Config.FB_GROUPS_MODA)
            
            msg += "_(Para agregar/quitar, usa los botones debajo)_"
            
            if len(msg) > 4000:
                msg = msg[:4000] + "\n\n... [Truncado]"

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🗑️ ELIMINAR UN GRUPO", "callback_data": "fb_group_browser"}],
                    [{"text": "AÑADIR GRUPO", "callback_data": "add_fb_group"}],
                    [{"text": "↩️ Volver a Redes", "callback_data": "nav_redes"}]
                ]
            }

            await self.send_notification(msg, reply_markup=keyboard, msg_id=_cb_msg_id)
            return

        # --- ACTIVAR/DESACTIVAR REDES ---
        if lower_text.startswith("toggle_net_"):
            net_key = lower_text[len("toggle_net_"):]
            active = self.user_state.get("active_networks", {
                "facebook": True, "facebook_bebes": True, "fb_page": True, "telegram": True,
                "pinterest": True, "tiktok": True, "youtube": True, "web": True
            })
            active[net_key] = not active.get(net_key, True)
            self.user_state["active_networks"] = active
            self._save_user_state()
            net_status = "ON" if active[net_key] else "OFF"
            # Toast inmediato + actualizar solo el teclado (más confiable que editMessageText)
            await self._answer_callback(callback_query, text=f"{net_key.upper()}: {net_status}")
            if _cb_msg_id:
                ok = await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
                if not ok:
                    await self.send_notification(
                        f"**{net_key.upper()}** → {'✅ ACTIVO' if active[net_key] else '❌ INACTIVO'}\n" + "⠀" * 40,
                        reply_markup=self.get_master_keyboard()
                    )
            return


        if lower_text == "toggle_fb_split":
            current = self.user_state.get("fb_split_blocks", 1)
            self.user_state["fb_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            new_val = self.user_state["fb_split_blocks"]
            await self._answer_callback(callback_query, text=f"Bloques FB General: {new_val}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return

        if lower_text == "toggle_fb_pets_split":
            current = self.user_state.get("fb_pets_split_blocks", 1)
            self.user_state["fb_pets_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback(callback_query, text=f"Bloques FB Mascotas: {self.user_state['fb_pets_split_blocks']}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return
            
        if lower_text == "toggle_fb_moda_split":
            current = self.user_state.get("fb_moda_split_blocks", 1)
            self.user_state["fb_moda_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback(callback_query, text=f"Bloques FB Moda: {self.user_state['fb_moda_split_blocks']}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return
            
        if lower_text == "toggle_fb_tenis_split":
            current = self.user_state.get("fb_tenis_split_blocks", 1)
            self.user_state["fb_tenis_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            await self._answer_callback(callback_query, text=f"Bloques FB Tenis: {self.user_state['fb_tenis_split_blocks']}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return

        if lower_text == "toggle_fb_bebes_split":
            current = self.user_state.get("fb_bebes_split_blocks", 1)
            self.user_state["fb_bebes_split_blocks"] = 2 if current == 1 else (3 if current == 2 else 1)
            self._save_user_state()
            new_val = self.user_state["fb_bebes_split_blocks"]
            await self._answer_callback(callback_query, text=f"Bloques FB Bebés: {new_val}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return


        # --- CONFIGURACIÓN DE HORARIOS POR RED ---
        if lower_text.startswith("prog_net_"):
            net = lower_text.replace("prog_net_", "")
            self.user_state["current_menu"] = "prog_net_grid"
            self.user_state["prog_selected_net"] = net
            self._save_user_state()
            await self.send_notification(
                f"🕒 **Configurando horarios para: {net.upper()}**\n" + "⠀" * 40, 
                reply_markup=self.get_master_keyboard(), 
                msg_id=_cb_msg_id
            )
            return
            
        if lower_text.startswith("toggle_custom_"):
            net = lower_text.replace("toggle_custom_", "")
            from core.scheduler import Scheduler
            s = Scheduler(self.orchestrator)
            config = s.load_slots()
            use_custom = config.get("use_custom", {}).get(net, False)
            if "use_custom" not in config: config["use_custom"] = {}
            config["use_custom"][net] = not use_custom
            s.save_slots(config)
            estado = 'ACTIVADO' if not use_custom else 'DESACTIVADO'
            await self._answer_callback(callback_query, text=f"Horario {net.upper()}: {estado}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return

        if lower_text.startswith("toggle_slot_"):
            try:
                parts = lower_text.split("_")
                slot = int(parts[-1])
                net = parts[2]

                from core.scheduler import Scheduler
                s = Scheduler(self.orchestrator)
                config = s.load_slots()

                if net == "general":
                    slots = config.get("general", [])
                    if slot in slots: slots.remove(slot)
                    else: slots.append(slot)
                    config["general"] = sorted(slots)
                else:
                    if "custom" not in config: config["custom"] = {}
                    if net not in config["custom"]: config["custom"][net] = []
                    slots = config["custom"][net]
                    if slot in slots: slots.remove(slot)
                    else: slots.append(slot)
                    config["custom"][net] = sorted(slots)

                s.save_slots(config)
                slot_estado = 'ON' if slot in slots else 'OFF'
                await self._answer_callback(callback_query, text=f"{slot:02d}:00 {net.upper()}: {slot_estado}")
                if _cb_msg_id:
                    await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            except Exception as e:
                print(f"Error toggling slot: {e}")
            return

        # --- MODO DE CONTENIDO/VIDEO ---
        if lower_text.startswith("video_mode_"):
            _msg_id = _cb_msg_id
            mode = lower_text[len("video_mode_"):]
            self.user_state["video_mode"] = mode
            self._save_user_state()
            mode_names = {"normal": "Normal", "benefits": "Beneficios", "comparison": "Comparativa"}
            await self.send_notification(
                f"🎬 Modo de contenido: **{mode_names.get(mode, mode)}** ✅\n" + "⠀" * 40,
                reply_markup=self.get_master_keyboard(),
                msg_id=_msg_id
            )
            return

        # --- VIDEO PREMIUM: pedir URL al fabricante ---
        if lower_text == "video_premium_btn":
            self.user_state["awaiting_guion"] = True
            work_dir = os.path.join(Config.BASE_DIR, "captures", "premium_temp")
            self.safe_makedirs(work_dir)
            self.user_state["premium_images_collected"] = []
            await self.send_notification(
                "VIDEO PREMIUM\n\n"
                "Paso 1/3: Escribe el guion.\n"
                "Una escena por linea. Ejemplo:\n\n"
                "Este producto tiene cancelacion de ruido activa\n"
                "Bateria de 30 horas de duracion\n"
                "Disponible hoy con 45% de descuento\n"
                "Consiguelo en el link de mi descripcion\n\n"
                "Manda el texto cuando este listo." + " " * 5,
                msg_id=_cb_msg_id
            )
            return

        # --- PUBLISH AMAZON/ML ---
        if lower_text == "publish_next_amazon":
            await self.send_notification("⚡ **Buscando siguiente producto de Amazon en la lista...**")
            try:
                history = set(self._load_history())
                products = self._load_queue()
                target = None
                for p in products:
                    p_id = p.get('id'); p_url = p.get('affiliate_url', '').lower()
                    if (p_id and p_id in history) or (p_url and p_url in history): continue
                    if "amazon" in p_url or "amzn" in p_url:
                        target = p; break
                if target:
                    active = self.user_state.get("active_networks", {})
                    target_platform = [k for k, v in active.items() if v] if active else "both"
                    img_path = target.get('visual_capture') or target.get('screenshot', '')
                    if img_path and not os.path.exists(img_path):
                        img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))
                    asyncio.create_task(self.orchestrator.run_publication(
                        target['affiliate_url'], target_platform=target_platform,
                        manual_image=img_path, pre_scraped_details=target
                    ))
                else:
                    await self.send_notification("⚠️ No encontré productos de Amazon en la cola.", reply_markup=self.get_master_keyboard())
            except Exception as e:
                await self.send_notification(f"❌ Error: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text == "publish_next_ml":
            await self.send_notification("⚡ **Buscando siguiente producto de Mercado Libre...**")
            try:
                history = set(self._load_history())
                products = self._load_queue()
                target = None
                for p in products:
                    p_id = p.get('id'); p_url = p.get('affiliate_url', '').lower()
                    if (p_id and p_id in history) or (p_url and p_url in history): continue
                    if ("mercadolibre" in p_url or "meli.la" in p_url) and is_product_ready_for_publication(p):
                        target = p; break
                if target:
                    active = self.user_state.get("active_networks", {})
                    target_platform = [k for k, v in active.items() if v] if active else "both"
                    img_path = target.get('visual_capture') or target.get('screenshot', '')
                    if img_path and not os.path.exists(img_path):
                        img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))
                    asyncio.create_task(self.orchestrator.run_publication(
                        target['affiliate_url'], target_platform=target_platform,
                        manual_image=img_path, pre_scraped_details=target
                    ))
                else:
                    await self.send_notification("⚠️ No encontré productos de Mercado Libre en la cola.", reply_markup=self.get_master_keyboard())
            except Exception as e:
                await self.send_notification(f"❌ Error: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text.startswith("publish_next_"):
            if lower_text == "publish_next_now":
                target_platform = [k for k, v in self.user_state.get("active_networks", {}).items() if v] if self.user_state.get("active_networks", {}) else "both"
            else:
                plat_map = {"tg": "telegram", "fb": "facebook", "pin": "pinterest", "tw": "twitter"}
                plat_key = lower_text.split("_")[-1]
                target_platform = plat_map.get(plat_key, "both")

            await self.send_notification("⚡ **Buscando siguiente producto en la lista...**")
            asyncio.create_task(self._process_publish_next(target_platform))
            return
            
        if lower_text.startswith("add_fb_niche_"):
            niche_map = {
                "add_fb_niche_fb_groups": "FB_GROUP_URLS",
                "add_fb_niche_fb_groups_baby": "FB_GROUPS_BABY_URLS",
                "add_fb_niche_fb_groups_pets": "FB_GROUPS_PETS_URLS",
                "add_fb_niche_fb_groups_tenis": "FB_GROUPS_TENIS_URLS",
                "add_fb_niche_fb_groups_moda": "FB_GROUPS_MODA_URLS",
            }
            target_env_var = niche_map.get(lower_text)
            if not target_env_var:
                await self.send_notification("Nicho no reconocido.", reply_markup=self.get_master_keyboard())
                return
            url_to_add = self.user_state.pop("pending_fb_group_url", None)
            if not url_to_add:
                await self.send_notification("❌ No se encontró el URL pendiente.", reply_markup=self.get_master_keyboard())
                return
                
            await self._add_fb_group_to_env(url_to_add, target_env_var)
            
            from dotenv import load_dotenv
            load_dotenv(override=True)
            # Releer .env para los grupos ya es automático gracias al @property en ConfigMeta.
            return
            

        # --- OMITIR GRUPOS FB FALLIDOS (descartarlos definitivamente) ---
        if lower_text == "omit_fb_failed":
            fb_failed_file = os.path.join(Config.BASE_DIR, "fb_failed_queue.json")
            try:
                count = self._count_fb_failed()
                if os.path.exists(fb_failed_file):
                    os.remove(fb_failed_file)
                await self.send_notification(
                    f"🗑️ *Cola de fallidos eliminada.*\n"
                    f"Se descartaron {count} publicaciones pendientes de FB.\n"
                    f"Los cursores no se vieron afectados.",
                    reply_markup=self.get_master_keyboard(),
                    msg_id=_cb_msg_id
                )
            except Exception as e:
                await self.send_notification(f"❌ Error al omitir fallidos: {e}", reply_markup=self.get_master_keyboard())
            return

        # --- NAVEGADOR DE GRUPOS FB (para borrar grupos) ---
        if lower_text == "fb_group_search":
            self.user_state["fb_group_search_mode"] = True
            await self.send_notification(
                "🔍 Envía una palabra clave o parte de la URL para buscar un grupo de Facebook:",
                reply_markup=self.get_master_keyboard()
            )
            return

        if lower_text == "fb_group_browser" or lower_text.startswith("fb_group_nav_"):
            groups = list(dict.fromkeys(
                Config.FB_GROUPS + 
                getattr(Config, 'FB_GROUPS_BABY', []) + 
                getattr(Config, 'FB_GROUPS_PETS', []) + 
                getattr(Config, 'FB_GROUPS_TENIS', []) + 
                getattr(Config, 'FB_GROUPS_MODA', [])
            ))
            if not groups:
                await self.send_notification(
                    "⚠️ No hay grupos de Facebook configurados en el .env.",
                    reply_markup=self.get_master_keyboard(),
                    msg_id=_cb_msg_id
                )
                return
            # Determinar índice actual
            idx = 0
            if lower_text.startswith("fb_group_nav_"):
                try:
                    idx = int(lower_text.split("fb_group_nav_")[1])
                except ValueError:
                    idx = 0
            idx = max(0, min(idx, len(groups) - 1))
            group_url = groups[idx]
            group_name = group_url.split("/groups/")[-1].strip("/") if "/groups/" in group_url else group_url

            nav_row = []
            if idx > 0:
                nav_row.append({"text": "◀️ Anterior", "callback_data": f"fb_group_nav_{idx - 1}"})
            if idx < len(groups) - 1:
                nav_row.append({"text": "Siguiente ▶️", "callback_data": f"fb_group_nav_{idx + 1}"})

            keyboard = {
                "inline_keyboard": [
                    nav_row,
                    [{"text": f"🗑️ ELIMINAR ESTE GRUPO", "callback_data": f"fb_group_delete_{idx}"}],
                    [{"text": "🔍 Buscar Grupo", "callback_data": "fb_group_search"}],
                    [{"text": "↩️ Volver a Redes", "callback_data": "nav_redes"}]
                ]
            }
            msg = (
                f"📋 *Grupo {idx + 1} de {len(groups)}*\n\n"
                f"🔗 [{group_name}]({group_url})"
            )
            await self.send_notification(msg, reply_markup=keyboard, msg_id=_cb_msg_id)
            return

        # --- ELIMINAR GRUPO FB POR ÍNDICE ---
        if lower_text.startswith("fb_group_delete_"):
            try:
                idx = int(lower_text.split("fb_group_delete_")[1])
            except ValueError:
                await self.send_notification("❌ Índice de grupo inválido.", reply_markup=self.get_master_keyboard())
                return
            groups = list(dict.fromkeys(
                Config.FB_GROUPS + 
                getattr(Config, 'FB_GROUPS_BABY', []) + 
                getattr(Config, 'FB_GROUPS_PETS', []) + 
                getattr(Config, 'FB_GROUPS_TENIS', []) + 
                getattr(Config, 'FB_GROUPS_MODA', [])
            ))
            if idx < 0 or idx >= len(groups):
                await self.send_notification("❌ Ese grupo ya no existe.", reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
                return
            group_url = groups[idx]
            group_name = group_url.split("/groups/")[-1].strip("/") if "/groups/" in group_url else group_url
            await self._remove_fb_group_from_env(group_url)
            
            from dotenv import load_dotenv
            load_dotenv(override=True)
            # La actualización en Config es automática vía @property
            
            # Volver al navegador con el índice anterior si es posible
            new_groups = list(dict.fromkeys(
                Config.FB_GROUPS + 
                getattr(Config, 'FB_GROUPS_BABY', []) + 
                getattr(Config, 'FB_GROUPS_PETS', []) + 
                getattr(Config, 'FB_GROUPS_TENIS', []) + 
                getattr(Config, 'FB_GROUPS_MODA', [])
            ))
            new_total = len(new_groups)
            if new_total == 0:
                await self.send_notification(
                    f"🗑️ Grupo *{group_name}* eliminado.\nYa no quedan grupos configurados.",
                    reply_markup=self.get_master_keyboard(),
                    msg_id=_cb_msg_id
                )
                return
            new_idx = max(0, min(idx, new_total - 1))
            new_url = new_groups[new_idx]
            new_name = new_url.split("/groups/")[-1].strip("/") if "/groups/" in new_url else new_url
            nav_row = []
            if new_idx > 0:
                nav_row.append({"text": "◀️ Anterior", "callback_data": f"fb_group_nav_{new_idx - 1}"})
            if new_idx < new_total - 1:
                nav_row.append({"text": "Siguiente ▶️", "callback_data": f"fb_group_nav_{new_idx + 1}"})
            keyboard = {
                "inline_keyboard": [
                    nav_row,
                    [{"text": "🗑️ ELIMINAR ESTE GRUPO", "callback_data": f"fb_group_delete_{new_idx}"}],
                    [{"text": "🔍 Buscar Grupo", "callback_data": "fb_group_search"}],
                    [{"text": "↩️ Volver a Redes", "callback_data": "nav_redes"}]
                ]
            }
            await self.send_notification(
                f"✅ Grupo *{group_name}* eliminado.\n\n"
                f"📋 *Grupo {new_idx + 1} de {new_total}*\n\n"
                f"🔗 [{new_name}]({new_url})",
                reply_markup=keyboard,
                msg_id=_cb_msg_id
            )
            return

        if lower_text == "last_published_show":
            details = self._load_last_published()
            if not details:
                await self.send_notification("⚠️ Aún no hay ningún producto publicado registrado.", reply_markup=self.get_master_keyboard())
                return
            await self._send_history_product_actions(details, msg_id=_cb_msg_id)
            return

        if lower_text == "force_video":
            await self.send_notification("🎬 **Generando video del último producto...** (Espera unos segundos)")
            try:
                details = self._load_last_published()
                if not details:
                    await self.send_notification("⚠️ No encontré el archivo `last_published.json`. Debes publicar algo primero.", reply_markup=self.get_master_keyboard())
                    return

                if "id" not in details and "title" not in details:
                    await self.send_notification("⚠️ El último registro no tiene datos suficientes.", reply_markup=self.get_master_keyboard())
                    return

                import tiktok_generator
                music = None
                music_files = glob.glob(os.path.join(tiktok_generator.MUSIC_DIR, "*.mp3")) + glob.glob(os.path.join(tiktok_generator.MUSIC_DIR, "*.m4a"))
                if music_files:
                    music = music_files[0]

                video_path = await asyncio.to_thread(tiktok_generator.create_tiktok_video, details, music)

                if video_path and os.path.exists(video_path):
                    caption = f"📱 **¡Video Recuperado!**\nSúbelo a TikTok/Reels:\n`{details.get('affiliate_url', '')}`"
                    await self.send_video(video_path, caption=caption)
                    await self.send_notification("✅ Video listo." + " " + "⠀" * 38, reply_markup=self.get_master_keyboard())
                else:
                    await self.send_notification("❌ Fallo generando el video de recuperación.", reply_markup=self.get_master_keyboard())
            except Exception as e:
                await self.send_notification(f"❌ Error forzando video: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text == "mode_facebook":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "facebook":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "facebook"
                msg = "📘 **Modo de publicación cambiado a:** `Solo Grupos FB`."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return

        if lower_text == "mode_fb_page":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "fb_page":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "fb_page"
                msg = "📄 **Modo de publicación cambiado a:** `Solo Página FB` (API Oficial)."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return

        if lower_text == "mode_telegram":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "telegram":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "telegram"
                msg = "✈️ **Modo de publicación cambiado a:** `Solo Telegram`."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return

        if lower_text == "mode_pinterest":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "pinterest":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "pinterest"
                msg = "📌 **Modo de publicación cambiado a:** `Solo Pinterest`."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return
            
        if lower_text == "mode_tiktok":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "tiktok":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "tiktok"
                msg = "🎵 **Modo de publicación cambiado a:** `Solo TikTok` (Sin publicar en YouTube u otras redes)."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return
            
        if lower_text == "mode_youtube":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "youtube":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "youtube"
                msg = "▶️ **Modo de publicación cambiado a:** `Solo YouTube Shorts`."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return
            
        if lower_text == "mode_video":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "video":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "video"
                msg = "🎬 **Modo de publicación cambiado a:** `Solo Video (TikTok y YouTube)`."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return
            
        if lower_text == "mode_web":
            current_mode = self.user_state.get("mode", "both")
            if current_mode == "web":
                self.user_state["mode"] = "both"
                msg = "✨ **Modo de publicación restablecido a:** `Todas las Redes`."
            else:
                self.user_state["mode"] = "web"
                msg = "🌐 **Modo de publicación cambiado a:** `Solo Web` (Ignora redes y video)."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return
            


        if lower_text in ["cola", "/cola"]:
            try:
                history = set(self._load_history())
                
                # Cargar colas
                q_gen = self._get_pending_queue(niche="general")
                q_baby = self._get_pending_queue(niche="baby")
                q_pets = self._get_pending_queue(niche="pets")
                
                q_moda = self._get_pending_queue(niche="moda")
                q_tenis = self._get_pending_queue(niche="tenis")
                total = len(q_gen) + len(q_baby) + len(q_pets) + len(q_moda) + len(q_tenis)
                if total == 0:
                    await self.send_notification(
                        "📭 **Las colas están vacías.** No hay ofertas pendientes de publicar.",
                        reply_markup=self.get_master_keyboard()
                    )
                    return
                    
                msg = (
                    f"📋 **Estado Global de Colas ({total} productos)**\n\n"
                    f"General: **{len(q_gen)}** en espera\n"
                    f"Bebes: **{len(q_baby)}** en espera\n"
                    f"Mascotas: **{len(q_pets)}** en espera\n"
                    f"Moda: **{len(q_moda)}** en espera\n"
                    f"Tenis: **{len(q_tenis)}** en espera\n\n"
                    f"_Nota: El sistema publicará 1 producto de cada cola con contenido durante los horarios programados._"
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "Ver Cola General", "callback_data": "queue_nav_general"}],
                        [{"text": "Ver Cola Bebes", "callback_data": "queue_nav_baby"}],
                        [{"text": "Ver Cola Mascotas", "callback_data": "queue_nav_pets"}],
                        [{"text": "Ver Cola Moda", "callback_data": "queue_nav_moda"}],
                        [{"text": "Ver Cola Tenis", "callback_data": "queue_nav_tenis"}],
                        [{"text": "VOLVER AL MENU", "callback_data": "nav_contenido"}]
                    ]
                }
                
                await self.send_notification(msg, reply_markup=keyboard, msg_id=_cb_msg_id)
            except Exception as e:
                await self.send_notification(f"❌ Error al consultar cola: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text == "clear_queue":
            pending = self._get_pending_queue()
            keyboard = {"inline_keyboard": [[
                {"text": "SI, VACIAR", "callback_data": "clear_queue_yes"},
                {"text": "CANCELAR",   "callback_data": "clear_queue_no"},
            ]]}
            await self.send_notification(
                f"Tienes {len(pending)} producto(s) en la cola. Esta accion es irreversible. Confirmas?",
                reply_markup=keyboard,
                msg_id=_cb_msg_id
            )
            return

        if lower_text == "clear_queue_no":
            await self.send_notification("Operacion cancelada." + " " * 5, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return

        if lower_text == "clear_queue_yes":
            try:
                products = self._load_queue()
                history = set(self._load_history())
                added_count = 0
                for p in products:
                    p_id = p.get('id')
                    if p_id and p_id not in history:
                        history.add(p_id)
                        added_count += 1
                        
                # Guardar historial
                self._save_history(history)
                # Vaciar TODAS las colas
                self._save_queue([], niche="general")
                self._save_queue([], niche="baby")
                self._save_queue([], niche="pets")
                await self.send_notification(
                    f"🗑️ **Cola Vaciada con Éxito**\nSe eliminaron **{added_count}** productos de la lista de espera y se marcaron como 'Ya Publicados' para que los scrapers los omitan en el futuro.", 
                    reply_markup=self.get_master_keyboard()
                )
            except Exception as e:
                await self.send_notification(f"❌ Error al vaciar cola: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text == "force_web":
            await self.send_notification("Iniciando Sincronizacion Forzada de la Landing Page...")
            try:
                from publishers.web_publisher import WebPublisher
                wp = WebPublisher()
                wp.telegram_bot = self

                build_ok = await asyncio.to_thread(wp.build)
                if not build_ok:
                    await self.send_notification("Error al reconstruir la Landing Page.", reply_markup=self.get_master_keyboard())
                    return

                count = await asyncio.to_thread(wp.push_to_github, "Forzado desde Telegram")
                await self.send_notification(
                    f"Landing Page lista. {count} archivos sincronizados con Cloudflare.",
                    reply_markup=self.get_master_keyboard()
                )
            except Exception as e:
                await self.send_notification(f"Error general: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text == "toggle_force_menu":
            self.user_state["show_force_menu"] = not self.user_state.get("show_force_menu", False)
            await self.send_notification("⚡ **Menú de Forzado**\n¿Qué deseas forzar?\n" + "\u2800" * 40, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return
            
        if lower_text == "toggle_network_menu":
            self.user_state["show_network_menu"] = not self.user_state.get("show_network_menu", False)
            await self.send_notification("📡 **Menú de Redes**\nElige en qué plataforma quieres que se enfoque el bot:\n" + "\u2800" * 40, reply_markup=self.get_master_keyboard())
            return
            
        if lower_text in ["force_pin", "force_fb", "force_tg", "force_fb_page", "force_youtube"]:
            platform_map = {
                "force_pin": "pinterest",
                "force_fb": "facebook",
                "force_fb_page": "fb_page",
                "force_tg": "telegram",
                "force_youtube": "youtube"
            }
            target_plat = platform_map[lower_text]
            
            await self.send_notification(f"🚀 **Forzando publicación en {target_plat.upper()} del último producto...**", reply_markup=self.get_master_keyboard())
            try:
                details = self._load_last_published()
                if not details:
                    await self.send_notification("⚠️ No encontré el archivo `last_published.json`. Debes publicar algo primero.")
                    return
                    
                # Inyectar bandera para evitar doble raspado innecesario
                details["skip_scrape"] = True
                    
                url = details.get("affiliate_url", details.get("real_url", ""))
                img_path = details.get("visual_capture") or details.get("screenshot", "")
                if img_path and not os.path.exists(img_path):
                    img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))
                
                # Ejecutar la publicación forzada asíncronamente
                asyncio.create_task(self.orchestrator.run_publication(
                    url,
                    target_platform=target_plat,
                    manual_image=img_path,
                    pre_scraped_details=details
                ))
            except Exception as e:
                await self.send_notification(f"❌ Error forzando {target_plat}: {e}", reply_markup=self.get_master_keyboard())
            return


        if lower_text == "get_status":
            try:
                from datetime import datetime as _dt
                _now = _dt.now()

                # ── Redes activas ────────────────────────────────────────────
                active = self.user_state.get("active_networks", {
                    "facebook": True, "fb_page": True, "telegram": True,
                    "pinterest": True, "tiktok": True, "youtube": True, "web": True
                })
                net_names = {
                    "facebook": "FB Grupos Gen", "facebook_bebes": "FB Bebes", "fb_page": "FB Page",
                    "telegram": "Telegram", "pinterest": "Pinterest",
                    "tiktok": "TikTok", "youtube": "YouTube", "web": "WordPress"
                }
                redes_lines = " | ".join(
                    f"{'✅' if active.get(k) else '❌'} {v}"
                    for k, v in net_names.items()
                )

                # ── Slots programados ────────────────────────────────────────
                try:
                    from core.scheduler import Scheduler
                    _s_config = Scheduler(self.orchestrator).load_slots()
                    _slots = sorted(_s_config.get("general", []))
                except Exception:
                    _slots = []
                if _slots:
                    slots_str = "  ".join(f"{h:02d}:00" for h in _slots)
                    _next = next((h for h in _slots if h > _now.hour), _slots[0] if _slots else None)
                    next_str = f"{_next:02d}:00" if _next is not None else "—"
                    if _next is not None and _next <= _now.hour:
                        next_str += " (mañana)"
                else:
                    slots_str = "⚠️ Sin slots configurados"
                    next_str = "—"

                # ── Cola de productos ────────────────────────────────────────
                try:
                    q_gen = self._get_pending_queue(niche="general")
                    q_baby = self._get_pending_queue(niche="baby")
                    q_pets = self._get_pending_queue(niche="pets")
                    q_tenis = self._get_pending_queue(niche="tenis")
                    q_moda = self._get_pending_queue(niche="moda")

                    total_pend = len(q_gen) + len(q_baby) + len(q_pets) + len(q_tenis) + len(q_moda)
                    queue_str = f"**{total_pend} en espera**\n"
                    queue_str += f"   ├ General: {len(q_gen)}\n"
                    queue_str += f"   ├ Bebes: {len(q_baby)}\n"
                    queue_str += f"   ├ Mascotas: {len(q_pets)}\n"
                    queue_str += f"   ├ Tenis: {len(q_tenis)}\n"
                    queue_str += f"   └ Moda: {len(q_moda)}"
                except Exception:
                    queue_str = "No disponible"

                # ── Grupos de FB ─────────────────────────────────────────────
                try:
                    fb_gen = len(Config.FB_GROUPS)
                    fb_baby = len(getattr(Config, 'FB_GROUPS_BABY', []))
                    fb_pets = len(getattr(Config, 'FB_GROUPS_PETS', []))
                    fb_tenis = len(getattr(Config, 'FB_GROUPS_TENIS', []))
                    fb_moda = len(getattr(Config, 'FB_GROUPS_MODA', []))
                    fb_total = fb_gen + fb_baby + fb_pets + fb_tenis + fb_moda
                    fb_str = f"**{fb_total} configurados**\n"
                    fb_str += f"   ├ General: {fb_gen}\n"
                    fb_str += f"   ├ Bebes: {fb_baby}\n"
                    fb_str += f"   ├ Mascotas: {fb_pets}\n"
                    fb_str += f"   ├ Tenis: {fb_tenis}\n"
                    fb_str += f"   └ Moda: {fb_moda}"
                except Exception:
                    fb_str = "No disponible"

                # ── Último publicado ─────────────────────────────────────────
                try:
                    _lp = self._load_last_published()
                    _lp_title = _lp.get("title", "—")[:50]
                    _lp_price = _lp.get("price", "—")
                    _lp_ts = _lp.get("published_at", "")
                    if _lp_ts:
                        try:
                            _lp_dt = _dt.fromisoformat(_lp_ts)
                            _elapsed = _now - _lp_dt
                            _h = int(_elapsed.total_seconds() // 3600)
                            _m = int((_elapsed.total_seconds() % 3600) // 60)
                            _lp_when = f"hace {_h}h {_m}m" if _h > 0 else f"hace {_m}m"
                        except Exception:
                            _lp_when = _lp_ts[:16]
                    else:
                        _lp_when = "—"
                    last_pub_str = f"`{_lp_title}` — ${_lp_price} ({_lp_when})"
                except Exception:
                    last_pub_str = "Sin datos"

                # ── Modo de video ────────────────────────────────────────────
                v_mode = self.user_state.get("video_mode", "normal")
                v_mode_names = {"normal": "Normal", "benefits": "Beneficios", "comparison": "Comparativa"}
                v_mode_str = v_mode_names.get(v_mode, v_mode)

                # ── Recursos del Servidor (VPS) ──────────────────────────────
                import shutil
                import platform
                
                try:
                    total, used, free = shutil.disk_usage(Config.BASE_DIR)
                    disk_used_gb = used / (1024**3)
                    disk_total_gb = total / (1024**3)
                    disk_percent = (used / total) * 100
                    disk_str = f"💾 **Disco:** {disk_percent:.1f}% ({disk_used_gb:.1f} / {disk_total_gb:.1f} GB)"
                except Exception as e:
                    disk_str = f"💾 **Disco:** Error ({e})"
                    
                ram_str = "🧠 **RAM:** N/A"
                if platform.system() == "Linux":
                    try:
                        mem_total = 0
                        mem_available = 0
                        with open('/proc/meminfo', 'r') as f:
                            for line in f:
                                if 'MemTotal' in line:
                                    mem_total = int(line.split()[1]) # KB
                                elif 'MemAvailable' in line:
                                    mem_available = int(line.split()[1]) # KB
                        if mem_total > 0:
                            mem_used = mem_total - mem_available
                            mem_used_gb = mem_used / (1024 * 1024)
                            mem_total_gb = mem_total / (1024 * 1024)
                            mem_percent = (mem_used / mem_total) * 100
                            ram_str = f"🧠 **RAM:** {mem_percent:.1f}% ({mem_used_gb:.1f} / {mem_total_gb:.1f} GB)"
                    except Exception as e:
                        ram_str = f"🧠 **RAM:** Error ({e})"
                        
                cpu_str = "⚡ **CPU:** N/A"
                if platform.system() == "Linux":
                    try:
                        def _read_cpu():
                            with open('/proc/stat', 'r') as f:
                                line = f.readline()
                            parts = line.split()
                            vals = [float(x) for x in parts[1:]]
                            idle = vals[3] + vals[4]
                            total = sum(vals)
                            return total, idle
                            
                        t1, id1 = _read_cpu()
                        await asyncio.sleep(0.1)
                        t2, id2 = _read_cpu()
                        diff_total = t2 - t1
                        diff_idle = id2 - id1
                        if diff_total > 0:
                            cpu_percent = (1.0 - (diff_idle / diff_total)) * 100
                            cpu_str = f"⚡ **CPU:** {cpu_percent:.1f}%"
                    except Exception as e:
                        cpu_str = f"⚡ **CPU:** Error ({e})"

                msg = (
                    f"📊 **Estado del Sistema — {_now.strftime('%d/%m/%Y %H:%M:%S')}**\n"
                    f"{'⠀' * 40}\n"
                    f"\n🌐 **Redes:**\n{redes_lines}\n"
                    f"\n⏰ **Horarios programados:**\n`{slots_str}`\n"
                    f"🔜 Próxima publicación: `{next_str}`\n"
                    f"\n📋 **Estado de Colas:**\n{queue_str}\n"
                    f"\n👥 **Grupos Facebook:**\n{fb_str}\n"
                    f"\n⚠️ **Fallidos FB pendientes:** {self._count_fb_failed()}\n"
                    f"\n📦 **Último publicado:**\n{last_pub_str}\n"
                    f"\n🎬 **Modo video:** `{v_mode_str}`\n"
                    f"\n🖥️ **Recursos del Servidor:**\n{cpu_str} | {ram_str}\n{disk_str}"
                )
                await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            except Exception as _e:
                await self.send_notification(f"❌ Error al generar estado: {_e}", reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return

        if lower_text == "toggle_queue_mode":
            current_queue = self.user_state.get("queue_mode", False)
            self.user_state["queue_mode"] = not current_queue
            self._save_user_state()
            status = "ACTIVO" if self.user_state["queue_mode"] else "DESACTIVADO"
            await self._answer_callback(callback_query, text=f"Modo Cola: {status}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return

        if lower_text == "toggle_video_ia_mode":
            current_ia = self.user_state.get("video_ia_mode", False)
            self.user_state["video_ia_mode"] = not current_ia
            self._save_user_state()
            status = "ACTIVO" if self.user_state["video_ia_mode"] else "DESACTIVADO"
            await self._answer_callback(callback_query, text=f"Modo Video IA: {status}")
            if _cb_msg_id:
                await self._edit_reply_markup(_cb_msg_id, self.get_master_keyboard())
            return

        if lower_text == "user_guide":
            sections = [
                (
                    "📖 *GUÍA DE USUARIO — GangasMX Bot*\n\n"
                    "*─── MENÚ PRINCIPAL ───*\n\n"
                    "• *PUBLICACION* — Publicar productos manualmente o ver el último\n"
                    "• *CONTENIDO* — Cola e historial de publicados\n"
                    "• *REDES* — Activar/desactivar plataformas y gestionar grupos FB\n"
                    "• *PROGRAMACION* — Horarios automáticos por red\n"
                    "• *ESTADO* — Diagnóstico en tiempo real (cola, CPU, RAM, último publicado)\n"
                    "• *MANTENIMIENTO* — Logs, web y reinicio del bot"
                ),
                (
                    "*─── PUBLICACION ───*\n\n"
                    "• *PUBLICAR SIG (Global)* — Publica el siguiente producto de la cola en todas las redes activas\n"
                    "• *PUB SIG (SOLO TG)* — Publica el siguiente solo en el canal de Telegram\n"
                    "• *PUB SIG (SOLO FB)* — Publica el siguiente solo en grupos de Facebook (respeta el nicho: bebés → grupos bebés)\n"
                    "• *PUB SIG (SOLO PINT)* — Publica el siguiente solo en Pinterest\n"
                    "• *VIDEO PREMIUM* — Flujo de 3 pasos: guión (6 líneas o `OK` para que Gemini lo genere) → fotos → video renderizado con voz\n"
                    "• *VER ÚLTIMO PUBLICADO* — Abre la ficha del último producto con opciones de republicar, crear video y ver links\n"
                    "• *🗑️ DESCARTAR FALLIDOS (N)* — Aparece solo cuando hay grupos de FB donde falló la publicación. Los descarta sin reintentar"
                ),
                (
                    "*─── CONTENIDO › VER COLA ───*\n\n"
                    "Muestra colas por nicho (General / Bebés / Mascotas). Al abrir un producto puedes:\n\n"
                    "• Editar título, precios, descuento, link\n"
                    "• Enviar una foto para reemplazar la imagen\n"
                    "• Cambiar el nicho (mueve el producto entre colas)\n"
                    "• Regenerar o editar el guión de video con IA\n"
                    "• Sincronizar precios en vivo desde ML\n"
                    "• Publicar ese producto ahora mismo\n"
                    "• Mover su posición en la cola (escribes un número)\n"
                    "• Eliminarlo (queda marcado como publicado)"
                ),
                (
                    "*─── CONTENIDO › VER HISTORIAL ───*\n\n"
                    "Lista todos los publicados. Los de bebés llevan `[BB]` y mascotas `[PETS]`. Al seleccionar uno:\n\n"
                    "• *🔗 Abrir Afiliado* — Abre el link meli.la\n"
                    "• *🛍️ Abrir Original* — Abre el link de ML\n"
                    "• *🔄 Volver a Publicar (Todo)* — Republica en todas las redes activas\n"
                    "• *🎬 CREAR VIDEO* — Genera video personalizado\n"
                    "• *📘 Repub. FB Grupos* — Solo grupos de Facebook (usa los grupos del nicho del producto)\n"
                    "• *✈️ Repub. Telegram* — Solo canal de Telegram\n"
                    "• *📌 Repub. Pinterest* — Solo Pinterest\n"
                    "• *🌐 Repub. Web* — Solo actualiza la landing page\n"
                    "• *🗑️ Quitar de Historial* — Elimina el marcador de duplicado para poder encolarlo de nuevo\n\n"
                    "*MODO COLA ON/OFF* — Activo: los links van a la cola. Desactivado: los links publican de inmediato"
                ),
                (
                    "*─── REDES ───*\n\n"
                    "• *[ON/OFF] FB GRUPOS GEN* — Toggle para grupos de Facebook generales\n"
                    "• *[ON/OFF] FB GRUPOS BEBES* — Toggle para grupos de Facebook de bebés\n"
                    "• *[ON/OFF] FB PAGE* — Toggle para la página oficial de Facebook\n"
                    "• *[ON/OFF] TELEGRAM* — Toggle para el canal de Telegram\n"
                    "• *[ON/OFF] PINTEREST* — Toggle para Pinterest\n"
                    "• *[ON/OFF] TIKTOK* — Toggle para TikTok\n"
                    "• *[ON/OFF] YOUTUBE* — Toggle para YouTube\n\n"
                    "• *BLOQUES FB GENERAL / BEBES* — Divide los grupos en bloques rotativos (1→2→3→1). Con 2 bloques publica en la mitad en un slot y la otra mitad en el siguiente. Reduce riesgo de ban.\n\n"
                    "• *AÑADIR GRUPO FB* — Pide URL → asigna nicho (General/Bebés/Mascotas) → guarda en .env sin reiniciar\n"
                    "• *🗑️ BORRAR GRUPO FB* — Navega entre grupos configurados y elimina los que ya no quieres"
                ),
                (
                    "*─── PROGRAMACION ───*\n\n"
                    "• *Horario General* — Cuadrícula de 8:00 a 22:00. Las horas [ON] son los slots donde el scheduler publica. Aplica a todas las redes sin horario propio.\n"
                    "• *Horario TikTok / YouTube* — Horario exclusivo para esas plataformas. Al activar el horario personalizado, publican en horas distintas al resto.\n\n"
                    "*─── MANTENIMIENTO ───*\n\n"
                    "• *ADMINISTRAR WEB* — Edita título, precio, descuento, categoría e imagen de productos en la landing page. Los cambios hacen rebuild y push a GitHub automáticamente.\n"
                    "• *REVISAR LOGS* — Muestra capturas de evidencia de publicaciones FB y capturas de errores\n"
                    "• *LIMPIAR LOGS* — Borra archivos de log acumulados\n"
                    "• *REINICIAR BOT* — Mata el proceso; systemd lo reinicia en segundos\n"
                    "• *📖 GUÍA DE USUARIO* — Esta guía"
                ),
                (
                    "*─── MENSAJES DIRECTOS ───*\n\n"
                    "*Envías un link de ML o Amazon:*\n"
                    "• Modo Cola ON → scrapea y encola (te pregunta nicho)\n"
                    "• Modo Cola OFF → publica inmediatamente en redes activas\n"
                    "• Múltiples links → siempre van a cola\n\n"
                    "*Prefijos para forzar red (antes del link):*\n"
                    "`tg https://...` → solo Telegram\n"
                    "`fb https://...` → solo FB grupos\n"
                    "`pin https://...` → solo Pinterest\n"
                    "`page https://...` → solo FB Page\n\n"
                    "*Envías foto + link en el caption:*\n"
                    "1. Gemini Vision hace OCR de precios e imagen\n"
                    "2. Si falla OCR → scrape del link como respaldo\n"
                    "3. Categoriza el producto\n"
                    "4. Encola o publica según el modo activo\n"
                    "El prefijo de red en el caption también funciona"
                ),
                (
                    "*─── MENSAJES DIRECTOS (continuación) ───*\n\n"
                    "*Envías una foto SIN link:*\n"
                    "• Si espera foto de edición de cola → reemplaza la imagen del producto\n"
                    "• Si estás en Video Premium → añade a la colección de escenas\n"
                    "• Sin contexto → se ignora\n\n"
                    "*Envías texto libre:*\n"
                    "• `/buscar laptops` → busca en ML/Amazon\n"
                    "• `/admin` → panel de administración web\n"
                    "• `/revisar` → curación de borradores\n"
                    "• `/test https://...` → captura de prueba sin publicar\n"
                    "• `/test_fb` → prueba si FB está bloqueando\n"
                    "• En modo edición → se toma como nuevo valor del campo\n"
                    "• En modo búsqueda → filtra la lista activa\n"
                    "• Cualquier otra cosa → Gemini responde como asistente con contexto del bot"
                ),
                (
                    "*─── FLUJOS ESPECIALES ───*\n\n"
                    "*Duplicado detectado:*\n"
                    "Si mandas un link ya publicado, el bot pregunta:\n"
                    "• Sí, forzar → lo encola con bandera de forzado\n"
                    "• No, descartar → lo ignora\n\n"
                    "*Borradores (/revisar):*\n"
                    "El scraper de Windows llena una lista de candidatos. Con /revisar los ves uno a uno:\n"
                    "• Sin link meli.la → se descartan automáticamente\n"
                    "• ✅ Aprobar → va a la cola\n"
                    "• ❌ Descartar → se elimina\n\n"
                    "*Video personalizado (desde cola o historial):*\n"
                    "1. Presionas Crear Video en cualquier producto\n"
                    "2. Escribes el guión (máximo 6 líneas, una por escena)\n"
                    "3. El bot genera audio con ElevenLabs y renderiza el video\n"
                    "4. Te lo manda por Telegram\n\n"
                    "*─── FUNCIONAMIENTO AUTOMÁTICO ───*\n\n"
                    "El scheduler corre 24/7 en el servidor:\n"
                    "• *7:50 AM* → diagnóstico matutino (colas, sesión FB, slots del día)\n"
                    "• *Cada hora programada (8-22)* → publica el siguiente producto de cada nicho\n"
                    "• *3:00 AM* → limpieza de archivos con más de 7 días\n"
                    "Si no hay productos válidos en un slot → notifica '🍽️ Colas vacías o con fallos'"
                ),
            ]
            # Guardar las secciones en estado y mostrar página 0
            self.user_state["guide_sections"] = sections
            await self._show_guide_page(0, msg_id=_cb_msg_id)
            return

        if lower_text.startswith("guide_page_"):
            page = int(lower_text.replace("guide_page_", ""))
            await self._show_guide_page(page, msg_id=_cb_msg_id)
            return

        if lower_text == "view_logs":
            await self.send_notification("⏳ **Extrayendo últimos registros de error...**")
            try:
                proc = await asyncio.create_subprocess_shell(
                    "journalctl -u amazon_bot.service -n 150 --no-pager",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                log_text = stdout.decode('utf-8', errors='replace').strip()
                err_text = stderr.decode('utf-8', errors='replace').strip()
                
                if not log_text and err_text:
                    log_text = f"[STDERR]\n{err_text}"
                elif not log_text:
                    log_text = "No se encontraron logs o el comando falló."
                
                # Prevenir que triple-backticks rompan el markdown
                log_text = log_text.replace("```", "'''")
                
                if len(log_text) > 3800:
                    log_text = "..." + log_text[-3800:]
                    
                await self.send_notification(f"📄 **Últimos Logs:**\n```text\n{log_text}\n```", reply_markup=self.get_master_keyboard())
            except Exception as e:
                await self.send_notification(f"❌ Error al ejecutar lectura de logs: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text == "toggle_fb_pause":
            is_paused = self.user_state.get("fb_paused", False)
            self.user_state["fb_paused"] = not is_paused
            
            if self.user_state["fb_paused"]:
                msg = "⏸️ **Publicación en Facebook PAUSADA.**\nEl bot seguirá guardando en la base de datos y/o web, pero no publicará nada en Facebook."
            else:
                msg = "▶️ **Publicación en Facebook ACTIVADA.**\nEl bot volverá a intentar publicar ofertas en los grupos de Facebook asignados."
                
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=_cb_msg_id)
            return

        if lower_text == "trigger_scrape":
            # El scraper masivo requiere sesión activa de ML y corre en Windows.
            # Creamos un archivo de señal que OneDrive sincroniza a Windows,
            # donde run_scraper_windows.py lo detecta y lanza ml_offers_scraper.py.
            flag_path = os.path.join(Config.BASE_DIR, "scrape_trigger.flag")
            try:
                import time
                with open(flag_path, "w", encoding="utf-8") as f:
                    f.write(str(time.time()))
                await self.send_notification(
                    "🔍 *Solicitud de recolección enviada a Windows*\n\n"
                    "OneDrive sincronizará la señal en segundos.\n"
                    "El scraper arrancará automáticamente en tu PC y llenará la cola.\n\n"
                    "⏳ Revisa la cola en unos minutos con el botón *Ver Cola*.",
                    reply_markup=self.get_master_keyboard()
                )
            except Exception as e:
                await self.send_notification(
                    f"❌ Error creando señal de scraping: {e}",
                    reply_markup=self.get_master_keyboard()
                )
            return

        if lower_text == "clear_logs":
            await self.send_notification("🧹 **Iniciando limpieza inteligente...**")
            try:
                history = set(self._load_history())
                deleted_count = 0
                if os.path.exists(Config.CAPTURES_DIR):
                    for filename in os.listdir(Config.CAPTURES_DIR):
                        prod_id = filename.split('.')[0]
                        if prod_id in history:
                            file_path = os.path.join(Config.CAPTURES_DIR, filename)
                            os.remove(file_path)
                            deleted_count += 1
                await self.send_notification(
                    f"✅ Limpieza completada. `{deleted_count}` archivos borrados.",
                    reply_markup=self.get_master_keyboard()
                )
            except Exception as e:
                await self.send_notification(f"❌ Error: {e}", reply_markup=self.get_master_keyboard())
            return

        if lower_text == "reboot_bot":
            await self.send_notification("REINICIANDO... Estare activo en unos segundos.")
            await asyncio.sleep(1)
            os._exit(0)

        if lower_text == "reboot_system":
            await self._execute_reboot_system()
            return

        if lower_text == "start_review" or lower_text == "/revisar":
            await self.show_next_draft()
            return

        if lower_text.startswith("approve_draft_"):
            p_id = text.split("approve_draft_")[1]
            await self.process_draft_action(p_id, approve=True, callback_query=callback_query)
            return

        if lower_text.startswith("discard_draft_"):
            p_id = text.split("discard_draft_")[1]
            await self.process_draft_action(p_id, approve=False, callback_query=callback_query)
            return

        if lower_text.startswith("draft_video_"):
            p_id = text.split("draft_video_")[1]
            _cb_msg_id = callback_query.get("message", {}).get("message_id")
            await self._start_custom_script_flow(p_id, msg_id=_cb_msg_id)
            return

        if lower_text == "cancel_custom_script":
            self.user_state.pop("awaiting_custom_script", None)
            self.user_state.pop("awaiting_custom_script_product_id", None)
            _cb_msg_id = callback_query.get("message", {}).get("message_id")
            await self.send_notification("❌ Creación de video cancelada.", msg_id=_cb_msg_id)
            return

        # ==========================================
        # 🧠 FALLBACK: INTEGRACIÓN CON GEMINI IA
        # ==========================================
        try:
            gemini_keys = Config.get_gemini_keys()
            if gemini_keys:
                await self.send_notification("🧠 *Pensando...*")

                # 1. Obtener contexto en tiempo real
                now_str = datetime.now().strftime("%I:%M %p")
                bot_status = "PAUSADO" if self.user_state.get("paused") else "ACTIVO (Operando normalmente)"
                interval_mins = Config.QUEUE_INTERVAL_MINS
                
                # Leer última publicación desde last_published.json
                last_pub_str = "No hay registro de publicaciones todavía en esta sesión."
                lp_data = self._load_last_published()
                if lp_data:
                    try:
                        last_pub_str = f"'{lp_data.get('title')}' publicado a las {lp_data.get('published_at')}"
                    except Exception as lp_err:
                        print(f"Error leyendo last_published.json: {lp_err}")
                
                # Leer total en cola de espera
                queue_count = len(self._load_queue())
                
                # 2. Diseñar la instrucción de sistema con contexto vivo
                system_instruction = (
                    "Eres Antigravity, el asistente de inteligencia artificial y programador de Eduardo. "
                    "Habla con él de forma muy atenta, profesional, simpática y en español de México (chido, mi buen, caray, etc. de forma discreta).\n\n"
                    "INFORMACIÓN DEL SISTEMA EN TIEMPO REAL:\n"
                    f"- Hora actual del servidor: {now_str}\n"
                    f"- Estado actual del bot: {bot_status}\n"
                    f"- Intervalo de publicación automática: cada {interval_mins} minutos\n"
                    f"- Último producto publicado con éxito: {last_pub_str}\n"
                    f"- Total de productos en la cola de espera (products_list.json): {queue_count} productos\n\n"
                    "INSTRUCCIONES DE RESPUESTA:\n"
                    "1. Responde de forma muy concisa, útil y súper servicial.\n"
                    "2. Si Eduardo te pregunta a qué hora es la siguiente publicación o sobre el estado, usa los datos del sistema anteriores para hacer un cálculo aproximado.\n"
                    "3. Si te pide realizar una acción técnica, recuérdale amablemente que puede usar los botones del teclado máster de control para ejecutar la acción de forma directa."
                )
                
                # 3. Mantener memoria de conversación
                self.chat_history.append({"role": "user", "parts": [{"text": text}]})
                self.chat_history = self.chat_history[-10:]
                
                payload = {
                    "contents": self.chat_history,
                    "systemInstruction": {
                        "parts": [
                            {"text": system_instruction}
                        ]
                    }
                }

                session = await self._get_send_session()
                reply_text = None
                last_status, last_err = None, None
                for gemini_key in gemini_keys:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={gemini_key}"
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            reply_text = data['candidates'][0]['content']['parts'][0]['text']
                            break
                        elif resp.status == 429:
                            print(f"[GEMINI ROTATION] Clave agotada/limitada, probando siguiente...")
                            last_status = resp.status
                            continue
                        else:
                            last_status = resp.status
                            last_err = await resp.text()
                            break

                if reply_text:
                    # Registrar respuesta en el historial de memoria
                    self.chat_history.append({"role": "model", "parts": [{"text": reply_text}]})
                    self.chat_history = self.chat_history[-10:]

                    await self.send_notification(reply_text, reply_markup=self.get_master_keyboard())
                else:
                    print(f"Error API Gemini REST: {last_status} - {last_err}")
                    await self.send_notification("⚠️ Lo siento, mi cerebro de IA devolvió un error de conexión.", reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification("⚠️ No se ha configurado una `GEMINI_API_KEY` válida en el archivo `.env`.", reply_markup=self.get_master_keyboard())
        except Exception as gemini_err:
            print(f"Error en Gemini Fallback REST: {gemini_err}")
            await self.send_notification("⚠️ Ocurrió un inconveniente al consultar mi cerebro de Inteligencia Artificial.", reply_markup=self.get_master_keyboard())

    async def handle_photo(self, photo_list, caption=""):
        """Maneja una foto enviada por Telegram con un link en el caption"""
        # Recopilacion de fotos para video premium
        if self.user_state.get("awaiting_premium_images"):
            try:
                file_id = photo_list[-1]["file_id"]
                get_file_url = f"https://api.telegram.org/bot{self.token}/getFile?file_id={file_id}"
                work_dir = os.path.join(Config.BASE_DIR, "captures", "premium_temp")
                self.safe_makedirs(work_dir)
                async with aiohttp.ClientSession() as _sess:
                    async with _sess.get(get_file_url) as _r:
                        _fd = await _r.json()
                        _fp = _fd["result"]["file_path"]
                    ext = os.path.splitext(_fp)[1] or ".jpg"
                    collected = self.user_state.get("premium_images_collected", [])
                    n = len(collected) + 1
                    dest = os.path.join(work_dir, f"scene_{n}{ext}")
                    dl_url = f"https://api.telegram.org/file/bot{self.token}/{_fp}"
                    async with _sess.get(dl_url) as _r:
                        with open(dest, "wb") as _f:
                            _f.write(await _r.read())
                collected.append(dest)
                self.user_state["premium_images_collected"] = collected
                msg = f"FOTO {n} RECIBIDA."
                if n < 3:
                    msg += f" Manda {3 - n} mas o escribe LISTO si ya tienes suficientes."
                else:
                    msg += " Puedes mandar mas o escribe LISTO para continuar."
                await self.send_notification(msg)
            except Exception as e:
                await self.send_notification(f"ERROR guardando foto: {e}")
            return

        if self.user_state.get("queue_editing_product_id") and self.user_state.get("queue_editing_field") == "img":
            product_id = self.user_state.get("queue_editing_product_id")
            await self.send_notification("Descargando nueva imagen para la cola...")
            try:
                file_id = photo_list[-1]["file_id"]
                get_file_url = f"https://api.telegram.org/bot{self.token}/getFile?file_id={file_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(get_file_url) as response:
                        file_data = await response.json()
                        file_path = file_data["result"]["file_path"]
                    extension = os.path.splitext(file_path)[1] or ".jpg"
                    local_path = os.path.join(Config.CAPTURES_DIR, f"{product_id}{extension}")
                    os.makedirs(Config.CAPTURES_DIR, exist_ok=True)
                    download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                    async with session.get(download_url) as response:
                        with open(local_path, "wb") as file:
                            file.write(await response.read())

                relative_path = f"captures/{product_id}{extension}"
                niche = self.user_state.get("queue_niche", "general")
                if not self._update_queue_product(product_id, "img", relative_path, niche=niche):
                    raise ValueError("producto no encontrado en la cola")
                self.user_state.pop("queue_editing_product_id", None)
                self.user_state.pop("queue_editing_field", None)
                await self.send_notification(f"Imagen actualizada para `{product_id}`.")
                product = next((item for item in self._load_queue_data(niche=niche) if item.get("id") == product_id), None)
                if product:
                    await self._send_queue_product_actions(product)
            except Exception as exc:
                await self.send_notification(f"Error actualizando imagen de cola: {exc}")
            return
        # --- MODO EDICIÓN DE IMAGEN ---
        if self.user_state.get("editing_product_id") and self.user_state.get("editing_field") == "img":
            p_id = self.user_state.get("editing_product_id")
            await self.send_notification("⏳ Descargando nueva imagen para la web...")
            try:
                file_id = photo_list[-1]['file_id']
                get_file_url = f"https://api.telegram.org/bot{self.token}/getFile?file_id={file_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(get_file_url) as resp:
                        file_data = await resp.json()
                        file_path = file_data['result']['file_path']
                        
                    download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                    ext = os.path.splitext(file_path)[1] or ".jpg"
                    local_path = os.path.join(Config.CAPTURES_DIR, f"{p_id}{ext}")
                    os.makedirs(Config.CAPTURES_DIR, exist_ok=True)
                    async with session.get(download_url) as resp:
                        with open(local_path, 'wb') as f:
                            f.write(await resp.read())
                
                self.user_state.pop("editing_product_id", None)
                self.user_state.pop("editing_field", None)
                await self._update_web_db(p_id, "img", f"captures/{p_id}{ext}")
                await self.send_notification("✅ ¡Imagen guardada! Actualizando web en segundo plano...", reply_markup=self.get_master_keyboard())
            except Exception as e:
                await self.send_notification(f"❌ Error actualizando imagen: {e}", reply_markup=self.get_master_keyboard())
            return

        if not caption: return
        
        # Extraer URL del caption
        url_match = re.search(r'https?://[^\s]+', caption)
        if not url_match:
            await self.send_notification("⚠️ No encontré un link válido en el comentario de la foto.")
            return
        
        url = url_match.group(0)
        status_msg_id = None
        status_resp = await self.send_notification(f"📸 **Foto recibida.** Analizando imagen con IA (Gemini Vision) para: {url}")
        if status_resp and status_resp.get("ok"):
            status_msg_id = status_resp["result"]["message_id"]
        
        # 1. Descargar la foto
        try:
            file_id = photo_list[-1]['file_id']
            get_file_url = f"https://api.telegram.org/bot{self.token}/getFile?file_id={file_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(get_file_url) as resp:
                    file_data = await resp.json()
                    file_path = file_data['result']['file_path']
                    
                download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                ext = os.path.splitext(file_path)[1] or ".jpg"
                local_path = os.path.join(Config.CAPTURES_DIR, f"manual_{random.randint(100,999)}{ext}")
                async with session.get(download_url) as resp:
                    with open(local_path, 'wb') as f:
                        f.write(await resp.read())
            
            # 2. Análisis con Gemini Vision si es Mercado Libre o Amazon
            pre_scraped = None
            try:
                import PIL.Image
                from core.ai_service import generate_with_gemini_rotation

                if Config.get_gemini_keys():
                    img = PIL.Image.open(local_path)
                    
                    prompt = """
                    Analiza esta captura de pantalla de un producto.
                    Extrae exactamente la siguiente información y devuélvela ÚNICAMENTE como un JSON válido sin Markdown.
                    {
                      "title": "Nombre central y limpio del producto (muy corto, ej. 'Tenis Adidas', 'Cargador Rápido', 'Monitor Gamer'). NO uses descripciones, letras raras, ni modelos largos.",
                      "list_price": "El precio tachado original (con el signo $, o string vacío si no hay)",
                      "offer_price": "El precio final de oferta (con el signo $)",
                      "discount": "El porcentaje de descuento (con el signo %, o string vacío si no hay)"
                    }
                    No incluyas texto adicional fuera del JSON.
                    """
                    response = generate_with_gemini_rotation([prompt, img])

                    # Limpiar markdown si Gemini lo devuelve
                    raw_json = response.text.replace('```json', '').replace('```', '').strip()
                    extracted = json.loads(raw_json)
                    
                    # Agregar id y skip flag
                    import time as _time
                    p_id = ""
                    ml_match = re.search(r'MLM-?(\d+)', url)
                    if ml_match: p_id = f"MLM{ml_match.group(1)}"
                    else: p_id = f"MANUAL_{int(_time.time())}"
                    
                    # Renombrar archivo a su ID final usando sufijo _manual para evitar sobreescritura del scraper
                    final_path = os.path.join(Config.CAPTURES_DIR, f"{p_id}_manual.png")
                    if os.path.exists(final_path): os.remove(final_path)
                    os.rename(local_path, final_path)
                    local_path = final_path
                    
                    pre_scraped = {
                        "title": extracted.get("title", "Oferta Especial"),
                        "list_price": extracted.get("list_price", ""),
                        "offer_price": extracted.get("offer_price", ""),
                        "discount": extracted.get("discount", ""),
                        "id": p_id,
                        "affiliate_url": url,
                        "screenshot": f"captures/{p_id}_manual.png",
                        "visual_capture": f"captures/{p_id}_manual.png",
                        "skip_scrape": True
                    }
                    
                    # Si Gemini no obtuvo precio, scrapeamos el URL para completar
                    if not pre_scraped.get("offer_price"):
                        await self.send_notification("⚠️ IA incompleta. Scrapeando el enlace en modo incógnito...", msg_id=status_msg_id)
                        try:
                            scraped = await self.orchestrator.scrape_product_details(url)
                            if scraped:
                                pre_scraped["offer_price"] = scraped.get("offer_price", "")
                                pre_scraped["list_price"]  = scraped.get("list_price", pre_scraped["list_price"])
                                pre_scraped["discount"]    = scraped.get("discount", pre_scraped["discount"])
                                if not pre_scraped["title"] or pre_scraped["title"] == "Oferta Especial":
                                    pre_scraped["title"]   = scraped.get("title", pre_scraped["title"])
                        except Exception as scrape_e:
                            print(f"Fallback scrape failed: {scrape_e}")

                    list_msg = f"{''.join(c + '\u0336' for c in str(pre_scraped['list_price']))} ➡️ " if pre_scraped['list_price'] else ""
                    # Omitimos el "Análisis completado" para no spam y saltamos directo a Encolado abajo, 
                    # o lo dejamos si es necesario, pero como "Encolado" sobreescribe, no lo verá mucho.
                else:
                    await self.send_notification("⚠️ No se encontró GEMINI_API_KEY en el entorno, procesando sin OCR.")
            except Exception as gemini_e:
                print(f"Error en Gemini Vision: {gemini_e}")
                import traceback
                error_trace = traceback.format_exc()
                print(error_trace)
                await self.send_notification(f"⚠️ Error leyendo la imagen con IA: {str(gemini_e)}. Se procesará normalmente.", msg_id=status_msg_id)
            
            # Categorización de Nichos
            try:
                # Productos manuales SIEMPRE van a GENERAL, sin categorización automática
                if pre_scraped:
                    pre_scraped["niche"] = "[CAT:GENERAL]"
            except Exception:
                if pre_scraped: pre_scraped["niche"] = "[CAT:GENERAL]"

            # 3. Mandar al Orchestrator o a la Cola
            if self.user_state.get("queue_mode"):
                if not pre_scraped:
                    import time as _time
                    p_id = f"MANUAL_{int(_time.time())}"
                    await self.send_notification("⚠️ IA de visión falló. Scrapeando el enlace en modo incógnito...", msg_id=status_msg_id)
                    try:
                        scraped = await self.orchestrator.scrape_product_details(url)
                    except:
                        scraped = None
                        
                    if scraped and scraped.get("title") and scraped.get("title") != "Oferta Especial en Mercado Libre":
                        pre_scraped = {
                            "title": scraped.get("title"),
                            "list_price": scraped.get("list_price", ""),
                            "offer_price": scraped.get("offer_price", "Revisar"),
                            "discount": scraped.get("discount", ""),
                            "id": p_id,
                            "affiliate_url": url,
                            "screenshot": f"captures/{p_id}_manual.png",
                            "visual_capture": f"captures/{p_id}_manual.png",
                            "skip_scrape": False
                        }
                    else:
                        pre_scraped = {
                            "title": "Producto Manual (IA Falló)",
                            "list_price": "",
                            "offer_price": "Revisar",
                            "discount": "",
                            "id": p_id,
                            "affiliate_url": url,
                            "screenshot": f"captures/{p_id}_manual.png",
                            "visual_capture": f"captures/{p_id}_manual.png",
                            "skip_scrape": False
                        }
                p_id = pre_scraped.get("id")
                affiliate_url = pre_scraped.get("affiliate_url")
                if self._is_in_history(p_id, affiliate_url):
                    import time
                    temp_id = f"temp_{int(time.time())}"
                    self._save_temp_queue_request(temp_id, pre_scraped)
                    
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "Sí, forzar publicación", "callback_data": f"force_dup_{temp_id}"},
                                {"text": "No, descartar", "callback_data": f"discard_dup_{temp_id}"}
                            ]
                        ]
                    }
                    await self.send_notification(
                        f"⚠️ **Este producto ya fue publicado anteriormente (detectado en historial):**\n"
                        f"`{pre_scraped.get('title', 'Sin título')}`\n\n"
                        f"¿Deseas volver a agregarlo a la cola y forzar su publicación?",
                        reply_markup=keyboard
                    )
                else:
                    cat_val = pre_scraped.get("niche", "[CAT:GENERAL]")
                    if "BEBES" in cat_val:
                        niche_key = "baby"
                    elif "MASCOTAS" in cat_val:
                        niche_key = "pets"
                    else:
                        niche_key = "general"

                    # Forzar publicación para encolamientos manuales con foto (bypasea filtro de duplicados visual)
                    pre_scraped["force_publish"] = True

                    active_queue = self._load_queue_data(niche=niche_key)
                    if not any(item.get("id") == pre_scraped["id"] for item in active_queue):
                        active_queue.insert(0, pre_scraped)
                        self._save_queue_data(active_queue, niche=niche_key)
                        self._reset_cursors_for_new_items()
                    
                    await self.send_notification(
                        f"✅ **Encolado (Foto Manual):**\n`{pre_scraped['title']}`\n💰 {pre_scraped.get('offer_price', '')}\n🎯 Nicho: `{pre_scraped.get('niche', '[CAT:GENERAL]')}`",
                        reply_markup=self.get_master_keyboard(),
                        msg_id=status_msg_id
                    )
            else:
                lower_cap = caption.lower().strip()
                override_plat = None
                if lower_cap.startswith("tg "): override_plat = "telegram"
                elif lower_cap.startswith("fb "): override_plat = "facebook"
                elif lower_cap.startswith("pin "): override_plat = "pinterest"
                elif lower_cap.startswith("page "): override_plat = "fb_page"
                
                if override_plat:
                    target_platform = override_plat
                    await self.send_notification(f"🎯 Forzando publicación manual solo en: **{override_plat.capitalize()}**", msg_id=status_msg_id)
                else:
                    active = self.user_state.get("active_networks", {})
                    target_platform = [k for k, v in active.items() if v] if active else "both"
                    
                asyncio.create_task(self.orchestrator.run_publication(url, target_platform=target_platform, manual_image=local_path, pre_scraped_details=pre_scraped))

        except Exception as e:
            await self.send_notification(f"❌ Error procesando foto: {e}", reply_markup=self.get_master_keyboard(), msg_id=status_msg_id if 'status_msg_id' in locals() else None)

    async def listener(self):
        """Radar de Telegram unificado y protegido contra bucles"""
        print("📡 Radar de Telegram iniciado...")
        
        # 1. Ignorar pasado al arrancar
        updates = await self._get_updates(timeout=1)
        if updates:
            self.offset = updates[-1]["update_id"] + 1
            print(f"🧹 Mensajes antiguos ignorados. Nuevo offset: {self.offset}")
            
        # Enviar mensaje de bienvenida / reactivación con los botones
        await self.send_notification(
            "✅ **Sistemas Reactivados**\nEl bot está en línea y listo para recibir comandos.",
            reply_markup=self.get_master_keyboard()
        )

        # Iniciar generación de assets en segundo plano para el top 10 al arrancar
        asyncio.create_task(self._ensure_top_10_queue_assets())

            
        while True:
            try:
                updates = await self._get_updates(offset=self.offset)
                for result in updates:
                    self.offset = result["update_id"] + 1
                    
                    # Mensajes de texto y FOTOS
                    msg = result.get("message", {})
                    if str(msg.get("chat", {}).get("id", "")) == str(self.chat_id):
                        text = msg.get("text", "").strip()
                        caption = msg.get("caption", "").strip()
                        photo = msg.get("photo")
                        
                        if text:
                            await self.handle_command(text)
                        elif photo:
                            await self.handle_photo(photo, caption)
                    
                    # Botones (Callback Query)
                    cb = result.get("callback_query", {})
                    if cb:
                        await self.handle_command(cb.get("data"), callback_query=cb)
                        # Confirmar click
                        ans_url = f"https://api.telegram.org/bot{self.token}/answerCallbackQuery"
                        session = await self._get_send_session()
                        await session.post(ans_url, json={"callback_query_id": cb.get("id")})
                        
            except Exception as e:
                print(f"Error radar: {e}")
                await asyncio.sleep(5)
            await asyncio.sleep(1)


    async def _show_user_guide(self, msg_id=None):
        """Muestra la primera página de la guía de usuario."""
        await self._show_guide_page(1, msg_id=msg_id)

    async def _send_logs(self, msg_id=None):
        """Envía las últimas líneas de bot.log."""
        try:
            log_file = os.path.join(Config.BASE_DIR, "bot.log")
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-25:]
                log_text = "".join(lines)[-3500:]
                msg = f"📄 **Últimos logs del bot:**\n```\n{log_text}\n```"
            else:
                msg = "⚠️ No se encontró el archivo `bot.log`."
            await self.send_notification(msg, reply_markup=self.get_master_keyboard(), msg_id=msg_id)
        except Exception as e:
            await self.send_notification(f"❌ Error leyendo logs: {e}", reply_markup=self.get_master_keyboard(), msg_id=msg_id)

    async def _show_all_fb_groups(self, msg_id=None):
        """Muestra la lista completa de grupos de Facebook configurados."""
        try:
            def format_links(title, links):
                if not links: return f"**{title}**: Ninguno\n"
                formatted = "\n".join([f"• [{link.split('/groups/')[-1].strip('/')}]({link})" for link in links])
                return f"**{title}** ({len(links)}):\n{formatted}\n\n"

            msg = "📊 **TUS GRUPOS DE FACEBOOK**\n\n"
            msg += format_links("📱 General", Config.FB_GROUPS)
            msg += format_links("🧸 Bebés", getattr(Config, 'FB_GROUPS_BABY', []))
            msg += format_links("🐶 Mascotas", getattr(Config, 'FB_GROUPS_PETS', []))
            msg += format_links("👟 Tenis", getattr(Config, 'FB_GROUPS_TENIS', []))
            msg += format_links("👗 Moda", getattr(Config, 'FB_GROUPS_MODA', []))
            msg += "_(Para agregar/quitar, usa los botones debajo)_"

            if len(msg) > 4000:
                msg = msg[:4000] + "\n\n... [Truncado]"

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🗑️ ELIMINAR UN GRUPO", "callback_data": "fb_group_browser"}],
                    [{"text": "AÑADIR GRUPO", "callback_data": "add_fb_group"}],
                    [{"text": "↩️ Volver a Redes", "callback_data": "nav_redes"}]
                ]
            }
            await self.send_notification(msg, reply_markup=keyboard, msg_id=msg_id)
        except Exception as e:
            await self.send_notification(f"❌ Error mostrando grupos FB: {e}", reply_markup=self.get_master_keyboard(), msg_id=msg_id)

    async def _force_video_generation(self):
        """Fuerza la generación de video para el último producto publicado."""
        try:
            details = self._load_last_published()
            if not details:
                await self.send_notification("⚠️ No hay producto publicado recientemente para generar video.", reply_markup=self.get_master_keyboard())
                return
            p_title = details.get('title', 'Producto')[:45]
            await self.send_notification(f"🎬 Generando video para: `{p_title}`...")
            from tiktok_generator import create_tiktok_video
            video_path = await asyncio.to_thread(create_tiktok_video, details)
            if video_path and os.path.exists(video_path):
                await self.send_notification(f"✅ Video generado exitosamente:\n`{video_path}`", reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification("❌ No se pudo generar el video.", reply_markup=self.get_master_keyboard())
        except Exception as e:
            await self.send_notification(f"❌ Error generando video: {e}", reply_markup=self.get_master_keyboard())

    async def _force_web_sync(self):
        """Fuerza la reconstrucción y sincronización con la web."""
        try:
            await self.send_notification("🌐 Reconstruyendo landing page y sincronizando con la web...")
            from publishers.web_publisher import WebPublisher
            web_pub = self.orchestrator.web_publisher or WebPublisher()
            success = await asyncio.to_thread(web_pub.build)
            if success:
                if getattr(Config, "GITHUB_TOKEN", None):
                    await asyncio.to_thread(web_pub.publish, {}, "")
                await self.send_notification("✅ Sincronización web completada exitosamente.", reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification("❌ Error al reconstruir la web.", reply_markup=self.get_master_keyboard())
        except Exception as e:
            await self.send_notification(f"❌ Error en sincronización web: {e}", reply_markup=self.get_master_keyboard())

    async def _process_publish_next_amazon(self):
        """Publica el siguiente producto de Amazon en la cola."""
        await self._process_publish_next_by_source("amazon")

    async def _process_publish_next_ml(self):
        """Publica el siguiente producto de Mercado Libre en la cola."""
        await self._process_publish_next_by_source("mercadolibre")

    async def _process_publish_next_by_source(self, source: str):
        """Helper para publicar el siguiente producto según su fuente (Amazon o ML)."""
        try:
            history = set(self._load_history())
            products = self._load_queue()
            target = None
            for p in products:
                p_id = p.get('id')
                p_url = p.get('affiliate_url', '')
                if not p_id:
                    continue
                if (p_id and p_id in history) or (p_url and p_url in history):
                    continue
                from core.discard_manager import is_already_discarded
                if is_already_discarded(p_id):
                    continue
                if source == "amazon" and (p.get("source") == "amazon" or "amazon.com" in p_url):
                    target = p
                    break
                elif source == "mercadolibre" and ("meli.la" in p_url or "mercadolibre" in p_url or p.get("source") == "ml"):
                    target = p
                    break

            if not target:
                await self.send_notification(f"⚠️ No hay productos listos de {source.upper()} en la cola.", reply_markup=self.get_master_keyboard())
                return

            target_platform = [k for k, v in self.user_state.get("active_networks", {}).items() if v] if self.user_state.get("active_networks", {}) else "both"
            p_title = target.get('title', target.get('id', 'Producto'))[:45]
            await self.send_notification(f"🚀 **Publicando siguiente {source.upper()}:** `{target.get('id')}`\n📦 {p_title}")
            img_path = target.get('visual_capture') or target.get('screenshot', '')
            if img_path and not os.path.exists(img_path):
                img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))

            success = await self.orchestrator.run_publication(
                target['affiliate_url'],
                target_platform=target_platform,
                manual_image=img_path,
                pre_scraped_details=target
            )
            if success:
                await self.send_notification(f"✅ ¡Publicación de {source.upper()} completada!\n📦 `{target.get('id')}`", reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification(f"⚠️ Publicación de {source.upper()} descartada o falló.", reply_markup=self.get_master_keyboard())
        except Exception as e:
            await self.send_notification(f"❌ Error publicando producto de {source}: {e}", reply_markup=self.get_master_keyboard())


    def _load_queue_data(self, niche="general"):
        data = json_load(self._get_queue_file(niche), default=[])
        return data if isinstance(data, list) else []

    def _save_queue_data(self, products, niche="general"):
        try:
            json_save_atomic(self._get_queue_file(niche), products, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando cola de productos {niche}: {e}")
            return

    def _reset_cursors_for_new_items(self):
        pass

    async def _ensure_top_10_queue_assets(self, force_product_id=None):
        """
        Asegura que los primeros 10 productos en cola (o uno forzado) tengan guion y galería.
        """
        try:
            # Evitar colisiones usando un flag de bloqueo
            if getattr(self, "_asset_generation_running", False) and not force_product_id:
                return
            self._asset_generation_running = True
            
            for current_niche in ["general", "baby", "pets", "tenis", "moda"]:
                pending = self._get_pending_queue(niche=current_niche)
                targets = []
                if force_product_id:
                    target = next((p for p in pending if p.get("id") == force_product_id), None)
                    if target:
                        targets = [target]
                else:
                    targets = pending[:10]

                updated_any = False
                for product in targets:
                    p_id = product.get("id")
                    has_images = bool(product.get("gallery_images"))
                    has_script = bool(product.get("script") and len(product.get("script")) == 6)
                    
                    if has_images and has_script and not force_product_id:
                        continue
                        
                    # Omitir generación de assets de video (galería y script) para nichos que no llevan video
                    cat = product.get("niche", "[CAT:GENERAL]")
                    if "[CAT:BEBES]" in cat or "[CAT:MASCOTAS]" in cat:
                        continue
                        
                    # Scrapear imagenes
                    if not has_images:
                        try:
                            from scrapers.ml_scraper import get_gallery_images_headless
                            url = product.get("affiliate_url") or product.get("real_url")
                            
                            from playwright.async_api import async_playwright
                            from core.session_manager import SessionManager
                            gallery = []
                            async with async_playwright() as p:
                                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
                                context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                                try:
                                    from playwright_stealth import stealth_async
                                    await stealth_async(context)
                                except: pass
                                page = await context.new_page()
                                gallery = await get_gallery_images_headless(page, url)
                                await browser.close()
                                
                            if gallery:
                                product["gallery_images"] = gallery
                                has_images = True
                        except Exception:
                            pass
                            
                    # Forzar regeneración de script si fue invocado por el botón manual
                    if force_product_id:
                        has_script = False
                            
                    # Generar Script
                    if not has_script:
                            try:
                                lines = await self.ai_service.generate_6_lines(product)
                                if not lines:
                                    # Fallback genérico sin tono de vendedor antiguo
                                    title_clean = product.get("title", "este increíble artículo").split("-")[0].strip()[:40]
                                    lines = [
                                        f"No dejes pasar la oportunidad de llevarte {title_clean}.",
                                        "Es el aliado perfecto para tu día a día gracias a su excelente calidad.",
                                        "Al estar diseñado con los mejores materiales, su rendimiento es súper confiable.",
                                        "Hoy está disponible a un costo increíblemente bajo que vale la pena aprovechar.",
                                        "Consigue el tuyo directamente en el enlace que te dejé abajo.",
                                        "¡Haz tu compra ahora y dale este refuerzo a tu vida!"
                                    ]
                                product["script"] = lines
                                has_script = True
                            except Exception:
                                pass
                        
                    # Actualizar base de datos
                    all_products = self._load_queue_data(niche=current_niche)
                    for p in all_products:
                        if p.get("id") == p_id:
                            p["gallery_images"] = product.get("gallery_images", [])
                            p["script"] = product.get("script", [])
                            break
                    self._save_queue_data(all_products, niche=current_niche)
                    updated_any = True

                if updated_any:
                    print(f"[ASSETS] Cola {current_niche} actualizada con nuevos assets de video.")
        except Exception as e:
            print(f"[ASSETS] Error en _ensure_top_10_queue_assets: {e}")
        finally:
            self._asset_generation_running = False


    def _get_pending_queue(self, niche="general"):
        products = self._load_queue_data(niche=niche)
        history = set(self._load_history())
        return [
            product for product in products
            if product.get("force_publish") or (product.get("id") not in history and product.get("affiliate_url") not in history)
        ]

    def _is_in_history(self, p_id, affiliate_url):
        history = set(self._load_history())
        return (p_id and p_id in history) or (affiliate_url and affiliate_url in history)

    def _save_temp_queue_request(self, temp_id, product_data):
        if not hasattr(self, 'temp_queue'):
            self.temp_queue = {}
        self.temp_queue[temp_id] = product_data

    def _pop_temp_queue_request(self, temp_id):
        if not hasattr(self, 'temp_queue'):
            return None
        return self.temp_queue.pop(temp_id, None)

    async def _handle_retry_affiliate(self, niche: str, product_id: str, callback_query):
        msg_id = callback_query.get("message", {}).get("message_id") if callback_query else None
        await self._answer_callback(callback_query, text="Generando link... espera unos 30s")
        if msg_id:
            await self.send_notification("🔄 *Iniciando generación de link afiliado...*", chat_id=Config.TELEGRAM_CHAT_ID)
            
        queue = self._load_queue_data(niche=niche)
        prod = next((p for p in queue if str(p.get("id")) == product_id), None)
        if not prod:
            await self.send_notification("❌ El producto ya no está en la cola.")
            return
            
        original_url = prod.get("original_url") or prod.get("affiliate_url") or prod.get("url")
        if not original_url:
            await self.send_notification("❌ El producto no tiene URL original.")
            return
            
        import asyncio
        import sys
        import os
        script_path = os.path.join(Config.BASE_DIR, "affiliate_linker.py")
        process = await asyncio.create_subprocess_exec(
            sys.executable, script_path, "--headless", original_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Config.BASE_DIR
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode('utf-8')
        
        meli_url = None
        for line in output.split('\n'):
            if line.strip().startswith("https://meli.la/"):
                meli_url = line.strip()
                break
                
        if meli_url:
            queue = self._load_queue_data(niche=niche)
            for q in queue:
                if str(q.get("id")) == product_id:
                    q["affiliate_url"] = meli_url
                    q["url"] = meli_url
                    q.pop("review_status", None)
                    q.pop("affiliate_alert_sent", None) # reset alert
                    break
            self._save_queue_data(queue, niche=niche)
            await self.send_notification(f"✅ ¡Link de afiliado generado con éxito!\nProducto: `{prod.get('title', '')[:50]}`\nLink: {meli_url}")
        else:
            await self.send_notification(f"❌ Falló la generación de link afiliado para `{prod.get('title', '')[:50]}`.")

    async def _handle_force_duplicate(self, temp_id, callback_query):
        product_data = self._pop_temp_queue_request(temp_id)
        if not product_data:
            await self.send_notification("⚠️ Esta solicitud temporal ya no existe o ya fue procesada.")
            return

        product_data["force_publish"] = True

        cat_val = product_data.get("niche", "[CAT:GENERAL]")
        if "BEBES" in cat_val:
            niche_key = "baby"
        elif "MASCOTAS" in cat_val:
            niche_key = "pets"
        elif "TENIS" in cat_val:
            niche_key = "tenis"
        elif "MODA" in cat_val:
            niche_key = "moda"
        else:
            niche_key = "general"

        active_queue = self._load_queue_data(niche=niche_key)

        # Remove it if it was buried deep in the queue, so we can push it to the top
        active_queue = [item for item in active_queue if item.get("id") != product_data.get("id")]
        
        active_queue.insert(0, product_data)
        self._save_queue_data(active_queue, niche=niche_key)
        self._reset_cursors_for_new_items()

        msg_id = callback_query.get("message", {}).get("message_id") if callback_query else None
        title = product_data.get("title", "Sin Título")
        notify_text = f"✅ *Producto agregado a la cola (forzado):*\n`{title}`"

        if msg_id:
            url = f"https://api.telegram.org/bot{self.token}/editMessageText"
            payload = {
                "chat_id": self.chat_id,
                "message_id": msg_id,
                "text": notify_text,
                "parse_mode": "Markdown"
            }
            try:
                session = await self._get_send_session()
                await session.post(url, json=payload)
            except Exception as e:
                print(f"Error editing message: {e}")
                await self.send_notification(notify_text)
        else:
            await self.send_notification(notify_text)

    async def _handle_discard_duplicate(self, temp_id, callback_query):
        from core.discard_manager import register_discard

        product_data = self._pop_temp_queue_request(temp_id)
        if product_data:
            screenshot = product_data.get("screenshot", "")
            if screenshot and os.path.exists(screenshot):
                try:
                    os.remove(screenshot)
                except:
                    pass

            # Registrar como descartado por duplicado
            product_id = product_data.get("id", "desconocido")
            register_discard(product_id, "duplicado_rechazado", product_data)

        msg_id = callback_query.get("message", {}).get("message_id") if callback_query else None
        title = product_data.get("title", "Producto") if product_data else "Producto"
        notify_text = f"❌ *Producto descartado (Duplicado):*\n`{title}`"

        if msg_id:
            url = f"https://api.telegram.org/bot{self.token}/editMessageText"
            payload = {
                "chat_id": self.chat_id,
                "message_id": msg_id,
                "text": notify_text,
                "parse_mode": "Markdown"
            }
            try:
                session = await self._get_send_session()
                await session.post(url, json=payload)
            except Exception as e:
                print(f"Error editing message: {e}")
                await self.send_notification(notify_text)
        else:
            await self.send_notification(notify_text)


    async def _show_queue_browser(self, page=0, msg_id=None):
        try:
            niche = self.user_state.get("queue_niche", "general")
            pending = self._get_pending_queue(niche=niche)
        except Exception as exc:
            await self.send_notification(f"Error leyendo cola: {exc}", reply_markup=self.get_master_keyboard())
            return

        if not pending:
            await self.send_notification("La cola esta vacia.", reply_markup=self.get_master_keyboard())
            return

        page_size = 12
        total_pages = max(1, (len(pending) + page_size - 1) // page_size)
        page = max(0, min(int(page), total_pages - 1))
        self.user_state["queue_page"] = page
        start = page * page_size
        rows = []
        for idx, product in enumerate(pending[start:start + page_size]):
            product_id = product.get("id", "")
            title = product.get("title", "Sin titulo")[:38]
            discount = product.get("discount", "")
            offer = product.get("offer_price", "")
            info_parts = []
            if discount:
                info_parts.append(discount)
            if offer:
                info_parts.append(str(offer))
            prefix = f"{discount} - " if discount else ""
            display_text = f"{start + idx + 1}. {prefix}{title}"
            rows.append([{"text": display_text, "callback_data": f"queue_show_{product_id}"}])

        navigation = []
        if page > 0:
            navigation.append({"text": "Anterior", "callback_data": f"queue_page_{page - 1}"})
        if page + 1 < total_pages:
            navigation.append({"text": "Siguiente", "callback_data": f"queue_page_{page + 1}"})
        if navigation:
            rows.append(navigation)
        rows.append([{"text": "Buscar", "callback_data": "queue_search_"}])
        rows.append([{"text": "Volver al menu", "callback_data": "queue_exit_"}])

        await self.send_notification(
            f"**Editor de cola ({niche.upper()})**\n{len(pending)} pendientes - pagina {page + 1}/{total_pages}\nSelecciona un producto:",
            reply_markup={"inline_keyboard": rows},
            msg_id=msg_id
        )

    async def _send_queue_product_actions(self, product, msg_id=None):
        product_id = product.get("id", "")
        title      = product.get("title", "Sin titulo")
        offer_price = product.get("offer_price", "")
        list_price  = product.get("list_price", "")
        discount    = product.get("discount", "")
        _aff_url = product.get("affiliate_url", "")
        if "meli.la" in _aff_url:
            affiliate_status = "meli.la listo"
        elif product.get("source") == "amazon" or any(domain in _aff_url for domain in ["amazon.com", "amzn.to", "a.co", "amazon.com.mx", "link.amazon"]):
            affiliate_status = "Amazon listo"
        else:
            affiliate_status = "link pendiente"
        img_path = product.get("visual_capture") or product.get("screenshot") or product.get("image_url") or ""
        import os
        from core.config import Config
        is_http = img_path.startswith("http")
        if img_path and not is_http and not os.path.exists(img_path):
            img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))
        if img_path and not is_http and not os.path.exists(img_path):
            img_path = ""

        # Calcular ahorro
        savings_line = ""
        try:
            o = float(str(offer_price).replace("$","").replace(",","").strip())
            l = float(str(list_price).replace("$","").replace(",","").strip())
            if l > o:
                savings_line = f"\n💰 Ahorro: `${l - o:,.2f}`"
        except Exception:
            pass

        affiliate_url = product.get("affiliate_url", "")
        real_url = product.get("real_url", "")
        links_line = ""
        if affiliate_url:
            links_line += f"🔗 [Link de Afiliado]({affiliate_url})"
        if real_url:
            if links_line:
                links_line += " | "
            links_line += f"🛍️ [Link Original]({real_url})"
        if links_line:
            links_line = f"\n\n{links_line}"

        niche = product.get("niche", "[CAT:GENERAL]")
        is_baby = niche == "[CAT:BEBES]"

        script_text = ""
        if not is_baby:
            script = product.get("script")
            if script and isinstance(script, list):
                script_text = "\n\n📝 **Guion del Video (6 escenas):**\n" + "\n".join(f"{i+1}. {line}" for i, line in enumerate(script))
            else:
                script_text = "\n\n📝 **Guion del Video:** No pre-generado. (Se usará fallback al publicar)"

        caption = (
            f"*{title}*\n"
            f"Oferta: `{offer_price}` | Anterior: `{list_price}` | Dcto: `{discount}`\n"
            f"🎯 Nicho: `{niche}`"
            f"{savings_line}\n"
            f"Estado: `{affiliate_status}`"
            f"{links_line}"
            f"{script_text}"
        )

        # Encontrar el ID del siguiente producto pendiente
        niche = self.user_state.get("queue_niche", "general")
        pending = self._get_pending_queue(niche=niche)
        ids = [p.get("id") for p in pending]
        try:
            idx = ids.index(product_id)
            prev_id = ids[idx - 1] if idx > 0 else None
            next_id = ids[idx + 1] if idx + 1 < len(ids) else None
        except ValueError:
            prev_id = None
            next_id = None

        keyboard_rows = [
            [
                {"text": "✏️ Título",        "callback_data": f"queue_title_{product_id}"},
                {"text": "✏️ Precio oferta", "callback_data": f"queue_offer_{product_id}"},
            ],
            [
                {"text": "✏️ Precio anterior", "callback_data": f"queue_list_{product_id}"},
                {"text": "✏️ Descuento",       "callback_data": f"queue_disc_{product_id}"},
            ],
            [
                {"text": "✏️ Enlace", "callback_data": f"queue_link_{product_id}"},
                {"text": "✏️ Imagen", "callback_data": f"queue_img_{product_id}"},
            ],
            [
                {"text": "🎯 Cambiar Nicho", "callback_data": f"queue_niche_{product_id}"},
            ],
        ]
        
        if not is_baby:
            keyboard_rows.append([
                {"text": "🤖 Generar Guion", "callback_data": f"queue_aiscript_{product_id}"},
                {"text": "✏️ Editar Guion",  "callback_data": f"queue_editscript_{product_id}"}
            ])

        keyboard_rows.append([
            {"text": "🔄 Actualizar Datos En Vivo", "callback_data": f"queue_sync_{product_id}"}
        ])
        
        # Agregar botones para abrir enlaces directamente si están disponibles
        open_links_row = []
        if affiliate_url:
            open_links_row.append({"text": "🔗 Abrir Afiliado", "url": affiliate_url})
        if real_url:
            open_links_row.append({"text": "🛍️ Abrir Original", "url": real_url})
        if open_links_row:
            keyboard_rows.append(open_links_row)

        keyboard_rows.extend([
            [{"text": "🚀 Publicar Ahora",    "callback_data": f"queue_pub_{product_id}"}],
            [{"text": "🔄 Mover de posición", "callback_data": f"queue_move_{product_id}"}],
            [{"text": "No publicar",          "callback_data": f"queue_del_{product_id}"}],
        ])
        
        if not is_baby:
            keyboard_rows.append([{"text": "CREAR VIDEO", "callback_data": f"queue_video_{product_id}"}])
            
        keyboard_rows.extend([
            *([[{"text": "⬅️ Anterior", "callback_data": f"queue_show_{prev_id}"},
                {"text": "➡️ Siguiente", "callback_data": f"queue_show_{next_id}"}]] if prev_id and next_id else
               [[{"text": "⬅️ Anterior", "callback_data": f"queue_show_{prev_id}"}]] if prev_id else
               [[{"text": "➡️ Siguiente", "callback_data": f"queue_show_{next_id}"}]] if next_id else []),
            [{"text": "Volver",               "callback_data": f"queue_back_{self.user_state.get('queue_page', 0)}"}],
        ])

        keyboard = {"inline_keyboard": keyboard_rows}

        if img_path:
            existing_card_msg_id = self.user_state.get("product_card_msg_id")
            if existing_card_msg_id:
                # Editar el mensaje de foto existente para no spamear el chat
                ok = await self._edit_photo_message(existing_card_msg_id, img_path, caption=caption, reply_markup=keyboard)
                if ok:
                    if msg_id and msg_id != existing_card_msg_id:
                        await self.delete_message(msg_id)
                    return  # Edicion exitosa, no enviamos nada nuevo
            if msg_id:
                await self.delete_message(msg_id)
            # Primera vez o fallo de edicion: enviamos la foto con botones integrados
            new_msg_id = await self.send_photo(img_path, caption=caption, parse_mode="Markdown", reply_markup=keyboard)
            if new_msg_id:
                self.user_state["product_card_msg_id"] = new_msg_id
        else:
            # Sin foto: limpiar el card guardado y editar o enviar texto
            self.user_state.pop("product_card_msg_id", None)
            await self.send_notification(caption, reply_markup=keyboard, msg_id=msg_id)


    async def _show_guide_page(self, page: int, msg_id=None):
        """Muestra una sección de la guía con botones Anterior / Siguiente."""
        sections = self.user_state.get("guide_sections", [])
        if not sections:
            await self.send_notification("⚠️ Guía no disponible. Toca 📖 GUÍA DE USUARIO de nuevo.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
            return

        total = len(sections)
        page = max(0, min(page, total - 1))
        text = sections[page]

        # Encabezado de página
        header = f"📖 *Guía de Usuario* — Página {page + 1} de {total}\n{'─' * 32}\n\n"
        content = header + text

        # Construir botonera de navegación
        nav_row = []
        if page > 0:
            nav_row.append({"text": "⬅️ Anterior", "callback_data": f"guide_page_{page - 1}"})
        if page < total - 1:
            nav_row.append({"text": "Siguiente ➡️", "callback_data": f"guide_page_{page + 1}"})

        keyboard = {"inline_keyboard": [
            nav_row,
            [{"text": "🔙 Cerrar Guía", "callback_data": "nav_mantenimiento"}]
        ]}

        await self.send_notification(content, reply_markup=keyboard, msg_id=msg_id)

    async def _search_queue(self, keyword):
        keyword = keyword.strip().lower()
        matches = [
            product for product in self._get_pending_queue()
            if keyword in product.get("title", "").lower() or keyword in product.get("id", "").lower()
        ]
        if not matches:
            await self.send_notification(f"No encontre productos con `{keyword}`.")
            await self._show_queue_browser(self.user_state.get("queue_page", 0))
            return
        rows = [
            [{"text": product.get("title", "Sin titulo")[:42], "callback_data": f"queue_show_{product.get('id', '')}"}]
            for product in matches[:10]
        ]
        rows.append([{"text": "Volver", "callback_data": f"queue_page_{self.user_state.get('queue_page', 0)}"}])
        await self.send_notification(
            f"**Resultados de cola:** {len(matches)}",
            reply_markup={"inline_keyboard": rows},
        )

    async def _handle_queue_callback(self, text, callback_query, msg_id=None):
        parts = text.split("_", 2)
        if len(parts) < 3:
            return
        action, value = parts[1], parts[2]

        if action == "back":
            photo_msg_id = self.user_state.pop("product_card_msg_id", None)
            if photo_msg_id:
                await self.delete_message(photo_msg_id)
            elif msg_id:
                await self.delete_message(msg_id)
            
            try:
                page_val = int(value)
            except (ValueError, TypeError):
                page_val = 0
            await self._show_queue_browser(page_val)
            return
        if action == "page":
            await self._show_queue_browser(int(value), msg_id=msg_id)
            return
        if action == "search":
            self.user_state["queue_search_mode"] = True
            await self.send_notification("Escribe una palabra del titulo o el ID del producto:")
            return
        if action == "exit":
            await self.handle_command("cola", callback_query)
            
            return

        if action == "nav":
            niche = value
            self.user_state["queue_niche"] = niche
            self.user_state["queue_page"] = 0
            await self._show_queue_browser(page=0, msg_id=msg_id)
            return

        target = None
        products = []
        niche = self.user_state.get("queue_niche", "general")
        
        if value and action not in ["search", "exit", "nav", "back", "superreport", "page"]:
            is_new_enqueue = action == "niche" and any(value.startswith(prefix) for prefix in ["general_", "baby_", "pets_", "tenis_", "moda_"])
            if not is_new_enqueue:
                for n in ["general", "baby", "pets", "tenis", "moda"]:
                    q = self._load_queue_data(niche=n)
                    found = next((p for p in q if p.get("id") == value), None)
                    if found:
                        target = found
                        products = q
                        niche = n
                        self.user_state["queue_niche"] = n
                        break
                if not target:
                    products = self._load_queue_data(niche=niche)
        else:
            products = self._load_queue_data(niche=niche)
            target = next((p for p in products if p.get("id") == value), None) if value else None

        is_new_enqueue = action == "niche" and value and any(value.startswith(prefix) for prefix in ["general_", "baby_", "pets_", "tenis_", "moda_"])
        if not target and not is_new_enqueue and action not in ["search", "exit", "nav", "back", "superreport", "page"]:
            await self.send_notification(f"Producto `{value}` no encontrado en la cola.")
            return
        if action == "show":
            await self._send_queue_product_actions(target, msg_id=msg_id)
            return
        if action == "niche":
            # Detectar si es una selección de nicho desde _process_queue_command
            # (callback: queue_niche_general_{temp_id}) vs. cambio de nicho del browser (queue_niche_{product_id})
            _niche_prefix_map = [
                ("general_", "general", "[CAT:GENERAL]"),
                ("baby_", "baby", "[CAT:BEBES]"),
                ("pets_", "pets", "[CAT:MASCOTAS]"),
                ("tenis_", "tenis", "[CAT:TENIS]"),
                ("moda_", "moda", "[CAT:MODA]"),
            ]
            for _prefix, _niche_key, _niche_tag in _niche_prefix_map:
                if value.startswith(_prefix):
                    _temp_id = value[len(_prefix):]
                    _product_data = self._pop_temp_queue_request(_temp_id)
                    if not _product_data:
                        await self.send_notification("⚠️ Esta solicitud ya no existe o expiró. Vuelve a enviar el enlace.")
                        return
                    _product_data["niche"] = _niche_tag
                    _active_queue = self._load_queue_data(niche=_niche_key)
                    if not any(item.get("id") == _product_data.get("id") for item in _active_queue):
                        _active_queue.append(_product_data)
                        self._save_queue_data(_active_queue, niche=_niche_key)
                        self._reset_cursors_for_new_items()
                    _title = _product_data.get("title", "Sin título")
                    _confirm = f"✅ **Producto agregado a la cola {_niche_key.upper()}:**\n`{_title[:80]}`"
                    _cb_msg_id = callback_query.get("message", {}).get("message_id") if callback_query else None
                    if _cb_msg_id:
                        try:
                            _edit_url = f"https://api.telegram.org/bot{self.token}/editMessageText"
                            _session = await self._get_send_session()
                            await _session.post(_edit_url, json={"chat_id": self.chat_id, "message_id": _cb_msg_id, "text": _confirm, "parse_mode": "Markdown"})
                        except Exception:
                            await self.send_notification(_confirm)
                    else:
                        await self.send_notification(_confirm)
                    return

            # Cambio de nicho del browser de cola existente
            niches = ["[CAT:GENERAL]", "[CAT:BEBES]", "[CAT:MASCOTAS]", "[CAT:MODA]", "[CAT:TENIS]"]
            _niche_tag_to_key = {
                "[CAT:GENERAL]": "general", "[CAT:BEBES]": "baby",
                "[CAT:MASCOTAS]": "pets", "[CAT:MODA]": "moda", "[CAT:TENIS]": "tenis",
            }
            current_niche = target.get("niche", "[CAT:GENERAL]")
            try:
                next_index = (niches.index(current_niche) + 1) % len(niches)
            except ValueError:
                next_index = 0

            new_niche_tag = niches[next_index]
            new_niche_key = _niche_tag_to_key.get(new_niche_tag, "general")

            # Eliminar de la cola original
            products = [p for p in products if p.get("id") != target.get("id")]
            self._save_queue_data(products, niche=niche)

            # Agregar a la cola del nuevo nicho
            target["niche"] = new_niche_tag
            new_queue = self._load_queue_data(niche=new_niche_key)
            if not any(p.get("id") == target.get("id") for p in new_queue):
                new_queue.append(target)
                self._save_queue_data(new_queue, niche=new_niche_key)

            # Seguir al producto en su nuevo nicho
            self.user_state["queue_niche"] = new_niche_key

            await self._send_queue_product_actions(target, msg_id=msg_id)
            return
        if action == "video":
            await self._start_custom_script_flow(value, msg_id=msg_id)
            return
        if action == "aiscript":
            await self.send_notification(f"🤖 Regenerando guion con IA en vivo para `{value}`...")
            await self._ensure_top_10_queue_assets(force_product_id=value)
            niche = self.user_state.get("queue_niche", "general")
            updated_products = self._load_queue_data(niche=niche)
            new_target = next((p for p in updated_products if p.get("id") == value), None)
            if new_target:
                await self._send_queue_product_actions(new_target, msg_id=msg_id)
            await self.send_notification("✅ Guion con IA regenerado y guardado.")
            return
        if action == "editscript":
            self.user_state["queue_editing_product_id"] = value
            self.user_state["queue_editing_field"] = "script"
            await self.send_notification(
                f"✏️ **Editar guion para `{value}`**\n"
                f"Escribe o pega el nuevo guion. Escribe **exactamente una escena por línea** (máximo 6 líneas/escenas).\n\n"
                f"💡 **Ejemplo:**\n"
                f"Esta es la mejor oferta del día\n"
                f"Tenis casuales Adidas con 40% de descuento\n"
                f"Son súper cómodos y duraderos\n"
                f"Consigue los tuyos con envío gratis en mi perfil"
            )
            return

        if action == "del":
            history = self._load_history()
            known_history = set(history)
            for value_to_block in (target.get("id"), target.get("affiliate_url")):
                if value_to_block and value_to_block not in known_history:
                    history.append(value_to_block)
                    known_history.add(value_to_block)
            self._save_history(history)
            self._save_queue_data([product for product in products if product.get("id") != value], niche=niche)
            await self.send_notification(f"Producto `{value}` bloqueado y eliminado de la cola.")
            await self._show_queue_browser(self.user_state.get("queue_page", 0))
            return
        if action == "sync":
            url_to_scrape = target.get("affiliate_url", "") or target.get("real_url", "")
            if not url_to_scrape:
                await self.send_notification("No hay enlace configurado para sincronizar.")
                return
            await self.send_notification(f"⏳ Consultando precios actuales para `{value}` en vivo...")
            try:
                fresh = await self.orchestrator.scrape_product_details(url_to_scrape)
                if not fresh or not fresh.get("title") or fresh.get("title") == "Oferta Especial en Mercado Libre":
                    await self.send_notification("❌ No se pudieron extraer datos de la página. ¿El producto está pausado o sin stock?")
                    return
                # Actualizar campos en el producto de la cola
                for fld in ["title", "offer_price", "list_price", "discount"]:
                    if fresh.get(fld):
                        target[fld] = fresh[fld]
                niche = self.user_state.get("queue_niche", "general")
                self._save_queue_data(products, niche=niche)
                await self.send_notification("✅ Datos de la cola actualizados con éxito con la tienda en vivo.")
                
                # Volver a cargar y mostrar el producto actualizado
                updated_products = self._load_queue_data(niche=niche)
                new_target = next((p for p in updated_products if p.get("id") == value), None)
                if new_target:
                    await self._send_queue_product_actions(new_target)
            except Exception as e:
                await self.send_notification(f"❌ Error al sincronizar: {e}")
            return

        if action == "pub":
            active = self.user_state.get("active_networks", {})
            target_platform = [k for k, v in active.items() if v] if active else "both"
            img_path = target.get("visual_capture") or target.get("screenshot", "")
            if img_path and not os.path.exists(img_path):
                img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))
            await self.send_notification(f"🚀 **Publicando ahora:** `{value}`")
            asyncio.create_task(self.orchestrator.run_publication(
                target["affiliate_url"],
                target_platform=target_platform,
                manual_image=img_path,
                pre_scraped_details=target
            ))
            return
        if action == "move":
            self.user_state["queue_editing_product_id"] = value
            self.user_state["queue_editing_field"] = "move"
            await self.send_notification(f"¿A qué posición de la cola quieres mover este producto?\nEscribe un número (ej: 1 para ponerlo al principio).")
            return
            
        if action in ("title", "offer", "list", "disc", "link", "img"):
            self.user_state["queue_editing_product_id"] = value
            self.user_state["queue_editing_field"] = action
            if action == "img":
                await self.send_notification(f"Envia la nueva imagen para `{value}`.")
            else:
                await self.send_notification(f"Escribe el nuevo valor para `{action}` en `{value}`.")

    async def _process_queue_edit_text(self, text):
        product_id = self.user_state.get("queue_editing_product_id")
        field = self.user_state.get("queue_editing_field")
        niche = self.user_state.get("queue_niche", "general")
        if not product_id or field == "img":
            return
        if field == "link" and not text.strip().startswith(("http://", "https://")):
            await self.send_notification("El enlace debe comenzar con http:// o https://. Intenta otra vez.")
            return

        if field == "move":
            try:
                new_pos = int(text.strip()) - 1
            except ValueError:
                await self.send_notification("Debes escribir un número válido. Intenta otra vez.")
                return
            
            # Cargar historial para filtrar pendientes de la misma forma exacta
            history = set(self._load_history())
            products_all = self._load_queue_data(niche=niche)
            
            # Obtener elementos pendientes de products_all y sus índices reales
            pending_with_indices = []
            for idx, p in enumerate(products_all):
                p_id = p.get("id")
                p_url = p.get("affiliate_url")
                is_pending = p.get("force_publish") or (p_id not in history and p_url not in history)
                if is_pending:
                    pending_with_indices.append((idx, p))
            
            target_pending_idx = next((i for i, item in enumerate(pending_with_indices) if item[1].get("id") == product_id), None)
            
            if target_pending_idx is not None:
                # Ajustar límites de la nueva posición
                if new_pos < 0:
                    new_pos = 0
                if new_pos >= len(pending_with_indices):
                    new_pos = len(pending_with_indices) - 1
                
                # Guardar las posiciones originales que ocupan los pendientes
                original_slots = sorted([item[0] for item in pending_with_indices])
                
                # Reordenar localmente la lista de pendientes
                target_item = pending_with_indices.pop(target_pending_idx)
                pending_with_indices.insert(new_pos, target_item)
                
                # Extraer los productos reordenados
                reordered_pending = [item[1] for item in pending_with_indices]
                
                # Inyectar de vuelta en products_all en las mismas posiciones reservadas
                for idx, prod in zip(original_slots, reordered_pending):
                    products_all[idx] = prod
                    
                self._save_queue_data(products_all, niche=niche)
                self._reset_cursors_for_new_items()
                await self.send_notification(f"✅ Producto movido a la posición {new_pos + 1}.")
                self.user_state.pop("queue_editing_product_id", None)
                self.user_state.pop("queue_editing_field", None)
                await self._show_queue_browser(self.user_state.get("queue_page", 0))
            else:
                await self.send_notification(f"Producto `{product_id}` no encontrado en la cola de pendientes.")
            return

        text = text.strip()
        if field in ["list_price", "offer_price"]:
            if text and text[0].isdigit():
                text = f"${text}"
        elif field == "discount":
            import re
            m = re.match(r'^-?(\d+)\s*(%?)(\s*off)?$', text, re.IGNORECASE)
            if m:
                text = f"{m.group(1)}% OFF"

        updated = self._update_queue_product(product_id, field, text, niche=niche)
        if not updated:
            await self.send_notification(f"Producto `{product_id}` no encontrado.")
            return
        self.user_state.pop("queue_editing_product_id", None)
        self.user_state.pop("queue_editing_field", None)
        await self.send_notification(f"Producto `{product_id}` actualizado.")
        product = next((item for item in self._load_queue_data(niche=niche) if item.get("id") == product_id), None)
        if product:
            await self._send_queue_product_actions(product)

    def _update_queue_product(self, product_id, field, value, niche="general"):
        products = self._load_queue_data(niche=niche)
        target = next((product for product in products if product.get("id") == product_id), None)
        if not target:
            return False
        if field == "script":
            lines = [l.strip() for l in value.splitlines() if l.strip()]
            if not lines:
                return False
            target["script"] = lines[:6]
            self._save_queue_data(products, niche=niche)
            return True

        field_map = {
            "title": "title",
            "offer": "offer_price",
            "list": "list_price",
            "disc": "discount",
            "link": "affiliate_url",
            "img": "screenshot",
        }
        target[field_map[field]] = value
        if field == "img":
            target["visual_capture"] = value
            target.pop("image_url", None)
            
        if field == "link":
            target.pop("affiliate_status", None)
            target.pop("affiliate_error", None)
        self._save_queue_data(products, niche=niche)
        return True


    async def _show_history_browser(self, page=0, msg_id=None):
        db_path = os.path.join(Config.BASE_DIR, "website_db.json")
        if not os.path.exists(db_path):
            await self.send_notification("La base de datos de publicados está vacía o no existe.", reply_markup=self.get_master_keyboard())
            return
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            await self.send_notification(f"Error leyendo historial: {e}", reply_markup=self.get_master_keyboard())
            return

        if not data:
            await self.send_notification("No hay productos publicados registrados.", reply_markup=self.get_master_keyboard())
            return

        page_size = 12
        total_pages = max(1, (len(data) + page_size - 1) // page_size)
        page = max(0, min(int(page), total_pages - 1))
        self.user_state["history_page"] = page
        start = page * page_size
        rows = []
        for idx, product in enumerate(data[start:start + page_size]):
            product_id = product.get("id", "")
            title = product.get("title", "Sin titulo")[:32]
            discount = product.get("discount", "")
            prefix = f"{discount} - " if discount else ""
            niche = product.get("niche", "general")
            if niche in ("baby", "[CAT:BEBES]"):
                niche_label = "[BB] "
            elif niche in ("pets", "[CAT:MASCOTAS]"):
                niche_label = "[PETS] "
            else:
                niche_label = ""
            display_text = f"{start + idx + 1}. {niche_label}{prefix}{title}"
            rows.append([{"text": display_text, "callback_data": f"history_show_{product_id}"}])

        navigation = []
        if page > 0:
            navigation.append({"text": "Anterior", "callback_data": f"history_page_{page - 1}"})
        if page + 1 < total_pages:
            navigation.append({"text": "Siguiente", "callback_data": f"history_page_{page + 1}"})
        if navigation:
            rows.append(navigation)
        rows.append([{"text": "Buscar", "callback_data": "history_search_"}])
        rows.append([{"text": "Volver al menu", "callback_data": "history_exit_"}])

        await self.send_notification(
            f"**Historial de Publicados**\n{len(data)} productos publicados - página {page + 1}/{total_pages}\nSelecciona un producto:",
            reply_markup={"inline_keyboard": rows},
            msg_id=msg_id
        )

    async def _send_history_product_actions(self, product, msg_id=None):
        product_id = product.get("id", "")
        title      = product.get("title", "Sin titulo")
        offer_price = product.get("offer_price", "")
        list_price  = product.get("list_price", "")
        discount    = product.get("discount", "")
        img_path = product.get("visual_capture") or product.get("screenshot", "")
        import os
        from core.config import Config
        if img_path and not os.path.exists(img_path):
            img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))
        if img_path and not os.path.exists(img_path):
            img_path = ""

        # Calcular ahorro
        savings_line = ""
        try:
            o = float(str(offer_price).replace("$","").replace(",","").strip())
            l = float(str(list_price).replace("$","").replace(",","").strip())
            if l > o:
                savings_line = f"\n💰 Ahorro: `${l - o:,.2f}`"
        except Exception:
            pass

        affiliate_url = product.get("affiliate_url", "")
        real_url = product.get("real_url", "")
        links_line = ""
        if affiliate_url:
            links_line += f"🔗 [Link de Afiliado]({affiliate_url})"
        if real_url:
            if links_line:
                links_line += " | "
            links_line += f"🛍️ [Link Original]({real_url})"
        if links_line:
            links_line = f"\n\n{links_line}"

        caption = (
            f"🟢 *PUBLICADO: {title}*\n"
            f"Oferta: `{offer_price}` | Anterior: `{list_price}` | Dcto: `{discount}`"
            f"{savings_line}"
            f"{links_line}"
        )

        # Encontrar el ID del siguiente y anterior producto publicado
        db_path = os.path.join(Config.BASE_DIR, "website_db.json")
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []
        ids = [p.get("id") for p in data]
        try:
            idx = ids.index(product_id)
            prev_id = ids[idx - 1] if idx > 0 else None
            next_id = ids[idx + 1] if idx + 1 < len(ids) else None
        except ValueError:
            prev_id = None
            next_id = None

        keyboard_rows = []
        
        # Enlaces de compra directos
        open_links_row = []
        if affiliate_url:
            open_links_row.append({"text": "🔗 Abrir Afiliado", "url": affiliate_url})
        if real_url:
            open_links_row.append({"text": "🛍️ Abrir Original", "url": real_url})
        if open_links_row:
            keyboard_rows.append(open_links_row)

        keyboard_rows.extend([
            [{"text": "🔄 Volver a Publicar (Todo)", "callback_data": f"history_repub_{product_id}"}],
            [{"text": "🎬 CREAR VIDEO", "callback_data": f"history_video_{product_id}"}],
            [
                {"text": "📘 Repub. FB Grupos", "callback_data": f"history_repnet_{product_id}_facebook"},
                {"text": "✈️ Repub. Telegram", "callback_data": f"history_repnet_{product_id}_telegram"}
            ],
            [
                {"text": "📌 Repub. Pinterest", "callback_data": f"history_repnet_{product_id}_pinterest"},
                {"text": "🌐 Repub. Web", "callback_data": f"history_repnet_{product_id}_web"}
            ],
            [{"text": "🗑️ Quitar de Historial", "callback_data": f"history_forget_{product_id}"}],
            *([[{"text": "⬅️ Anterior", "callback_data": f"history_show_{prev_id}"},
                {"text": "➡️ Siguiente", "callback_data": f"history_show_{next_id}"}]] if prev_id and next_id else
               [[{"text": "⬅️ Anterior", "callback_data": f"history_show_{prev_id}"}]] if prev_id else
               [[{"text": "➡️ Siguiente", "callback_data": f"history_show_{next_id}"}]] if next_id else []),
            [{"text": "Volver al listado", "callback_data": f"history_back_{self.user_state.get('history_page', 0)}"}],
        ])

        keyboard = {"inline_keyboard": keyboard_rows}

        if img_path:
            existing_card_msg_id = self.user_state.get("product_card_msg_id")
            if existing_card_msg_id:
                ok = await self._edit_photo_message(existing_card_msg_id, img_path, caption=caption, reply_markup=keyboard)
                if ok:
                    if msg_id and msg_id != existing_card_msg_id:
                        await self.delete_message(msg_id)
                    return
            if msg_id:
                await self.delete_message(msg_id)
            new_msg_id = await self.send_photo(img_path, caption=caption, parse_mode="Markdown", reply_markup=keyboard)
            if new_msg_id:
                self.user_state["product_card_msg_id"] = new_msg_id
        else:
            self.user_state.pop("product_card_msg_id", None)
            await self.send_notification(caption, reply_markup=keyboard, msg_id=msg_id)

    async def _search_history(self, keyword):
        db_path = os.path.join(Config.BASE_DIR, "website_db.json")
        if not os.path.exists(db_path):
            await self.send_notification("⚠️ No se encontró la base de datos de publicados.")
            return
            
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            await self.send_notification(f"❌ Error leyendo DB: {e}")
            return
            
        matches = [p for p in data if keyword.lower() in p.get("title", "").lower() or keyword.lower() in str(p.get("id", "")).lower()]
        
        if not matches:
            await self.send_notification(f"🤷‍♂️ No encontré nada en el historial con la palabra o ID: `{keyword}`")
            return

        rows = []
        for i, p in enumerate(matches[:15]):
            p_id = p.get("id", "")
            title = p.get("title", "Sin Título")[:38]
            rows.append([{"text": title, "callback_data": f"history_show_{p_id}"}])

        rows.append([{"text": "Volver al listado", "callback_data": f"history_back_{self.user_state.get('history_page', 0)}"}])

        keyboard = {"inline_keyboard": rows}
        await self.send_notification(
            f"🔍 **Resultados de Búsqueda Historial para '{keyword}':** {len(matches)}\nSelecciona un producto:",
            reply_markup=keyboard
        )

    async def _handle_history_callback(self, text, callback_query, msg_id=None):
        parts = text.split("_", 2)
        if len(parts) < 3:
            return
        action = parts[1]
        value = parts[2]

        if action == "back":
            photo_msg_id = self.user_state.pop("product_card_msg_id", None)
            if photo_msg_id:
                await self.delete_message(photo_msg_id)
            elif msg_id:
                await self.delete_message(msg_id)
            
            try:
                page_val = int(value)
            except (ValueError, TypeError):
                page_val = 0
            await self._show_history_browser(page_val)
            return
        if action == "page":
            await self._show_history_browser(int(value), msg_id=msg_id)
            return
        if action == "search":
            self.user_state["history_search_mode"] = True
            await self.send_notification("Escribe una palabra del título o el ID del producto a buscar en el historial:")
            return
        if action == "exit":
            await self.handle_command("cola", callback_query)
            
            return

        db_path = os.path.join(Config.BASE_DIR, "website_db.json")
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                products = json.load(f)
        except Exception:
            products = []

        if action == "repnet":
            last_sep = value.rfind("_")
            if last_sep == -1:
                return
            p_id_val, network = value[:last_sep], value[last_sep + 1:]
            target = next((p for p in products if p.get("id") == p_id_val), None)
        else:
            target = next((p for p in products if p.get("id") == value), None)

        if not target:
            await self.send_notification(f"Producto `{value}` no encontrado en el historial.")
            return

        if action == "show":
            await self._send_history_product_actions(target, msg_id=msg_id)
            return

        if action == "video":
            await self._start_custom_script_flow(value, msg_id=msg_id)
            return

        if action == "forget":
            history = self._load_history()
            p_url = target.get("affiliate_url", "")
            p_real = target.get("real_url", "")
            p_id = target.get("id", "")

            new_history = [item for item in history if item not in (p_url, p_real, p_id) and item]
            self._save_history(new_history)

            await self.send_notification(f"✅ Producto `{p_id}` eliminado del historial de duplicados. Ya puedes volver a encolarlo.")
            await self._show_history_browser(self.user_state.get("history_page", 0), msg_id=msg_id)
            return

        if action == "repub":
            url = target.get("affiliate_url") or target.get("real_url", "")
            img_path = target.get("visual_capture") or target.get("screenshot", "")
            if img_path and not os.path.exists(img_path):
                img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))
            
            details_copy = target.copy()
            details_copy["skip_scrape"] = True
            details_copy["force_publish"] = True

            await self.send_notification(f"🚀 **Republicando en TODAS las redes:** `{target.get('title', '')[:40]}`...")
            asyncio.create_task(self.orchestrator.run_publication(
                url,
                target_platform="both",
                manual_image=img_path,
                pre_scraped_details=details_copy
            ))
            return

        if action == "repnet":
            url = target.get("affiliate_url") or target.get("real_url", "")
            img_path = target.get("visual_capture") or target.get("screenshot", "")
            if img_path and not os.path.exists(img_path):
                img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))

            details_copy = target.copy()
            details_copy["skip_scrape"] = True
            details_copy["force_publish"] = True

            await self.send_notification(f"🚀 **Republicando en {network.upper()}:** `{target.get('title', '')[:40]}`...")
            asyncio.create_task(self.orchestrator.run_publication(
                url,
                target_platform=network,
                manual_image=img_path,
                pre_scraped_details=details_copy
            ))
            return


    async def _generate_and_preview_script(self, product, vtype, msg_id=None):
        """Llama a Gemini para generar guion segun tipo de video y datos del producto."""
        gemini_keys = Config.get_gemini_keys()
        if not gemini_keys:
            await self.send_notification("ERROR: No hay GEMINI_API_KEY en .env", reply_markup=self.get_master_keyboard())
            return

        title    = product.get("title", "este producto")
        offer    = product.get("offer_price", "")
        original_p = product.get("list_price", "")
        discount = product.get("discount", "")
        category = product.get("category", "")

        # Un solo tipo de video: oferta con estructura P+B+CTA
        instruction = "un video de OFERTA que identifica un problema, muestra beneficios y convoca a la acción inmediata"

        # Ocultar precios reales para forzar un guion atemporal (evergreen)
        price_info = "Tiene un gran descuento actualmente. (NO mencionar el precio exacto)"

        prompt = (
            f"Eres un experto en copywriting digital y creador de contenido viral de TikTok/Shorts en México, especializado en suplementos, tecnología y estilo de vida.\n"
            f"Tu objetivo es crear {instruction} para promocionar este producto.\n\n"
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
            f"EJEMPLO ESTRUCTURA:\n"
            f"Tus tenis viejos ya no aguantan las corridas largas sin rozaduras\n"
            f"El dolor de pies al terminar el día es frustrante y agotador\n"
            f"Estos Nike tienen el soporte biomecánico más avanzado del mercado\n"
            f"Corres sin molestias, máximo confort y tu cuerpo te lo agradece\n"
            f"Consigue el tuyo directamente en el enlace que te dejé abajo\n"
            f"¡Compra ahora, antes que se agoten a este precio!\n\n"
            f"Salida: Devuelve ÚNICAMENTE las 6 líneas exactas, nada más."
        )

        try:
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}

            raw = None
            for gemini_key in gemini_keys:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={gemini_key}"
                max_retries = 3
                backoff = 1.5
                key_exhausted = False
                for attempt in range(max_retries):
                    try:
                        session = await self._get_send_session()
                        async with session.post(url, json=payload, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                                break
                            elif resp.status == 429:
                                print(f"[GEMINI ROTATION] Clave agotada/limitada, probando siguiente...")
                                key_exhausted = True
                                break
                            elif resp.status == 503 and attempt < max_retries - 1:
                                print(f"[GEMINI] Servidor ocupado ({resp.status}). Reintentando en {backoff}s...")
                                await asyncio.sleep(backoff)
                                backoff *= 2
                            else:
                                err = await resp.text()
                                print(f"[GEMINI] Error HTTP {resp.status}: {err[:200]}")
                                break
                    except Exception as ex:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                        else:
                            print(f"[GEMINI] Error de conexión: {ex}")
                            break
                if raw or not key_exhausted:
                    break

            # Fallback en caso de que Gemini esté caído o haya fallado la API
            if not raw:
                await self.send_notification("⚠️ Gemini no está disponible temporalmente (503/Exceso de demanda). Usando plantilla de respaldo...")
                lines = [
                    f"¿Buscas el mejor precio para {title}?",
                    f"Acabamos de encontrar esta increíble oferta.",
                    f"De un precio original de {original_p or 'su costo regular'}, bajó considerablemente.",
                    f"Llévatelo ahora por solo {offer or 'el mejor precio'} con un gran descuento.",
                    "Consigue el tuyo en el enlace de la descripción de este video."
                ]
            else:
                lines = [l.strip() for l in raw.splitlines() if l.strip()][:6]
                if not lines:
                    await self.send_notification("Gemini devolvió una respuesta vacía. Intentando con plantilla de respaldo...")
                    lines = [
                        f"¿Buscas el mejor precio para {title}?",
                        f"Acabamos de encontrar esta increíble oferta.",
                        f"De un precio original de {original_p or 'su costo regular'}, bajó considerablemente.",
                        f"Llévatelo ahora por solo {offer or 'el mejor precio'} con un gran descuento.",
                        "Consigue el tuyo en el enlace de la descripción de este video."
                    ]

            self.user_state["awaiting_guion_approval"] = True
            self.user_state["pending_guion_lines"] = lines
            
            clean_script = "\n".join(lines)
            await self.send_notification(clean_script)
            await self.send_notification(
                f"☝️ **GUION GENERADO ({vtype.upper()})**\n\n"
                "• Escribe **OK** si te gusta y quieres continuar.\n"
                "• O bien: **copia el guion de arriba, edítalo y envíalo aquí mismo** para usar tu versión corregida."
            )
        except Exception as e:
            await self.send_notification(f"Error generando guion: {e}", reply_markup=self.get_master_keyboard())

    async def _execute_premium_render(self, images, work_dir):
        """Paso 2/3 y 3/3: genera voz y renderiza el video con las imágenes dadas."""
        try:
            from core.voice_generator import process_script
            from core.advanced_video_maker import create_final_video
            import asyncio as _aio

            await self.send_notification(
                f"FOTOS LISTAS: {len(images)} imagen(es)\n"
                "PASO 2/3: Generando voz con ElevenLabs..."
            )

            script_path = os.path.join(Config.BASE_DIR, "guion.json")
            audio_data = await _aio.to_thread(process_script, script_path, work_dir)
            if not audio_data:
                await self.send_notification(
                    "ERROR: Fallo la generacion de voz.\n"
                    "Verifica ELEVENLABS_API_KEY en .env y que guion.json tenga escenas validas.",
                    reply_markup=self.get_master_keyboard()
                )
                return

            await self.send_notification(
                "PASO 3/3: Renderizando video con moviepy..."
            )

            out_video = os.path.join(Config.BASE_DIR, "tiktok_videos", "premium_render.mp4")
            final = await _aio.to_thread(create_final_video, images, audio_data, out_video)

            if final and os.path.exists(final):
                # Leer link de afiliado del último publicado
                _link = ""
                try:
                    _lp_path = os.path.join(Config.BASE_DIR, "last_published.json")
                    if os.path.exists(_lp_path):
                        with open(_lp_path, encoding="utf-8") as _lf:
                            _lp = json.load(_lf)
                        _link = _lp.get("affiliate_url") or _lp.get("url") or ""
                except Exception:
                    pass
                _caption = "VIDEO PREMIUM LISTO"
                if _link:
                    _caption += f"\n\nLink para descripcion:\n{_link}"
                await self.send_video(final, caption=_caption)
                await self.send_notification("LISTO." + " " * 5, reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification("ERROR: Fallo el render con moviepy.", reply_markup=self.get_master_keyboard())
        except Exception as e:
            await self.send_notification(f"ERROR CRITICO en render premium: {e}", reply_markup=self.get_master_keyboard())

    def safe_makedirs(self, path):
        import os
        os.makedirs(path, exist_ok=True)
        try:
            os.chmod(path, 0o777)
            parent = os.path.dirname(path)
            if os.path.basename(parent) == "captures":
                os.chmod(parent, 0o777)
        except Exception as e:
            print(f"[PERMISSIONS] Failed to chmod path {path}: {e}")

    async def _execute_premium_flow(self, target_url):
        work_dir = os.path.join(Config.BASE_DIR, "captures", "premium_temp")
        self.safe_makedirs(work_dir)

        await self.send_notification(
            f"PRODUCCION PREMIUM INICIADA\n"
            f"URL: {target_url}\n"
            "PASO 1/3: Extrayendo imagenes del fabricante..."
        )
        try:
            from core.manufacturer_scraper import scrape_manufacturer_images
            images = await scrape_manufacturer_images(target_url, work_dir, min_images=3)
        except Exception as e:
            images = []
            await self.send_notification(f"ERROR en scraper: {e}")

        if not images:
            # Fallback: pedir fotos al usuario
            self.user_state["awaiting_premium_images"] = True
            self.user_state["premium_images_collected"] = []
            await self.send_notification(
                "NO SE PUDIERON EXTRAER IMAGENES AUTOMATICAMENTE\n\n"
                "Puedes mandarme las fotos tu mismo directamente aqui.\n"
                "Manda entre 3 y 6 fotos del producto una por una.\n"
                "Cuando termines escribe: LISTO"
            )
            return

        await self.send_notification(
            f"PASO 1/3 COMPLETO: {len(images)} imagen(es) descargadas"
        )
        await self._execute_premium_render(images, work_dir)

    async def show_next_draft(self):
        """Busca el primer borrador de products_draft.json y lo envía para revisión."""
        drafts = self._load_drafts()
        if not drafts:
            await self.send_notification(
                "📋 **Curación de Ofertas**\nNo hay borradores pendientes en `products_draft.json`.",
                reply_markup=self.get_master_keyboard()
            )
            return

        reviewable = [
            product for product in drafts
            if product.get("review_status") == "needs_review"
            or (not product.get("source") and not product.get("review_status"))
        ]

        # Auto-descartar los que no tienen meli.la (no se pueden aprobar)
        without_link = [p for p in reviewable if "meli.la" not in str(p.get("affiliate_url", ""))]
        if without_link:
            from core.history_manager import load_history_map
            from core.storage import json_save_atomic
            from datetime import datetime
            h_map = load_history_map()
            now_iso = datetime.now().isoformat()
            for p in without_link:
                pid = p.get("id")
                aff = p.get("affiliate_url")
                if pid:
                    h_map[str(pid)] = now_iso
                if aff:
                    h_map[str(aff)] = now_iso
                    match = re.search(r"MLM-?(\d+)", aff.upper())
                    if match:
                        h_map[f"MLM{match.group(1)}"] = now_iso
            json_save_atomic(Config.HISTORY_FILE, h_map, indent=2, ensure_ascii=False)
            without_ids = {p.get("id") for p in without_link}
            drafts = [p for p in drafts if p.get("id") not in without_ids]
            self._save_drafts(drafts)
            reviewable = [p for p in reviewable if p.get("id") not in without_ids]
            await self.send_notification(
                f"🗑️ {len(without_link)} producto(s) sin link de afiliado descartado(s) automáticamente."
            )

        if not reviewable:
            waiting_automatic = sum(
                product.get("review_status") in ("pending_affiliate", "pending_validation")
                for product in drafts
            )
            await self.send_notification(
                f"No hay productos que necesiten aprobacion. Pendientes de proceso automatico: {waiting_automatic}.",
                reply_markup=self.get_master_keyboard(),
            )
            return

        product = reviewable[0]
        p_id = product.get("id")
        from core.utils import escape_markdown
        title = escape_markdown(product.get("title", "Sin Título"))
        list_price = escape_markdown(product.get("list_price", ""))
        offer_price = escape_markdown(product.get("offer_price", "Ver en enlace"))
        discount = escape_markdown(product.get("discount", ""))
        aff_url = product.get("affiliate_url", "")
        screenshot = product.get("screenshot", "")
        image_url = product.get("image_url", "")
        
        # Corregir ruta del screenshot
        if screenshot and not os.path.exists(screenshot):
            screenshot = os.path.join(Config.BASE_DIR, "captures", os.path.basename(screenshot))

        caption = (
            f"📦 **Producto en Revisión** (Pendientes: {len(reviewable)})\n\n"
            f"📝 **Título:** {title}\n"
            f"💰 **Precio Anterior:** {''.join(c + '\u0336' for c in str(list_price))}\n"
            f"🏷️ **Precio Oferta:** `{offer_price}` ({discount})\n\n"
            f"🔗 [Enlace de Oferta]({aff_url})"
        )
        confidence_score = product.get("confidence_score")
        confidence_reasons = product.get("confidence_reasons") or []
        if confidence_score is not None:
            caption += f"\n\nConfianza: `{confidence_score}/100`"
        if confidence_reasons:
            caption += "\nMotivos:\n" + "\n".join(f"- {reason}" for reason in confidence_reasons[:4])
        
        # Teclado inline interactivo
        action_row = []
        if "meli.la" in aff_url:
            action_row.append({"text": "✅ Aprobar", "callback_data": f"approve_draft_{p_id}"})
        action_row.append({"text": "❌ Descartar", "callback_data": f"discard_draft_{p_id}"})
        reply_markup = {
            "inline_keyboard": [
                action_row,
                [
                    {"text": "Abrir oferta", "url": aff_url},
                    {"text": "🎬 CREAR VIDEO", "callback_data": f"draft_video_{p_id}"}
                ]
            ]
        }

        # Intentar enviar la foto con aiohttp
        if screenshot and os.path.exists(screenshot):
            url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
            data = aiohttp.FormData()
            data.add_field("chat_id", str(self.chat_id))
            data.add_field("caption", caption)
            data.add_field("parse_mode", "Markdown")
            data.add_field("reply_markup", json.dumps(reply_markup))
            
            with open(screenshot, 'rb') as f:
                data.add_field("photo", f, filename=os.path.basename(screenshot))
                try:
                    session = await self._get_send_session()
                    async with session.post(url, data=data) as resp:
                        res = await resp.json()
                        if not res.get("ok"):
                            await self.send_notification(caption, reply_markup=reply_markup)
                except Exception as e:
                    print(f"Error enviando foto a Telegram: {e}")
                    await self.send_notification(caption, reply_markup=reply_markup)
        elif image_url.startswith(("http://", "https://")):
            url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
            payload = {
                "chat_id": self.chat_id,
                "photo": image_url,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_markup": reply_markup,
            }
            try:
                session = await self._get_send_session()
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()
                    if not result.get("ok"):
                        await self.send_notification(caption, reply_markup=reply_markup)
            except Exception:
                await self.send_notification(caption, reply_markup=reply_markup)
        else:
            await self.send_notification(caption, reply_markup=reply_markup)

    async def process_draft_action(self, p_id, approve, callback_query=None):
        """Mueve o descarta el borrador y actualiza el chat."""
        drafts = self._load_drafts()
        if not drafts:
            await self.send_notification("⚠️ Archivo de borradores no encontrado.")
            return

        # Buscar el producto
        target = None
        remaining_drafts = []
        for d in drafts:
            if d.get("id") == p_id:
                target = d
            else:
                remaining_drafts.append(d)

        self._save_drafts(remaining_drafts)

        if not target:
            if callback_query:
                msg_id = callback_query.get("message", {}).get("message_id")
                await self.edit_caption(msg_id, "⚠️ Oferta expirada o ya procesada.")
            else:
                await self.send_notification("⚠️ Oferta no encontrada en los borradores.")
            return

        from core.utils import escape_markdown
        title = escape_markdown(target.get("title", "Sin Título"))
        screenshot = target.get("screenshot", "")
        if screenshot and not os.path.exists(screenshot):
            screenshot = os.path.join(Config.BASE_DIR, "captures", os.path.basename(screenshot))

        action_text = ""
        if approve:
            # Mover a la cola correspondiente
            target["review_status"] = "approved_manual"
            target.pop("affiliate_status", None)
            target.pop("affiliate_error", None)
            
            niche_val = target.get("niche", "[CAT:GENERAL]")
            if "[CAT:BEBES]" in niche_val:
                niche_key = "baby"
            elif "[CAT:MASCOTAS]" in niche_val:
                niche_key = "pets"
            else:
                niche_key = "general"
                
            active_queue = self._load_queue_data(niche=niche_key)
            if not any(item.get("id") == p_id for item in active_queue):
                active_queue.insert(0, target)
                self._save_queue_data(active_queue, niche=niche_key)
                self._reset_cursors_for_new_items()
            
            action_text = f"✅ **Aprobado y en cola de publicación:**\n`{title}`"
        else:
            if screenshot and os.path.exists(screenshot):
                try: os.remove(screenshot)
                except: pass
                
            # Registrar el descarte en el historial para no volver a scrapear
            history = set(self._load_history())
            if p_id:
                history.add(p_id)
            aff_url = target.get("affiliate_url")
            if aff_url:
                history.add(aff_url)
                # Extraer ID MLM de la URL como precaución extra
                match = re.search(r'MLM-?(\d+)', aff_url)
                if match:
                    history.add(f"MLM{match.group(1)}")
                    
            self._save_history(history)
            action_text = f"❌ **Descartado y eliminado:**\n`{title}`"

        if callback_query:
            msg_id = callback_query.get("message", {}).get("message_id")
            await self.edit_caption(msg_id, action_text)
        else:
            await self.send_notification(action_text)

        # Mostrar el siguiente de inmediato
        remaining_reviews = sum(
            product.get("review_status") == "needs_review"
            or (not product.get("source") and not product.get("review_status"))
            for product in remaining_drafts
        )
        if remaining_reviews > 0:
            await self.show_next_draft()
        else:
            await self.send_notification(
                "🎉 **¡Todo listo!** Has curado todos los borradores de la cola.",
                reply_markup=self.get_master_keyboard()
            )

    async def edit_caption(self, message_id, caption, reply_markup=None):
        """Edita la leyenda y limpia botones de un mensaje con foto de forma dinámica."""
        url = f"https://api.telegram.org/bot{self.token}/editMessageCaption"
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        else:
            payload["reply_markup"] = {"inline_keyboard": []}
            
        try:
            session = await self._get_send_session()
            async with session.post(url, json=payload) as resp:
                return await resp.json()
        except Exception as e:
            print(f"Error editando caption: {e}")
            return None

    async def _show_admin_browser(self, msg_id=None):
        """Muestra los 10 productos más recientes como botones inline para gestión rápida."""
        db_path = os.path.join(Config.BASE_DIR, "website_db.json")
        if not os.path.exists(db_path):
            await self.send_notification("\u26a0\ufe0f No se encontr\u00f3 la base de datos web.")
            return
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            await self.send_notification(f"\u274c Error leyendo DB: {e}")
            return

        if not data:
            await self.send_notification("\ud83d\udce6 La base de datos web est\u00e1 vac\u00eda.")
            return

        # Los 10 más recientes (primeros en la lista, se insertan al inicio)
        recientes = data[:10]
        rows = []
        for p in recientes:
            p_id = p.get("id", "")
            title = p.get("title", "Sin T\u00edtulo")[:38]
            rows.append([{"text": title, "callback_data": f"admin_show_{p_id}"}])

        # Botón de búsqueda al final
        rows.append([{"text": "🔍 Buscar por nombre...", "callback_data": "admin_search_"}])

        # Botón para salir
        rows.append([{"text": "❌ Salir al Menú Principal", "callback_data": "admin_exit_"}])

        keyboard = {"inline_keyboard": rows}
        await self.send_notification(
            f"\ud83d\udee0\ufe0f **Panel de Administraci\u00f3n Web**\n"
            f"Mostrando los \u00faltimos {len(recientes)} productos. Toca uno para editarlo:",
            reply_markup=keyboard
        )

    async def _send_product_action_buttons(self, p: dict, next_id: str = None, prev_id: str = None, msg_id=None):
        """Envía o edita los botones de acción para un producto específico."""
        p_id = p.get("id", "")
        title = p.get("title", "Sin Título")
        price = p.get("offer_price", "$0")
        cat = p.get("category", "Sin categoría")
        msg = f"📦 **{title}**\n💰 Precio: {price}\n🏷️ Categoría: {cat}"
        rows = [
            [
                {"text": "❌ Eliminar", "callback_data": f"admin_del_{p_id}"},
                {"text": "📸 Imagen", "callback_data": f"admin_img_{p_id}"}
            ],
            [
                {"text": "✏️ Precio", "callback_data": f"admin_price_{p_id}"},
                {"text": "✏️ Descuento", "callback_data": f"admin_disc_{p_id}"}
            ],
            [
                {"text": "✏️ Título", "callback_data": f"admin_title_{p_id}"},
                {"text": "🏷️ Categoría", "callback_data": f"admin_cat_{p_id}"}
            ],
        ]
        if prev_id and next_id:
            rows.append([{"text": "⬅️ Anterior", "callback_data": f"admin_show_{prev_id}"},
                         {"text": "➡️ Siguiente", "callback_data": f"admin_show_{next_id}"}])
        elif prev_id:
            rows.append([{"text": "⬅️ Anterior", "callback_data": f"admin_show_{prev_id}"}])
        elif next_id:
            rows.append([{"text": "➡️ Siguiente", "callback_data": f"admin_show_{next_id}"}])
        rows.append([{"text": "⬅️ Volver al panel", "callback_data": "admin_back_"}])
        keyboard = {"inline_keyboard": rows}
        await self.send_notification(msg, reply_markup=keyboard, msg_id=msg_id)

    async def _search_web_database(self, keyword):
        """Busca un producto en la base de datos web y devuelve botones de admin."""
        import json
        import os
        from core.config import Config
        db_path = os.path.join(Config.BASE_DIR, "website_db.json")
        if not os.path.exists(db_path):
            await self.send_notification("⚠️ No se encontró la base de datos de la web (website_db.json).")
            return
            
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            await self.send_notification(f"❌ Error leyendo DB: {e}")
            return
            
        matches = [p for p in data if keyword.lower() in p.get("title", "").lower()]
        
        if not matches:
            await self.send_notification(f"\ud83e\udd37\u200d\u2642\ufe0f No encontré nada en la web con la palabra: `{keyword}`")
            return

        await self.send_notification(f"\ud83d\udd0d **Resultados para '{keyword}':** ({len(matches)} encontrados)")

        for i, p in enumerate(matches[:5]):
            prev_p = matches[i - 1] if i > 0 else None
            next_p = matches[i + 1] if i + 1 < len(matches[:5]) else None
            prev_id = prev_p.get("id") if prev_p else None
            next_id = next_p.get("id") if next_p else None
            await self._send_product_action_buttons(p, next_id=next_id, prev_id=prev_id)

    async def _handle_admin_callback(self, text, callback_query):
        """Maneja los clics de los botones de administrador."""
        # Formato normal:   admin_del_ID, admin_img_ID, admin_cat_ID
        # Formato setcat:   admin_setcat_ID_Categoria  (4 segmentos)
        parts = text.split("_", 2)
        if len(parts) < 3: return
        action = parts[1]   # del | img | price | disc | title | cat | setcat
        p_id = parts[2]     # Para setcat este campo contiene "ID_Categoria"
        msg_id = callback_query.get("message", {}).get("message_id")
        
        if action == "del":
            await self._update_web_db(p_id, "delete", None)
            await self.edit_caption(msg_id, f"\u2705 **Producto Eliminado de la Web:** {p_id}")
        elif action == "show":
            # Mostrar botones de acción para el producto seleccionado en el browser
            db_path = os.path.join(Config.BASE_DIR, "website_db.json")
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ids = [p.get("id") for p in data]
                target = next((p for p in data if p.get("id") == p_id), None)
                if target:
                    try:
                        idx = ids.index(p_id)
                        prev_id = ids[idx - 1] if idx > 0 else None
                        next_id = ids[idx + 1] if idx + 1 < len(ids) else None
                    except ValueError:
                        prev_id = None
                        next_id = None
                    await self._send_product_action_buttons(target, next_id=next_id, prev_id=prev_id, msg_id=msg_id)
                else:
                    await self.send_notification(f"\u26a0\ufe0f Producto `{p_id}` no encontrado en la DB.")
            except Exception as e:
                await self.send_notification(f"\u274c Error: {e}")
        elif action == "search":
            self.user_state["admin_search_mode"] = True
            await self.send_notification("🔍 Escribe el nombre o palabra clave del producto a buscar:")
        elif action == "back":
            await self._show_admin_browser(msg_id=msg_id)
        elif action == "exit":
            await self.handle_command("cola", callback_query)
            
        elif action == "cat":
            # Mostrar botones con las categorías disponibles
            cats = ["Tecnolog\u00eda", "Moda", "Hogar", "Herramientas", "Videojuegos", "Otros"]
            cat_keyboard = {
                "inline_keyboard": [[{"text": c, "callback_data": f"admin_setcat_{p_id}_{c}"}] for c in cats]
            }
            await self.send_notification(f"\ud83c\udff7\ufe0f Selecciona la nueva categor\u00eda para `{p_id}`:", reply_markup=cat_keyboard)
        elif action == "setcat":
            # El ID puede tener _ (ej MANUAL_1781361855), la Categoría nunca.
            # Usamos rfind para partir desde el ÚLTIMO guion bajo.
            prefix = "admin_setcat_"
            rest = text[len(prefix):]           # MANUAL_1781361855_Tecnología
            underscore_idx = rest.rfind("_")    # último _
            real_p_id = rest[:underscore_idx]   # MANUAL_1781361855
            new_cat = rest[underscore_idx + 1:] # Tecnología
            await self._update_web_db(real_p_id, "cat", new_cat)
            await self.edit_caption(msg_id, f"✅ Categoría actualizada a **{new_cat}** para `{real_p_id}`.")
            await self._show_admin_browser()
        elif action in ["img", "price", "disc", "title"]:
            fields = {"img": "imagen", "price": "precio", "disc": "descuento", "title": "título"}
            self.user_state["editing_product_id"] = p_id
            self.user_state["editing_field"] = action
            prompt = f"✍️ **Modo Edición Activado**\nEstás editando el **{fields[action]}** del producto `{p_id}`.\n\n"
            if action == "img":
                prompt += "📷 **Envíame la nueva foto** ahora mismo (usa el clip de adjuntar)."
            else:
                prompt += "Escríbeme el nuevo valor y presiona enviar:"
            await self.send_notification(prompt)
            
    async def _process_admin_edit_text(self, text):
        """Procesa el texto ingresado en el modo edición."""
        p_id = self.user_state.get("editing_product_id")
        field = self.user_state.get("editing_field")
        
        if not p_id or field == "img": 
            return
            
        self.user_state.pop("editing_product_id", None)
        self.user_state.pop("editing_field", None)
        await self._update_web_db(p_id, field, text)
        await self.send_notification(f"✅ ¡Guardado! Actualizando web en segundo plano...", reply_markup=self.get_master_keyboard())
        await self._show_admin_browser()
        
    async def _update_web_db(self, p_id, field, new_value):
        """Actualiza el JSON de forma inmediata. Build y push a GitHub corren en segundo plano."""
        import json
        import os
        import asyncio
        from core.config import Config
        db_path = os.path.join(Config.BASE_DIR, "website_db.json")

        try:
            data = json_load(db_path, default=[])

            if field == "delete":
                data = [p for p in data if p.get("id") != p_id]
            else:
                for p in data:
                    if p.get("id") == p_id:
                        if field == "price": p["offer_price"] = new_value
                        elif field == "disc": p["discount"] = new_value
                        elif field == "title": p["title"] = new_value
                        elif field == "img":
                            p["screenshot"] = new_value
                            p["visual_capture"] = new_value
                            p.pop("image_url", None)
                        elif field == "cat": p["category"] = new_value
                        break

            json_save_atomic(db_path, data, indent=2, ensure_ascii=False)

            async def _bg_push():
                try:
                    from publishers.web_publisher import WebPublisher
                    wp = WebPublisher()
                    await asyncio.to_thread(wp.build)
                    count = await asyncio.to_thread(wp.push_to_github, f"Admin: {field} en {p_id}")
                    print(f"[ADMIN] Subidos {count} archivos a GitHub.")
                    await self.send_notification(f"🌐 **Web actualizada** ({count} archivos subidos).")
                except Exception as e:
                    print(f"[ADMIN] Error en push a GitHub: {e}")
                    await self.send_notification(f"⚠️ Error al subir web a GitHub: {str(e)[:80]}")

            asyncio.create_task(_bg_push())

        except Exception as e:
            print(f"Error actualizando DB web: {e}")
            await self.send_notification(f"❌ Error actualizando base de datos: {e}")

    async def _run_fb_test_command(self):
        """Ejecuta una prueba de publicación en FB para comprobar si el bloqueo se levantó."""
        try:
            from playwright.async_api import async_playwright
            from publishers.facebook_publisher import FacebookPublisher, FacebookLimitedException
            from core.session_manager import SessionManager
            from core.config import Config
            
            if not Config.FB_GROUPS:
                await self.send_notification("⚠️ Error: No hay grupos de FB configurados en el .env")
                return
                
            test_group = Config.FB_GROUPS[0]
            publisher = FacebookPublisher()
            
            details = {
                "title": "Producto de Prueba Sistema",
                "offer_price": "$99",
                "list_price": "$199",
                "discount": "50% OFF",
                "visual_capture": "" 
            }
            url = "https://meli.la/test"
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context(
                    storage_state=SessionManager.get_storage_state(),
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                try:
                    result = await publisher.post_to_group(page, test_group, details, url)
                    if result:
                        await self.send_notification("✅ **¡ÉXITO!**\nLa publicación se realizó correctamente. Parece que el bloqueo ya fue levantado.")
                    else:
                        await self.send_notification("⚠️ No se pudo completar la publicación. Revisa el log local.")
                except FacebookLimitedException as e:
                    await self.send_notification(f"🛑 **BLOQUEO ACTIVO DETECTADO**\nFacebook aún te tiene limitado:\n`{str(e)}`")
                except Exception as e:
                    await self.send_notification(f"❌ Error desconocido en la prueba: {str(e)[:150]}")
                    
                await page.close()
                await context.close()
                await browser.close()
        except Exception as main_e:
            await self.send_notification(f"❌ Error al iniciar Playwright: {main_e}")

    async def _handle_search_request(self, keyword):
        """Busca productos en Mercado Libre y Amazon para un término de búsqueda, los filtra y guarda en borradores."""
        import urllib.parse
        import shutil
        from playwright.async_api import async_playwright
        from core.utils import filter_blacklist_product
        
        encoded_keyword = urllib.parse.quote(keyword)
        ml_search_url = f"https://listado.mercadolibre.com.mx/{encoded_keyword}"
        amz_search_url = f"https://www.amazon.com.mx/s?k={encoded_keyword}"
        
        await self.send_notification(f"🔍 **Buscando \"{keyword}\" en Mercado Libre y Amazon...**")
        
        ml_results = []
        amz_results = []
        
        # 1. Iniciar Playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=[
                "--no-sandbox",
                "--disable-translate",
                "--disable-features=Translate",
                "--lang=es-MX"
            ])
            
            # Contexto limpio para Mercado Libre (para evitar bloqueos)
            ml_context = await browser.new_context(
                viewport={"width": 1536, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            ml_page = await ml_context.new_page()
            
            # Navegar a Mercado Libre
            try:
                print(f"Buscando en ML: {ml_search_url}")
                await ml_page.goto(ml_search_url, wait_until="commit", timeout=45000)
                await asyncio.sleep(3)
                
                # Extraer enlaces
                elements = await ml_page.query_selector_all("a")
                seen_urls = set()
                wave_links = []
                for el in elements:
                    href = await el.get_attribute('href')
                    if href and 'articulo.mercadolibre.com.mx' in href:
                        clean_url = href.split('?')[0].split('#')[0]
                        if clean_url not in seen_urls:
                            wave_links.append(href)
                            seen_urls.add(clean_url)
                
                # Tomar los primeros 3 para procesar
                wave_links = wave_links[:3]
                
                # Scrapear detalles y capturar
                from ml_offers_scraper import capture_product
                for url in wave_links:
                    match = re.search(r'MLM-?(\d+)', url)
                    product_id = f"MLM{match.group(1)}" if match else f"MLM_manual_{random.randint(1000, 9999)}"
                    image_path = os.path.abspath(f"{Config.CAPTURES_DIR}/{product_id}.png")
                    
                    try:
                        details = await capture_product(ml_page, url, image_path)
                        details["id"] = product_id
                        details["screenshot"] = f"captures/{product_id}.png"
                        
                        # Validar filtros (Palabras prohibidas, precio mínimo, descuento mínimo)
                        if filter_blacklist_product(details):
                            if os.path.exists(image_path):
                                try: os.remove(image_path)
                                except: pass
                            continue
                            
                        ml_results.append(details)
                    except Exception as e:
                        print(f"Error procesando {product_id} en búsqueda: {e}")
            except Exception as e:
                await self.send_notification(f"⚠️ Error buscando en Mercado Libre: {e}")
            finally:
                await ml_context.close()
                
            # Contexto con sesión para Amazon (por si acaso y para SiteStripe)
            amz_context = await browser.new_context(
                storage_state=Config.STORAGE_PATH if os.path.exists(Config.STORAGE_PATH) else None,
                viewport={"width": 1366, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            amz_page = await amz_context.new_page()
            
            try:
                from scrapers.amazon_scraper import AmazonScraper
                scraper = AmazonScraper()
                
                print(f"Buscando en Amazon: {amz_search_url}")
                await amz_page.goto(amz_search_url, wait_until="commit", timeout=45000)
                await asyncio.sleep(3)
                
                # Extraer enlaces de Amazon
                elements = await amz_page.query_selector_all("a.a-link-normal[href*='/dp/']")
                seen_urls = set()
                amz_links = []
                for el in elements:
                    href = await el.get_attribute("href")
                    if href and "/dp/" in href:
                        asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
                        if asin_match:
                            asin = asin_match.group(1)
                            clean_url = f"https://www.amazon.com.mx/dp/{asin}"
                            if clean_url not in seen_urls:
                                amz_links.append(clean_url)
                                seen_urls.add(clean_url)
                
                # Tomar los primeros 3
                amz_links = amz_links[:3]
                
                for url in amz_links:
                    asin_match = re.search(r"/dp/([A-Z0-9]{10})", url)
                    product_id = asin_match.group(1) if asin_match else f"AMZ_{random.randint(1000, 9999)}"
                    
                    try:
                        details = await scraper.scrape_amazon_product(amz_page, url)
                        if details.get("title") == "Desconocido (¿Bloqueado?)" or details.get("offer_price") == "N/A":
                            continue
                            
                        # Intentar SiteStripe
                        affiliate_link = await scraper.get_sitestripe_link(amz_page)
                        if affiliate_link == "ENLACE_POR_DEFECTO" or not affiliate_link:
                            affiliate_link = url
                            
                        details["affiliate_url"] = affiliate_link
                        details["id"] = product_id
                        
                        # Validar filtros
                        if filter_blacklist_product(details):
                            temp_capture = details.get("visual_capture")
                            if temp_capture and os.path.exists(temp_capture):
                                try: os.remove(temp_capture)
                                except: pass
                            continue
                            
                        # Mover captura a captures
                        temp_capture = details.get("visual_capture")
                        image_filename = f"captures/{product_id}.png"
                        image_path = os.path.abspath(os.path.join(Config.BASE_DIR, image_filename))
                        if temp_capture and os.path.exists(temp_capture):
                            shutil.move(temp_capture, image_path)
                            details["screenshot"] = image_filename
                        else:
                            details["screenshot"] = ""
                            
                        amz_results.append(details)
                    except Exception as e:
                        print(f"Error procesando {product_id} en búsqueda Amazon: {e}")
            except Exception as e:
                await self.send_notification(f"⚠️ Error buscando en Amazon: {e}")
            finally:
                await amz_context.close()
                await browser.close()
                
        # 3. Guardar resultados consolidados en products_draft.json
        all_results = ml_results + amz_results
        if all_results:
            drafts_existing = self._load_drafts()
            existing_ids = {item["id"] for item in drafts_existing if isinstance(item, dict) and item.get("id")}
            added_count = 0
            for task in all_results:
                if task["id"] not in existing_ids:
                    drafts_existing.append(task)
                    added_count += 1
                    existing_ids.add(task["id"])
            self._save_drafts(drafts_existing)
                
            await self.send_notification(
                f"✅ **Búsqueda finalizada para \"{keyword}\"!**\n"
                f"Se agregaron `{added_count}` nuevos productos a tus borradores (`products_draft.json`).\n\n"
                f"Presiona el botón `📋 Curar Ofertas` para revisarlos chido.",
                reply_markup=self.get_master_keyboard()
            )
        else:
            await self.send_notification(
                f"⚠️ No encontré ofertas que cumplan con tus filtros para \"{keyword}\".",
                reply_markup=self.get_master_keyboard()
            )

    async def perform_search(self, keyword):
        await self._handle_search_request(keyword)

    async def _process_queue_command(self, url, affiliate_override=None, msg_id=None, is_video_ia=False):
        """Procesa un link para agregarlo a la cola sin publicarlo."""
        from playwright.async_api import async_playwright
        from scrapers.ml_scraper import scrape_ml_product_headless
        from scrapers.amazon_scraper import AmazonScraper
        from playwright_stealth import Stealth
        import time
        import hashlib
        import os
        import json
        import re
        from core.config import Config
        
        is_ml = "mercadolibre.com.mx" in url or "meli.la" in url
        details = None
        cap_path = None
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-translate", "--disable-features=Translate", "--disable-blink-features=AutomationControlled"]
                )
                
                context_args = {
                    "viewport": {"width": 1536, "height": 900},
                    "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
                }
                context = await browser.new_context(**context_args)
                stealth = Stealth()
                await stealth.apply_stealth_async(context)
                page = await context.new_page()
                
                if is_ml:
                    details = await scrape_ml_product_headless(page, url)
                else:
                    amazon_scraper = AmazonScraper()
                    details = await amazon_scraper.scrape_amazon_product(page, url)
                
                if not details:
                    await self.send_notification("❌ Error: No se pudieron extraer los detalles del producto.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
                    await context.close()
                    await browser.close()
                    return
                    
                if affiliate_override:
                    details["affiliate_url"] = affiliate_override
                elif is_ml and "meli.la" not in url:
                    # Auto-generar link de afiliado para MercadoLibre
                    try:
                        await self.send_notification("⚙️ Generando link de afiliado meli.la...", msg_id=msg_id)
                        import sys
                        sys.path.insert(0, Config.BASE_DIR)
                        import affiliate_linker
                        mapping = await affiliate_linker.run_linkbuilder([url], headless=True)
                        if mapping and url in mapping:
                            details["affiliate_url"] = mapping[url]
                            print(f"[COLA] Link afiliado generado: {mapping[url]}")
                        else:
                            details["affiliate_url"] = url
                            details["review_status"] = "pending_affiliate"
                            print(f"[COLA] No se pudo generar link afiliado para: {url}")
                    except Exception as aff_err:
                        details["affiliate_url"] = url
                        details["review_status"] = "pending_affiliate"
                        print(f"[COLA] Error en affiliate_linker: {aff_err}")
                else:
                    details["affiliate_url"] = url
                
                # Generar ID
                p_id = details.get("id")
                if not p_id:
                    if is_ml:
                        ml_match = re.search(r'MLM-?(\d+)', url)
                        p_id = f"MLM{ml_match.group(1)}" if ml_match else f"MANUAL_ML_{int(time.time())}"
                    else:
                        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
                        p_id = asin_match.group(1) if asin_match else f"MANUAL_AMZ_{int(time.time())}"
                
                details["id"] = p_id
                details["is_video_ia"] = is_video_ia
                
                # Auto-captura idéntica a orchestrator
                cap_path = os.path.join(Config.CAPTURES_DIR, f"{p_id}.png")
                os.makedirs(Config.CAPTURES_DIR, exist_ok=True)
                
                if os.path.exists(cap_path):
                    try:
                        if os.path.getsize(cap_path) == 14163:
                            os.remove(cap_path)
                    except Exception:
                        pass

                if not os.path.exists(cap_path):
                    if is_ml:
                        target_url = url
                        if details and details.get("real_url"):
                            target_url = details["real_url"]
                        elif "meli.la" in url or "/social/" in url:
                            clean_id = p_id
                            if clean_id.startswith("MLM") and "-" not in clean_id:
                                num_part = clean_id[3:]
                                clean_id = f"MLM-{num_part}"
                            target_url = f"https://articulo.mercadolibre.com.mx/{clean_id}"
                            
                        await page.goto(target_url, wait_until="commit", timeout=45000)
                        await page.wait_for_timeout(4000)
                        
                        # Verificar si es una página de "esta página no existe" o 404
                        page_content = await page.content()
                        if "esta página no existe" in page_content.lower() or "error-state" in page_content.lower():
                            catalog_id = p_id.replace("-", "")
                            target_url = f"https://www.mercadolibre.com.mx/p/{catalog_id}"
                            await page.goto(target_url, wait_until="commit", timeout=45000)
                            await page.wait_for_timeout(4000)

                        await page.evaluate('''() => {
                            const styles = `
                                #stripe, header, .ui-pdp-container, .ui-pdp-official-store-header,
                                .ui-vip-navigation, #redirect_context, .ui-vip-grouped-header,
                                .andes-tooltip, .andes-tooltip__content, .andes-popover,
                                .andes-modal, .onboarding-cp, [class*="onboarding"],
                                .ui-pdp-sut, #nav-header-menu, .nav-header { display: none !important; }
                                .ui-pdp-container--pdp { display: block !important; margin-top: 0 !important; padding-top: 0 !important; }
                                body { background-color: white !important; overflow: hidden !important; }
                            `;
                            const styleSheet = document.createElement("style");
                            styleSheet.innerText = styles;
                            document.head.appendChild(styleSheet);
                        }''')
                        await page.wait_for_timeout(1000)
                        await page.screenshot(path=cap_path, clip={"x": 176, "y": 0, "width": 1184, "height": 572})
                    else:
                        await page.goto(url, wait_until="load", timeout=45000)
                        await page.wait_for_timeout(2000)
                        img_sel = "#imgTagWrapperId, #main-image-container, #landingImage"
                        price_sel = "#corePrice_feature_div, #priceInsideBuyBox_feature_div, #centerCol"
                        captured = False
                        try:
                            img_elem = await page.wait_for_selector(img_sel, timeout=5000)
                            price_elem = await page.wait_for_selector(price_sel, timeout=5000)
                            if img_elem and price_elem:
                                await img_elem.scroll_into_view_if_needed()
                                await page.wait_for_timeout(1000)
                                img_box = await img_elem.bounding_box()
                                price_box = await price_elem.bounding_box()
                                if img_box and price_box:
                                    vp = page.viewport_size
                                    x = min(img_box["x"], price_box["x"]) - 10
                                    y = min(img_box["y"], price_box["y"]) - 10
                                    w = max(img_box["x"]+img_box["width"], price_box["x"]+price_box["width"]) - x + 20
                                    h = max(img_box["y"]+img_box["height"], price_box["y"]+price_box["height"]) - y + 20
                                    w = min(w, vp["width"] - x)
                                    h = min(h, vp["height"] - y)
                                    await page.screenshot(path=cap_path, clip={"x":x,"y":y,"width":w,"height":h})
                                    captured = True
                        except: pass
                        if not captured:
                            ppd = await page.query_selector("#ppd")
                            if ppd:
                                await ppd.screenshot(path=cap_path)
                            else:
                                await page.screenshot(path=cap_path)
                
                details["screenshot"] = cap_path

                # Categorización por IA para el Sistema de Nichos
                # Productos manuales SIEMPRE van a GENERAL, sin categorización automática
                details["niche"] = "[CAT:GENERAL]"
                print(f"[NICHOS] Producto manual asignado a GENERAL: {p_id}")

                # Generar assets de video (script y galería) SOLO para nichos que lo requieren
                if "[CAT:BEBES]" not in details["niche"] and "[CAT:MASCOTAS]" not in details["niche"]:
                    # Generar script de 6 escenas ANTES de encolar
                    try:
                        lines = await self.ai_service.generate_6_lines(details)
                        if not lines:
                            title = details.get("title", "este producto")
                            offer = details.get("offer_price", "")
                            lines = [
                                f"¿Buscas la mejor oferta para {title[:40]}?",
                                "Hoy tiene un descuento increíble que no puedes dejar pasar.",
                                "Acaba de bajar a un súper precio de locura.",
                                "Es perfecto por su excelente calidad y diseño.",
                                "Consigue el tuyo en el enlace de la descripción hoy mismo.",
                                "¡No esperes más antes de que se agote la oferta!"
                            ]
                        details["script"] = lines
                        print(f"[ASSETS] Script de 6 escenas generado para {p_id}: {lines[0][:40]}...")
                    except Exception as script_err:
                        print(f"[ASSETS] Error generando script antes de encolar: {script_err}")

                    # Scrapear gallery_images si faltan
                    if not details.get("gallery_images"):
                        try:
                            from scrapers.ml_scraper import get_gallery_images_headless
                            real_url = details.get("real_url") or url
                            
                            anon_context = await browser.new_context(
                                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                            )
                            try:
                                from playwright_stealth import stealth_async
                                await stealth_async(anon_context)
                            except: pass
                            
                            temp_page = await anon_context.new_page()
                            gallery = await get_gallery_images_headless(temp_page, real_url)
                            await anon_context.close()
                            
                            if gallery:
                                details["gallery_images"] = gallery
                                print(f"[ASSETS] Galería scrapeada: {len(gallery)} imágenes para {p_id}")
                        except Exception as gal_err:
                            print(f"[ASSETS] Error scrapeando galería antes de encolar: {gal_err}")

                await context.close()
                await browser.close()
                
            # Verificar duplicado antes de agregar a la cola
            affiliate_url = details.get("affiliate_url")
            if self._is_in_history(p_id, affiliate_url):
                import time
                temp_id = f"temp_{int(time.time())}"
                self._save_temp_queue_request(temp_id, details)
                
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "Sí, forzar publicación", "callback_data": f"force_dup_{temp_id}"},
                            {"text": "No, descartar", "callback_data": f"discard_dup_{temp_id}"}
                        ]
                    ]
                }
                await self.send_notification(
                    f"⚠️ **Este producto ya fue publicado anteriormente (detectado en historial):**\n"
                    f"`{details.get('title', 'Sin título')}`\n\n"
                    f"¿Deseas volver a agregarlo a la cola y forzar su publicación?",
                    reply_markup=keyboard,
                    msg_id=msg_id
                )
            else:
                import time
                temp_id = f"queue_{int(time.time())}"
                self._save_temp_queue_request(temp_id, details)
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "🌐 General", "callback_data": f"queue_niche_general_{temp_id}"}],
                        [{"text": "👶 Bebés", "callback_data": f"queue_niche_baby_{temp_id}"}],
                        [{"text": "🐶 Mascotas", "callback_data": f"queue_niche_pets_{temp_id}"}],
                        [{"text": "👟 Tenis", "callback_data": f"queue_niche_tenis_{temp_id}"}],
                        [{"text": "👗 Moda", "callback_data": f"queue_niche_moda_{temp_id}"}],
                        [{"text": "❌ Cancelar Encolamiento", "callback_data": f"discard_dup_{temp_id}"}]
                    ]
                }
                
                await self.send_notification(
                    f"✅ **¡Producto Scrapeado y Listo!**\n\n"
                    f"📦 {details.get('title')}\n"
                    f"💰 {details.get('offer_price')}\n"
                    f"🛒 ID: `{p_id}`\n\n"
                    f"🎯 **¿A qué cola de nicho deseas agregarlo?**",
                    reply_markup=keyboard,
                    msg_id=msg_id
                )
            
        except Exception as e:
            await self.send_notification(f"❌ Error interno al encolar el producto: {e}", reply_markup=self.get_master_keyboard(), msg_id=msg_id)

    async def _process_test_command(self, url, affiliate_override=None):
        """Genera y envía la captura de prueba sin encolar ni publicar."""
        await self.send_notification(f"🧪 Iniciando prueba visual para:\n{url}")
        
        try:
            from playwright.async_api import async_playwright
            from scrapers.amazon_scraper import AmazonScraper
            from scrapers.ml_scraper import scrape_ml_product_headless
            from playwright_stealth import Stealth
            import time
            import hashlib
            import os
            import re
            from core.config import Config
            from core.session_manager import SessionManager
            
            is_ml = "mercadolibre.com.mx" in url or "meli.la" in url
            details = None
            cap_path = None
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-translate", "--disable-features=Translate", "--disable-blink-features=AutomationControlled"]
                )
                context_args = {
                    "viewport": {"width": 1536, "height": 900},
                    "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
                }
                context = await browser.new_context(**context_args)
                stealth = Stealth()
                await stealth.apply_stealth_async(context)
                page = await context.new_page()
                
                if is_ml:
                    details = await scrape_ml_product_headless(page, url)
                else:
                    amazon_scraper = AmazonScraper()
                    details = await amazon_scraper.scrape_amazon_product(page, url)
                
                if not details:
                    await self.send_notification("❌ Error: No se pudieron extraer los detalles.")
                    await context.close()
                    await browser.close()
                    return
                
                # Asignar el override si existe
                if affiliate_override:
                    details["affiliate_url"] = affiliate_override
                else:
                    details["affiliate_url"] = url
                    
                p_id = details.get("id")
                if not p_id:
                    if is_ml:
                        ml_match = re.search(r'MLM-?(\d+)', url)
                        p_id = f"MLM{ml_match.group(1)}" if ml_match else f"MANUAL_ML_{int(time.time())}"
                    else:
                        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
                        p_id = asin_match.group(1) if asin_match else f"MANUAL_AMZ_{int(time.time())}"
                
                cap_path = os.path.join(Config.CAPTURES_DIR, f"TEST_{p_id}.png")
                os.makedirs(Config.CAPTURES_DIR, exist_ok=True)
                
                if is_ml:
                    target_url = url
                    if "meli.la" in url or "/social/" in url:
                        clean_id = p_id
                        if clean_id.startswith("MLM") and "-" not in clean_id:
                            num_part = clean_id[3:]
                            clean_id = f"MLM-{num_part}"
                        target_url = f"https://articulo.mercadolibre.com.mx/{clean_id}"
                        
                    await page.goto(target_url, wait_until="commit", timeout=45000)
                    await page.wait_for_timeout(4000)
                    
                    # Verificar si es una página de "esta página no existe" o 404
                    page_content = await page.content()
                    if "esta página no existe" in page_content.lower() or "error-state" in page_content.lower():
                        catalog_id = p_id.replace("-", "")
                        target_url = f"https://www.mercadolibre.com.mx/p/{catalog_id}"
                        await page.goto(target_url, wait_until="commit", timeout=45000)
                        await page.wait_for_timeout(4000)

                    await page.evaluate('''() => {
                        const styles = `
                            #stripe, header, .ui-pdp-container, .ui-pdp-official-store-header,
                            .ui-vip-navigation, #redirect_context, .ui-vip-grouped-header,
                            .andes-tooltip, .andes-tooltip__content, .andes-popover,
                            .andes-modal, .onboarding-cp, [class*="onboarding"],
                            .ui-pdp-sut, #nav-header-menu, .nav-header { display: none !important; }
                            .ui-pdp-container--pdp { display: block !important; margin-top: 0 !important; padding-top: 0 !important; }
                            body { background-color: white !important; overflow: hidden !important; }
                        `;
                        const styleSheet = document.createElement("style");
                        styleSheet.innerText = styles;
                        document.head.appendChild(styleSheet);
                    }''')
                    await page.wait_for_timeout(1000)
                    await page.screenshot(path=cap_path, clip={"x": 176, "y": 0, "width": 1184, "height": 572})
                else:
                    await page.goto(url, wait_until="load", timeout=45000)
                    await page.wait_for_timeout(2000)
                    img_sel = "div#imgTagWrapperId img, div#img-canvas img"
                    price_sel = "div#corePriceDisplay_desktop_feature_div, div#corePrice_desktop"
                    captured = False
                    try:
                        img_elem = await page.wait_for_selector(img_sel, timeout=5000)
                        price_elem = await page.wait_for_selector(price_sel, timeout=5000)
                        if img_elem and price_elem:
                            await img_elem.scroll_into_view_if_needed()
                            await page.wait_for_timeout(1000)
                            img_box = await img_elem.bounding_box()
                            price_box = await price_elem.bounding_box()
                            if img_box and price_box:
                                vp = page.viewport_size
                                x = min(img_box["x"], price_box["x"]) - 10
                                y = min(img_box["y"], price_box["y"]) - 10
                                w = max(img_box["x"]+img_box["width"], price_box["x"]+price_box["width"]) - x + 20
                                h = max(img_box["y"]+img_box["height"], price_box["y"]+price_box["height"]) - y + 20
                                w = min(w, vp["width"] - x)
                                h = min(h, vp["height"] - y)
                                await page.screenshot(path=cap_path, clip={"x":x,"y":y,"width":w,"height":h})
                                captured = True
                    except: pass
                    if not captured:
                        ppd = await page.query_selector("#ppd")
                        if ppd: await ppd.screenshot(path=cap_path)
                        else: await page.screenshot(path=cap_path)
                
                await context.close()
                await browser.close()
                
            if os.path.exists(cap_path):
                await self.send_photo(
                    photo_path=cap_path,
                    caption=f"📸 **PRUEBA VISUAL**\n\nAquí tienes cómo se ve la captura.\n⚠️ *Este producto NO ha sido publicado ni agregado a la cola.*",
                    parse_mode="Markdown"
                )
                await self.send_notification("✅ Prueba visual finalizada.", reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification("❌ Error: No se pudo generar la captura de prueba.", reply_markup=self.get_master_keyboard())
                
        except Exception as e:
            await self.send_notification(f"❌ Error en la prueba visual: {e}", reply_markup=self.get_master_keyboard())

    async def _start_custom_script_flow(self, product_id, msg_id=None):
        self.user_state["awaiting_custom_script_product_id"] = product_id
        self.user_state["awaiting_custom_script"] = True
        
        # Encontrar detalles del producto para mostrar en el prompt
        product = self._find_product_by_id(product_id)
        prod_title = product.get("title", "Sin Título") if product else "Producto Desconocido"
        
        prompt_text = (
            f"🎬 **CREAR VIDEO MANUAL**\n"
            f"Producto: *{prod_title}*\n\n"
            f"Por favor, escribe o pega el guion para este video.\n"
            f"Escribe una escena/frase por línea (máximo 5-6 líneas/escenas preferentemente).\n\n"
            f"💡 **Ejemplo de guion:**\n"
            f"Esta es la mejor oferta del día\n"
            f"Tenis casuales Adidas con 40% de descuento\n"
            f"Son súper cómodos y duraderos\n"
            f"Consigue los tuyos con envío gratis en mi perfil"
        )
        
        # Ofrecer botón de cancelar
        keyboard = {"inline_keyboard": [
            [{"text": "❌ Cancelar", "callback_data": "cancel_custom_script"}]
        ]}
        
        await self.send_notification(prompt_text, reply_markup=keyboard, msg_id=msg_id)

    def _find_product_by_id(self, product_id):
        # 1. Buscar en cola de todos los nichos
        for niche in ["general", "baby", "pets"]:
            products = self._load_queue_data(niche=niche)
            for p in products:
                if p.get("id") == product_id:
                    return p
        # 2. Buscar en borradores (drafts)
        drafts = self._load_drafts()
        for p in drafts:
            if p.get("id") == product_id:
                return p
        # 3. Buscar en historial de publicados
        db_path = os.path.join(Config.BASE_DIR, "website_db.json")
        if os.path.exists(db_path):
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    published = json.load(f)
                    if isinstance(published, list):
                        for p in published:
                            if p.get("id") == product_id:
                                return p
            except Exception as e:
                print(f"Error leyendo website_db en _find_product_by_id: {e}")
        return None

    async def _execute_custom_script_render(self, product, images):
        try:
            from core.voice_generator import process_script
            from core.advanced_video_maker import create_final_video
            import asyncio as _aio

            work_dir = os.path.join(Config.BASE_DIR, "captures", "premium_temp")
            self.safe_makedirs(work_dir)

            script_path = os.path.join(Config.BASE_DIR, "guion.json")
            audio_data = await _aio.to_thread(process_script, script_path, work_dir)
            if not audio_data:
                await self.send_notification(
                    "❌ ERROR: Falló la generación de voz para tu guion.\n"
                    "Verifica tu conexión y que el guion tenga escenas válidas.",
                    reply_markup=self.get_master_keyboard()
                )
                return

            await self.send_notification("🎬 Renderizando video con MoviePy (Efecto zoom y paneo sobre la captura del producto)...")

            out_video = os.path.join(Config.BASE_DIR, "tiktok_videos", f"custom_{product.get('id')}.mp4")
            # Crear directorio de videos si no existe
            self.safe_makedirs(os.path.dirname(out_video))
            
            final = await _aio.to_thread(create_final_video, images, audio_data, out_video)

            if final and os.path.exists(final):
                link = product.get("affiliate_url") or product.get("real_url") or ""
                caption = f"🎬 **¡Video Premium listo!**\n\n📌 **Producto:** {product.get('title')}\n🔗 **Enlace:** {link}"
                await self.send_video(final, caption=caption)
                await self.send_notification("✅ Proceso completado con éxito.", reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification("❌ ERROR: Falló el renderizado del video con MoviePy.", reply_markup=self.get_master_keyboard())
        except Exception as e:
            await self.send_notification(f"❌ ERROR CRÍTICO en renderizado: {e}", reply_markup=self.get_master_keyboard())

    def _recalculate_fb_blocks(self):
        """Recalcula automáticamente el número de bloques para cada nicho basándose en cantidad de grupos activos.
        Optimizado: Invalida caché una sola vez para detectar cambios desde el panel web."""
        import math

        # Mapeo de variables de entorno a claves de user_state
        niche_config = {
            "FB_GROUP_URLS": "fb_split_blocks",
            "FB_GROUPS_BABY_URLS": "fb_bebes_split_blocks",
            "FB_GROUPS_PETS_URLS": "fb_pets_split_blocks",
            "FB_GROUPS_TENIS_URLS": "fb_tenis_split_blocks",
            "FB_GROUPS_MODA_URLS": "fb_moda_split_blocks",
        }

        # Invalidar caché una sola vez para detectar cambios desde el panel web
        Config.__class__._cache.pop("FB_GROUPS", None)
        Config.__class__._cache.pop("FB_GROUPS_BABY", None)
        Config.__class__._cache.pop("FB_GROUPS_PETS", None)
        Config.__class__._cache.pop("FB_GROUPS_TENIS", None)
        Config.__class__._cache.pop("FB_GROUPS_MODA", None)
        Config.__class__._env_loaded = False

        for env_var, block_key in niche_config.items():
            try:
                # Acceder a la propiedad de Config (ahora rellena el caché, no lo invalida)
                if env_var == "FB_GROUP_URLS":
                    active_groups = Config.FB_GROUPS
                elif env_var == "FB_GROUPS_BABY_URLS":
                    active_groups = Config.FB_GROUPS_BABY
                elif env_var == "FB_GROUPS_PETS_URLS":
                    active_groups = Config.FB_GROUPS_PETS
                elif env_var == "FB_GROUPS_TENIS_URLS":
                    active_groups = Config.FB_GROUPS_TENIS
                else:  # FB_GROUPS_MODA_URLS
                    active_groups = Config.FB_GROUPS_MODA

                num_groups = len(active_groups)

                # Criterio: 1 bloque por cada ~5 grupos, mínimo 1
                optimal_blocks = max(1, math.ceil(num_groups / 5))

                # Actualizar user_state
                self.user_state[block_key] = optimal_blocks
                print(f"[BLOCKS] {env_var}: {num_groups} grupos activos → {optimal_blocks} bloques")
            except Exception as e:
                print(f"[BLOCKS] Error recalculando {env_var}: {e}")

        # Guardar cambios
        self._save_user_state()

    async def _add_fb_group_to_env(self, url, env_var="FB_GROUP_URLS"):
        import re as _re
        env_path = os.path.join(Config.BASE_DIR, ".env")
        if not url.startswith("http"):
            await self.send_notification(
                "URL invalida. Debe empezar con http. Intentalo de nuevo.",
                reply_markup=self.get_master_keyboard()
            )
            return
        try:
            with open(env_path, "r", encoding="utf-8") as _f:
                env_content = _f.read()
            match = _re.search(rf"^{env_var}=(.*)$", env_content, _re.MULTILINE)
            if match:
                existing = match.group(1).strip()
                urls = [u.strip() for u in existing.split(",") if u.strip()]
                if url in urls:
                    await self.send_notification(
                        f"Ese grupo ya existe en la lista ({len(urls)} grupos en total).",
                        reply_markup=self.get_master_keyboard()
                    )
                    return
                urls.append(url)
                new_line = f"{env_var}=" + ",".join(urls)
                env_content = _re.sub(rf"^{env_var}=.*$", new_line, env_content, flags=_re.MULTILINE)
            else:
                env_content += f"\n{env_var}={url}"
                urls = [url]
            with open(env_path, "w", encoding="utf-8") as _f:
                _f.write(env_content)

            # Invalidar caché de Config para que recargue el .env
            Config.__class__._cache.clear()
            Config.__class__._env_loaded = False

            # Recalcular bloques automáticamente
            self._recalculate_fb_blocks()

            await self.send_notification(
                f"Grupo anadido. Ahora tienes {len(urls)} grupos de Facebook.",
                reply_markup=self.get_master_keyboard()
            )
        except Exception as e:
            await self.send_notification(
                f"Error al actualizar .env: {e}",
                reply_markup=self.get_master_keyboard()
            )

    async def _search_fb_groups(self, keyword):
        query = keyword.lower()
        groups = Config.FB_GROUPS
        if not groups:
            await self.send_notification("⚠️ No hay grupos configurados.", reply_markup=self.get_master_keyboard())
            return
            
        matches = [i for i, g in enumerate(groups) if query in g.lower()]
        
        if not matches:
            await self.send_notification(f"❌ No se encontraron grupos que coincidan con '{keyword}'.", reply_markup=self.get_master_keyboard())
            return
            
        if len(matches) == 1:
            idx = matches[0]
            # Simulamos el callback para ir directo a ese grupo
            await self.handle_command(f"fb_group_nav_{idx}", callback_query={"message": {}})
            return
            
        # Si hay varios, mostrar botones con los resultados (max 10)
        kb = []
        for idx in matches[:10]:
            g = groups[idx]
            g_name = g.split("/groups/")[-1].strip("/") if "/groups/" in g else g
            kb.append([{"text": g_name[:30], "callback_data": f"fb_group_nav_{idx}"}])
            
        kb.append([{"text": "↩️ Volver al Navegador", "callback_data": "fb_group_browser"}])
        await self.send_notification(f"🔍 Se encontraron {len(matches)} grupos. Selecciona uno:", reply_markup={"inline_keyboard": kb})

    async def _remove_fb_group_from_env(self, url: str):
        """Elimina un grupo de Facebook del .env de forma permanente en cualquier nicho."""
        import re as _re
        env_path = os.path.join(Config.BASE_DIR, ".env")
        try:
            with open(env_path, "r", encoding="utf-8") as _f:
                env_content = _f.read()
            
            for env_var in ["FB_GROUP_URLS", "FB_GROUPS_BABY_URLS", "FB_GROUPS_PETS_URLS"]:
                match = _re.search(rf"^{env_var}=(.*)$", env_content, _re.MULTILINE)
                if match:
                    existing = match.group(1).strip()
                    urls = [u.strip() for u in existing.split(",") if u.strip() and u.strip() != url]
                    new_line = f"{env_var}=" + ",".join(urls)
                    env_content = _re.sub(rf"^{env_var}=.*$", new_line, env_content, flags=_re.MULTILINE)
                    
            with open(env_path, "w", encoding="utf-8") as _f:
                _f.write(env_content)

            # Invalidar caché de Config para que recargue el .env
            Config.__class__._cache.clear()
            Config.__class__._env_loaded = False

            # Recalcular bloques automáticamente
            self._recalculate_fb_blocks()
        except Exception as e:
            print(f"Error removiendo grupo de .env: {e}")


    async def _process_publish_next(self, target_platform):
        try:
            plat_str = f" en {target_platform.upper()}" if isinstance(target_platform, str) and target_platform != "both" else ""
            max_attempts = 5
            attempt = 0
            published_success = False
            tried_ids = set()

            while attempt < max_attempts:
                attempt += 1
                history = set(self._load_history())
                products = self._load_queue()
                target = None
                for p in products:
                    p_id = p.get('id')
                    p_url = p.get('affiliate_url')
                    if not p_id or p_id in tried_ids:
                        continue
                    if (p_id and p_id in history) or (p_url and p_url in history):
                        continue
                    from core.discard_manager import is_already_discarded
                    if is_already_discarded(p_id):
                        continue
                    if not is_product_ready_for_publication(p):
                        continue
                    target = p
                    break

                if not target:
                    await self.send_notification("⚠️ No hay más productos válidos en la lista para publicar.", reply_markup=self.get_master_keyboard())
                    return

                tried_ids.add(target.get('id'))
                p_title = target.get('title', target.get('id', 'Producto'))[:45]
                await self.send_notification(f"🚀 **Publicando ahora{plat_str}:** `{target.get('id')}`\n📦 {p_title}")
                img_path = target.get('visual_capture') or target.get('screenshot', '')
                if img_path and not os.path.exists(img_path):
                    from core.config import Config
                    img_path = os.path.join(Config.BASE_DIR, "captures", os.path.basename(img_path))

                success = await self.orchestrator.run_publication(
                    target['affiliate_url'],
                    target_platform=target_platform,
                    manual_image=img_path,
                    pre_scraped_details=target
                )

                if success:
                    published_success = True
                    await self.send_notification(f"✅ **¡Publicación completada exitosamente{plat_str}!**\n📦 `{target.get('id')}`", reply_markup=self.get_master_keyboard())
                    break
                else:
                    await self.send_notification(f"⚠️ Producto `{target.get('id')}` descartado por validación de oferta/descuento. Probando siguiente producto de la cola...")
                    await asyncio.sleep(2)

            if not published_success and attempt >= max_attempts:
                await self.send_notification("⚠️ Se evaluaron varios productos de la cola y ninguno cumplió con el descuento mínimo configurado.", reply_markup=self.get_master_keyboard())

        except Exception as e:
            await self.send_notification(f"❌ Error en publicación: {e}", reply_markup=self.get_master_keyboard())

    async def _process_manual_publication(self, url: str, target_platform, affiliate_override=None):
        """Procesa URL manual: la agrega a la cola (no publica directo).

        Flujo:
        1. Scrape del producto
        2. Si es duplicado: ofrece "Forzar"
        3. Si no: ofrece elegir nicho
        4. Agrega a la cola (siguiente en publicarse)
        """
        # Usar la misma función que el modo cola
        await self._process_queue_command(url, affiliate_override=affiliate_override)


    async def _run_meli_test_command(self):
        try:
            import affiliate_linker
            test_urls = ["https://articulo.mercadolibre.com.mx/MLM-12345678"]
            mapping = await affiliate_linker.run_linkbuilder(test_urls, headless=True)

            if mapping and mapping.get(test_urls[0]):
                await self.send_notification(f"✅ ¡Éxito! Sesión activa en Linux. Link generado:\n{mapping[test_urls[0]]}")
            else:
                await self.send_notification("❌ Falló la generación. Revisa el screenshot a continuación para ver si ML pidió Login o Captcha.")

            import glob
            import os
            from core.config import Config
            screenshots = glob.glob(os.path.join(Config.BASE_DIR, "logs", "lb_result_*.png"))
            if screenshots:
                latest = max(screenshots, key=os.path.getctime)
                await self.send_photo(latest, caption="📸 Captura del LinkBuilder de ML")
        except Exception as e:
            await self.send_notification(f"❌ Error crítico en el test: {e}")

    async def _generate_video_ia_direct(self, url: str, msg_id: int = None):
        """Genera directamente un video IA (3 imágenes Flow + producto + audio) y lo envía a Telegram."""
        from playwright.async_api import async_playwright
        from scrapers.ml_scraper import scrape_ml_product_headless
        from scrapers.amazon_scraper import AmazonScraper
        from playwright_stealth import Stealth
        import time
        import os
        import json
        import re
        from core.config import Config
        from tiktok_generator import create_tiktok_video
        
        is_ml = "mercadolibre.com.mx" in url or "meli.la" in url
        details = None
        
        try:
            await self.send_notification(f"⏳ **Iniciando generación de Video IA...**\n`{url}`", msg_id=msg_id)
            
            # 1. Scrape del producto
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-translate", "--disable-features=Translate", "--disable-blink-features=AutomationControlled"]
                )
                context = await browser.new_context(
                    viewport={"width": 1536, "height": 900},
                    user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
                )
                stealth = Stealth()
                await stealth.apply_stealth_async(context)
                page = await context.new_page()
                
                if is_ml:
                    details = await scrape_ml_product_headless(page, url)
                else:
                    amazon_scraper = AmazonScraper()
                    details = await amazon_scraper.scrape_amazon_product(page, url)
                
                if not details:
                    await self.send_notification("❌ Error: No se pudieron extraer los detalles del producto.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
                    await context.close()
                    await browser.close()
                    return
                
                # Obtener ID
                p_id = details.get("id")
                if not p_id:
                    if is_ml:
                        ml_match = re.search(r'MLM-?(\d+)', url)
                        p_id = f"MLM{ml_match.group(1)}" if ml_match else f"MANUAL_ML_{int(time.time())}"
                    else:
                        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
                        p_id = asin_match.group(1) if asin_match else f"MANUAL_AMZ_{int(time.time())}"
                    details["id"] = p_id
                
                # Auto-generar link afiliado si es ML
                if is_ml and "meli.la" not in url:
                    try:
                        import affiliate_linker
                        mapping = await affiliate_linker.run_linkbuilder([url], headless=True)
                        if mapping and url in mapping:
                            details["affiliate_url"] = mapping[url]
                        else:
                            details["affiliate_url"] = url
                    except Exception as aff_err:
                        details["affiliate_url"] = url
                else:
                    details["affiliate_url"] = details.get("affiliate_url") or url
                
                # Screenshot del producto
                cap_path = os.path.join(Config.CAPTURES_DIR, f"{p_id}.png")
                os.makedirs(Config.CAPTURES_DIR, exist_ok=True)
                
                if is_ml:
                    target_url = url
                    if "meli.la" in url or "/social/" in url:
                        clean_id = p_id
                        if clean_id.startswith("MLM") and "-" not in clean_id:
                            clean_id = f"MLM-{clean_id[3:]}"
                        target_url = f"https://articulo.mercadolibre.com.mx/{clean_id}"
                        
                    await page.goto(target_url, wait_until="commit", timeout=45000)
                    await page.wait_for_timeout(4000)
                    await page.evaluate('''() => {
                        const styles = `
                            .andes-modal, .onboarding-cp, [class*="onboarding"],
                            .ui-pdp-sut, #nav-header-menu, .nav-header { display: none !important; }
                            .ui-pdp-container--pdp { display: block !important; margin-top: 0 !important; padding-top: 0 !important; }
                            body { background-color: white !important; overflow: hidden !important; }
                        `;
                        const styleSheet = document.createElement("style");
                        styleSheet.innerText = styles;
                        document.head.appendChild(styleSheet);
                    }''')
                    await page.wait_for_timeout(1000)
                    await page.screenshot(path=cap_path, clip={"x": 176, "y": 0, "width": 1184, "height": 572})
                else:
                    await page.goto(url, wait_until="load", timeout=45000)
                    await page.wait_for_timeout(2000)
                    img_sel = "#imgTagWrapperId, #main-image-container, #landingImage"
                    price_sel = "#corePrice_feature_div, #priceInsideBuyBox_feature_div, #centerCol"
                    captured = False
                    try:
                        img_elem = await page.wait_for_selector(img_sel, timeout=5000)
                        price_elem = await page.wait_for_selector(price_sel, timeout=5000)
                        if img_elem and price_elem:
                            await img_elem.scroll_into_view_if_needed()
                            await page.wait_for_timeout(1000)
                            img_box = await img_elem.bounding_box()
                            price_box = await price_elem.bounding_box()
                            if img_box and price_box:
                                vp = page.viewport_size
                                x = min(img_box["x"], price_box["x"]) - 10
                                y = min(img_box["y"], price_box["y"]) - 10
                                w = max(img_box["x"]+img_box["width"], price_box["x"]+price_box["width"]) - x + 20
                                h = max(img_box["y"]+img_box["height"], price_box["y"]+price_box["height"]) - y + 20
                                w = min(w, vp["width"] - x)
                                h = min(h, vp["height"] - y)
                                await page.screenshot(path=cap_path, clip={"x":x,"y":y,"width":w,"height":h})
                                captured = True
                    except: pass
                    if not captured:
                        ppd = await page.query_selector("#ppd")
                        if ppd:
                            await ppd.screenshot(path=cap_path)
                        else:
                            await page.screenshot(path=cap_path)
                
                details["screenshot"] = cap_path
                await context.close()
                await browser.close()
            
            # 2. Generar Guion y Prompts con Gemini
            await self.send_notification(
                f"🧠 **Generando guion educativo y 3 prompts visuales con Gemini...**\n"
                f"📦 `{details.get('title', '')[:50]}`",
                msg_id=msg_id
            )
            
            title = details.get("title", "este producto")
            category = details.get("category", "")
            
            guion_lines = []
            image_prompts = []
            
            try:
                from core.config import Config
                from core.ai_service import generate_with_gemini_rotation
                if Config.get_gemini_keys():
                    guion_prompt = (
                        f"Eres experto en marketing de contenido viral y creación de TikToks/Shorts educativos en México.\n"
                        f"Genera un guion de 6 líneas dando un CONSEJO o TRUCO ÚTIL sobre el nicho del producto, terminando con la recomendación del producto.\n"
                        f"También genera 3 PROMPTS distintos en inglés para una IA de imágenes.\n\n"
                        f"Datos:\n"
                        f"- Producto: {title}\n"
                        f"{'- Categoría: ' + category if category else ''}\n\n"
                        f"ESTRUCTURA EXACTA DE 9 LÍNEAS:\n"
                        f"L1-2 (GANCHO IMPACTANTE): Un dato curioso, error común o revelación que capture la atención de inmediato.\n"
                        f"L3-4 (DESARROLLO EDUCATIVO): La explicación práctica de por qué ocurre esto y cómo resolverlo.\n"
                        f"L5-6 (RECOMENDACION NATURAL): Presenta el producto como la solución ideal y menciona el link en el perfil/descripción.\n"
                        f"L7 (IMAGE PROMPT 1): Cinematic photorealistic prompt in English for scene 1 (e.g. 'Hyper-realistic lifestyle photo of... 8k, warm cinematic lighting').\n"
                        f"L8 (IMAGE PROMPT 2): Cinematic photorealistic prompt in English for scene 2.\n"
                        f"L9 (IMAGE PROMPT 3): Cinematic photorealistic prompt in English for scene 3.\n\n"
                        f"REGLAS OBLIGATORIAS:\n"
                        f"- ⛔ ESTRICTAMENTE PROHIBIDO empezar con '¿Buscas...', '¿Estás buscando...', '¿Quieres...', o fórmulas trilladas.\n"
                        f"- ✅ USA GANCHOS DINÁMICOS: 'El 90% comete este error...', 'Si tienes este problema...', 'Pocos saben este truco...', 'Esto cambió por completo cómo...', 'Cuidado si haces esto...'\n"
                        f"- TONO: Creador casual, cercano y auténtico. NADA de '¡Cómpralo ya!'.\n"
                        f"- SALIDA: EXACTAMENTE 9 líneas de texto plano. Sin prefijos, sin numeración, sin comillas ni asteriscos.\n"
                    )
                    resp = generate_with_gemini_rotation(guion_prompt)
                    if resp and resp.text:
                        lines = [l.strip() for l in resp.text.strip().split("\n") if l.strip()]
                        # Limpiar si la IA puso "L1:", "1.", etc.
                        cleaned_lines = []
                        for l in lines:
                            cleaned = re.sub(r'^(?:L\d+[\s:\-.]*|\d+[\s:\-.]*|Escena\s*\d+[\s:\-.]*|\*+)\s*', '', l, flags=re.IGNORECASE).strip()
                            if cleaned:
                                cleaned_lines.append(cleaned)
                        if len(cleaned_lines) >= 6:
                            guion_lines = cleaned_lines[:6]
                        if len(cleaned_lines) >= 9:
                            image_prompts = [cleaned_lines[6], cleaned_lines[7], cleaned_lines[8]]
            except Exception as gem_err:
                print(f"[VIDEO_IA] Error en Gemini: {gem_err}")
                
            if not guion_lines:
                import random
                hooks = [
                    f"El 90% de las personas comete este error al cuidar {title[:25]}.",
                    f"Si tienes esto en casa, necesitas conocer este secreto hoy mismo.",
                    f"Pocos saben este truco que te ahorrará muchísimo tiempo y dinero.",
                    f"Esto cambió por completo la forma en que aprovechamos este producto.",
                    f"Cuidado con este detalle que casi nadie nota a simple vista."
                ]
                selected_hook = random.choice(hooks)
                guion_lines = [
                    selected_hook,
                    "Muchos suelen descuidar la calidad del material y terminan gastando el doble.",
                    "La clave está en elegir algo duradero, práctico y bien diseñado.",
                    f"Esta opción se ha vuelto viral por su increíble rendimiento y comodidad.",
                    "Además hoy tiene un súper descuento por tiempo limitado.",
                    "Te dejé el enlace directo en la descripción para que no te lo pierdas."
                ]
            if not image_prompts:
                image_prompts = [
                    f"Hyper-realistic lifestyle photo related to {title[:40]}, warm natural lighting, 8k resolution, cinematic aesthetic",
                    f"Cinematic close-up macro shot showing details of modern {title[:40]}, photorealistic",
                    f"Happy person enjoying using aesthetic {title[:40]} in a beautiful modern home, photorealistic"
                ]
                
            details["guion_lines"] = guion_lines
            details["image_prompts"] = image_prompts
            
            # Guardar también en guion.json por compatibilidad
            guion_dict = {f"escena{i+1}": line for i, line in enumerate(guion_lines)}
            guion_dict["image_prompt_1"] = image_prompts[0]
            guion_dict["image_prompt_2"] = image_prompts[1]
            guion_dict["image_prompt_3"] = image_prompts[2]
            guion_path = os.path.join(Config.BASE_DIR, "guion.json")
            with open(guion_path, "w", encoding="utf-8") as f:
                json.dump(guion_dict, f, indent=2, ensure_ascii=False)
            
            # 3. Generar el Video (Google Flow + Audios + Montaje)
            await self.send_notification(
                f"🎨 **Generando 3 imágenes IA en Google Flow y renderizando video...**\n"
                f"⏱ Esto tomará entre 1 a 2 minutos. Por favor espera...",
                msg_id=msg_id
            )
            
            video_path = await asyncio.to_thread(create_tiktok_video, details)
            
            if video_path and os.path.exists(video_path):
                await self.send_notification(f"📤 **¡Video IA renderizado con éxito! Subiendo a Telegram...**", msg_id=msg_id)
                caption = (
                    f"🎬 **Video IA Generado:**\n"
                    f"📦 `{details.get('title', '')}`\n"
                    f"💰 {details.get('offer_price', details.get('price', ''))}\n"
                    f"🔗 [Link de Afiliado]({details.get('affiliate_url', url)})"
                )
                await self.send_video(video_path, caption=caption)
                await self.send_notification("✅ **Proceso completado.** ¿Deseas hacer otro?", reply_markup=self.get_master_keyboard())
            else:
                await self.send_notification("❌ Error: No se pudo generar el archivo de video final.", reply_markup=self.get_master_keyboard(), msg_id=msg_id)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            await self.send_notification(f"❌ Error crítico en Modo Video IA: {e}", reply_markup=self.get_master_keyboard(), msg_id=msg_id)

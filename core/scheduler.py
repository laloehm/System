import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from core.config import Config
from core.storage import json_load, json_save_atomic
from core.utils import is_product_ready_for_publication
from core.cleanup import run_cleanup

SCHEDULER_CONFIG = os.path.join(Config.BASE_DIR, "scheduler_config.json")
DEFAULT_SLOTS = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]


class Scheduler:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.last_cleanup_date = None
        self.daily_stats = {"published": 0, "empty_slots": 0}

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPERS: Métodos de utilidad para run_worker()
    # ═══════════════════════════════════════════════════════════════════════════

    def _is_product_valid_for_slot(self, product: dict) -> tuple:
        """Valida un producto antes de intentar publicar. Retorna (is_valid, error_msg)"""
        has_error = False
        for field in ["title", "offer_price", "list_price", "discount"]:
            val = str(product.get(field, "")).strip().lower()
            if any(bad_word in val for bad_word in ["n/a", "null", "desconocido", "ver precio", "oferta especial", "revisar", "ia falló"]):
                has_error = True
                break
        if not str(product.get("title", "")).strip() or not str(product.get("offer_price", "")).strip():
            has_error = True

        return (not has_error, "Contiene valores N/A" if has_error else "")

    async def _notify_validation_alert(self, niche_name: str, product: dict):
        """Notifica a Telegram sobre un error de validación en el producto."""
        if not self.orchestrator.telegram_bot:
            return
        msg = f"⚠️ *ALERTA DE EXTRACCIÓN ({niche_name.upper()})*\nEl producto `{product.get('title', 'Sin título')[:50]}` contiene valores 'N/A'.\n🛡️ Ha sido saltado."
        asyncio.create_task(self.orchestrator.telegram_bot.send_notification(msg))

    async def _notify_permanent_discard(self, niche_name: str, product: dict, reason: str):
        """Notifica cuando un producto es descartado permanentemente."""
        if not self.orchestrator.telegram_bot:
            return
        msg = f"🚫 *PRODUCTO DESCARTADO ({niche_name.upper()})*\nEl producto `{product.get('title', 'Sin título')[:50]}` ({reason}).\n🛡️ Ha sido saltado permanentemente."
        asyncio.create_task(self.orchestrator.telegram_bot.send_notification(msg))

    async def _send_slot_summary(self, next_slot: int, slot_results: dict):
        """Envía el resumen de resultados del slot a Telegram."""
        if not self.orchestrator.telegram_bot:
            return

        summary = f"📊 **Resumen de Publicación ({next_slot:02d}:00)**\n\n"
        for niche, res in slot_results.items():
            summary += f"🔹 {niche.upper()}: {res}\n"
        if not slot_results:
            summary += "No hubo colas activas en este slot."

        keyboard = self.orchestrator.telegram_bot.get_master_keyboard()
        await self.orchestrator.telegram_bot.send_notification(summary, reply_markup=keyboard)

    def load_slots(self):
        default_config = {
            "general": list(DEFAULT_SLOTS),
            "custom": {
                "telegram": [], "facebook": [], "fb_page": [], "twitter": [],
                "pinterest": [], "tiktok": [], "youtube": [], "web": []
            },
            "use_custom": {
                "telegram": False, "facebook": False, "fb_page": False, "twitter": False,
                "pinterest": False, "tiktok": False, "youtube": False, "web": False
            }
        }
        try:
            if os.path.exists(SCHEDULER_CONFIG):
                data = json_load(SCHEDULER_CONFIG, default={})

                # Manejar compatibilidad con versión anterior
                if "slots" in data:
                    default_config["general"] = sorted([int(s) for s in data.get("slots", []) if 0 <= int(s) <= 23])
                    return default_config

                if "general" in data:
                    # Fusionar con defaults para asegurar que custom/use_custom siempre existan
                    if "custom" not in data:
                        data["custom"] = default_config["custom"]
                    else:
                        for net in default_config["custom"]:
                            if net not in data["custom"]:
                                data["custom"][net] = []
                    if "use_custom" not in data:
                        data["use_custom"] = default_config["use_custom"]
                    else:
                        for net in default_config["use_custom"]:
                            if net not in data["use_custom"]:
                                data["use_custom"][net] = False
                    return data
        except Exception:
            pass
        return default_config

    @staticmethod
    def save_slots(config_dict):
        try:
            json_save_atomic(SCHEDULER_CONFIG, config_dict, indent=2)
        except Exception as e:
            print(f"[SCHEDULER] Error guardando config horaria: {e}")

    @staticmethod
    def load_cursors():
        path = os.path.join(Config.BASE_DIR, "cursors.json")
        default_cursors = {
            "telegram": 0, "facebook": 0, "fb_page": 0, "twitter": 0,
            "pinterest": 0, "tiktok": 0, "youtube": 0, "web": 0
        }
        data = json_load(path, default={})
        if isinstance(data, dict):
            for k, v in data.items():
                if k in default_cursors and isinstance(v, int):
                    default_cursors[k] = v
        return default_cursors

    @staticmethod
    def save_cursors(cursors):
        path = os.path.join(Config.BASE_DIR, "cursors.json")
        try:
            json_save_atomic(path, cursors, indent=2)
        except Exception:
            pass

    async def run_worker(self):
        """Vigilante de slots diarios configurables (default: cada hora de 8 a 22)"""
        print("🕒 Iniciando Vigilante de Tiempos...")

        while True:
            try:
                now = datetime.now()
                current_hour = now.hour
                current_date = now.date()
                slots = self.load_slots()

                # REFILL AUTOMÁTICO DE COLAS (fondo, sin bloquear)
                from core.apify_refiller import check_and_refill
                asyncio.create_task(check_and_refill(self.orchestrator))

                # MANTENIMIENTO DIARIO (3:00 AM)
                if current_hour == 3 and self.last_cleanup_date != current_date:
                    print("🧹 Iniciando rutina diaria de mantenimiento...")
                    try:
                        await asyncio.to_thread(run_cleanup, 7)
                        self.last_cleanup_date = current_date
                        if self.orchestrator.telegram_bot:
                            await self.orchestrator.telegram_bot.send_notification(
                                "✅ *Mantenimiento:* Archivos de más de 7 días eliminados."
                            )
                    except Exception as clean_err:
                        print(f"⚠️ Error en limpieza: {clean_err}")

                # Siguiente slot
                config = self.load_slots()
                all_hours = set(config.get("general", []))
                for net, hours in config.get("custom", {}).items():
                    if config.get("use_custom", {}).get(net, False):
                        all_hours.update(hours)
                
                sorted_all_hours = sorted(list(all_hours))
                if not sorted_all_hours:
                    sorted_all_hours = [12] # Fallback seguro
                    
                next_slot = next((s for s in sorted_all_hours if s > current_hour), sorted_all_hours[0])
                target_time = now.replace(hour=next_slot, minute=0, second=0, microsecond=0)
                if target_time <= now:
                    target_time += timedelta(days=1)

                print(f"⏳ Próximo slot programado a las {next_slot:02d}:00. Esperando {(target_time - now).total_seconds():.1f} segundos.")

                # Esperar al slot base
                remaining = (target_time - datetime.now()).total_seconds()
                if remaining > 0:
                    await asyncio.sleep(remaining)

                # JITTER ANTI-BLOQUEO: Variación aleatoria (30s a 180s) para simular publicación orgánica humana
                jitter_seconds = random.randint(30, 180)
                print(f"🎲 [ANTI-BLOQUEO] Aplicando jitter aleatorio de {jitter_seconds}s para slot {next_slot:02d}:00 (simulación humana)...")
                await asyncio.sleep(jitter_seconds)

                # --- EJECUCIÓN DEL SLOT ---
                print(f"🚀 [SLOT {next_slot:02d}:00] Iniciando publicación programada...")
                
                config = self.load_slots()
                active_networks = self.orchestrator.telegram_bot.user_state.get("active_networks", {}) if self.orchestrator.telegram_bot else {}
                
                # Identificar TODAS las redes que deberían correr a esta hora
                networks_scheduled = []
                all_known_nets = ["facebook", "facebook_bebes", "facebook_pets", "facebook_tenis", "facebook_moda", "fb_page", "telegram", "twitter", "pinterest", "tiktok", "youtube", "web"]
                for net in all_known_nets:
                    is_active = active_networks.get(net, True)
                    if not is_active: continue
                    use_custom = config.get("use_custom", {}).get(net, False)
                    sched = config.get("custom", {}).get(net, []) if use_custom else config.get("general", [])
                    if next_slot in sched:
                        networks_scheduled.append(net)

                if not networks_scheduled:
                    print(f"💤 Ninguna red activa está programada para las {next_slot:02d}:00.")
                    await asyncio.sleep(70)
                    continue

                published_in_slot = False
                slot_results = {}
                from core.history_manager import load_recent_history
                history = load_recent_history()

                # Recalcular bloques automáticamente cada slot (detecta cambios en grupos pausados/agregados)
                if self.orchestrator.telegram_bot:
                    self.orchestrator.telegram_bot._recalculate_fb_blocks()

                queues_to_check = [
                    ("general", Config.JSON_QUEUE_FILE, networks_scheduled),
                    ("baby", getattr(Config, "JSON_QUEUE_BABY_FILE", os.path.join(Config.BASE_DIR, "products_list_baby.json")), [n for n in ["facebook_bebes", "telegram"] if n in networks_scheduled] if active_networks.get("facebook_bebes", False) else []),
                    ("pets", getattr(Config, "JSON_QUEUE_PETS_FILE", os.path.join(Config.BASE_DIR, "products_list_pets.json")), [n for n in ["facebook_pets", "telegram"] if n in networks_scheduled] if active_networks.get("facebook_pets", False) else []),
                    ("tenis", getattr(Config, "JSON_QUEUE_TENIS_FILE", os.path.join(Config.BASE_DIR, "queue_tenis.json")), [n for n in ["facebook_tenis", "telegram"] if n in networks_scheduled] if active_networks.get("facebook_tenis", False) else []),
                    ("moda", getattr(Config, "JSON_QUEUE_MODA_FILE", os.path.join(Config.BASE_DIR, "queue_moda.json")), [n for n in ["facebook_moda", "telegram"] if n in networks_scheduled] if active_networks.get("facebook_moda", False) else [])
                ]

                # Bucle independiente por cada cola
                for niche_name, q_file, target_nets in queues_to_check:
                    if not target_nets:
                        continue
                    
                    products = json_load(q_file, default=[])
                    if not isinstance(products, list) or not products:
                        if niche_name not in slot_results:
                            slot_results[niche_name] = "📭 Cola vacía"
                        continue
                        
                    # Purgar productos que ya fueron descartados previamente o ya publicados en el historial
                    from core.discard_manager import is_already_discarded
                    cleaned_products = [
                        p for p in products
                        if p.get("force_publish") or (
                            not (p.get('id') and is_already_discarded(p.get('id')))
                            and not (p.get('id') and str(p.get('id')) in history)
                            and not (p.get('affiliate_url') and p.get('affiliate_url') in history)
                            and not (p.get('url') and p.get('url') in history)
                        )
                    ]
                    if len(cleaned_products) < len(products):
                        print(f"[SCHEDULER] Purgados {len(products) - len(cleaned_products)} productos (descartados/ya publicados) de la cola {niche_name.upper()}")
                        products = cleaned_products
                        try:
                            json_save_atomic(q_file, products, indent=2, ensure_ascii=False)
                        except Exception as e:
                            print(f"[SCHEDULER] Error guardando cola purgada: {e}")

                    found_product = None
                    for p in products:
                        p_id = p.get('id')
                        p_url = p.get('affiliate_url')

                        if not p.get("force_publish") and ((p_id and p_id in history) or (p_url and p_url in history)):
                            continue

                        # Usar validación consolidada (no doble chequeo)
                        is_valid, err_msg = self._is_product_valid_for_slot(p)
                        is_ready = is_product_ready_for_publication(p)

                        if not is_valid:
                            print(f"[SCHEDULER] Producto {p.get('id')} FALLA validación slot: {err_msg}")
                        if not is_ready:
                            print(f"[SCHEDULER] Producto {p.get('id')} NO LISTO: affiliate_status={p.get('affiliate_status')}, url={p.get('affiliate_url')}")

                        if is_valid and is_ready:
                            found_product = p
                            print(f"[SCHEDULER] ✅ Producto {p.get('id')} VÁLIDO y LISTO para publicar")

                            # ANTES DE PUBLICAR: recargar cola para verificar que no fue borrado
                            fresh_products = json_load(q_file, default=[])
                            product_still_exists = any(
                                (fp.get('id') and fp.get('id') == p_id) or
                                (fp.get('affiliate_url') and fp.get('affiliate_url') == p_url)
                                for fp in fresh_products
                            )
                            if not product_still_exists:
                                print(f"⚠️ Producto {p_id} fue borrado de la cola, saltando...")
                                found_product = None
                                continue

                            img_path = found_product.get("screenshot", "")
                            if img_path and not os.path.isabs(img_path):
                                img_path = os.path.join(Config.BASE_DIR, img_path)

                            if not found_product.get("niche"):
                                found_product["niche"] = niche_name

                            if self.orchestrator._publish_lock.locked():
                                import time
                                lock_time = getattr(self.orchestrator, '_lock_acquired_time', None)
                                if lock_time and (time.time() - lock_time) > 600:
                                    print(f"[SCHEDULER] ⚠️ Detectado lock huérfano en orquestador (>10 min). Limpiando lock...")
                                    self.orchestrator._publish_lock = asyncio.Lock()
                                    self.orchestrator._lock_acquired_time = None
                                    if self.orchestrator.telegram_bot:
                                        asyncio.create_task(self.orchestrator.telegram_bot.send_notification(
                                            "🛡️ *Auto-Recuperación Scheduler:* Lock atascado por más de 10 min liberado automáticamente."
                                        ))
                                else:
                                    print(f"[SCHEDULER] ⏳ Orquestador ocupado con otra publicación. Posponiendo slot de {niche_name.upper()}...")
                                    break

                            print(f"🚀 Intentando publicar de cola '{niche_name.upper()}' en: {', '.join(n.upper() for n in target_nets)}")
                            print(f"   Producto: {found_product.get('id')} | {found_product.get('title', '')[:60]}")
                            print(f"   URL: {found_product.get('affiliate_url', '')}")
                            print(f"   Imagen: {img_path if img_path else 'NINGUNA'}")
                            error_reason = None
                            try:
                                success = await self.orchestrator.run_publication(
                                    found_product["affiliate_url"],
                                    target_platform=target_nets,
                                    manual_image=img_path,
                                    pre_scraped_details=found_product
                                )
                            except Exception as e:
                                error_reason = str(e)[:200]
                                print(f"❌ Error crítico publicando {found_product.get('id')}: {e}")
                                success = False
                                if self.orchestrator.telegram_bot:
                                    asyncio.create_task(self.orchestrator.telegram_bot.send_notification(
                                        f"⚠️ *ERROR CRÍTICO EN {niche_name.upper()}*\nProducto: `{found_product.get('title', 'Sin título')[:50]}`\nError: `{str(e)[:150]}`"
                                    ))

                            # Si no hay error_reason pero falló, marca como error desconocido
                            if not success and not error_reason:
                                error_reason = "Error desconocido en run_publication() - retornó False"

                            print(f"[SCHEDULER] run_publication() retornó: {success} | Error: {error_reason if error_reason else 'Ninguno'}")
                            if success:
                                published_in_slot = True
                                slot_results[niche_name] = f"✅ Publicado"
                                self.daily_stats["published"] += 1
                                if found_product.get("id"): history.add(found_product["id"])
                                if found_product.get("affiliate_url"): history.add(found_product["affiliate_url"])

                                found_product.pop("failed_attempts", None)
                                found_product.pop("last_error", None)
                                if found_product.pop("force_publish", None):
                                    try:
                                        json_save_atomic(q_file, products, indent=2, ensure_ascii=False)
                                    except Exception as e:
                                        print(f"Error removiendo force_publish de la cola {niche_name}: {e}")

                                print(f"✅ Éxito en la cola {niche_name.upper()}.")
                                await asyncio.sleep(45)
                                break
                            else:
                                from core.discard_manager import is_already_discarded
                                p_id_chk = found_product.get('id')
                                if p_id_chk and is_already_discarded(p_id_chk):
                                    print(f"[SCHEDULER] Producto {p_id_chk} ya fue descartado por el orquestador. Omitiendo incremento de intentos.")
                                    slot_results[niche_name] = "⚠️ Producto descartado por reglas"
                                    continue

                                attempts = found_product.get("failed_attempts", 0) + 1
                                found_product["failed_attempts"] = attempts
                                if error_reason:
                                    found_product["last_error"] = error_reason

                                print(f"[SCHEDULER] ❌ FALLÓ PUBLICAR {found_product.get('id')}: Intento {attempts}/3. Error: {error_reason}")

                                if attempts >= 3:
                                    print(f"[SCHEDULER] 🚫 DESCARTANDO {found_product.get('id')} después de 3 intentos fallidos")
                                    from core.discard_manager import register_discard

                                    found_product["force_publish"] = False
                                    if found_product.get("id"): history.add(found_product.get("id"))
                                    if found_product.get("affiliate_url"): history.add(found_product.get("affiliate_url"))

                                    # Registrar con motivo real
                                    discard_reason = f"falló_3_veces: {error_reason}" if error_reason else "falló_3_veces_sin_error_capturado"
                                    register_discard(found_product.get("id", "desconocido"), discard_reason, found_product)

                                    print(f"❌ Producto {found_product.get('id', 'Sin ID')} falló 3 veces. Descartado: {discard_reason}")
                                    slot_results[niche_name] = "❌ Descartado permanente"
                                    await self._notify_permanent_discard(niche_name, found_product, discard_reason)
                                else:
                                    print(f"❌ Falló la publicación de {found_product.get('id', 'Sin ID')} (intento {attempts}/3). Error: {error_reason or 'desconocido'}. Intentando el siguiente...")
                                    slot_results[niche_name] = f"❌ Falló publicación ({attempts}/3)"

                                try:
                                    json_save_atomic(q_file, products, indent=2, ensure_ascii=False)
                                except:
                                    pass

                                found_product = None
                                continue
                        else:
                            url = str(p.get("affiliate_url", p.get("url", ""))).lower()
                            pid = str(p.get("id", "")).upper()
                            is_ml = pid.startswith("MLM") or "mercadolibre" in url or "meli.la" in url
                            if is_ml and "meli.la" not in url:
                                attempts = p.get("failed_attempts", 0) + 1
                                p["failed_attempts"] = attempts
                                
                                if attempts >= 3:
                                    p["force_publish"] = False
                                    if p.get("id"): history.add(p["id"])
                                    if p.get("affiliate_url"): history.add(p["affiliate_url"])
                                    slot_results[niche_name] = "❌ Descartado (Sin meli.la)"
                                    await self._notify_permanent_discard(niche_name, p, "no generó link meli.la en 3 intentos")
                                else:
                                    if not p.get("affiliate_alert_sent"):
                                        p["affiliate_alert_sent"] = True
                                        if self.orchestrator.telegram_bot:
                                            msg = f"⚠️ *ALERTA DE AFILIADO ({niche_name.upper()})*\nEl producto `{p.get('title', 'Sin título')[:50]}` no tiene enlace `meli.la`.\n🛡️ Ha sido saltado (Intento {attempts}/3)."
                                            reply_markup = {"inline_keyboard": [[{"text": "🔄 Reintentar Link", "callback_data": f"retry_aff_{niche_name}_{p.get('id')}"}]]}
                                            asyncio.create_task(self.orchestrator.telegram_bot.send_notification(msg, reply_markup=reply_markup))
                                    slot_results[niche_name] = "⚠️ Saltado (Sin meli.la)"
                                
                                try:
                                    json_save_atomic(q_file, products, indent=2, ensure_ascii=False)
                                except:
                                    pass
                                continue
                            continue


                if not published_in_slot:
                    self.daily_stats["empty_slots"] += 1
                    print(f"🍽️ Sin productos válidos o todos fallaron a las {next_slot:02d}:00")

                await self._send_slot_summary(next_slot, slot_results)



                await asyncio.sleep(70)

            except Exception as e:
                print(f"Error en Scheduler: {e}")
                import traceback
                error_trace = traceback.format_exc()
                if self.orchestrator.telegram_bot:
                    asyncio.create_task(self.orchestrator.telegram_bot.send_notification(
                        f"🚨 *ERROR FATAL EN EL SCHEDULER* 🚨\nEl bucle principal crasheó y está en pausa por 10 min.\n\n`{str(e)}`\n\nRevisa los logs del sistema."
                    ))
                await asyncio.sleep(600)

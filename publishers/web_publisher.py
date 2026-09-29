"""
publishers/web_publisher.py
Módulo encargado exclusivamente de:
  1. Insertar el producto en website_db.json
  2. Reconstruir el HTML de la Landing Page (build_site)
  3. Subir los archivos a GitHub via REST API (sin git local, sin permisos de Linux)

No depende del orquestador. Recibe el dict de detalles del producto y opera de forma
autónoma. Retorna PublishResult si todo fue exitoso.
"""
import os
import json
import asyncio
import urllib.request
import urllib.error
import base64
import hashlib
import time
from core.config import Config
from core.storage import json_load, json_save_atomic
from core.publisher_base import Publisher, PublishResult


# ─── Credenciales GitHub (centralizadas aquí) ───────────────────────────────
GITHUB_USER  = "laloehm"
GITHUB_REPO  = "gangas-mx"
GITHUB_BRANCH = "main"
VALID_EXTENSIONS = (".html", ".css", ".js", ".json", ".ico", ".png", ".svg", ".txt", ".webp", ".jpg", ".jpeg", ".xml")


class WebPublisher(Publisher):
    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)

    # ─── 1. Insertar producto en la base de datos de la web ─────────────────
    def add_product_to_db(self, details: dict) -> bool:
        """
        Inserta el producto en website_db.json si no existe ya.
        Mantiene un máximo de 100 productos (los más recientes primero).
        Retorna True si se insertó, False si ya existía o hubo error.
        """
        web_db_file = os.path.join(Config.BASE_DIR, "website_db.json")
        try:
            w_data = json_load(web_db_file, default=[])
            if not isinstance(w_data, list):
                w_data = []

            existing_ids  = {item.get("id") for item in w_data if item.get("id")}
            existing_urls = {item.get("affiliate_url") for item in w_data if item.get("affiliate_url")}

            p_id  = details.get("id")
            p_url = details.get("affiliate_url")

            if not (p_id or p_url):
                raise ValueError("Producto sin ID ni URL; no se puede deduplicar")

            if (p_id and p_id in existing_ids) or (p_url and p_url in existing_urls):
                print("[WEB PUBLISHER] Producto ya existe en website_db. Omitido.")
                return False

            import datetime
            if "published_at" not in details:
                details["published_at"] = datetime.datetime.now().isoformat()

            w_data.insert(0, details)
            w_data = w_data[:100]

            json_save_atomic(web_db_file, w_data, indent=4, ensure_ascii=False)

            print(f"[WEB PUBLISHER] Producto agregado a website_db ({len(w_data)} total).")
            return True
        except Exception as e:
            print(f"[WEB PUBLISHER] Error en add_product_to_db: {e}")
            raise

    # ─── 2. Reconstruir la Landing Page ─────────────────────────────────────
    def build(self) -> bool:
        """
        Llama a build_site.build_site() para regenerar el HTML.
        Retorna True si tuvo éxito.
        """
        try:
            import importlib
            import build_site
            importlib.reload(build_site)
            build_site.build_site()
            print("[WEB PUBLISHER] Landing Page reconstruida correctamente.")
            return True
        except Exception as e:
            print(f"[WEB PUBLISHER] Error reconstruyendo la Landing Page: {e}")
            return False

    # ─── 3. Subir archivos a GitHub via REST API ─────────────────────────────
    @staticmethod
    def _git_blob_sha(content: bytes) -> str:
        """Computa el SHA que GitHub asigna a un blob (sha1 del header + contenido)."""
        header = f"blob {len(content)}\0".encode()
        return hashlib.sha1(header + content).hexdigest()

    def _get_remote_shas(self, headers: dict) -> dict:
        """
        Obtiene {rel_path: blob_sha} de todos los archivos en el repo con 3 requests.
        Mucho más eficiente que hacer un GET individual por archivo.
        """
        api_git = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/git"
        try:
            req = urllib.request.Request(
                f"{api_git}/ref/heads/{GITHUB_BRANCH}", headers=headers
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                commit_sha = json.loads(r.read())["object"]["sha"]

            req = urllib.request.Request(
                f"{api_git}/commits/{commit_sha}", headers=headers
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                tree_sha = json.loads(r.read())["tree"]["sha"]

            req = urllib.request.Request(
                f"{api_git}/trees/{tree_sha}?recursive=1", headers=headers
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                tree = json.loads(r.read())

            return {item["path"]: item["sha"] for item in tree.get("tree", []) if item["type"] == "blob"}
        except Exception as e:
            print(f"[WEB PUBLISHER] No se pudo obtener árbol remoto (se subirán todos los archivos): {e}")
            raise RuntimeError("No se pudo obtener el arbol remoto de GitHub") from e

    @staticmethod
    def _refresh_content_sha(file_url: str, headers: dict):
        try:
            req = urllib.request.Request(file_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read()).get("sha")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def push_to_github(self, commit_message: str = "Auto-update") -> int:
        """
        Sube a GitHub solo los archivos que cambiaron comparando SHAs locales vs remotos.
        3 requests para obtener el árbol + 1 PUT por archivo modificado (en lugar de 2 por archivo).
        Retorna el número de archivos subidos con éxito.
        """
        from dotenv import load_dotenv
        load_dotenv(override=True)
        github_token = os.getenv("GITHUB_TOKEN", "")
        if not github_token:
            raise RuntimeError("GITHUB_TOKEN no esta configurado")

        public_dir = os.path.join(Config.BASE_DIR, "public")
        api_base   = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents"
        headers    = {
            "Authorization": f"token {github_token}",
            "Accept":        "application/vnd.github.v3+json",
            "Content-Type":  "application/json"
        }

        # Recopilar archivos válidos con su contenido
        local_files = []
        for root, dirs, files in os.walk(public_dir):
            dirs[:] = [d for d in dirs if d != ".git"]
            for fname in files:
                if fname.endswith(VALID_EXTENSIONS):
                    full_path = os.path.join(root, fname)
                    rel_path  = os.path.relpath(full_path, public_dir).replace("\\", "/")
                    with open(full_path, "rb") as fh:
                        content = fh.read()
                    local_files.append((rel_path, content))

        # Obtener SHAs remotos en 3 requests
        remote_shas = self._get_remote_shas(headers)

        # Filtrar solo los archivos que cambiaron o son nuevos
        changed = []
        skipped = 0
        for rel_path, content in local_files:
            local_sha = self._git_blob_sha(content)
            if remote_shas.get(rel_path) == local_sha:
                skipped += 1
            else:
                changed.append((rel_path, content))

        print(f"[WEB PUBLISHER] {len(local_files)} archivos totales — {skipped} sin cambios — subiendo {len(changed)}...")
        success_count = 0
        failed_paths = []

        for rel_path, content in changed:
            content_b64 = base64.b64encode(content).decode("utf-8")
            file_url = f"{api_base}/{rel_path}"
            uploaded = False
            last_error = None
            for attempt in range(1, 4):
                payload = {
                    "message": commit_message[:50],
                    "content": content_b64,
                    "branch":  GITHUB_BRANCH
                }
                remote_sha = remote_shas.get(rel_path)
                if attempt > 1:
                    remote_sha = self._refresh_content_sha(file_url, headers)
                if remote_sha:
                    payload["sha"] = remote_sha

                try:
                    data = json.dumps(payload).encode("utf-8")
                    req_put = urllib.request.Request(file_url, data=data, headers=headers, method="PUT")
                    with urllib.request.urlopen(req_put, timeout=30) as resp:
                        resp.read()
                    success_count += 1
                    uploaded = True
                    break
                except Exception as error:
                    last_error = error
                    print(f"[WEB PUBLISHER] Intento {attempt}/3 subiendo {rel_path} fallo: {error}")
                    if attempt < 3:
                        time.sleep(2 ** attempt)
            if not uploaded:
                failed_paths.append(rel_path)
                print(f"[WEB PUBLISHER] ERROR definitivo en {rel_path}: {last_error}")

        print(f"[WEB PUBLISHER] OK: {success_count}/{len(changed)} archivos subidos ({skipped} sin cambios omitidos).")
        if failed_paths:
            raise RuntimeError(
                f"GitHub quedo incompleto: {len(failed_paths)} archivo(s) fallaron: "
                + ", ".join(failed_paths[:5])
            )
        return success_count

    async def publish(self, details: dict, affiliate_link: str, **kwargs) -> PublishResult:
        """
        Ejecuta el flujo completo de publicación web:
          1. Inserta en website_db.json
          2. Reconstruye el HTML
          3. Sube a GitHub via API

        kwargs:
            commit_message (str, opcional): Mensaje del commit en GitHub
        """
        commit_message = kwargs.get("commit_message", "Auto-update")

        try:
            added = self.add_product_to_db(details)
            if not added:
                msg = "Producto ya existía en website_db"
                return PublishResult(True, "web", msg)

            build_ok = await asyncio.to_thread(self.build)
            if not build_ok:
                msg = "Error reconstruyendo landing page"
                return PublishResult(False, "web", msg)

            count = await asyncio.to_thread(self.push_to_github, commit_message)
            msg = f"Landing Page actualizada ({count} archivos)"
            return PublishResult(True, "web", msg, details={"files_updated": count})

        except Exception as error:
            msg = f"Error publicando en web: {str(error)[:100]}"
            print(f"[WEB PUBLISHER] {msg}")
            await self._notify_telegram(f"❌ Web: {msg}")
            return PublishResult(False, "web", msg, error=error)

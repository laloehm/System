import os
from core.config import Config

class SessionManager:
    @staticmethod
    def get_storage_state():
        """Retorna la ruta de la sesión si existe, o None con un aviso."""
        if os.path.exists(Config.STORAGE_PATH):
            print(f"[SESSION] Sesion detectada: {Config.STORAGE_PATH}")
            return Config.STORAGE_PATH
        print(f"[SESSION] AVISO: No se encontro sesion en {Config.STORAGE_PATH}. Se iniciara sin loguear.")
        return None

    @staticmethod
    async def save_session(context):
        """Guarda el estado actual del contexto en el archivo unificado."""
        await context.storage_state(path=Config.STORAGE_PATH)
        print(f"[SESSION] Sesion actualizada y guardada en {Config.STORAGE_PATH}")

# Documentación de Cambios: Gestor de Grupos de FB (Telegram)
**Fecha:** 15 de Julio de 2026

## 1. Problema Resuelto
El sistema carecía de una manera fácil de visualizar todos los grupos de Facebook registrados en los distintos nichos (General, Bebés, Mascotas, Moda, Tenis). Además, el borrado de grupos de Facebook fallaba o estaba incompleto, ya que el componente del bot encargado de borrarlos (`fb_group_browser`) no estaba indexando los nichos más recientes (Tenis y Moda).

## 2. Modificaciones al Código (`core/telegram_bot.py`)
Se implementaron y estabilizaron las siguientes funcionalidades dentro del menú **REDES**:

### 2.1 Botón: "📊 VER GRUPOS FB CONFIGURADOS"
- **Función interna (`show_fb_groups`)**: Ahora consolida los grupos de TODAS las variables de `.env` usando `Config.FB_GROUPS`, `Config.FB_GROUPS_BABY`, `Config.FB_GROUPS_PETS`, `Config.FB_GROUPS_TENIS` y `Config.FB_GROUPS_MODA`.
- **Formato Visual**: Se reemplazó el texto bruto por hipervínculos estructurados usando Markdown (`[ID del Grupo](URL)`). Esto permite al usuario tocar el nombre y abrir la app de Facebook directamente para validar que el grupo existe o ver su contenido, mejorando radicalmente el UX.
- **Limpieza de Interfaz**: Se removieron teclados interactivos flotantes masivos que saturaban la pantalla, volviendo a un esquema de botones funcionales agrupados (`Eliminar un Grupo`, `Añadir Grupo`, `Volver`).

### 2.2 Botón: "🗑️ ELIMINAR UN GRUPO" (`fb_group_browser`)
- **Ampliación de Nichos**: Anteriormente, el carrusel de eliminación ignoraba las categorías nuevas. El código fue refactorizado (líneas 1225-1300) para inyectar dinámicamente `Config.FB_GROUPS_TENIS` y `Config.FB_GROUPS_MODA` en la lista global de grupos que alimenta el carrusel.
- **Flujo de Seguridad**: Cuando se da clic en "🗑️ ELIMINAR ESTE GRUPO" dentro del carrusel interactivo, el sistema extrae el índice global actualizado, hace un "match" seguro, y lo borra de la variable correcta en el `.env`, recargando la configuración al vuelo mediante las propiedades `@classmethod` en `core/config.py`.

## 3. Recuperación de Emergencia
- Se realizó un _rollback_ manual de la variable `FB_GROUP_URLS` en el archivo `.env` para recuperar el primer grupo (`https://www.facebook.com/groups/1331451857548984`) tras un borrado accidental provocado por una iteración fallida de la botonera inline. El estado original ha sido preservado íntegramente.

## 4. Estado Actual de Sesiones (Manual Login)
- Se corrigió el archivo `manual_login.py` reduciendo el `viewport` forzado de `height: 2000` a una resolución estándar de laptop (`1366x768`), asegurando que las ventanas headless visuales en el servidor Linux tengan habilitadas las barras de desplazamiento (scroll) nativas del sistema operativo, permitiendo re-iniciar sesión en Meta/Amazon sin interrupciones de UI.

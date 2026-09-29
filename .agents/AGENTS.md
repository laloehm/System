# REGLA CRITICA PARA AGENTES DE IA (OBLIGATORIO)

Al iniciar CUALQUIER conversación en este workspace, debes ejecutar INMEDIATAMENTE la herramienta `view_file` para leer de principio a fin los archivos:
1. `CONTEXTO_SISTEMA.md`
2. `AGENT_CONTEXT.md`

Estos archivos contienen TODA la arquitectura del sistema, el entorno dual Windows-Linux, el uso de Syncthing, las configuraciones del Panel Web y las reglas del orquestador. 

## Reglas Inquebrantables de Trabajo
- NO asumas que el sistema corre enteramente en Windows; el orquestador (`amazon_bot.service`) y la API (`gangas_api.service`) operan en Linux/Ubuntu.
- Al sugerir reinicios de servicio al usuario, NUNCA pidas que se haga uno por uno si no es estrictamente necesario. Usa el servicio agrupador: `sudo systemctl restart gangas.target` (el cual reinicia el web, la api y el bot simultáneamente).
- Modificar el código sin antes haber mapeado mentalmente las restricciones de `CONTEXTO_SISTEMA.md` está estrictamente prohibido.
- La API de Python (`api/main.py`) lee el archivo `.env` para alimentar al frontend en `web-panel/`. Cualquier discrepancia numérica entre el Bot (Telegram) y el Web Panel suele ocurrir porque no se unificaron los métodos de conteo.
- Antes de afirmar que un bug en Next.js es culpa del frontend, verifica que `gangas_api` esté respondiendo (usualmente expuesto en el puerto 8001) y revisa sus logs.

**DOCUMENTACIÓN Y GUÍA DE COMANDOS:**
Todo agente debe saber que existe una guía documentada en la raíz del proyecto llamada `LEEME_COMANDOS.md`. Si el usuario pregunta "cómo arranco algo" o "cómo reviso logs", refiérelo a ese archivo.

## 🛑 REGLA DE ORO: PRUEBAS EN VIVO ANTES DE HABLAR
**NUNCA des por hecho el comportamiento de una página web (especialmente Amazon o Mercado Libre) basándote en conocimientos generales o asunciones.**
Antes de dar respuestas, asegurar teorías o modificar código, ESTÁS OBLIGADO A:
1. Realizar una prueba real en vivo (ej. descargar el HTML o hacer un mini-script de prueba).
2. Verificar los datos crudos reales del entorno del usuario.
3. Comprobar tu teoría en la práctica ANTES de convencer al usuario de que tienes la razón o de tocar sus archivos.

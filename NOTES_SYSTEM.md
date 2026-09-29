# 📋 Sistema de Notas para Grupos de Facebook - Documentación Completa

**Última actualización:** 2026-08-29
**Estado:** ✅ Funcionando
**Responsable:** Claude Code

---

## 🎯 Problema Original

El usuario necesitaba agregar notas/comentarios a grupos de Facebook sin necesidad de borrar o recrear el grupo. Las notas debían:
- Ser persistentes
- Editables en cualquier momento
- Visibles en la lista de grupos
- Accesibles desde UI, no desde archivos

---

## ✅ Soluciones Implementadas

### 1. **Core Module de Notas** 
**Archivo:** `core/facebook_groups_notes.py`
**Función:** Gestionar guardar/obtener/eliminar notas

**Cambios clave:**
```python
- Usa ruta absoluta: Config.BASE_DIR + "facebook_groups_notes.json"
- Límite: 1000 caracteres por nota
- Funciones: get_note(), save_note(), delete_note(), get_all_notes()
```

**Si falla:** Verificar que `Config.BASE_DIR` apunta a `/home/laloehm/Desktop/System-Afiliados` en Linux

---

### 2. **API Endpoints**
**Archivo:** `api/main.py` (líneas 1156-1223)

**Endpoints creados:**
```
GET    /api/facebook/groups/notes?url={group_url}
POST   /api/facebook/groups/notes?url={group_url}
DELETE /api/facebook/groups/notes?url={group_url}
```

**Modelo Pydantic:** `NoteRequest` (línea 11)
```python
class NoteRequest(BaseModel):
    note: str = ""
```

**Por qué Query Params en lugar de Path Params:**
- FastAPI no maneja bien URLs complejas en path parameters
- Error 404 cuando URL tenía caracteres especiales (https://)
- Query params funcionan correctamente con URL encoding

**Si falla con 404:**
1. Reiniciar API: `sudo systemctl restart gangas_api.service`
2. Verificar endpoint: `sudo systemctl status gangas_api.service`
3. Ver logs: `sudo journalctl -u gangas_api.service -n 50`

---

### 3. **Frontend - Panel Web**
**Archivo:** `web-panel/src/app/networks/groups/page.tsx`

**Componentes modificados:**

#### A. Helper `apiFetch()` (líneas 30-39)
- Fallback automático puerto 3000 → 8001
- Usa URLSearchParams para query params
- Resuelve problemas de CORS

#### B. Función `fetchNote()` (líneas 60-73)
- Obtiene nota del servidor
- Cachea en `groupNotes` state
- Llamada: `fetchNote(url)`

#### C. Función `openNoteModal()` (líneas 75-87)
- Abre modal para editar
- Carga nota desde cache o API
- Abre inmediatamente (mejor UX)

#### D. Función `saveNote()` (líneas 89-133)
- Valida 1000 caracteres máximo
- Usa barra de progreso visual
- Manejo robusto de errores con alerts en cada paso

#### E. Renderizado (líneas 330-389)
- Muestra preview de nota: primeros 80 chars
- Badge ACTIVO/PAUSADO
- Ícono lápiz para editar

**Si no carga notas:**
1. Limpiar caché: F12 → Application → Clear All
2. Recarga: Ctrl+F5
3. Verificar API está corriendo: `sudo systemctl status gangas_api.service`

---

### 4. **Archivo de Datos**
**Archivo:** `facebook_groups_notes.json`

**Estructura:**
```json
{
  "https://www.facebook.com/groups/1265564392008661": {
    "note": "Texto de la nota",
    "updated_at": "2026-08-29T20:58:20.952419",
    "character_count": 65
  }
}
```

**Si se corrompe:**
1. Backing up: `cp facebook_groups_notes.json facebook_groups_notes.json.bak`
2. Limpiar: `echo "{}" > facebook_groups_notes.json`
3. API recargará automáticamente

---

## 🔧 Comandos de Referencia Rápida

### Reiniciar TODO
```bash
sudo systemctl restart gangas.target
```

### Reiniciar solo API
```bash
sudo systemctl restart gangas_api.service
```

### Ver status de TODO
```bash
sudo systemctl status gangas.target
sudo systemctl status gangas_api.service gangas_web.service amazon_bot.service
```

### Ver logs de API
```bash
sudo journalctl -u gangas_api.service -n 100 -f
```

### Limpiar caché frontend
- F12 → Application → Local Storage → Clear All
- Ctrl+F5 (recargar)

---

## 🐛 Troubleshooting

### Problema: Nota no se guarda
**Pasos de debug:**
1. ¿El alert muestra PASO 6 correctamente? → API está respondiendo
2. Ver logs API: `sudo journalctl -u gangas_api.service -n 20`
3. Verificar permisos: `ls -l facebook_groups_notes.json`
4. Si dice permission denied: `sudo chmod 666 facebook_groups_notes.json`

### Problema: Modal no abre o no muestra nota
1. Recarga navegador: Ctrl+F5
2. Limpiar cache: F12 → Application → Clear All
3. Verificar API responde: Abre en navegador `http://localhost:8001/api/facebook/groups/notes?url=https%3A%2F%2Fwww.facebook.com%2Fgroups%2F123`

### Problema: Error 404 al guardar
1. API no fue reiniciada después de cambios de código
2. Ejecuta: `sudo systemctl restart gangas_api.service`
3. Espera 5 segundos
4. Recarga navegador: Ctrl+F5

### Problema: Nota guardada pero no aparece en lista
1. Recarga navegador: Ctrl+F5
2. Limpiar cache: F12 → Application → Clear All
3. Cierra y abre modal nuevamente

---

## 📁 Archivos Críticos

| Archivo | Línea | Función |
|---------|-------|---------|
| `core/facebook_groups_notes.py` | - | Lógica de notas |
| `api/main.py` | 1156-1223 | Endpoints REST |
| `api/main.py` | 11 | Modelo NoteRequest |
| `web-panel/.../groups/page.tsx` | 30-39 | apiFetch helper |
| `web-panel/.../groups/page.tsx` | 60-87 | fetchNote + openNoteModal |
| `web-panel/.../groups/page.tsx` | 89-133 | saveNote |
| `web-panel/.../groups/page.tsx` | 330-389 | Renderizado notas |
| `facebook_groups_notes.json` | - | Storage de notas |

---

## ⚙️ Flujo Completo

```
Usuario hace clic en lápiz
    ↓
openNoteModal(url) se ejecuta
    ↓
Abre modal inmediatamente
    ↓
fetchNote(url) en background
    ↓
GET /api/facebook/groups/notes?url=X
    ↓
core/facebook_groups_notes.py → get_note(url)
    ↓
Lee facebook_groups_notes.json
    ↓
Retorna nota
    ↓
Frontend actualiza setEditingNote()
    ↓
Usuario ve nota en textarea
    ↓
Usuario edita y hace clic "Guardar"
    ↓
saveNote() valida (max 1000 chars)
    ↓
POST /api/facebook/groups/notes?url=X
    ↓
core/facebook_groups_notes.py → save_note(url, note)
    ↓
Escribe facebook_groups_notes.json (atómico)
    ↓
Retorna success: true
    ↓
Frontend cierra modal
    ↓
Lista se actualiza mostrando nota preview
```

---

## 🚀 Próximos Pasos (Opcional)

1. Agregar búsqueda de notas
2. Exportar notas a CSV
3. Historial de cambios en notas
4. Compartir notas entre usuarios

---

## 📞 Contacto

Si hay dudas:
1. Verificar este archivo
2. Revisar logs: `sudo journalctl -u gangas_api.service`
3. Limpiar cache frontend y reiniciar API

**Documentado por:** Claude Code
**Para:** Ambas IAs (Claude y Gemini)

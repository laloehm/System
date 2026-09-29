@echo off
echo Registrando tarea GangasMX_TriggerWatcher en Task Scheduler...

schtasks /Delete /F /TN "GangasMX_TriggerWatcher" 2>nul

schtasks /Create /F /TN "GangasMX_TriggerWatcher" ^
  /TR "\"C:\Users\eduardo.hernandez\AppData\Local\Programs\Python\Python313\pythonw.exe\" \"C:\Users\eduardo.hernandez\OneDrive - Valtech\Documents\System\watch_trigger.py\"" ^
  /SC MINUTE /MO 5 ^
  /RL HIGHEST ^
  /IT

if %ERRORLEVEL% == 0 (
    echo.
    echo OK: Tarea registrada correctamente con ruta completa de Python.
    echo Corre cada 5 minutos en segundo plano, sin ventana visible.
) else (
    echo.
    echo ERROR: Ejecuta este archivo como Administrador.
)
pause

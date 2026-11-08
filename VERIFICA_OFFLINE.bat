@echo off
cd /d "%~dp0"
python verify_release.py
if errorlevel 1 (
  echo Verifica non superata. Consultare reports\release_verification.json
  pause
  exit /b 1
)
echo Verifica software della patch superata. Consultare dist\ESITO_VERIFICHE.txt
pause

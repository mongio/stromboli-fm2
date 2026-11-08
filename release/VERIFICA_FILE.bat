@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verifica_file.ps1"
if errorlevel 1 (
  echo Non usare i WAV finche la verifica non risulta corretta.
  echo Do not use the WAVs until the check passes.
  pause
  exit /b 1
)
pause

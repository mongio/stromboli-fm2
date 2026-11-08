#!/bin/sh
# Controlla che i due WAV coincidano con quelli verificati (macOS).
# Non installa nulla, non riproduce audio, non aggiorna lo strumento.
cd "$(dirname "$0")" || exit 1
if shasum -a 256 -c SHA256SUMS.txt; then
  echo
  echo "Entrambi i WAV sono integri. Leggi la guida prima di aggiornare."
else
  echo
  echo "ERRORE: non usare i WAV finche la verifica non risulta corretta."
fi
echo
read -r -p "Premi Invio per chiudere..." _

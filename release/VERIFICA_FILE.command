#!/bin/sh
# Controlla che i due WAV coincidano con quelli verificati (macOS).
# Non installa nulla, non riproduce audio, non aggiorna lo strumento.
cd "$(dirname "$0")" || exit 1
if shasum -a 256 -c SHA256SUMS.txt; then
  echo
  echo "Entrambi i WAV sono integri. Leggi la guida prima di aggiornare."
  echo "Both WAVs are intact. Read the guide before updating."
else
  echo
  echo "ERRORE: non usare i WAV finche la verifica non risulta corretta."
  echo "ERROR: do not use the WAVs until the check passes."
fi
echo
read -r -p "Premi Invio per chiudere / Press Enter to close..." _

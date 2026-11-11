# Mario Texture's STROMBOLI

*Erutta a tempo, mai due volte uguale.*

**Patch beta per il firmware del Korg volca fm2.** Seconda generazione, con MIDI OUT. Non
ufficiale, si applica al firmware ufficiale 1.12: probabilità e condizioni per step, HOLD, nuove modalità di arpeggio e arpeggio sul MIDI OUT, scale, humanize e
salto d'ottava, delay in alternativa al riverbero, chain evoluto (ordine libero con ripetizioni, cattura dal vivo,
registrazione mentre la catena suona).

> [!WARNING]
> **Solo per il volca fm2** (il volca fm di seconda generazione, 2022: 6 voci, MIDI IN **e OUT** su minijack TRS da
> 3,5 mm, chorus e riverbero). **Non** è per il primo volca fm (2016: 3 voci, solo MIDI IN, DIN a 5 poli), che ha un firmware e un
> aggiornamento diversi. Non provare a installarlo sul primo volca fm.

*[English version: README.md](README.md)*

> Non ufficiale: non è fatta né approvata da Korg. Qui ci sono **solo la patch e gli strumenti**: nessun firmware Korg
> e nessun WAV pronto. I WAV li costruisci tu dall'aggiornamento ufficiale scaricato dal sito Korg. Si torna sempre
> indietro con l'aggiornamento ufficiale Korg 1.12 (o con il WAV di ripristino costruito qui). Uso a tuo rischio.

Versione **1.24 beta** (ratchet, microtiming e swing per pattern, LOFI più sporco): provata nell'emulatore; la 1.21 e la 1.22 sono provate su un volca fm2 vero.

## Cosa aggiunge

| Funzione | Come |
|---|---|
| Probabilità per step, condizioni (1-2, 2-4, 1ST…), probabilità generale, comandi rapidi | pagina FUNC + EDIT, modalità P, C, GL |
| HOLD, tasto riparte / spegne | FUNC + OCTAVE +, FUNC + OCTAVE − |
| 7 nuove modalità di arpeggio, arpeggio sul MIDI OUT | manopola ARP TYPE |
| 15 scale con tonica, anche per il sequencer | FUNC + SAVE, modalità SC, tn |
| Humanize e salto d'ottava per pattern | modalità HU, OC |
| Delay o delay lo-fi al posto del riverbero (scelta salvata nel pattern): SYNC o tempo libero, feedback, mono / ping-pong | modalità FX, dt, Fb; FUNC + 4 acceso/spento |
| Catena in ordine libero con ripetizioni (fino a 64 voci), registrazione su catena con salvataggio, funzioni FUNC e REC durante la catena, copia dei pattern, REC fisso dopo un motion | modalità CR; FUNC + MEMORY |
| Program Change in ingresso: cambia il programma (PC mod 64) | MIDI IN |
| Phaser da Rhodes o tremolo (stereo / pan) al posto del chorus, salvati nel pattern; velocità libera o a tempo | modalità MOD, rt, rS / Fo; FUNC + 3 acceso/spento |
| Delay LOFI a nastro: wow e flutter, ripetizioni più scure, saturazione morbida | modalità FX = LOFI |
| Direzione di riproduzione per pattern: avanti, indietro, pendolo, caso | modalità dr |
| Mutazione delle note in scala (alla Turing Machine), per pattern | modalità Mu |
| Ratchet (2–4 colpi con probabilità e andamento del volume) e microtiming per step, swing per pattern | modalità rA, ti |

La guida completa è in [docs/GUIDA_1_24.txt](docs/GUIDA_1_24.txt), le cose da provare in
[docs/PROVE_1_24.txt](docs/PROVE_1_24.txt), le note tecniche in `docs/NOTE_TECNICHE_1_xx.md`. Tutti i documenti hanno una versione inglese in `docs/en/`.

## Costruire i WAV

Serve: Python 3.11+, gli strumenti LLVM 18 (`llvm-mc`, `llvm-objcopy`, `llvm-readobj`, `llvm-nm`) e
`pip install -r requirements.txt`.

1. Scarica **volca fm2 System Updater 1.12** dal [sito Korg](https://www.korg.com/us/support/download/software/0/892/4964/)
   e metti `volca_fm2_updater_0112.zip`, così com'è, nella cartella `reference/`.
2. `python3 build_release.py` → nella cartella `dist/`: `01_INSTALLA_FM2_1_24_BETA.wav`,
   `02_RIPRISTINA_ORIGINALE_1_12.wav`, `SHA256SUMS.txt` e la guida.
3. Facoltativo ma consigliato: `python3 verify_release.py` (circa 10 minuti) esegue tutte le prove e scrive
   `dist/ESITO_VERIFICHE.txt`.

Stesso aggiornamento Korg → stessi WAV. Si installa con la procedura Korg (accensione con FUNC + PLAY, WAV nel SYNC
IN). **I WAV sono dati: non ascoltarli mai su casse o cuffie.**

## Licenza

Patch e strumenti sono software libero sotto GNU GPL versione 3 (solo), testo in `LICENSE`; dettagli in
[LICENSING.md](LICENSING.md). Il firmware Korg non è incluso ed è coperto dalla licenza Korg.

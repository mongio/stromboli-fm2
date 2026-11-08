# FM2 1.19 beta: file del repository

Non serve per aggiornare il FM2: le istruzioni sono in `GUIDA_1_19.txt`. Le note tecniche sono in questa cartella `docs/`, i sorgenti e gli script nella radice del repository.

| File | Funzione |
|---|---|
| `src/fm2_119.S` | Sorgente ARM/Thumb della 1.19, blob in ITCM a 0x2000 |
| `src/fm2_119_flash.S` | Codice della chain (1.19), blob in flash a 0x0020FC40 |
| `verify_119.py` | Prove di CH LIBERA, CC, CR con il modello del journal |
| `NOTE_TECNICHE_1_19.md` | Chain Korg, agganci e funzionamento della 1.19 |
| `verify_118.py` | Prove del delay: modello indipendente campione per campione, tempi, ISR, cambi di effetto, tempo, CPU, pagine |
| `NOTE_TECNICHE_1_18.md` | Delay: riverbero Korg, buffer, aggancio nell'interrupt audio, algoritmo, misura del tempo, interfaccia |
| `verify_117.py` | Prove di scale, humanize e salto d'ottava |
| `NOTE_TECNICHE_1_17.md` | Scale: agganci, mappe delle note, sequencer; humanize e ottava |
| `verify_116.py` | Prove delle modalità di arpeggio e del MIDI OUT |
| `NOTE_TECNICHE_1_16.md` | Arpeggiatore: modalità generate, compatibilità, MIDI OUT |
| `verify_115.py` | Prove dell'HOLD |
| `NOTE_TECNICHE_1_15.md` | HOLD: sustain virtuale e modalità TASTO |
| `build_patch.py` | Costruisce l'immagine 1.19 dall'originale Korg 1.12, controllando ogni preimmagine |
| `build_release.py` | Genera i due WAV (installazione 1.19, ripristino 1.12 con intestazione 1.15) |
| `verify_114.py` | Prove delle funzioni della 1.14 |
| `verify_patch.py`, `verify_panel.py` | Prove ereditate dalla 1.13 più le nuove |
| `verify_release.py` | Verifica completa (91 gruppi): ricostruisce e decodifica i WAV, installa via FSK |
| `probability_format.py` | Formati PRB1 (1.13), PRB2 (1.14/1.15) e PRB3 (1.16–1.18) |
| `build/`, `reports/`, `dist/` | Generati (non nel repository): immagine, listato, esiti, WAV |
| `reference/` | Qui va messo l'updater Korg 1.12 scaricato da Korg (non nel repository); facoltative le immagini delle beta 1.13–1.18 per le prove di aggiornamento |
| `release/` | Script di controllo dei WAV copiati in `dist/` |
| `NOTE_TECNICHE_1_14.md` | Mappa del firmware (fase 0), formato, hook, semantica, prove |
| `NOTE_TECNICHE_1_13.md`, `LEGGIMI_1_13.md` | Documentazione della beta 1.13 |

Per riprodurre: Python 3.11+, `pip install -r requirements.txt`, LLVM 18 e
`python3 build_release.py`, poi `python3 verify_release.py`.

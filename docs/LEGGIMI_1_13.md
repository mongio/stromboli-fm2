# FM2 — probabilità per step, beta sperimentale 1.13 per collaudo

3 novembre 2026. Base: firmware originale Korg volca FM2 1.12.

Per l’esito completo, inclusi i WAV installazione/ripristino, leggere
`../ESITO_VERIFICHE.txt` e `reports/release_verification.json`.
Nel test di 10.000 passaggi al 50%, il PRNG nativo ha prodotto 4.956 esecuzioni
e 5.044 skip, con ogni decisione coincidente con il modello indipendente.

Questa è una prima modifica concreta del **sequencer interno**: una patch ARM
compilata e provata eseguendo l’immagine modificata sul computer. Non è un
sequencer esterno che invia note via MIDI.

Il pacchetto comprende due WAV pronti per il collaudo hardware. Le istruzioni
operative sono in `../LEGGIMI_PRIMA_DEL_COLLAUDO.txt`. La beta si identifica come
**1.13**; è una modifica sperimentale indipendente, non un aggiornamento Korg.
Il file di ripristino reinstalla byte per byte il contenuto originale 1.12,
con intestazione di trasporto 1.14 per essere accettato dopo la beta.
Nessun collaudo fisico è stato eseguito: quello è lo scopo della consegna.

## Comportamento

- Ogni step ha una probabilità intera da 0 a 100%.
- 100% esegue sempre lo step; 0% non avvia le sue note.
- Un valore intermedio viene valutato a ogni passaggio, per l’intero accordo.
- Lo step scorre anche quando le note sono saltate. Clock e motion continuano.
- Se lo step viene saltato, le precedenti note del sequencer, comprese quelle
  tenute con TIE, ricevono il normale rilascio. Le note MIDI suonate dal vivo
  rimangono indipendenti.
- I pattern senza estensione valida seguono il comportamento originale, al 100%.

La probabilità è salvata nel pattern usando 28 byte che il formato 1.12 riserva.
Sono verificati salvataggio, riavvio simulato e trasferimento SysEx dei 16 pattern.
La beta aggiunge una pagina nativa sul pannello. Le seguenti operazioni descrivono
il comportamento implementato e provato sul banco software; non sono ancora
utilizzabili sul FM2 che monta il firmware originale.

## Comandi sul pannello

1. Tenere premuto **FUNC**, poi premere **EDIT**: si apre la pagina probabilità.
2. Rilasciare i pulsanti. Toccare un tasto **1–16** per selezionare lo step:
   il suo LED lampeggia, il display mostra ad esempio `05 P050`.
3. Muovere il cursore **VELOCITY/VALUE**: il valore va da **0 a 100%**.
   Toccare uno step o aprire la pagina non modifica il pattern.
4. **PLAY** permette di avviare e fermare la riproduzione anche nella pagina.
5. Premere **FUNC** o **EDIT** per uscire. Poi salvare normalmente il pattern
   con **FUNC + MEMORY**, seguito dalla locazione **1–16**.

| Display | Significato |
|---|---|
| `05 P050` | Step 5, probabilità 50% |
| `12 P100` | Step 12, probabilità 100% |
| `03 P000` | Step 3, nessun nuovo attacco, durata conservata |

Il valore rappresenta la percentuale impostata. Il cursore cambia solo tale
percentuale durante questa pagina; il parametro velocity nativo resta invariato.
Il PROGRAM encoder viene consumato senza cambiare programma durante la pagina.
Gli altri pulsanti di editing/memoria sono sospesi: uscire prima di registrare,
caricare o salvare. I comandi originali continuano a funzionare fuori dalla pagina.
Al primo movimento del cursore il valore assume la posizione fisica corrente.
La selezione resta indipendente dallo step in riproduzione.

Un profilo assente o corrotto viene mostrato al 100%, coerentemente col playback.
La prima modifica inizializza un profilo valido; tutti gli altri step partono
al 100% quando i metadati precedenti non erano validi.

## Cosa contiene

| File | Funzione |
|---|---|
| `src/probability_thumb.S` | Sorgente della modifica ARM/Thumb |
| `build/probability_code_ARM.bin` | Decisione probabilistica, 184 byte |
| `src/panel_thumb.S` | Pagina pannello, controlli e rendering nativo |
| `build/panel_code_ARM.bin` | Codice pannello compilato |
| `verify_panel.py` | Debounce originale, tutti gli step/valori, glyph e LED |
| `build/probability_code.asm` | Disassemblato leggibile, con pool delle costanti distinto |
| `build/candidate_logical_1_13_BETA.bin` | Immagine logica completa per prove software |
| `build/patch_manifest.json` | Byte originali attesi, cambiamenti e checksum |
| `edit_probability.py` | Modifica le probabilità di un pattern o di un dump SysEx |
| `probability_format.py` | Formato dell’estensione e codec dei file |
| `verify_patch.py` | Regressioni funzionali |
| `build_release.py` | Creazione e decodifica indipendente dei due WAV |
| `verify_release.py` | Verifica completa, update reale 1.12 → beta → originale con periferiche modellate |
| `reports/ESITO.txt` | Esito complessivo delle prove eseguite |
| `reports/patch_verification.json` | Risultati dettagliati e limiti dei modelli |
| `NOTE_TECNICHE_IT.md` | Punto d’inserimento, memoria, semantica e limiti |
| `examples/` | Profilo e pattern sintetico dimostrativo |
| `baseline/` | Strumenti di esecuzione e test derivati dal dossier dell’originale |
| `reference/` | Updater originale, usato esclusivamente come sorgente dei byte |

## Consultazione e riproduzione

Per capire la modifica basta leggere questo file, le note tecniche e i risultati.
Non occorre collegare lo strumento.

Per rigenerare e provare il prototipo, con Python 3.12 e le dipendenze indicate:

```sh
python -m pip install -r requirements.txt
python verify_release.py
```

Lo script rigenera i due WAV e verifica i byte effettivi su disco. Esegue
regressioni, controlli versione/CRC, ingresso di recupero, audio a sei voci con
pagina aperta e i due percorsi FSK/installazione/boot. La parte fisica delle
periferiche rimane modellata. `VERIFICA_OFFLINE.bat` avvia lo stesso comando;
serve solo per riprodurre le prove tecniche, non per aggiornare il FM2.

## Preparazione dei valori

Gli step nei comandi sono numerati da 1 a 16. Per esempio, partendo da un dump
di una sequenza, il comando seguente imposta lo step 2 al 50% e lo step 6 allo 0%:

```sh
python edit_probability.py sequenza.syx sequenza_probabilita.syx --set 2=50 --set 6=0
```

Per vedere i valori presenti:

```sh
python edit_probability.py sequenza_probabilita.syx
```

Per applicare un profilo di 16 valori:

```sh
python edit_probability.py sequenza.syx sequenza_probabilita.syx --profile examples/profilo_16_step.json
```

Lo strumento conserva il tipo di file e l’intestazione del dump. Crea un file
separato e non trasmette MIDI. I valori preparati avranno effetto nella versione
che integra questa patch; il firmware originale ignora l’estensione.

## Stato del lavoro

Sono implementati probabilità, pagina pannello, persistenza, confezionamento WAV
1.13 e ripristino esatto alla 1.12. Restano da eseguire sul dispositivo reale
il collaudo operativo, le misure del carico e delle scadenze degli interrupt e
la conferma fisica di installazione/ripristino. I risultati software non sono
una certificazione hardware né una garanzia di recupero in qualsiasi guasto.

Risorse aggiunte: 184 byte per il ramo probabilità, 828 byte per il pannello,
16 byte di stato scrivibile in ITCM. Nessuna nuova allocazione SRAM applicativa.

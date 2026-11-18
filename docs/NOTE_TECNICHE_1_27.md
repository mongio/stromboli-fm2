# Note tecniche 1.27: forme d'onda degli operatori FM

Base: 1.26. Sorgenti `src/fm2_127.S` (ITCM, nessun codice nuovo), `src/fm2_127_sram.S` (SRAM, codice nuovo in
fondo al file), `src/fm2_127_flash.S` (flash, invariato). Prove nuove `verify_127.py`; verifica completa
`verify_patch.py` e `verify_release.py`. Filtro e LFO: `NOTE_TECNICHE_1_26.md`; parti: `NOTE_TECNICHE_1_25.md`.

## Come Korg calcola gli operatori
- I 32 algoritmi (tabella a ITCM `0x105A`, kernel `0x0C60–0x1058`) sono sequenze di `bl` a **undici routine
  di operatore** (`0x0250`, `0x0350`, `0x0430`, `0x0510`, `0x05F0`, `0x06E0`, `0x07C0`, `0x08C0`, `0x09A0`,
  `0x0A80`, `0x0B60`) e finiscono con `b 0x123A`. Le routine differiscono solo per l'ingresso di modulazione
  (feedback, `sb`, `sl`) e per dove va l'uscita (`r8` audio, `sb`, `sl`, storia del feedback `[ip+4/8]`).
- Ogni routine: incremento di fase dalla tabella esponenziale `[ip+0x58]`, inviluppo (`[r7+4]`, segmenti da
  `[r7+0x18]`), ampiezza dalle tabelle `[ip+0x5C]`/`[ip+0x50]`, poi la sinusoide:
  `ldr.w r2,[ip,#0x54]` → indice = bit 14–23 della fase (1024 voci), voce di 8 byte (valore, pendenza),
  uscita = valore + (frazione 14 bit × pendenza) >> 14.
- Tabella seno Korg: `0x20006810`, 1024 × (valore, pendenza), ampiezza 2^24, pendenza = valore successivo −
  valore (con il giro). Anche l'LFO con forma seno (ITCM `0x1172`) la legge da `[ip+0x54]`.
- Record dell'operatore: voce + `0x90` + 0x50·i, i = 0–5. Il blocco i del programma (17 byte, il blocco 0 è OP6)
  va nel record i (verificato). La parola `+0x14` del record non è mai usata da Korg: resta intatta all'inizio
  della nota, durante la nota e al rilascio (verificato con un valore sentinella).

## Aggancio
| Dove | Era | Ora |
|---|---|---|
| ITCM `0x030A 0x03FC 0x04DC 0x05BA 0x069C 0x078A 0x087A 0x096A 0x0A4C 0x0B2A 0x0C1A` | `ldr.w r2,[ip,#0x54]` (`dcf85420`) | `ldr.w r2,[r7,#0x14]` (`d7f81420`) |
| `multi_gain` (BL a `0x0020E79E`) | — | prima della chiamata Korg `wave_voice(programma, voce)` |
| letterale del veneer `0x20015170` (logico `0x23174`) | `0x0020F019` (import voce DX7) | `wave_dx7` |
| `panel_keys` | — | alla prima scansione dei tasti `wave_build` |
Stessa istruzione, stessa dimensione, stessi cicli: le voci costano esattamente come prima (contate: 2456,3
istruzioni per campione nel ciclo delle voci, Korg 1.12 = 1.27 con e senza forme).

## Dove sta la forma d'onda
Bit 7 dei byte 11, 12, 13 del blocco di ogni operatore (forma = b11 | b12 << 1 | b13 << 2, 0–7).
- Korg li ignora: provato byte per byte (bit 7 acceso su ciascuno dei 128 byte del programma, stato della voce e
  audio confrontati) → nei blocchi degli operatori sono ignorati i byte 11, 12, 13 e 15; nel resto 110, 111,
  116 e i nomi. Restano liberi per il futuro: bit 7 del byte 15 di ogni operatore, 110, 111, 116, 118–127.
- Un SysEx DX7 non può accenderli (byte MIDI di 7 bit).
- L'import di una voce DX7 (`0x0020F018`) scrive i campi con `bfi` sui byte del programma in uso, cioè lascia il
  bit 7 com'era: `wave_dx7` li azzera prima di chiamare Korg.
- Salvataggio (`0x0020EF20`), cambio programma (`0x0020E456`), dump e ricezione di programma Korg (8 bit
  impacchettati a 7): conservano i bit (verificato).
- `0x0020E518` (programma della voce con le manopole MODULATOR/CARRIER) copia i 128 byte e cambia solo i byte
  0–3, 5, 6 e 14: i bit restano.
- Il RANDOM Korg (`0x0020EBD8`) parte dalla copia salvata `0x2000524C` e scrive i campi con maschere.

## Le tabelle (`wave_build`)
Catena di 12 quarti di periodo da 256 voci (24576 byte) a `0x20035B00–0x2003BB00`: RAM dopo il buffer del
riverbero/delay (`0x20029B00 + 0xC000 = 0x20035B00`) e prima del buffer SysEx `0x2003C000` (usato fino a
`0x2003D000` nelle prove). Nessun riferimento Korg in quella zona (cercati i letterali `0x2003xxxx`; nelle prove
di memoria, SysEx, salvataggio ed effetti nessuna scrittura).

Tipi di quarto (dalla tabella Korg, valori esatti): 0 zero, 1 sale (seno 0–255), 2 scende (256–511), 3 sotto zero
(512–767), 4 gobba a frequenza doppia (seno 0, 2, …, 510), 5 gobba negativa.

Catena: `3 0 3 0 1 2 0 4 4 0 0 5`. Ogni forma è una finestra di quattro quarti consecutivi (1024 voci):

| Forma | Nome | Primo quarto | Quarti |
|---|---|---|---|
| 0 | SIN | — | tabella Korg |
| 1 | HAL | 3 | 0 1 2 0 |
| 2 | 3-4 | 2 | 3 0 1 2 |
| 3 | PUL | 0 | 3 0 3 0 |
| 4 | ALt | 1 | 0 3 0 1 |
| 5 | dbL | 8 | 4 0 0 5 |
| 6 | dbA | 6 | 0 4 4 0 |
| 7 | HAb | 4 | 1 2 0 4 |

Pendenza = voce successiva della catena − voce; l'ultima va verso 0. All'ultima voce di una finestra la
pendenza punta al quarto seguente della catena invece che all'inizio della finestra: differenza solo
nell'ultimo 1/1024 di periodo, e solo dove i due valori differiscono.

La ricerca della catena (12 quarti = 9 finestre, 7 forme utili) è in `verify_127.py` (modello) e nelle note
di lavoro; la memoria libera non basta per tabelle complete separate (8 KB ciascuna).

Costruzione: 51049 istruzioni (~0,25 ms) una volta per accensione, alla prima scansione dei tasti (`WV+4` = 1).
Se serve prima (nessuna scansione), `wave_voice` la fa al primo operatore con forma ≠ 0.

## Inizio nota (`wave_voice`)
Chiamata da `multi_gain` **prima** di `0x0020DF14`: a quel punto `0x0020E6DC` ha già spento la voce (`+0x0E` = 0),
quindi l'interrupt audio non legge mai un puntatore a metà. Per ogni record: forma 0 → `0x20006810`, altrimenti
`0x20035B00 + primo_quarto × 2048`. 113 istruzioni.

Nota: se la voce suona ancora, `0x0020E814` mette la nota in coda e la fa partire dalla routine di servizio
`0x0020E8C2` dopo la dissolvenza; anche quel percorso passa da `0x0020E6DC` (verificato).

## Pagina Wv (modalità 23)
Dopo LF (24 modalità, `mode_order` … 21 22 23). Tasti 1–6 (OP1–OP6, blocco 5 − n), slider 0–127 → forma 0–7
(`adc_map`), scrittura nel programma in uso `0x20004F5C`; le voci della parte A che suonano (tutte, se le parti
sono spente) prendono subito i puntatori nuovi. Display `OP3 dbL`.

## Stato
ITCM `0x3880` (`WV`, 16 byte, zero nell'immagine): +0 non usato, +4 catena costruita.

## Prove (`verify_127.py`)
- **off_identical**: 32 algoritmi, due voci, campione per campione = Korg 1.12; puntatori = seno; interrupt con
  sei voci, chorus e riverbero = Korg 1.12.
- **tables**: 3072 voci uguali al modello; costruita una sola volta; picco 2^24.
- **oracle**: tutti gli operatori sulla forma w = Korg 1.12 con la sua tabella seno sostituita dalla finestra w
  (LFO non sul seno), algoritmi 1, 5, 7, 16, 32: identici campione per campione; diversi dal seno.
- **operators**: blocco i → record i, forme miste, nota successiva con il programma nuovo.
- **storage**: salvataggio, cambio programma, SysEx di programma Korg, import DX7 (bit azzerati, il resto come
  Korg).
- **pages**: 6 operatori × 8 forme, display, programma, voci che suonano, tasti 7–16, ordine LF → Wv → P.
- **cpu**: ciclo delle voci identico (2456,3 istruzioni per campione) con e senza forme.

Le prove precedenti confrontano lo stato delle voci con Korg escludendo la parola `+0x14` dei record degli
operatori (`verify_125.vdata`, `verify_114.ram`, `verify_patch.core_snapshot`).

# FM2 1.14 beta: note tecniche

7 novembre 2026. Base: firmware Korg volca FM2 1.12. La 1.14 estende la beta
1.13 (probabilità per step, collaudata sul FM2 dall'utente il 7/11/2026).

## Fase 0: mappa del firmware

**Pattern (1.920 byte)**
- 0–79: intestazione. 0 `PTST`, 4 tag `E8 4E`, 6 maschera step attivi/muti,
  12 maschera ACTIVE STEP, 15 numero di step attivi, 16–41 flag motion delle lane.
- 80 + 112·i: step i. 0–11 note (6×u16), 12–17 campo per voce, 18–23 velocity
  (tutte a zero = pausa), 24–29 gate, 30–42 parametri, 43–107 motion
  (13 lane × 5 punti), 108–111 non toccati dalla conversione dal formato legacy.
- **1872–1887: usati dal firmware Korg**, un flag per step scritto in
  `0x20012904` (`pattern[0x750 + step] = 1`). Non sono liberi.
- 1888–1915: riservati, liberi. La 1.13 li usava per PRB1, la 1.14 per PRB2.
- 1916–1919: `PTED`.

I byte per step 31 e 108–111 la conversione legacy non li scrive. Potrebbero
essere liberi, ma nessuno l'ha dimostrato: li valuto per la fase 2.

**Tasti** (id del dispatcher `0x20012184`): 0 FUNC, 3 PLAY, 4 EDIT,
6 OCTAVE/OPERATOR + (chiama `0x20015260` con +1), 7 OCTAVE/OPERATOR −
(chiama con −1). Gli id 1, 2 e 5 corrispondono a SAVE/EXPORT, MEMORY e REC,
non ancora assegnati con certezza.

**Sequencer**: `0x00208CF8` è il clock. Lo step corrente è in `CLOCK+0xB`
(`0x200031A3`). L'unico chiamante della routine di step `0x0020B7BE` è il clock
(`0x0020903E`). Lo start del trasporto è `0x002090C0`, raggiunto da
`0x00209190` (r2=1, partenza da capo: imposta lo step a 0xFF) e da
`0x00209174` (r2=0, continue). È agganciato per azzerare il contatore dei giri.

**Updater**: il bootloader accetta solo una versione di trasporto maggiore del
byte di versione installato (`0x420D`). Oltre al bootloader, quel byte lo leggono
solo la schermata di versione con REC (`0x20012294`) e l'intestazione dei dump
SysEx esportati (`0x20013EF8`, `0x20013F22`). Nessun codice lo usa per
convertire o rifiutare dati.

**Scelta per la 1.14**: il byte di versione installato vale **11** e l'intestazione
del WAV di installazione 1.14. Di conseguenza:
- il WAV **ufficiale Korg 1.12** (non modificato) viene accettato sopra la beta.
  È provato con un'installazione FSK completa del file preso dall'archivio Korg;
- la beta si installa sopra 1.12 e 1.13, e anche sopra se stessa;
- accendendo con REC si legge 1.11. In modalità GL, il tasto 16 mostra "BETA 1.14".

Il file di ripristino del pacchetto (intestazione 1.15, payload Korg 1.12) resta
necessario solo per chi ha la 1.13, che dichiarava 13. Le beta future devono
mantenere il byte a 11 e usare un'intestazione di trasporto maggiore di 12.

**ITCM libera**: da `0x174C` a `0x3FFF` è tutto riempimento FF. Il firmware
originale non contiene literal né `movw` che puntino a quell'intervallo:
le uniche costanti trovate sono valori aritmetici.

## Implementazione

Un unico blob ITCM a `0x2000` (1.988 byte), assemblato con **llvm-mc**:

| Indirizzo | Contenuto |
|---|---|
| `0x2000..0x201F` | tabella di 8 `B.W` (step, start, tasti, pulsanti, ADC, display, encoder, LED) |
| `0x2020..0x27C3` | codice e literal pool |
| `0x3E00..0x3EFF` | testi: condizioni (12×4) e messaggi dei comandi (8×12) |
| `0x3F00..0x3F1F` | stato: pagina, step, modalità, messaggio, tasti, ultimo step, primo giro, contatore giri |

Gli hook sono gli stessi della 1.13, più uno nuovo: `0x002090C0`
(`f8b5 1646` → `b.w 0x2004`). Ogni preimmagine viene confrontata prima della
sostituzione. Il settore del bootloader resta identico.

**Bug di Keystone**: con più literal pool, Keystone calcola male i salti verso
indirizzi assoluti (`bl #0x2094A4` assemblato come `0x2094CC`, con errori fino
a 0x62 byte). Nella 1.13 non succedeva perché ogni file aveva un solo pool, in
fondo. La 1.14 non usa salti assoluti: tutti gli indirizzi esterni passano da
literal (`ldr r12,=addr; blx/bx r12`) e l'assembler è llvm-mc. Ho ricontrollato
con capstone tutti i literal e i salti del blob.

## Formato PRB2 (byte 1888–1915)

| Offset | Contenuto |
|---|---|
| +0 | tag `0xA2` |
| +1..+16 | probabilità 0–100 per step |
| +17..+24 | condizioni a nibble (step 2k nibble basso, 2k+1 nibble alto), valori 0–11 |
| +25 | probabilità generale 0–100 |
| +26..+27 | FNV-1a-32 di +0..+25 ripiegato a 16 bit, little endian |

Un blocco non valido equivale a 100%, nessuna condizione, generale 100. Un PRB1
valido (1.13) viene letto, solo per le probabilità, e convertito alla prima
modifica. La prova con un singolo bit alterato copre tutti i 224 bit: ricadono
tutti sul 100%. Una prima versione con controllo a 8 bit lasciava passare una
collisione su 256, ed è stata sostituita.

## Semantica

- Ordine di decisione: pausa o step muto nativo → condizione → probabilità.
- Probabilità effettiva = (p·generale + 50) / 100. A 0% e 100% non consuma
  numeri casuali, e nemmeno quando una condizione è falsa.
- Giro: uno step con indice non maggiore del precedente apre un nuovo giro.
  Il contatore va da 0 a 839 (multiplo di 2, 3 e 4); "primo giro" è un flag a parte.
- Condizione A:B vera quando giro mod B = A−1. 1ST vale solo al giro 0,
  N1ST a tutti i giri successivi.

## Prove (49/49)

- 33 gruppi della 1.13 (riproduzione PRB1, regressioni native, pannello in
  modalità P, boot, installazione FSK) eseguiti sull'immagine 1.14.
- 10 gruppi nuovi (`verify_114.py`): condizioni con il clock nativo per 25 giri,
  maschera ACTIVE STEP, azzeramento con PLAY nativo, matrice probabilità ×
  generale (3.600 casi), fail-open su 224 bit, modalità e slider (128 posizioni
  ciascuno), conversione PRB1, comandi rapidi, journal NOR con riavvio, tasti
  +/− fuori pagina confrontati con l'originale, pagina aperta durante la riproduzione.
- Rilascio: guardie di versione e CRC, recupero, audio a 6 voci con pagina aperta,
  installazione FSK reale 1.12 → 1.14 e 1.13 → 1.14, ripristino 1.14 → 1.12
  identico byte per byte, sia con il file del pacchetto sia con il **WAV ufficiale
  Korg 1.12** originale.

Restano senza prova la temporizzazione reale degli interrupt e i comandi fisici
del pannello.

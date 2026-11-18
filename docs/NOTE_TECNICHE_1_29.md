# Note tecniche 1.29: VA semplice, EDIT con sigle Korg, effetti e motion del filtro nel pattern, filtro per parte

Base: 1.28. Sorgenti `src/fm2_129.S` (ITCM), `src/fm2_129_sram.S` (SRAM), `src/fm2_129_flash.S` (flash).
Prove `verify_129.py` (contiene anche le prove 1.28 aggiornate); verifica completa `verify_patch.py`,
`verify_release.py`. 1.28: `NOTE_TECNICHE_1_28.md`.

## Perché
Sulla 1.28 il VA con phaser e delay bloccava lo strumento con più di due o tre note: il conto del processore
contava le istruzioni e non i cicli dei salti. Ora `verify_cpu` stima i cicli (istruzioni + 2 × salti presi) con
gli effetti più pesanti (phaser 8 stadi + delay, filtro e due LFO) e chiede al massimo 4000 cicli per campione
(bilancio ~4311).

## VA semplice (ITCM)
Un solo kernel `va_simple` per tutti gli algoritmi (`va_kernel_of` a `0x209C`, BL a `0x0020DFA8`); tolti i 32
kernel e i tipi d'operatore della 1.28. Record dell'operatore come in Korg (`ip+0x90+0x50·i`, OP1 = record 5):
- OP1 = OSC 1, OP2 = OSC 2: forma (SA Sq PU tr Si), ratio/detune, livello e inviluppo Korg (`va_body`).
- OP3 = sub / rumore (S1 un'ottava sotto OSC 1, S2 due ottave, no rumore), livello = quantità (`va_env`, solo
  inviluppo).
- OP4 = larghezza dell'impulso PU (PWM, `va_env`), OP5 = intonazione di OSC 2 fino a +1 ottava (`va_env`),
  OP6 non usato.
- ALGORITHM & 7: 1 MIX, 2 SYNC (OSC 2 riparte con OSC 1), 3 RING, 4 FM (OSC 2 modula la fase di OSC 1),
  5 SYNC+FM, 6 MIX con OSC 2 un'ottava sopra, 7 RING + SUB, 8 CROSS (OSC 1 modula OSC 2); da 9 si ripete.
- Record 0: `+0x14` modo (bit 0–2), giro di OSC 1 (bit 3), contatore del sub (bit 4–5); `+0x10` ultima uscita
  di OSC 1. Record 1..5: forma + 1, 0 = spento (livello d'uscita 0); OSC 1 gira sempre (il sub segue la sua fase).
- SRAM: `wave_voice` (scrive i record), `wave_follow` (voce VA = kernel `va_simple`), limiti e nomi di WAvE
  per operatore in VA.

## EDIT (SRAM)
- Sigle a 4 lettere e valori 0–99 come Korg: `A CUtF 64`, segno di modificato in posizione 6, valore 7–8.
  Valori 0..max → 0..99 arrotondati; EnvA 0..126 → 50 = zero; divisioni (`L1dv`) numero diretto; scelte a
  2 lettere. `EnGn` FM/VA; `WAvE` con nomi a 2 lettere (FM: Si HA 34 PU AL db dA Hb; VA: SA Sq PU tr Si / S1 S2
  no / PW / Pi / --).
- Pagina A: EnGn poi 22 parametri del blocco del programma (filtro e due LFO), passo fino a `0x3D` (literal
  `0x20012982/86`). Gli effetti escono dall'EDIT e dal blocco del programma (byte 24–36 non più usati:
  `ext_apply`/`ext_capture` solo byte 2–23).

## Pagine FUNC+EDIT
Tolte FL (21) e LF (22): 21 pagine (`mode_order`). Restano MOD rt rS FX dt Fb come prima. LED di EDIT acceso
fisso nelle pagine (verificato: il refresh del modo `0x49` lascia il LED `0x20` acceso).

## Blocco STROMBOLI del pattern (52 byte)
`0 'P'  1 versione 1  2–6 FX (0x3F80 +0 +2 +4 +5 +6)  7–14 MOD (0x3B80 +0 +2 +3 +4 +5 +6 +7 +9)
15 bit 0 motion del taglio, bit 1 della risonanza, bit 7 tipi dai bit PRB3  16–31 taglio per step
32–47 risonanza per step  48–50 0  51 controllo = (somma 0..50) ^ 0x5A`.
- RAM: blocco del pattern in uso `0x2001B040`, 16 blocchi `0x2001B074–0x2001B3B4` (riempimento FF; il codice
  SRAM finisce prima di `0x2001B040`).
- Flash: il journal scrive un pattern per settore (`0x20013A9A`: intestazione, 1920 byte a +0x010); il blocco
  va a +0x800 (`pat_sector` sostituisce la chiamata finale, b.w a `0x20013ABC`). All'accensione (stato 2, BL
  a `0x200138D8` al posto di `0x20014A88`) `pat_sector_load` legge i 52 byte dallo stesso settore (lettura SPI
  sincrona `0x20015218`) e li controlla; dati di fabbrica, settore Korg o beta precedente = default.
- WRITE nativo (literal del veneer `0x0020FA94`, era `0x200134ED`): blocco in uso → blocco dello slot,
  sigillato. Caricamento di un pattern (`load_fx` in flash passa il numero) → `load_types`: blocco dello slot →
  in uso → stato degli effetti. Default con bit 7: tipi dai bit PRB3 come nella 1.21–1.27 (nessun blocco =
  REVRB e CHORUS). Pattern ricevuto via SysEx (BL a `0x20014AC8`): blocco dello slot ai default. Copia FUNC +
  MEMORY: copia anche il blocco. Catena CR: `save_if_modified` salva anche se cambia solo il blocco.
- Le pagine FUNC+EDIT degli effetti scrivono il blocco in uso (`pat_capture`); i bit PRB3 non vengono più
  scritti. Il cambio di programma non tocca gli effetti.

## FUNC + 3 / FUNC + 4
Literal dei veneer `0x002232F4` (era `0x0020C88B`, chorus acceso/spento) e `0x0022316C` (era `0x0020C8B7`,
riverbero): `rot_mod` SPENTO → CHORUS → PHASER → TREMOLO → SPENTO, `rot_fx` SPENTO → REVERB → DELAY → LOFI →
SPENTO. Acceso/spento resta il bit Korg del pattern (+0x44 bit 7, +0x45 bit 2, con il LED), il tipo nel
blocco. Messaggio sul display finché FUNC è premuto.

## Motion del filtro
- Registrazione (`filt_set`, cioè FUNC + TRANSPOSE / VELOCITY e CC 74 / 71): con PLAY e REC accesi il valore va
  nello step suonato (`0x3F3B`, scritto da `fire`); la prima volta riempie tutti i 16 step.
- Riproduzione: `fire` chiama `pm_play(step)` prima della routine Korg dello step: taglio e risonanza dal
  blocco.
- FUNC + 14 (cancella motion Korg, literal del veneer `0x00223254`, era `0x0020A225`): cancella anche il
  motion del filtro.

## Filtro per parte
`filt_control` legge i parametri da `filt_params(voce)`: FILT per la parte A (o senza parti), il blocco del
programma della parte b / C. Tipo per voce in `+0x2D` dello stato della voce; `filt_voice` (ITCM) usa quello
(0 = niente filtro). `filt_flags` accende il filtro se una parte b / C ha un filtro; `filt_start` lo ricalcola
a ogni nota. Gli LFO restano quelli della parte A.

## Processore (cicli stimati per campione, interrupt intero, sei voci)
| Caso | cicli |
|---|---|
| Korg 1.12 | 3346 |
| FM | 3494 |
| FM + filtro + 2 LFO + phaser 8 + delay | 3896 |
| VA 2 oscillatori | 2903 |
| VA tutto acceso, CROSS, + filtro + LFO + phaser 8 + delay | 3992 |
| VA tutto acceso, SYNC+FM, + filtro + LFO + phaser 8 + delay | 3999 |

## Prove (`verify_129.py`)
Oltre alle 1.28 aggiornate: va_exact (VA SIN = FM entro 5 %), va_modes (8 modi, sub, PWM, OP5), va_off,
cpu (cicli), block_edit (22 parametri, sigle e valori), pattern_block (rotazione, WRITE, caricamento, PRB3,
cambio programma), pattern_motion, pattern_journal (settori, accensione, SysEx), part_filter. Le prove
precedenti su pagine FL/LF, tipi nel pattern e FUNC + 4 sono aggiornate al nuovo comportamento.

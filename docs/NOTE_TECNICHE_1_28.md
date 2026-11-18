# Note tecniche 1.28: EDIT esteso, motore VA, blocco STROMBOLI del programma

Base: 1.27. Sorgenti `src/fm2_128.S` (ITCM: motore VA), `src/fm2_128_sram.S` (SRAM: EDIT, blocco del
programma), `src/fm2_128_flash.S` (invariato). Prove `verify_128.py`; verifica completa `verify_patch.py`,
`verify_release.py`. Forme d'onda: `NOTE_TECNICHE_1_27.md`; filtro: `NOTE_TECNICHE_1_26.md`.

## EDIT Korg
Stato E = `0x20002A08`: +0 programma in uso, +2 parametro dell'operatore, +3 parametro di A, +4 operatore 0–5
(OP1–OP6) o 6 (A). Modalità EDIT = `[0x200029DA]` 0x16. Manopola PROGRAM: `0x200114B8` → passo `0x20012978`
(operatori 0..0x15, A 0x16..0x26). Slider VELOCITY: `0x20012C50` → setter `0x20012A2C(E, 0..127)`. Lettura:
`0x20012F78` (programma in uso), `0x2001302C` (copia salvata `0x2000524C`), testo `0x200101D4` (nome a 5
caratteri da `0x2000AB78`, valore a 2 cifre, segno di modificato 0x15).

Agganci (prime istruzioni sostituite da `b.w`, le stesse rieseguite all'uscita): getter, setter e testo;
limiti del passo `0x20012996/0x2001299A` 0x15 → 0x16 (WAv) e `0x20012982/0x20012986` 0x26 → 0x4A.
- Operatore, 0x16 **WAv**: forma d'onda (bit 7 dei byte 11–13, 1.27).
- A, 0x27 **EnG**: motore, bit 7 del byte 110 del programma (FM/VA).
- A, 0x28–0x4A: i 35 parametri del blocco (tabella `ext_desc`: nome, byte del blocco, massimo, tipo di
  lettura). Display `A FCu 064`, segno di modificato in posizione 5.

## Blocco STROMBOLI del programma (48 byte)
`0 'S'  1 versione 1  2–11 filtro (FILT+0..9)  12–17 LFO 1  18–23 LFO 2  24–28 FX (0x3F80 +0 +2 +4 +5 +6)
29–36 MOD (0x3B80 +0 +2 +3 +4 +5 +6 +7 +9)  37–46 0  47 controllo = (somma 0..46) ^ 0xA5`.

RAM: blocco del programma in uso `0x2001B3C0`, 64 blocchi `0x2001B400–0x2001C000` (riempimento FF della
sezione SRAM, valori di default scritti dal costruttore). Il codice SRAM finisce prima di `0x2001B3C0`.

Salvataggio in flash: il journal Korg scrive i programmi a gruppi di 16 in un settore di 4 KB (`0x20013ACC`:
intestazione, 16 × 128 byte a +0x010, 16 × 12 byte di metadati a +0x810; il resto è 0xFF e il settore è
scritto per intero). I 16 blocchi vanno a +0x900–0xBFF: `ext_sector` sostituisce la chiamata finale (b.w a
`0x20013B0A`). Lettura all'accensione: dopo la copia dei metadati (BL a `0x20013982`, stato 6) `ext_sector_load`
legge i 768 byte dello stesso settore (lettura SPI sincrona `0x20015218`) e controlla ogni blocco; un blocco
senza 'S', versione o controllo giusto (settore scritto da Korg o da una beta precedente) = default.
Programmi di fabbrica (nessun settore nel journal) = default.

Programma: caricamento `0x0020E456` (BL a `0x0020E490` → `ext_load`: blocco del banco → blocco in uso →
stato del filtro, degli LFO e degli effetti); salvataggio `0x0020EF20` (BL a `0x0020EF36` → `ext_save`: blocco
in uso → banco, con il controllo; poi Korg segna il gruppo da salvare). SysEx di programma Korg ricevuto
(`0x0020F33C`, BL a `0x0020F346` → `ext_sysex`): blocco di quel programma ai default. Import voce DX7: blocco
in uso ai default.

Le pagine FUNC+EDIT (MOD rt rS FX dt Fb FL LF), FUNC + TRANSPOSE / VELOCITY e i CC 74 / 71 cambiano lo stato
come prima e poi lo copiano nel blocco in uso (`ext_capture`). Il caricamento di un pattern non imposta più
i tipi di effetto (`load_types`), le pagine non li scrivono più nel pattern (`set_fxmod`): i bit dei passi
13–16 (PRB3) sono liberi.

## Motore VA
Bit 7 del byte 110 del programma (ignorato da Korg, conservato da salvataggio, cambio programma e SysEx di
programma Korg; l'import DX7 lo azzera). All'inizio della nota `va_kernel_of` (BL a `0x0020DFA8`, era la
tabella dei kernel `0x00204578`) sceglie `va_kernels`: un kernel per algoritmo con la stessa sequenza di tipi
di operatore dei kernel Korg (ricavata dal costruttore e verificata). Ogni operatore: codice Korg di pitch,
inviluppo e livello (copia di `0x0510–0x05B5`), poi una routine d'onda al posto del seno: SAu SQR P25 P12 TRI
SIN NOI S-H. Parola +0x14 del record: routine (bit 0–13) e valore tenuto del S-H (bit 14–31); 0 = operatore
spento (livello d'uscita 0). Dente di sega e impulsi con polyBLEP (alias a 1760 Hz: −30 dB contro −14 dB
dell'onda ingenua). Impulsi: percorso veloce senza stack lontano dai fronti.

## Processore (istruzioni per campione, interrupt completo, sei voci)
| Caso | max | media |
|---|---|---|
| Korg 1.12 | 2854 | 2819 |
| FM 1.28 | 2932 | 2897 |
| FM + filtro + 2 LFO | 3465 | 3239 |
| VA 2 SAu | 2164 | 2108 |
| VA 2 SQR + filtro + LFO | 2790 | 2531 |
| VA 6 SAu + filtro + LFO | 3887 | 3631 |
| VA 6 SQR + filtro + LFO | 4255 | 3969 |
| VA 6 P12 + filtro + LFO | 4245 | 3923 |
Bilancio: ~4311 cicli per campione. Il caso peggiore VA è vicino al limite (istruzioni, non cicli): da
verificare sullo strumento.

## Prove (`verify_128.py`)
edit_native (148 parametri Korg identici), block_edit (35 parametri: letture, setter, getter, segno di
modificato, stato), block_program (salvataggio con controllo, cambio programma, FUNC + manopola e CC nel
blocco, pattern che non cambia i tipi, SysEx e import DX7 → default), block_journal (settori con i blocchi,
ricarica, settore Korg → default, controllo sbagliato → default solo per quel programma), edit_wave,
edit_engine, va_sine (VA tutto SIN = FM Korg campione per campione, 32 algoritmi), va_waves (ogni routine
contro un modello indipendente, alias), va_storage, va_off, cpu.

# Note tecniche 1.22: spazio, phaser e tremolo al posto del chorus, LOFI a nastro

Base: 1.21. Sorgenti `src/fm2_122.S` (ITCM, codice audio), `src/fm2_122_sram.S` (SRAM, codice non audio, nuovo),
`src/fm2_122_flash.S` (flash a `0x0020FC40`). Prove: `verify_122_mod.py` (nuovo), `verify_118.py` (modello del
LOFI aggiornato), `verify_122.py`, `verify_122_more.py`; verifica completa `verify_patch.py` 97/97 e
`verify_release.py`.

## Spazio: codice non audio in SRAM
- Nella 1.21 l'ITCM era pieno (codice fino a `0x3BD4`, limite `0x3C00`).
- Il caricatore Korg copia `0xC000` byte della sezione ff13 a `0x20010000`. La coda `0x200164B0–0x2001C000`
  (22,4 KB) è riempimento FF: nessun riferimento nel firmware e nessuna scrittura a runtime (verificato
  nell'emulatore). `build_patch.py` controlla che sia ancora tutto FF prima di usarla.
- Il codice che non gira nell'interrupt audio (pannello, pagine, letture, tasti, clock, catene, start) è in
  `src/fm2_122_sram.S` a `0x200164B0`, con una tabella di 25 `b.w` nello stesso ordine di quella ITCM. Le voci
  ITCM non audio sono trampolini `ldr pc, =0x200164B0+4k+1`: gli agganci nel firmware non cambiano.
  Dall'SRAM le funzioni ITCM si chiamano con `ICALL` (`ldr r12, =sym; blx r12`); i simboli ITCM sono esportati
  in `itcm_symbols.inc` al momento della costruzione.
- Nell'ITCM restano il codice audio (delay, modulazione) e i dati: codice `0x2000–0x2A48`, tabella del phaser
  `0x3A00`, stato della modulazione `0x3B80`, stato del delay `0x3F80`. SRAM fino a `0x20017EB4`; flash fino a
  `0x0020FF74` (limite `0x0020FFF0`).

## Modulazione: CHORUS / PHASER / TREMOLO
- L'interrupt audio (ITCM `0x0010`) chiama il chorus Korg `0x12AC` tramite il literal ITCM `0x0238` (`0x12AD`)
  con r0, r1 = voci L, R >> 8 e somma il risultato (<< 8) al segnale diretto. Il chorus viene chiamato sempre,
  anche spento (livello obiettivo 0): costo uguale acceso o spento.
- Il literal `0x0238` ora vale `0x2061` (voce 24 della tabella ITCM, `mod_audio`). Con tipo 0 e nessuna
  transizione: salto diretto a `0x12AD` (uscita identica alla 1.12, verificato sull'ISR intero).
- Stato `0x3B80`: +00 tipo richiesto, +01 tipo attivo, +02 SYNC, +03 STEREO/PAN, +04 divisione SYNC 0..6,
  +05 slider LIBERO, +06 risonanza, +07 forma, +08 transizione (0 regime, 1 dissolvenza in uscita, 2
  azzeramento, 3 dissolvenza in entrata), +0A contatore, +0C fase LFO, +10 incremento LIBERO, +14..+30 stati
  degli allpass L/R, +34/+38 ultima uscita L/R, +3C sedicesimi dallo start, +40 risonanza Q15.
- Livello e acceso/spento sono quelli del chorus Korg (stato `0x200011D0`: +40 livello levigato, +44
  obiettivo 0..`0x1E00000`, FUNC + 3 mette l'obiettivo a 0). `mod_common` leviga il livello come il chorus Korg.
- Cambio di tipo: dissolvenza del segnale effetto in 256 campioni (5 ms), azzeramento delle linee del chorus
  Korg `0x20000070–0x200011CF` (1112 parole, 8 per campione) solo tornando al chorus, azzeramento degli stati
  del phaser, dissolvenza in entrata di 256 campioni.
- LFO: LIBERO, fase += 2^32 / (50 · periodo in ms), periodo da tabella (20000 ms · 0,005^(v/127), da 20 s a
  100 ms). SYNC: fase = ((sedicesimi & (k−1)) · f16 + e) · ⌊(2^32−1)/(k · f16)⌋, con k = 2^divisione
  sedicesimi per giro, f16 = campioni per sedicesimo misurati dal delay (1.18), e = campioni dall'ultimo
  sedicesimo; senza clock per più di due sedicesimi continua da solo alla stessa velocità. Il contatore dei
  sedicesimi (`+3C`) è incrementato da `tempo_tick` e azzerato allo start.
- Seno parabolico: s = x · (32768 − |x|) / 2^13, x = fase >> 16.
- **Phaser**: 4 allpass del primo ordine per canale, y = a·x + s, s = x − a·y (`smmla`/`smmls` Q31),
  coefficiente a = (tan(πfc/fs) − 1)/(tan(πfc/fs) + 1) da una tabella di 65 valori (fc da 120 a 1600 Hz,
  esponenziale) interpolata linearmente sul seno; retroazione dall'uscita del canale, risonanza 0..100 ×180
  (Q15, al massimo 0,55); con STEREO il canale R ha la fase +90°. Uscita = y · livello / 2^25 (al massimo 0,94):
  sommata al diretto dà le tacche del phaser.
- **Tremolo**: profondità = livello normalizzato (0..65535, al massimo 1); u = seno · (16 + forma·41/64) / 16
  saturato (forma 100 = quasi quadra), 0..65535; PAN: uR = 65535 − uL. Uscita = −x · profondità · u / 2^24:
  sommata al diretto dà un guadagno da 1 a 1 − profondità.
- Il tipo è salvato nel pattern nei bit 7 degli step 15–16 di PRB3: gli step 13–16 sono ora un campo di 4 bit
  (bit 0–1 effetto REVRB/DELAY/LOFI, bit 2–3 modulazione), scritto da `set_fxmod` e letto a ogni caricamento da
  `load_types` (chiamato da `load_fx` in flash). Con questo i bit liberi del pattern sono finiti. Pattern senza
  blocco = REVRB e CHORUS.
- Pagine 10 MOD, 11 rt, 12 rS/Fo, 13 CR (14 modalità). Messaggi nuovi 30 STEREO, 31 PAN. La lettura del livello
  "CHORS nnn" diventa "PHASE nnn" / "TREMO nnn" (`mod_label`).

## LOFI a nastro
- Nel campione leggero della coppia (1.18) si calcola la posizione di lettura `+44` = D + wow + flutter:
  wow 0,54 Hz ±16 posizioni (±0,64 ms), flutter 6,8 Hz ±0,25 posizioni, limitata alla linea. Il DELAY legge a D.
- Retroazione: smorzamento d += (y − d)/2 (circa 2,8 kHz a 25 kHz), taglio dei bassi h += (d − h)/64 (circa
  60 Hz), uscita d − h; saturazione morbida x − x³/(3·2^30) sul valore scritto (al posto del limitatore).
- Stato `0x3F80`: +44 posizione di lettura, +48/+4C taglio dei bassi L/R, +50/+54 fasi di wow e flutter.

## Carico del processore (istruzioni per campione, ISR intero, 6 voci)
1.12 riverbero + chorus 2848; 1.22: CHORUS + REVRB 2884 (involucro del riverbero, come dalla 1.18),
PHASER + REVRB 2922, TREMOLO + REVRB 2854, PHASER + LOFI ping-pong 2869, PHASER + DELAY ping-pong 2835.
La combinazione phaser + riverbero è la più pesante: +2,6% sulla 1.12, +1,3% sulla 1.21 (provata sullo
strumento). Da controllare sullo strumento (PROVE).

## Prove nuove (`verify_122_mod.py`)
Tabella e stato iniziale; phaser e tremolo uguali al modello Python campione per campione (STEREO/MONO, PAN,
LIBERO/SYNC, risonanza, forma, livello che cambia); tacche del phaser, profondità e periodo del tremolo, fase
SYNC; CHORUS identico alla 1.12 sull'ISR intero; transizioni (durate, linee del chorus azzerate, nessuno scatto);
CPU; pagine e letture; tipi nel pattern (selezione, catena, pagine che scrivono solo i propri bit); FUNC + 3 e
livello. Il modello del delay (`verify_118.py`) comprende il LOFI a nastro.

## Prova sullo strumento
Solo emulatore per ora.

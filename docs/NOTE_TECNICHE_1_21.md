# Note tecniche 1.21: catena semplificata, FUNC in catena, copia, REC FISSO, Program Change, effetto nel pattern

Base: 1.19. Sorgenti `src/fm2_121.S`, `src/fm2_121_flash.S`; prove `verify_121.py`,
`verify_121_more.py` (`fx_per_pattern`, `add_keeps_step`).

## Tipo di effetto nel pattern
- Il firmware Korg salva già nel pattern riverbero acceso/spento (bit 2 del byte 0x45) e livello (0x49); il chorus
  ha il livello in 0x48. Il tipo di STROMBOLI (`0x3F80`: 0 REVRB, 1 DELAY, 2 LOFI) era generale.
- Ora è nei bit 7 delle probabilità degli step 13–14 del blocco PRB3 (campo `set_bits`/`block_bits` con primo
  indice 12; restano liberi gli step 15–16). La pagina FX scrive il campo nel pattern in uso.
- Ogni caricamento di pattern (`0x00208900`, 5 chiamate: `0x00208C7C`, `0x00208CCE`, `0x0020900C` tramite
  `chain_load`, `0x00209144`, `0x002092AE`) passa per `load_fx` (voce +1C della tabella flash), che dopo il
  caricamento imposta `0x3F80` dal campo. Senza blocco PRB3 (pattern Korg o precedenti) = REVRB. Il cambio di tipo
  usa la dissolvenza e l'azzeramento della 1.18.
- dt e Fb restano generali (non ci sono bit). Tornando al firmware Korg il pattern resta valido (i bit sono ignorati).

## Aggiunta alla catena senza ricominciare
- `chain_force` chiamava `0x0020C5D6`, che con la catena attiva mette lo step in attesa (`0x200031A3` =
  `CLOCK+0xB`) a 0xFF: il pattern ripartiva da capo a ogni tasto aggiunto (anche con CC nella 1.19).
- Ora, se il sequencer suona, lo step viene rimesso com'era: il pattern continua e la catena prosegue alla fine
  del giro. Da fermo resta 0xFF (PLAY parte dall'inizio).

## Spazio
ITCM fino a `0x3BD4` (limite `0x3C00`), flash fino a `0x0020FF88` (limite `0x0020FFF0`).

Base: 1.19. Sorgenti `src/fm2_121.S` (ITCM) e `src/fm2_121_flash.S` (flash a `0x0020FC40`).
Prove: `verify_121.py` e `verify_121_more.py`; verifica completa `verify_release.py` 95/95.

## Catena: solo CR
- Pagina CR (modalità 10; ora 11 modalità, P → … → Fb → CR → P). Lo slider scrive lo stesso valore in
  `0x1D00+0` (catena libera) e `+2` (registrazione su catena). CR ON → OFF: `+4` = 0 e flag chain nativo
  `0x20003E34+0x15` = 0, il pattern corrente continua.
- Tolti: pagine CH e CC, cattura (`cap_wrap`, aggancio `0x00208E30`), lista di cattura `0x1C80`, `chain_msg`
  ("CATENA nn"). Spiegazione delle scritte della 1.19: "CC REC" = stato 2 della cattura (CC su ON poi PLAY),
  "CATENA nn" = messaggio allo STOP dopo una cattura.
- Tasto 16 nella pagina CR: `0x1D0F` REC AUTO (0) / REC FISSO (1), messaggi 28/29; con REC FISSO la pagina
  mostra "CR ON   F".
- Stato `0x1D00`: +0E pattern suonato prima + 1 (0 = nessuno; scritto in `chain_next`), +0F REC FISSO.

## REC con CR ON e salvataggio
- Nel firmware Korg REC non risponde mentre una catena suona (anche a sequencer fermo): era il "REC non più
  selezionabile" della 1.19. Con CR ON il controllo "catena attiva" del pannello risponde "no" al gestore di
  REC (vedi sotto), quindi REC va acceso e spento quando si vuole.
- `trans_hook`: con CR ON e catena, quando REC passa da acceso a spento (a mano, dopo un motion) oppure il PLAY
  si ferma con REC acceso, `save_if_modified(CLOCK+6)` (WRITE nativo `0x20815C` solo se il pattern è cambiato).

## FUNC durante la catena
- Il pannello chiede "catena attiva?" tramite il veneer SRAM `0x200150E0` (literal `0x200150E4`, originale
  `0x0020C5D3`: `ldrb r0, [r0, #0x15]`). Literal sostituito con `chain_q` (ITCM). Con CR ON risponde 0 se il
  chiamante (LR) è uno di: REC `0x20011AB0`, FUNC + tasti `0x200111D8`, FUNC + MEMORY `0x20011F3C`,
  destinazione del WRITE `0x20010B80`, FUNC + PLAY `0x20011A28`, FUNC + EDIT `0x2001207C`,
  FUNC + SAVE `0x20011D70`. Negli altri casi (e con CR OFF) risponde come Korg.

## Copia del pattern (FUNC + MEMORY)
- In `chain_q`, chiamante FUNC + MEMORY: `copy_previous`. Condizioni: REC acceso, pattern precedente noto e
  diverso dal corrente, pattern corrente vuoto (byte +24..+29 gate e +43..+107 motion di tutti i 16 step a zero).
- Copia dei 1920 byte dalla banca in RAM (`[0x2001D08C] + n·1920`) al pattern in uso `0x2001E12C`, WRITE nativo
  sul pattern corrente, ricaricamento con `0x208900` mantenendo lo step (`CLOCK+0xB`), messaggio "CPY 03-04".
  Altrimenti WRITE Korg.

## REC FISSO
- BL a `0x00209062` (era `0x00208598`, REC spento alla fine di un giro di motion) → voce +18 della tabella flash
  (`motion_end`): con `0x1D0F` = 1 non fa niente.

## Program Change in ingresso
- Il dispatcher dei messaggi MIDI `0x00207D98` gestisce solo 0x80, 0x90, 0xB0, 0xE0: il Program Change è
  ignorato dal firmware Korg (verificato nell'emulatore).
- Literal del veneer `0x20014F64` (era `0x00207D99`) → voce +0C della tabella flash (`midi_in`): per 0xCn
  controlla la ricezione dei messaggi (`0x20002F4C+0x1C4`) e il canale (`0x00205C9C`), poi
  `0x200133A4(0x20002A08, PC mod 64, 1)`, la stessa funzione usata dalla manopola PROGRAM
  (`0x20013458`: programma corrente in `[0x20002A08]`, limite 0..63). Gli altri messaggi vanno al dispatcher Korg.

## Prova sullo strumento
Verificato nell'emulatore (pannello, clock, journal, MIDI) e su un volca fm2 vero (novembre 2026).

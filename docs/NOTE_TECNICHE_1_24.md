# Note tecniche 1.24: ratchet, microtiming e swing, LOFI più sporco, ordine delle pagine

Base: 1.23. Sorgenti `src/fm2_124.S` (ITCM), `src/fm2_124_sram.S` (SRAM), `src/fm2_124_flash.S` (flash).
Prove nuove `verify_124.py`; `verify_118.py` aggiornato (modello del LOFI); verifica completa `verify_patch.py`
e `verify_release.py`.

## Clock del sequencer (analisi)
- `0x00208CF8(r0, r1)` è chiamato a ogni tick del clock interno con r0 = 0 (72 tick per sedicesimo,
  `CLOCK+0xC` = tick 0..71, `CLOCK = 0x20003198`). Con r0 = 1 (impulso di sincronia) elabora in un colpo i
  tick che mancano allo step. Ogni tick è un giro del ciclo `0x00208D7E … 0x00209096` (r8 = tick da fare).
- Al confine dello step (tick 72): rilascio delle note normali `0x0020BB50` (`0x00208E0C`), contatore
  `CLOCK+0xB` + 1, LED `0x0020FC10`, poi la routine dello step `0x0020B7BE` (`0x0020903E`).
- Gate: tabella delle voci dello step `0x20003DC4` (6 × 4 byte: nota, gate, 1 normale / 2 legata, voce);
  il gate è contato in unità di `CLOCK+0xE` tick da `0x0020BB28`, nota spenta da `0x0020B774`.

## Agganci nuovi
- BL `0x00209096` (era `ADD.W r8, r8, #-1`) → `seq_tick` (voce 27): fa il decremento e, a ogni tick,
  gestisce lo step in ritardo, i colpi del ratchet, la previsione e lo step in anticipo.
- BL `0x00208E0C` (era `0x0020BB50`) → `bnd_release` (voce 28): niente rilascio sul confine se lo step
  successivo è già stato suonato in anticipo.
- `step_map` (1.23) ora decide: step già suonato in anticipo → niente; ritardo > 0 → in attesa; altrimenti
  `fire`.

## Microtiming e swing
- Ritardo dello step = microtiming dello step suonato (−36…+36) + swing sui contatori dispari
  (swing 0…25 → (s·36 + 12)/25 tick, cioè 50…75 %), limitato a −36…+66; contatore 0 mai in anticipo.
- In ritardo: `step_map` memorizza step, contatore e tick; `seq_tick` lo suona quando `CLOCK+0xC` arriva.
- In anticipo: a metà step (tick 36, se non c'è uno step in attesa) `seq_tick` calcola lo step successivo
  (`step_of`, che lo mette anche in cache per il LED) e il suo ritardo; se è negativo lo suona al tick
  72 + ritardo, dopo aver rilasciato le note dello step in corso, e segna il contatore (`+27`).
- `prob_entry` conta i giri sul contatore dello step suonato (`+22`), non su `CLOCK+0xB`.

## Ratchet
- Per step: colpi 1–4, probabilità 100/75/50/25 %, andamento PARI/CALA/CRESCE. `fire` tira la
  probabilità (PRNG nativo `0x002094A4`) prima di suonare, così il primo colpo ha già il volume giusto.
- Distanza = tick rimasti nello step / colpi (72 normale, 72 − ritardo se in ritardo). Ogni colpo:
  rilascio delle note normali (`0x0020BB50`), routine dello step con il flag "colpo" (`+23`: niente nuova
  decisione di probabilità/condizione, niente nuova mutazione), gate delle note nuove × distanza / 72.
- Volume: CALA v·(n − k)/n, CRESCE v·(k + 1)/n (`rat_vel` in `seq_note`).
- Solo se lo step è stato suonato (`+24` = decisione di `prob_entry`).

## Salvataggio
- Record di 35 byte nei byte 108–111 degli step 2–10 (byte 300… del pattern; mai letti da Korg, vedi
  1.23): `A5`, swing, ratchet × 16, microtiming × 16, controllo = xor dei 34 byte ^ `5A`. Scritto dalle
  pagine (`save_seq2`), letto a ogni caricamento (`load_seq2` da `load_types`); non valido = tutto spento.
- Stato in ITCM `0x3980` (128 byte, descritto nel sorgente prima di `step_map`).

## LOFI
- Soffio: xorshift32 (`0x3F80+0x58`, seme `0x9E3779B9`), (rumore >> 24) · fb / 2^16 aggiunto al valore
  scritto (mono; L e R da bit diversi in ping-pong), prima della saturazione.
- Fb fino a 120 con LOFI (pagina Fb: massimo 120 se FX = LOFI): guadagno d'anello > 1, limitato dalla
  saturazione x − x³/3 (ampiezza massima 2/3). DELAY limita fb a 100 (`FB_MONO`/`FB_PP`).
- Wow × 2,5 (±0,8 ms), flutter × 2.
- CPU: LOFI ping-pong 2843 istruzioni per campione (riverbero 1.12: 2848).

## Pagine
- 18 modalità; ordine di navigazione da `mode_order`: P C GL HU OC SC tn MOD rt rS FX dt Fb dr Mu rA ti CR
  (numeri di modalità invariati, rA = 15, ti = 16, CR = 17).
- rA/ti: i tasti scelgono lo step come in P/C; il tasto dello step già scelto cambia l'andamento (rA,
  messaggi PARI/CALA/CRESCE) o passa allo swing (ti).
- Il costruttore controlla ora che ogni ADR all'indietro punti a un'etichetta: llvm-mc 18 assembla senza
  errore un ADR oltre 4095 byte (era successo a `mod_label`).

## Prove (`verify_124.py`)
Linea temporale di note-on/note-off tick per tick identica alla 1.12 a funzioni spente (anche con REC);
colpi 2/3/4, volumi, rilasci, probabilità 25/50/75, niente colpi su uno step muto; ritardi, anticipi, step 1
mai in anticipo, swing 50/58/75, ratchet dopo ritardo e anticipo, catena sulla battuta; ordine delle pagine,
letture rA/ti/SWING, record (WRITE, caricamento, non valido); LOFI: soffio, autooscillazione limitata, Fb 120
con LOFI e 100 con DELAY.

## Prova sullo strumento
Solo emulatore per ora.

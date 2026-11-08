# Note tecniche 1.19: chain evoluto

## Chain Korg (1.12, verificata nell'emulatore con il modello del journal)
- 16 pattern da 1920 byte, copia in RAM a `[0x2001D08C]` = `0x20020000`; il
  caricamento `0x208900(n)` legge da lì; il journal NOR li scrive dopo.
- Selezione: pannello in modo `0x13` (MEMORY tenuto) → `0x20011886` → veneer
  SRAM `0x20014FC0` (literal `0x20014FC4` = `0x0020C611`) →
  `0x20C610(chain, tasti tenuti, tasti prima)`. Intervallo dal tasto più basso
  al più alto; con REC (`0x20DB70(0x20003F8C)`, stato 2 o 3) un pattern solo.
  Carica subito il primo (`0x208CB8`). Poi `0x20014FB8` (→ `0x208C5C`) mostra
  il pattern.
- Struttura `0x20003E34`: +0 step del cambio, +2 maschera, +4 lista[16],
  +0x14 numero, +0x15 modo chain, +0x18 posizione.
- Clock `0x208CF8` (CLOCK `0x20003198`: +6 pattern corrente, +0xB step): allo
  step `chain+0` → `0x20C5B0` (avanza) → `0x208900` (carica) → `0x20C5D6`
  (nuovo step di cambio). Dopo il caricamento lo step riparte da 0.
- Stato del trasporto `0x20003F8C`: bit 0 PLAY, bit 1 REC. Ogni cambio passa
  dal veneer `0x20FA68` (literal `0x20FA6C` = `0x20010B11`).
- WRITE nativo `0x20815C(n)`: `0x200134EC(PATTERN, n)` (copia in RAM e segna il
  journal), CLOCK+6 = n. Il firmware lo chiama anche dal clock (WRITE in
  attesa, CLOCK+0x1A).
- Start dall'inizio `0x2090C0(..., r2 = 1)`: in modo chain azzera la posizione
  e ricarica il primo pattern della lista.
- Motion: registrare una manopola fissa `0x20003638` allo step di partenza;
  tornati a quello step il firmware esce da REC (`0x208598`).

## Codice
- ITCM (`src/fm2_119.S`): pagine CH/CC/CR, flag di MEMORY premuto
  (`panel_button`), azzeramento di voce/ripetizione nello start dall'inizio
  (`start_hook`), testi `chain_disp` ("CH05  P07") e `chain_msg`
  ("CATENA nn"), nomi in `0x1980`.
- Flash (`src/fm2_119_flash.S`, blocco a `0x0020FC40`, nel riempimento FF
  della sezione applicativa; 6 voci di salto):

| Aggancio | Originale | Nuovo |
|---|---|---|
| literal `0x20014FC4` (veneer selezione) | `0x0020C611` | `chain_build` |
| BL `0x00209006` | `0x20C5B0` | `chain_next` |
| BL `0x0020900C` | `0x208900` | `chain_load` |
| `0x00208E30` (`ldrsb.w r3,[r4,#0xb]`) | — | BL `cap_wrap` |
| literal `0x0020FA6C` (veneer trasporto) | `0x20010B11` | `trans_hook` |
| BL `0x0020C666` (controllo REC nella selezione) | `0x20DB70` | `cr_check` |
| literal `0x20014FBC` (veneer lettura pattern) | `0x00208C5D` | `chain_disp` (ITCM) |

- Dati in ITCM: lista `0x1C00` (64 × {pattern, ripetizioni}), cattura
  `0x1C80`, stato `0x1D00` (+0 CH, +1 CC 0/1/2, +2 CR, +3 voci, +4 catena
  nostra attiva, +5 voce, +6 ripetizione, +7 MEMORY premuto, +8 voci catturate,
  +9 pattern del giro catturato, +0xA ultimo stato del trasporto, +0xB salta il
  prossimo caricamento, +0xC giro in corso, +0xD lettura nostra). Tutto a zero
  all'accensione.

## Funzionamento
- **CH LIBERA**: i tasti premuti (nuovi rispetto a prima) si aggiungono in
  ordine; lo stesso pattern di seguito aumenta le ripetizioni (max 99), max 64
  voci. Il primo tasto passa dalla selezione Korg a tasto singolo (carica il
  pattern). Con più di un giro: modo chain nativo forzato (lista nativa = prime
  16 voci, maschera, numero ≥ 2, `0x20C5D6`), e `chain_next` restituisce il
  pattern seguente della nostra lista. Ripetizione dello stesso pattern:
  `chain_load` salta il caricamento. Con CH KORG la selezione è quella nativa e
  chiude la nostra catena. In REC senza CR resta un pattern solo.
- **CC**: armata (1) → PLAY la avvia (2). `cap_wrap` vede l'inizio di ogni giro
  (step 0 dopo uno start o un caricamento, oppure step > 15) e registra il
  pattern del giro finito, poi campiona `CLOCK+6`. Allo STOP: il giro fermo
  sull'ultimo step conta; la cattura diventa la lista, CC = 0, primo pattern
  caricato, catena forzata, "CATENA nn". Nessun giro completo: resta armata.
- **CR**: `cr_check` restituisce "non in REC" alla selezione nativa, quindi la
  catena Korg resta intera in REC; anche la catena libera accetta voci. In
  `chain_next` e allo STOP (se REC era attivo e c'è una catena): se il pattern
  in memoria (`0x2001E12C`) differisce dalla sua copia in RAM → `0x20815C`.

## Prove (verify_119.py)
power_on; korg_unchanged (selezione e riproduzione identiche alla 1.18 in 5
casi, riduzione in REC); free_chain (ordine, ripetizioni, salto del
caricamento, ricarica al ritorno, nuova sessione, tasto singolo, oltre 16 voci,
limite 64, ripartenza, ritorno a KORG); free_chain_rec; capture (pattern Korg
cambiati a mano, catena Korg in riproduzione, giro parziale, cattura vuota, CC
spento); cr_save (CR OFF come Korg; CR ON: salvataggio al cambio e allo STOP,
nessun salvataggio dei pattern non cambiati, persistenza nel journal NOR, altri
pattern intatti); panel_memory (percorso reale MEMORY + tasti, lettura,
percorso KORG identico all'originale); pages.

Non provati sullo strumento: tempi reali del cambio pattern, caricamento a
metà giro del primo pattern di una catena nuova (come la selezione Korg).

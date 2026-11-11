# Note tecniche 1.23: livello del chorus, phaser più risonante, direzione e mutazione per pattern

Base: 1.22. Sorgenti `src/fm2_123.S` (ITCM), `src/fm2_123_sram.S` (SRAM), `src/fm2_123_flash.S` (flash).
Prove nuove `verify_123.py`; `verify_122_mod.py` aggiornato (modello del phaser); verifica completa
`verify_patch.py` 101/101 e `verify_release.py`.

## FUNC + manopola 7 (livello del chorus)
- Lo scanner delle manopole `0x00205AB0` chiama `0x002059D0(indice, valore, r2 = 0)`. Nel gestore Korg, con FUNC
  premuto (`0x0020FA60` ≠ 0) e r2 = 0, l'indice 7 diventa r2 (= 0, livello del chorus) e il 9 diventa 5
  (riverbero). La manopola 7 è di tipo 1 (ADC >> 5, 0..127).
- Il prologo `0x002059D0` è agganciato dalla 1.14 (`panel_adc`); dalla 1.16 l'indice 7 andava sempre ad
  `arp_knob` (ARP TYPE a 17 posizioni), anche con FUNC: il valore del chorus veniva ricalcolato come posizione
  di arpeggio (0, 13, 26 … 116, poi 13). Era così dalla 1.16 per il chorus e quindi anche per phaser e tremolo.
- Ora `arp_knob` con r2 = 0 chiede `0x0020FA60`: con FUNC passa al gestore Korg invariato. Verificato
  sull'intera corsa della manopola (ADC 0..4095 e ritorno): testi e livello identici alla 1.12; manopola 7
  senza FUNC identica alla 1.22.

## Phaser
- Ingresso dell'anello: u = x · gin + y_prec · fb (Q15), fb = risonanza · 301 (al massimo 0,92), gin = 1 − fb/2
  (`+42`), poi limitato a ±2^24 e saturato morbido u − u³/(3·2^48) (calcolato su u >> 9: la parte lineare
  resta a piena risoluzione).
- 4, 6 o 8 stadi (`+09` = 0, 1, 2; stati 5–8 a `+44..+50` L e `+54..+60` R, azzerati al cambio di tipo).
- Tabella dei coefficienti da 100 a 2400 Hz. Uscita = y · (livello + livello/16) / 2^25 (al massimo 0,996).
- MONO: una sola catena su (L + R)/2, stessa uscita sui due lati (metà calcolo).
- Pagina rS: tasto 16 = stadi (solo con il phaser), cifra 4/6/8 in fondo. All'accensione 6 stadi, risonanza 50.
- CPU (istruzioni per campione, ISR, 6 voci): 1.12 riverbero + chorus 2848; 1.22 phaser 4 stadi + riverbero
  2922 (provata sullo strumento); 1.23 phaser + riverbero: 4 stadi 2944, 6 stadi 2972, 8 stadi 2992,
  8 stadi MONO 2908; 8 stadi + LOFI ping-pong 2939.

## Direzione per pattern (pagina dr, modalità 13)
- Il clock `0x00208CF8` conta lo step in `CLOCK+0xB` (0..15, poi 0): da lì dipendono fine giro, catena,
  motion, registrazione. Non viene toccato.
- BL `0x0020903E` (clock → routine dello step `0x0020B7BE`) e BL `0x00208E42` (clock → LED dello step
  `0x0020FC10`) passano per `step_map` / `led_map` (voci 25 e 26 delle tabelle), che sostituiscono r0 con lo
  step da suonare (`step_of`): AVANTI c, INDIETRO 15 − c, PENDOLO avanti e indietro a giri alterni (verso
  invertito quando c = 0), CASO uno step a caso (PRNG nativo `0x002094A4`). Con REC (`0x20003F8C` bit 1)
  sempre avanti. Calcolato una volta per valore del contatore (il LED viene prima nel tick), cache
  `0x3F38`/`0x3F39`, azzerata allo start.
- `prob_entry` conta i giri (condizioni) sul contatore `CLOCK+0xB`, non sullo step suonato.
- Il motion (`0x0020B668`) resta sul contatore: segue il tempo.

## Mutazione (pagina Mu, modalità 14)
- In `seq_note` (BL `0x0020BA6E`, nota di ogni voce dello step prima di scala dal vivo, humanize, ottava):
  alla prima nota di ogni step suonato (`0x3F3A` messo da `step_of`), con probabilità Mu % lo step riceve uno
  spostamento nuovo d ∈ [−R, R] (R = 3 o 7, uniforme, 0 compreso) in `0x3F70 + step`.
- La nota diventa `scale_walk(nota, d)`: portata in scala verso l'alto, poi spostata di d gradi nella scala e
  tonica delle pagine SC/tn (`0x3F31`, `0x3F32`, maschere `0x1F70`), anche con la scala spenta; limiti 0..127.
  Con d = 0 la nota resta quella del pattern.
- Gli spostamenti restano fino alla mutazione successiva dello stesso step; si azzerano a ogni caricamento
  di pattern. Il pattern non viene mai scritto.

## Salvataggio di dr e Mu
- Byte 108–111 dello step 1 (byte 188–191 del pattern): mai letti dal firmware Korg durante la riproduzione
  (verificato con un controllo di lettura sulla memoria del pattern), copiati con il pattern dal WRITE e dai
  caricamenti. Blocco: `A4`, direzione | ampiezza << 2, Mu, controllo = xor dei tre ^ `5A`. Senza blocco
  valido: AVANTI, Mu 0, ampiezza 3 (pattern Korg e precedenti).
- Le pagine scrivono il blocco nel pattern in uso (`save_seqx`), `load_types` lo legge dopo ogni
  caricamento (`load_seqx`).

## Pagine e spazio
- 16 modalità: … rS (12), dr (13), Mu (14), CR (15).
- ITCM codice `0x2000–0x2C9C`, SRAM fino a `0x20018234`, flash fino a `0x0020FF74`. Tabelle a 27 voci.

## Prova sullo strumento
Solo emulatore per ora.

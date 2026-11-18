# Note tecniche 1.25: tre parti (split e layer)

Base: 1.24. Sorgenti `src/fm2_125.S` (ITCM), `src/fm2_125_sram.S` (SRAM), `src/fm2_125_flash.S` (flash, invariato).
Prove nuove `verify_125.py`; verifica completa `verify_patch.py` e `verify_release.py`.

## Motore Korg (analisi)
- Allocazione delle voci DSP: `0x00209574(sorgente, nota, velocity)`. Stato `VM = 0x200031C8`: `+7` modalità
  (tabella `0x2000B398`, 10 byte per modalità), `+8` voci per nota (1, oppure 2 / 3 con UNISON), `+0x27C` indice
  a rotazione. Sei record da `0x34` byte a `VREC = 0x2000330C`: `+0` tempo (`0x00204740`), `+4` stato (0 libero,
  1 acceso, 5 in rilascio), `+5` nota, `+6` altezza, `+0x10` indice della voce nella nota, `+0x13` velocity.
  Per ogni voce della nota: primo record libero, altrimenti uno in rilascio, altrimenti il record numero k.
  Poi `0x0020E814(voce, altezza, velocity, pan)` (BL a `0x00209746`).
- Arpeggiatore: `0x002093FE(sorgente, altezza, velocity)` → maschera delle voci avviate, stesso numero di voci
  per nota (BL a `0x00209488`).
- Note-off: `0x00209870(sorgente, nota)` rilascia tutti i record accesi con quella nota (`0x002094E6(maschera)`
  → `0x0020E7C8(voce)`) e li mette in rilascio.
- Avvio della voce: `0x0020E6DC(voce, altezza, velocity, pan)`, subito o più tardi dal servizio `0x0020E8C2` se
  la voce sta ancora suonando (`0x0020E814` la sfuma e lascia l'avvio in attesa). A ogni avvio:
  `0x0020E518(destinazione 0x200055A4, programma 0x20004F5C, macro 0x20005358)` copia i 128 byte del programma
  e applica le manopole EG (macro `+0..+3`) ai portanti o ai modulatori secondo l'algoritmo, **letto dal
  programma in uso** (`0x20004F5C+0x6E`, non dalla sorgente), e spegne gli operatori con macro `+5..+10` = 0.
  Poi trasposizione, LFO (copiato nella voce), `0x0020DF14`. La voce (624 byte) non rilegge più il programma:
  il rendering non accede a `0x20004F5C` (verificato con un controllo di lettura).
- Guadagno della voce: `+0x38` sinistra, `+0x3C` destra, scritti all'avvio dal pan (somma `0x20000`), usati
  dal rendering come guadagni lineari (verificato: dimezzandoli il livello si dimezza).
- Banco dei programmi in RAM: puntatore a `0x2001D090` (64 × 128 byte, stesso formato del programma in uso;
  nome ai byte 118–127).

## Altro motore Korg usato dalla seconda parte
- `0x0020DF14` (chiamata da `0x0020E6DC`, quinto argomento sullo stack = voce) scrive nella voce le profondità
  dell'LFO del programma: `+0x10` sensibilità di pitch (tabella `0x2000B84C`: 0 10 20 33 55 92 153 255),
  `+0x11` profondità di pitch (PMD × 165 >> 6), `+0x12` profondità di ampiezza. Il rendering le legge dalla
  voce a ogni campione (`0x11F2`, `0x11FE`, `0x121A`): basta scriverle per cambiare vibrato e tremolo.
- Dispatcher MIDI `0x00207D98(sorgente, messaggio)`, raggiunto dal veneer `0x20014F64`: accetta solo il canale
  del volca (`0x200029FC+9`) e gestisce 0x80, 0x90, 0xB0 (CC 6, 64, 98–101, 120–124 e quelli della tabella
  `0x2000B377`), 0xE0. CC 1, aftertouch e Program Change sono scartati.
- Note MIDI: `0x0020AB2C(nota, velocity)` → gestore logico `0x0020A78C(sorgente 0x20, …)`, che riconosce una
  nota tenuta dal solo numero di nota (stessa nota = riattacco). Per questo le note dei canali di b e C non
  passano dal gestore logico.
- Arpeggiatore attivo = `pattern+0x45` bit 0 e `pattern+0x46` ≠ 0 (`0x0020C8DE`).
- Record di voce `+0x18`: `0x00209574` scrive `FF` a ogni allocazione; letto solo nella copia
  dell'arpeggiatore.

## Stato (ITCM `0x3900`, 128 byte)
Sedici byte per parte (A `+00`, b `+10`, C `+20`): `+0` programma (0 OFF, 1–64; non usato per A), `+1` nota
bassa, `+2` nota alta, `+3` ottava 0–6 (3 = nessuna), `+4` pan 0–14 (7 = centro), `+5` livello 0–100, `+6` voci
0 (libere) / 1–6, `+8` dinamica minima, `+9` dinamica massima, `+10` dissolvenza 0–7 (larghezze 0 8 16 24 32
48 64 96).
`+30` attivo (un programma in b o C, i canali accesi, o un parametro di A diverso dal predefinito), `+32` parte
di ogni voce DSP (6), `+38` interruttore dei canali, `+39` parte forzata + 1 (MIDI), `+3A` avvio diretto (MIDI),
`+3B` numero di parti della nota in avvio, `+3C` quelle parti (3), `+40` il loro guadagno (3 × 16 bit: livello
× dissolvenza, 25500 = pieno), `+48` guadagno di ogni voce DSP (6 × 16 bit), `+54` modulation wheel per parte
(3), `+57` aftertouch per parte (3), `+5A` profondità di pitch, `+60` di ampiezza, `+66` sensibilità di pitch
del programma di ogni voce DSP (6 ciascuna).

## Agganci
| Dove | Era | Ora | Funzione |
|---|---|---|---|
| `0x00209574` | `push.w {r4-r11,lr}` | `b.w 0x2074` | `multi_dsp_on`: voci per nota = parti che suonano la nota |
| `0x002093FE` | `push.w {r0-r2,r4-r11,lr}` | `b.w 0x2078` | `multi_arp_on`: lo stesso per l'arpeggiatore |
| `0x00209746` | `bl 0x0020E814` | `bl 0x207C` | `multi_call_a`: parte e guadagno della voce; marca del record |
| `0x00209488` | `bl 0x0020E814` | `bl 0x2080` | `multi_call_b`: parte e guadagno della voce (arpeggiatore) |
| `0x0020E6F0` | `bl 0x0020E518` | `bl 0x2084` | `multi_patch`: programma, ottava e pan della voce |
| `0x0020E79E` | `bl 0x0020DF14` | `bl 0x2088` | `multi_gain`: profondità LFO, controlli, guadagno della voce |
| `0x00209870` | `push.w {r3-r11,lr}` | `b.w 0x208C` | `multi_dsp_off`: il note-off Korg non tocca le note dei canali |
| literal `0x20014F64` | `0x0020FC4D` (1.21) | `midi_multi` | prima del gestore del Program Change e del dispatcher Korg |

Con `+30` = 0 gli agganci eseguono l'istruzione originale; `multi_gain` in più ricopia nello stato le tre
profondità LFO della voce e le riscrive uguali (controlli a zero).

## Funzionamento
- `multi_match(nota, velocity)`: le parti che suonano la nota, in ordine, con il loro guadagno. Una parte suona
  se è accesa (A sempre, b e C con un programma), la nota è nella zona di tastiera (non controllata per la
  parte forzata dal canale MIDI, che è allora l'unica), la velocity è nella zona di dinamica e la dissolvenza
  non è zero.
- `multi_fade`: larghezza W; x = distanza dal bordo interno più vicino (dL se > 1, dH se < 127), limitata a W;
  guadagno = 255 · x (2W − x) / W². Due parti che si incrociano con la stessa larghezza tengono la potenza tra
  1,00 e 1,13.
- `multi_dsp_on`: nessuna parte → la nota non suona. Poi `multi_limit` e, se le voci per nota Korg sono 1,
  `multi_steal` (anche con una parte sola: con layer e canali i record possono essere tutti accesi senza che
  il gestore logico Korg ne abbia liberato uno); con più parti `VM+8` = numero di parti per la durata della
  chiamata originale. Con UNISON `VM+8` non si tocca.
- `multi_steal(n)`: finché i record non accesi sono meno di n, il più vecchio acceso viene messo in rilascio;
  l'allocazione Korg lo prende e la voce riparte con la sfumatura originale.
- `multi_limit`: per ogni parte della nota con un limite, finché i record accesi di quella parte sono pari al
  limite, il più vecchio viene rilasciato con `0x002094E6`: lo stesso stato di un note-off di quella nota.
- `multi_call_a / b`: parte e guadagno della voce dalla lista della nota (le voci UNISON oltre la lista prendono
  la prima). Una voce avviata da un canale di parte marca il record: `+0x18` = `D0` + parte.
- `multi_patch` (r7 voce, r5 altezza, r4 pan del chiamante): ottava × `0xC00` nell'altezza, riportata tra 0 e
  `0x7F00` a ottave (solo se l'ottava non è zero); pan = valore × 9 + 1 (7 = non toccato); per b e C programma
  dal banco, macro = manopole EG in uso + tutti gli operatori accesi, con l'algoritmo del programma della parte
  scritto in `0x20004F5C+0x6E` per la durata di `0x0020E518`.
- `multi_gain`: chiama `0x0020DF14`, poi salva le profondità LFO del programma della voce, applica i controlli
  (`multi_ctrl_voice`) e, con le parti attive, moltiplica `+0x38` e `+0x3C` per guadagno / 25500.
- `multi_ctrl_voice`: profondità di pitch = programma + 2 × max(wheel, aftertouch); ampiezza = programma + 2 ×
  aftertouch; sensibilità di pitch almeno 33 (PMS 3) finché un controllo è alzato. A zero riscrive i valori del
  programma.
- `midi_multi` (ricezione accesa, sorgente ≤ 2): canale del volca → parte A; con i canali accesi il successivo
  → b, quello dopo → C (`multi_next_ch`: +1 modulo 16, il 10 è saltato). CC 1 e 0xD0: controllo della parte
  (di tutte con i canali spenti), poi tutte le voci. Con i canali accesi: note sul canale del volca → dispatcher
  Korg con la parte A forzata; sui canali di b e C (con un programma): note-on → `0x00209574` con la parte
  forzata e l'interruttore dell'arpeggiatore del pattern spento per la durata della chiamata; note-off →
  `multi_release` (record accesi con quella marca e quella nota, `0x002094E6`, in rilascio); Program Change →
  programma della parte; CC 120 / 123 → tutte le note della parte. Il resto va al gestore del Program Change in
  flash (`0x0020FC4C`) e al dispatcher Korg.
- `multi_dsp_off`: per la durata del note-off Korg i record accesi con marca `D1` / `D2` hanno stato `0x41`.

## Salvataggio
Record nei byte 108–111 degli step 11–16 (mai letti né scritti da Korg): `A7`, 21 byte di flusso di bit (per
ogni parte i campi con 7 7 7 3 4 7 3 – 7 7 3 bit, dal meno significativo, poi l'interruttore dei canali: 166
bit), controllo = xor dei 22 byte ^ `5A`; l'ultimo byte è libero. Assente, non valido o con un valore fuori
campo = parti spente. Il record della prima 1.25 (`A6`, sei byte per parte) viene ancora letto.

## Pagine
21 modalità: PA (18), Pb (19), PC (20) dopo CR. Tasti 1–11 = Pr Lo Hi Oc Pn LE Vo Ch dL dH dF (i tasti 12–16
non fanno niente; uno step scelto in un'altra pagina vale come tasto 1), slider = valore. Letture: `APr LIVE`,
`bPr OFF`, `b05 Disto`, `bLo DO  4`, `bOc -1`, `bPn L3`, `bLE 050`, `bVo --`, `bCh OFF` / `bCh 03` (canale
della parte), `bdL 064`, `bdF --` / `bdF 32`. Cambiando Ch i controlli delle parti tornano a zero.

## Spazio
ITCM: codice `0x2000–0x2D68`, stato `0x3900–0x397F`. SRAM: fino a `0x200192DC` (11820 byte su 23376).
Flash: invariata (il gestore del Program Change resta, chiamato da `midi_multi`).

## Prove (`verify_125.py`, 15 gruppi)
Parti spente: voci, record e campioni identici alla 1.12. Programma della parte identico alla voce Korg. Split,
layer (somma delle voci), furto, limite di voci (uguale a note-off + note-on). Ottava, pan, livello. Dinamica:
zone, guadagni della dissolvenza per ogni larghezza, potenza dell'incrocio, parte a zero senza voce. Canali:
stessa nota su tre canali con note-off separati; voce del canale identica alla voce Korg del programma; canali
per ogni canale del volca (10 saltato, giro dopo il 16); Program Change e CC 123 per parte; arpeggiatore acceso;
limiti e furti; 600 eventi a caso su tre canali senza note appese. Controlli: wheel, aftertouch, voce nuova,
ritorno a zero identico, per parte con i canali, sustain Korg intatto. Pagine, record (anche quello della
prima 1.25), sequencer.

## Limiti noti
- Canali di b e C: niente sustain, pitch bend, arpeggiatore, MIDI OUT, registrazione nel sequencer.
- Con l'arpeggiatore acceso le sue voci possono prendere quelle di una nota di canale.
- Il limite di voci non si applica alle note dell'arpeggiatore.
- Niente dissolvenza tra parti con un LFO (serve un aggiornamento periodico dei guadagni).

## Prova sullo strumento
Solo emulatore per ora.

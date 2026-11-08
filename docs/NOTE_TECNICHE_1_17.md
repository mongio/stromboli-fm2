# Note tecniche 1.17: scale, humanize, salto d'ottava

## Scala (generale, non salvata)
Stato in ITCM: 0x3F30 scala accesa, 0x3F31 scala 0..14, 0x3F32 tonica 0..11
(Do..Si), 0x3F33 opzione "sequenze in scala dal vivo". All'accensione:
spenta, MAG, DO, opzione NO. Non è salvata: non è stato trovato uno spazio
sicuro nelle impostazioni globali Korg.

Correzione (`quantize`): classe della nota rispetto alla tonica; se non è
nella maschera della scala (tabella a 0x1F70, bit i = i semitoni sopra la
tonica) si cerca la distanza minima d = 1..11, prima sopra poi sotto, quindi
a parità vince la nota sopra. Limiti 0..127 rispettati.

Scale: CROM, MAG (ionica), MIN (eolia), ARM (minore armonica), DOR, FRI, LID,
MIS, PMA (pentatonica maggiore), PMI (pentatonica minore), BLU (blues
esatonale), TON (toni interi), HIR (Hirajoshi 0 2 3 7 8), INS (In Sen
0 1 5 7 10), ARA (doppia armonica 0 1 4 5 7 8 11).

## Agganci
| Indirizzo | Originale | Nuovo | Scopo |
|---|---|---|---|
| 0x20AA8A | `adds r4,#5; uxtb r0,r4` | BL 0x203C | tastiera note-on: nota corretta in r4/r0, salvata per tasto (0x1800, 32 byte) |
| 0x20AACA | `adds r4,#5; uxtb r6,r4` | BL 0x2040 | tastiera note-off: nota salvata per quel tasto |
| 0x20AB2C / 0x20AB64 | prologo | B.W 0x2044 / 0x2048 | MIDI DIN note-on/off, mappa nota d'ingresso → nota suonata a 0x1820 (128 byte) |
| 0x20ABC0 / 0x20ABF8 | prologo | B.W 0x204C / 0x2050 | USB MIDI, mappa a 0x18A0 |
| 0x20BA6E | `strb.w r0,[r7,r4,lsl #2]` | BL 0x2054 | sequencer: nota salvata nello slot (0x20003DC4) = nota suonata |

Le mappe stanno nel riempimento FF originale dell'ITCM (0x1800..0x191F,
0xFF = nessuna nota), mai scritto dall'immagine.

Tutto ciò che sta a valle riceve la nota corretta: voce (0x20A78C), eco MIDI
(0x207BD4/0x207C74), lista delle note dell'arpeggiatore (0x20A4A8), HOLD e
**registrazione**: il registratore 0x20B480 (slot a 0x20003D54) riceve la
nota passata alla voce; la registrazione in tempo reale scrive poi lo slot
nel pattern (0x20B384). Verificato nell'emulatore chiamando le funzioni
native (v117/recording_note).

Sequencer: la nota dello step viene trasformata quando entra nello slot;
note-on (0x20AC54), eco MIDI e note-off (0x20B774 → 0x20AC70, e il rilascio
della voce 0x20A4F4) usano lo slot, quindi coincidono sempre. Il pattern non
viene mai modificato. Due note di un accordo che finiscono sulla stessa nota
della scala si comportano come una nota doppia nello step (il gestore delle
voci Korg riusa la voce).

## Humanize e salto d'ottava (per pattern, in PRB3)
Bit 7 delle probabilità degli step 5–8 (humanize) e 9–12 (ottava), 0..15.
Applicati nello stesso aggancio del sequencer (0x20BA6E), solo alle note del
sequencer:
- humanize: velocity ± 3·livello (livello 15 = ±45), limitata a 1..127;
- ottava: probabilità livello/15 per nota, su o giù a caso (metà e metà);
  se si uscirebbe da 0..127 si salta nell'altro verso. Con la scala attiva la
  nota resta in scala (il salto d'ottava conserva la classe).
Generatore: il PRNG nativo 0x2094A4, come per le probabilità.

## Interfaccia
Pagina FUNC+EDIT, modalità P → C → GL → HU → OC → SC → tn (OCTAVE +/−).
HU/OC: slider 0..15 ("HU 07"). SC: slider = scala ("SC MAG ON", "--" se
spenta), tasto 16 alterna l'opzione ("SEQ SI"/"SEQ NO"). tn: slider = tonica
("tn REb"; il diesis non ha glifo sul display, quindi bemolli).
FUNC + SAVE (fuori dalla pagina): scala accesa/spenta ("SCALA ON"/"SCALA
OFF"); il rilascio di SAVE va al codice Korg come prima. Nell'emulatore la
RAM dopo FUNC+SAVE coincide con l'originale a parte i buffer del display.

## Prove (verify_117.py)
scale_keyboard (15 scale × 12 toniche × 27 tasti, con eco MIDI; scala
spenta identica all'originale), release_after_change, midi_in (DIN e USB,
128 note), sequencer_live (opzione spenta identica all'originale), 
humanize_octave, recording_note, panel_modes, func_save.

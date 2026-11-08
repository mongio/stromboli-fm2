# FM2 1.15 beta: note tecniche

Base: 1.14 (vedi NOTE_TECNICHE_1_14.md), più l'HOLD.

## HOLD = pedale di sustain virtuale
- Il firmware Korg ha già un sustain: byte `0x20003C6C+0xE2` (stato attuale) e `+0xE3` (stato voluto), con il bit 0x01 per il CC 64 da MIDI DIN e 0x02 da USB (`0x0020AD84`). Un note-off con il sustain attivo lascia la voce attiva e azzera il suo flag "tasto tenuto" (`+2`) (`0x0020A5A4`). Il tick delle voci `0x0020AF08` copia lo stato voluto in quello attuale e, quando diventa zero, rilascia le voci tenute (`0x0020A4F5` e `0x0020A405`).
- La 1.15 usa il **bit 0x04**. Accendendo l'HOLD lo imposta in E2 ed E3; spegnendolo lo toglie solo da E3, così il rilascio lo fa Korg e rispetta un pedale ancora abbassato.
- Le note-off del sequencer (sorgente 0x10, `0x0020AC70`) passano r3=0 e non sono soggette al sustain: il sequencer non viene tenuto.
- Tasti: in `panel_button`, con la pagina chiusa, lo stato UI 0x12 (FUNC tenuto) e i tasti 6 o 7 premuti. Il firmware originale non fa nulla con FUNC + OCTAVE (verificato).
- Modalità TASTO: hook all'ingresso di `0x0020A78C` (assegnazione delle voci: `2de9f04f` → `b.w 0x2020`), solo per le sorgenti 0x40 (tastiera), 0x20 (MIDI DIN) e 0x30 (USB) e solo con l'HOLD attivo.
  - SPEGNE: se una voce tenuta suona la stessa nota, viene rilasciata con le stesse chiamate di Korg e la nota non viene suonata.
  - RIPARTE con l'arpeggiatore (`0x20002E5B` ≠ 0): se nessun tasto è tenuto, prima di suonare la nota nuova rilascia le voci tenute.
  - RIPARTE senza arpeggiatore: comportamento nativo (ripremere la nota la fa ripartire).
- Stato in ITCM: `0x3F14` HOLD, `0x3F15` TASTO. Non salvato.
- Messaggi: tabella testi `0x3EAC`–`0x3ED0`.

## Prove (55/55)
Le 50 della 1.14 più 5 HOLD (`verify_115.py`): accensione e spegnimento con il debouncer vero, drone tenuto attraverso il tick nativo, rispetto del pedale CC 64, RIPARTE con e senza arpeggiatore, SPEGNE, note MIDI DIN e USB, sequencer non toccato. Rilascio: installazione FSK 1.12/1.13/1.14 → 1.15, ripristino e WAV ufficiale Korg sopra la 1.15.

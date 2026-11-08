# FM2 1.16 beta: note tecniche

Base: 1.15. Novità: modalità di arpeggio generate e arpeggio sull'uscita MIDI.

## Arpeggiatore Korg (analisi)
- Tipo salvato nel pattern al byte 70 (69 e 71 vicini, 71 = DIV); tipo richiesto a runtime in `0x20003E11`, tipo attivo in `0x20003E10`; copia per l'interfaccia in `0x20002E5B`. La manopola TYPE (parametro ADC 7) usa l'indice `(v·5)>>6` (`0x20012EA0`).
- I tipi sono tabelle in SRAM: puntatori in `0x2000B420`. Ogni tabella ha un'intestazione (numero di passi, bit 8 = ordine inverso) e un passo per parola, con un nibble per ognuno dei 6 posti dell'accordo ordinato per altezza (3 = ottava base, 4 = +1, 5 = +2). Le voci dell'arpeggio stanno in `0x200031D4` (6 × 0x34, +4 = 1 se attiva, +7 nota, +0x13 velocity).
- Il validatore dei pattern di Korg non controlla il byte 70: un tipo ≥10 farebbe leggere al firmware Korg oltre la tabella.

## Modalità nuove
- La manopola dà 17 posizioni, `(v·17)>>7`: 0–9 sono i tipi Korg, 10–16 le modalità nuove 1–7 (UPdn1–3, Conv, dIvr, PEdL, Chrd). Hook nel gestore ADC già agganciato: per una modalità nuova passa a Korg il valore di Rise1 (13), per i tipi Korg il valore più piccolo che la mappatura Korg trasforma nell'indice voluto. Vale per pannello e CC MIDI.
- **Compatibilità**: il byte 70 resta sempre un tipo Korg valido (Rise1 per le modalità nuove). La modalità nuova va nel blocco **PRB3**: tag `0xA3`, bit 7 delle probabilità degli step 1–4. PRB3 ha lo stesso formato di PRB2 (le probabilità usano 7 bit); i blocchi PRB2 vengono letti e convertiti alla prima modifica.
- **Tabella generata** in ITCM a `0x3C00` per la modalità e il numero di note (1–6). Mentre una modalità nuova è attiva, la voce 1 della tabella Korg punta lì; altrimenti torna a `0x2000B57C` (Rise1 Korg).
- Aggiornamento: all'ingresso del tick `0x0020C40C` e all'ingresso di `0x0020BDFC` (una voce entra nell'arpeggio). Si rigenera solo quando cambiano la modalità o il numero di note.
- Nomi: il hook del testo `0x0020591C` sostituisce "tYP Rise1" (`0x2000AC82`) con il nome della modalità attiva (tabella in `0x3D80`).

## Arpeggio sul MIDI OUT
- Le note dell'arpeggio passano da `0x002097E4` (voce, nota, velocity), usata solo dall'arpeggiatore, più la prima nota all'avvio (`0x0020BDFC` con +2 = 0xFF, letta dalla voce). Hook all'ingresso: si mette in coda un note-on; quando inizia un passo nuovo (`0x0020C1F4`, contatore `0x3F22`) vanno in coda i note-off delle note del passo precedente.
- Note-off anche quando una voce esce dall'arpeggio (+4 ≠ 1), controllato al tick e nel servizio MIDI.
- Coda SPSC di 16 eventi in `0x3F40`, svuotata all'ingresso del servizio MIDI OUT nativo `0x00207F2C` (ciclo principale) con le funzioni native `0x00207BD5` / `0x00207C75` (DIN, USB, canale, tracciamento delle note inviate).
- Con l'arpeggiatore acceso (`0x20003E11` ≠ 0) l'eco MIDI della tastiera (BL in `0x0020AA8E`) e quella del sequencer (BL in `0x0020A732`, sorgente 0x10) vengono saltate; i note-off nativi restano (Korg invia l'off solo per le note effettivamente inviate).
- HOLD: la regola RIPARTE con arpeggiatore usa ora `0x20003E11`.

## Prove (62/62)
Le 55 della 1.15 più 7 della 1.16 (`verify_116.py`):
- 42 casi di modalità × numero di note confrontati con il modello, più l'accordo;
- 128 posizioni della manopola, con nomi e CC MIDI;
- compatibilità Korg: un pattern con una modalità nuova suona Rise1 sull'immagine originale, e la tabella Korg viene ripristinata;
- conversione PRB2 → PRB3;
- note dell'arpeggio sul MIDI, coppie on/off e rilascio quando l'arpeggio si ferma;
- eco della tastiera con l'arpeggiatore acceso e spento.

Rilascio: installazione FSK da 1.12/1.13/1.14/1.15, ripristino e WAV ufficiale Korg.

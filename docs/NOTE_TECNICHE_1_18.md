# Note tecniche 1.18: delay al posto del riverbero (a scelta)

## Il riverbero Korg (1.12)
- Interrupt audio in ITCM a `0x0010`, uno per frame stereo. Stato in
  `0x20000010`: +0x10/+0x14 uscita, +0x20/+0x24 voci, +0x28/+0x2C coppia
  dell'effetto, +0x50 livello dell'effetto (insegue +0x54 di 1/128 per frame),
  +1 effetto acceso.
- Catena: voci (`0x10DA`) → chorus (`0x12AC`) → `[+0x28] = L + R` →
  **riverbero `0x1460(r0 = 0x20000038)`**, chiamato tramite il literal ITCM
  `0x023C` (= `0x1461`) → uscita stereo dell'effetto moltiplicata per +0x50 e
  sommata al segnale diretto.
- Il riverbero gira a **metà frequenza** (filtro di decimazione a 5 coefficienti,
  due fasi alternate) su un buffer di **48 KiB a `0x20029B00..0x20035AFF`**
  (12.288 parole). Stato in `0x20001A54` (+0 puntatore al buffer, +0xD0 testa).
- Acceso/spento: **FUNC + tasto 4** → `0x200111CC` (tabella dei tasti FUNC) →
  veneer SRAM `0x20015168` (literal `0x2001516C` = `0x0020C8B7`) → bit 2 del
  byte 0x45 del pattern → `0x20453C`: +1 = acceso, +0x54 = livello o 0.
  FUNC + 3 = chorus.
- Livello: parametro 5 (`0x20012F48`), byte 0x49 del pattern (anche motion e
  CC), `0x20EA84`: 0..127 → +0x58 (127 = 0,89 in Q30). Il display compone
  "REVRB nnn" nel buffer `0x20002958` e chiama il testo `0x20591C`.
- Frequenza di campionamento: I2S2 (`0x40003800`) master con MCLK,
  I2SDIV = 2 → fs = I2SCLK / 1024; PLLI2S N = 200, R = 4, PLLM = 12 →
  I2SCLK = 51,2 MHz se HSE = 12,288 MHz (PLLQ = 9 dà 48 MHz all'USB solo con
  questo quarzo) → **fs = 50 kHz**, riverbero a 25 kHz. L'altezza delle
  note nell'emulatore è compatibile con circa 50 kHz. Se fosse diversa,
  cambierebbero solo i millisecondi mostrati in LIBERO (SYNC misura il tempo
  in frame e resta giusto).
- Clock del sequencer: 72 tick per sedicesimo; ogni tick passa da
  `0x208CF8`, che chiama per primo il tick dell'arpeggiatore `0x20C40C`
  (già agganciato dalla 1.16), con qualsiasi sorgente di clock.

## Aggancio
| Indirizzo | Originale | Nuovo | Scopo |
|---|---|---|---|
| ITCM `0x023C` (literal) | `0x00001461` | `0x00002059` | chiamata dell'effetto nell'interrupt audio → `fx_audio` |
| SRAM `0x2001516C` (literal del veneer, offset logico `0x2316C`) | `0x0020C8B7` | `0x0000205D` | FUNC + 4 → `fx_toggle` (originale + messaggio) |
| `arp_tick` (1.16) | — | `bl tempo_tick` all'ingresso | misura dei frame per sedicesimo |
| `panel_display` | — | "REVRB " → "DELAY "/"LOFI  " nel buffer `0x20002958` | lettura del livello |

`fx_audio` chiama il riverbero originale (tipo REVRB) oppure il delay; poi
l'interrupt applica come sempre il livello e l'acceso/spento Korg. Nessun dato
Korg cambia: tornando all'1.12 un pattern con l'effetto acceso suona con il
riverbero.

## Stato (ITCM `0x3F80`, 128 byte, scritti dall'immagine)
+00 tipo 0 REVRB 1 DELAY 2 LOFI · +01 configurazione attiva (tipo | ping-pong<<2,
0 = riverbero) · +02 SYNC · +03 ping-pong · +04 divisione 0..8 · +05 slider
LIBERO 0..127 · +06 feedback 0..100 · +07 fase · +08 contatore dei frame ·
+0C frame dell'ultimo sedicesimo · +10 frame per sedicesimo (6250 = 120 BPM) ·
+14 frame dell'ultimo tick · +18 tick 0..71 · +19 cambio 0/1 dissolvenza/2
pulizia · +1A contatore · +1C passa-basso d'ingresso · +20 primo campione della
coppia · +24 posizione di scrittura · +28 ritardo in campioni, 20.12 ·
+2C/+30 smorzamento L/R · +34..+40 uscite precedente/attuale.
All'accensione: REVRB, SYNC, 3-16, LIBERO 64, feedback 50, MONO. Non salvato.
Tabella LOFI in ITCM `0x1A00` (256 × int16), testi in `0x1940`.

## Algoritmo (per frame a 50 kHz)
1. Ingresso `x = L + R`; passa-basso `lp += (x−lp)/2 + (x−lp)/8` (≈ 7,5 kHz).
2. Frame dispari: si tiene `lp`, si emette la media tra uscita precedente e
   attuale (interpolazione lineare 25 → 50 kHz) e si fa avanzare il ritardo
   verso il valore impostato: `D += sat12((T − D) >> 9)`, cioè al massimo mezzo
   campione per campione (glissato "a nastro").
3. Frame pari: campione a 25 kHz `s = media >> 13` (scala 16 bit). Lettura
   interpolata `y = s0 + (s1 − s0)·frac/4096` a `w − D`. Smorzamento del
   ritorno `d += 3(y − d)/4` (≈ 5,5 kHz a giro), feedback `fb·321/32768`
   (100 → 0,98). Mono: `in = s + fb·d`. Ping-pong: `L ← s + fb·dR`,
   `R ← fb·dL`. Ginocchio morbido oltre ±24576, poi saturazione a 16 bit.
4. Uscita `y << 12` (= ingresso/2 → con REVRB 127 l'eco vale 0,89 del diretto).

Memoria: DELAY 16 bit, 24.576 campioni mono (983 ms) o 12.288 × 2 (491 ms);
LOFI 8 bit A-law (segno, segmento 3 bit, mantissa 4 bit di |v|>>4): 49.152
(1966 ms) o 24.576 × 2 (983 ms). Margine di 4 campioni.

Tempo: LIBERO `250 + v²·(max − 250)/127²` campioni (10 ms .. max). SYNC
`frame_per_16·k/12` con k in sesti di sedicesimo: 3, 4, 6, 8, 9, 12, 16, 18, 24
(1-32, 1-24, 1-16, 1-12, 3-32, 1-8, 1-6, 3-16, 1-4); dimezzato finché entra.

Misura del tempo: a ogni tick `tempo_tick` conta; ogni 72 tick
`periodo = frame ora − frame al sedicesimo precedente`, accettato tra 400 e
200.000 frame. Pausa > 25.000 frame tra due tick: si riparte a contare da quel
tick. Senza tick resta l'ultimo valore (all'accensione 120 BPM).

Cambio di tipo o di MONO/PING PONG: dissolvenza dell'effetto in corso su 256
frame, pulizia del buffer a 48 parole per frame (256 frame, uscita a zero),
poi azzeramento dello stato e partenza dell'effetto nuovo (il riverbero riparte
da un buffer vuoto). Tempo, feedback, SYNC/LIBERO e divisione non interrompono.

## Carico (istruzioni per frame, interrupt intero, 6 voci + chorus, emulatore)
| | massimo | media |
|---|---|---|
| riverbero 1.17 | 2848 | 2818 |
| riverbero 1.18 (tramite fx_audio) | 2876 | 2846 |
| DELAY / ping-pong | 2768 / 2789 | 2756 / 2768 |
| LOFI / ping-pong | 2783 / 2819 | 2763 / 2781 |
| cambio di effetto (512 frame) | 2918 | 2809 |

Il calcolo del tempo è nel frame dispari e i quattro formati hanno percorsi
dedicati, per tenere basso il picco. I cicli reali (attese di memoria,
pipeline) non sono misurati.

## Interfaccia
Pagina FUNC+EDIT: P → C → GL → HU → OC → SC → tn → **FX → dt → Fb** → P.
- FX: slider REVRB / DELAY / LOFI ("FX DELAY ").
- dt: SYNC → slider divisione ("dt 3-16  "); LIBERO → slider tempo
  ("dt  257ms"). Tasto 16: SYNC / LIBERO.
- Fb: slider 0..100, "Fb 050 MO" / "Fb 050 PP". Tasto 16: MONO / PING PONG.
- FUNC + 4: "REVRB ON/OFF", "DELAY ON/OFF", "LOFI ON/OFF".
- Il display non ha il punto né la "t" utili per puntati e terzine: le
  divisioni sono frazioni di battuta come nell'ARP DIV Korg.

## Prove (verify_118.py)
power_on, reverb_unchanged (uscita dell'interrupt identica alla 1.17 in 4
casi), dsp_model (ARM = modello Python indipendente, campione per campione e
buffer finale, 8 configurazioni, oltre 700.000 frame, con cambio di tempo
durante gli echi), times (LIBERO, SYNC a 120 BPM, dimezzamento, ordine L/R
del ping-pong), isr_integration (effetto spento = 1.17; primo eco a 2T;
decadimento; livello), transitions, tempo (60–240 BPM, ripartenza), cpu,
panel_pages, func4_and_label.

Non provati: tempi reali dell'interrupt sull'hardware, ascolto reale, clock
fermo a sequencer fermo (se il clock interno non gira da fermo, SYNC tiene
l'ultimo tempo misurato).

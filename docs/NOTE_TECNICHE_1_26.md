# Note tecniche 1.26: filtro per voce e due LFO

Base: 1.25 (seconda costruzione). Sorgenti `src/fm2_126.S` (ITCM), `src/fm2_126_sram.S` (SRAM),
`src/fm2_126_flash.S` (flash, invariato). Prove nuove `verify_126.py`; verifica completa `verify_patch.py` e
`verify_release.py`. Le parti (1.25) sono descritte in `NOTE_TECNICHE_1_25.md`.

## Processore e tempo per campione
- Configurazione del clock nel bootloader (`0x0020047C`): RCC_PLLCFGR = `0x0940694C` → HSE 12,288 MHz, PLLM 12,
  PLLN 421, PLLP 2 → SYSCLK ≈ 215,6 MHz, overdrive acceso (PWR `0x40007000`). È uno STM32F7 (Cortex-M7).
- L'interrupt audio (`0x0010`) calcola **un campione per chiamata**, a 50 kHz: circa 4311 cicli per campione.

## Punto audio
- Ciclo delle voci Korg in ITCM `0x10F0–0x12A2`: per ogni voce attiva (`[ip+0xE]` ≠ 0; `[ip+0xD]` = numero della
  voce, 0–5) il kernel dell'algoritmo lascia l'uscita mono in `r8`; a `0x123E` un livello addolcito (`+0x40` verso
  `+0x44`) la moltiplica; a `0x1266` `ldrd r2, r3, [ip, #0x38]` carica i guadagni sinistro / destro, poi
  `smull` e somma nel mix (`[sp]`).
- Picco di `r8` misurato su vari programmi a velocity 127: circa 2^27.
- Da `0x1266` alla voce successiva il ciclo usa solo `r8`, `r0–r3`, `r5`, `ip`, `sp`: `r4`, `r6`, `r7`, `r9–r11`
  vengono riscritti prima dell'uso alla voce dopo (verificato: con il filtro acceso ingressi delle voci e stato
  Korg identici a filtro spento).

## Aggancio
| Dove | Era | Ora |
|---|---|---|
| ITCM `0x1266` | `ldrd r2, r3, [ip, #0x38]` (`dce90e23`) | `bl 0x2090` → `filt_voice` (ITCM) |
| `0x0020E7EA` | `bl 0x00204580` (fine nota degli inviluppi Korg) | `bl 0x2094` → `filt_keyoff` (SRAM) |
| `multi_gain` (1.25, BL a `0x0020E79E`) | — | in più `filt_start(voce, altezza, velocity)` |
| `panel_adc` (prologo `0x002059D0`) | — | FUNC + manopola 1 / 3 → `filt_knob` |
| `midi_multi` (1.25) | — | CC 74 / 71 → `filt_set` |
Tabelle d'ingresso ITCM e SRAM: 39 voci (+0x90 `filt_voice`, +0x94 `filt_keyoff`, +0x98 `filt_control`).

## Filtro (per campione, `filt_voice`)
SVF trapezoidale (Simper), 12 dB. Con v0 = r8 × guadagno d'ingresso (Q15) / 65536 (cioè metà dell'ingresso per
lasciare spazio alla risonanza):
- v3 = v0 − ic2; v1 = (a1·ic1 + a2·v3) >> 30; v2 = ic2 + (a2·ic1 + a3·v3) >> 30
- ic1 = sat(2·v1 − ic1), ic2 = sat(2·v2 − ic2), saturati a ±2^30
- LP = v2, BP = v1, HP = v0 − (k·v1 >> 29) − v2; uscita = 2 × sat(y, ±2^27) (massimo 2^28 per voce, sei voci
  sotto 2^31)
- modulazione d'ampiezza (bit 2): ampiezza Q16 che sale o scende di un passo per campione, uscita × ampiezza >> 16.
Bit attivi `FILT+0x0F` = 0 (all'accensione): `filt_voice` esegue solo l'istruzione originale (7 istruzioni in
più per voce).

## Controllo (ogni 32 campioni per voce, `filt_control`)
- Un contatore di campioni (`FILT+0x34`, avanza quando il numero di voce non supera quello precedente) decide:
  la voce v si aggiorna quando contatore % 32 = 5·v. Al più un passo di controllo per campione.
- Taglio in 1/8 di semitono: 128 + taglio × 121 / 16 (note 16–136, 20 Hz–21 kHz) + inviluppo × EA × 12 / 65536
  (scalato da vE e dalla velocity) + (nota − 60) × 8 × tr / 100 + LFO (± 381 a profondità 127) + aftertouch × 2;
  limitato a 0–1088.
- g = tan(π fc / fs) dalla tabella `filt_g` (137 semitoni, Q26, fc al massimo 0,45 fs), lineare nel semitono.
- k = 2 − 1,9 × risonanza / 127 (Q26; risonanza + LFO, 0–127). Guadagno d'ingresso = 32767 − 96 × risonanza.
- a1 = 1 / (1 + g (g + k)) calcolato come (2^32 − 1) / D con D in Q16, poi Q30; a2 = g·a1, a3 = g·a2 (Q30);
  k per il passa alto in Q29.
- Inviluppo 0–65535: attacco lineare (`filt_att`, 0,5 ms–8 s), decadimento verso il sostegno e rilascio
  esponenziali (`filt_dec`, Q15, 60 dB in 2 ms–10 s). Il gate si chiude con la fine nota Korg (`filt_keyoff`):
  sustain e HOLD funzionano come prima.
- Ampiezza: tremolo 1 − profondità × (1 − (valore + 1)/2); dissolvenza A ↔ b con x = 0,5 + valore × profondità / 2:
  A = 1 − x², b = x (2 − x), C invariata. Il passo per campione è (obiettivo − ampiezza) / 32.

## LFO (`filt_lfos`, dal passo di controllo)
- Avanzano dei campioni passati dal passo precedente (contatore `FILT+0x34`); LFO 2 prima, perché può muovere la
  velocità dell'LFO 1 (± 127 posizioni della tabella).
- Velocità libera: `filt_lfo_rates` (0,05–30 Hz, passo di fase per campione). Sincronia: fase dai sedicesimi
  dall'avvio (`0x3B80+0x3C`) e dai campioni dall'ultimo sedicesimo (`0x3F80+0x8`, `+0xC`, `+0x10`), come la
  modulazione SYNC della 1.22; senza clock, libera allo stesso tempo.
- Forme: seno (parabolico), triangolo, dente di sega su / giù, quadra, S&H (nuovo valore casuale a ogni ciclo,
  LCG `FILT+0x30`).

## Stato (ITCM `0x3700–0x385F`)
Globale: `+00` tipo, `+01` taglio, `+02` risonanza, `+03` EA (63 = 0), `+04–07` A D S R, `+08` tr, `+09` vE,
`+0E` ultima voce vista, `+0F` bit attivi, LFO1 `+10` e LFO2 `+18` (forma, velocità, profondità, destinazione,
sincronia, divisione), `+20/+24` fase e valore LFO1, `+28/+2C` LFO2, `+30` stato casuale, `+34` contatore di
campioni, `+38` contatore all'ultimo passo LFO, `+3C` valori S&H.
Per voce (`+40 + 48 v`): ic1, ic2, a1, a2, a3, k, guadagno d'ingresso, ampiezza, passo, inviluppo; `+29` fase
dell'inviluppo, `+2A` nota, `+2B` velocity, `+2C` gate.
Le impostazioni sono globali e **non salvate** (nel pattern resta un solo byte libero).

## Comandi
- FUNC + TRANSPOSE (indice 1) / FUNC + VELOCITY (indice 3), solo dal pannello (r2 = 0) e con FUNC premuto
  (`0x0020FA60`): il gestore Korg non viene eseguito; filtro spento → LP. Display "CUTOF nnn" / "RESO  nnn".
  FUNC + manopola 7 e 9 restano di Korg (verificato).
- MIDI CC 74 / 71 su un canale accettato (quello del volca, o delle parti con i canali accesi).
- Pagine FL (21) e LF (22) dopo PC; 23 modalità in tutto. FL: tasti 1–10; LF: tasti 1–5 (LFO 1) e 9–13 (LFO 2).
  Il display non ha il "+": EA positivo è mostrato senza segno, le seghe sono `SAu` / `SAd`.

## Spazio
ITCM: codice `0x2000–0x2E74`, stato filtro `0x3700–0x385F`, parti `0x3900`. SRAM: fino a `0x2001A07C` (15308 byte
su 23376, tabelle comprese). Flash: invariata.

## Carico del processore (`verify_126.py`, istruzioni per campione dell'interrupt intero, sei voci, chorus e riverbero)
| | media | massimo |
|---|---|---|
| Korg 1.12 | 2819 | 2854 |
| STROMBOLI 1.24 | 2855 | 2890 |
| 1.26 filtro spento | 2897 | 2932 |
| 1.26 LP con inviluppo | 3197 | 3398 |
| 1.26 LP + due LFO (taglio, ampiezza) | 3239 | 3465 |
Circa +15% in media rispetto alla 1.12; il massimo comprende un passo di controllo. A 216 MHz ci sono circa 4311
cicli per campione; i cicli reali (attese, pipeline) non sono misurati: **è il punto da verificare sullo
strumento**.

## Prove (`verify_126.py`, 8 gruppi)
Filtro spento: identico alla 1.12 (anche dall'interrupt). Modello: ogni campione di ogni voce uguale al modello in
LP, BP, HP con inviluppo, risonanza e LFO; ingressi delle voci e stato Korg non toccati; mix = somma delle voci
filtrate. Coefficienti: g e k come previsto per 15 combinazioni; risposta misurata (spettro incrociato) uguale al
prototipo analogico entro 1 dB. Inviluppo: tempi di attacco e rilascio, sostegno, quantità, velocity, key
tracking. LFO: velocità, forme, sincronia, LFO 2 sulla velocità dell'LFO 1, tremolo, dissolvenza A ↔ b (potenza
1,00–1,14). Comandi: FUNC + TRANSPOSE / VELOCITY, Korg senza FUNC, FUNC + 7 / 9 invariati, CC 74 / 71. Pagine.
Carico del processore.

## Limiti noti
- Impostazioni non salvate; niente motion del taglio (usare CC 74 da un sequencer esterno).
- Un solo filtro per tutte le parti.
- Non provato sullo strumento.

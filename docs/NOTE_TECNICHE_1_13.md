# FM2 Probability beta 1.13 — integrazione e prove

## Inserimento nel codice originale

Il builder accetta soltanto il WAV originale con SHA-256 previsto dal dossier
1.12 e l’immagine logica:

`daf7052f0483a3bd82958f142d81038aeaec011d6f018de31261b8f5baed5e40`.

Il punto di modifica è nella routine che applica uno step, `0x0020B7BE`.
All’indirizzo `0x0020B7CA` il codice originale contiene:

```asm
ldrh r3, [r4, #6]
mov.w r8, #0
```

Questi sei byte sono controllati prima della sostituzione. La patch inserisce
un salto al proprio codice a `0x00002000`, nel riempimento FF della sezione FF11.
Al termine torna a `0x0020B7D0`, rieseguendo normalmente moltiplicazione dello
stride e istruzioni successive dell’originale.

Il codice aggiunto decide se mantenere la maschera originale letta dal pattern
o passare zero nel registro che la routine usa per lo step corrente. **La
maschera salvata nel pattern non viene modificata durante l’esecuzione.**
È quindi la routine nativa a gestire rilascio, allocazione e bookkeeping delle
note, come per uno step disabilitato. Il clock resta esterno a questo intervento.

La beta aggiunge gli ingressi pannello descritti sotto. Il builder conserva tutti
gli altri byte dell’immagine, salvo il minor applicativo 1.13 e i due campi di checksum FF00 e FF11. Controlla che tutte e cinque le somme LE16
modulo 65536 siano nuovamente zero. Formato e dimensione restano quelli
della base 1.12; la versione applicativa è 1.13, marcata sperimentale nel pacchetto. Le tabelle FM, i 32 kernel e i kernel chorus/riverbero non vengono
riscritti.

## Memoria e contesto CPU

| Risorsa | Uso aggiunto |
|---|---|
| Decisione probabilistica ITCM | 184 byte da `0x00002000` |
| Codice pannello ITCM | 828 byte da `0x00002400` |
| Salto nella flash applicativa | 6 byte a `0x0020B7CA` |
| Nuovo stato scrivibile | 16 byte in ITCM a `0x00003F00`; nessuna nuova allocazione SRAM |
| Metadata nel pattern esistente | 28 byte, dimensione totale del pattern invariata |
| Stack aggiuntivo del ramo probabilità | Massimo 64 byte, inclusa la chiamata al PRNG nativo; non comprende il percorso UI nativo |

Il sorgente usa il generatore già presente a `0x002094A4`. I valori 0% e 100%,
i pattern senza estensione valida, gli step già disabilitati e le pause native
non consumano numeri casuali. Con valori intermedi il PRNG originale avanza:
la sua sequenza è condivisa anche con le funzioni native che già lo usano,
compresi gli arpeggi casuali.

La routine salva e ripristina il contesto necessario e mantiene l’allineamento
dello stack per le chiamate. I test verificano SP e gli otto registri preservati
dal chiamato. Lo spazio ITCM scelto contiene FF nell’immagine originale; il boot
nativo carica l’esatto codice aggiunto nelle prove. Questo non sostituisce una
misura dell’occupazione e delle scadenze temporali sull’hardware fisico.

## Estensione del pattern

Il pattern resta lungo 1.920 byte. L’estensione usa i byte riservati 1888–1915;
il marcatore finale originale, ai byte 1916–1919, resta intatto.

| Offset assoluto nel pattern | Byte | Significato |
|---:|---:|---|
| 1888 | 4 | Tag ASCII `PRB1` |
| 1892 | 16 | Una percentuale 0–100 per ciascuno step |
| 1908 | 4 | Complemento LE32 del tag: `0xCEBDADAF` |
| 1912 | 4 | FNV-1a-32 dei sedici valori, LE32 |

Prima di applicare una percentuale il codice controlla entrambi i tag, l’intervallo
di tutti i valori e il digest. Un’estensione assente o non valida ripristina il
comportamento originale al 100%. La prova altera separatamente tutti i 224 bit
dell’estensione e verifica il fallback.

Le routine native di copia, SysEx e persistenza già trasferiscono l’intero blocco
di 1.920 byte. I test confermano la conservazione dell’estensione in tutti i 16
slot, dopo ricezione SysEx e dopo scrittura/rilettura del journal NOR modellato.

## Semantica musicale

La decisione è unica per lo step: un accordo passa interamente o viene saltato.
Le note di ingresso MIDI indipendenti dal sequencer non vengono sottoposte alla
probabilità. Uno step saltato conserva la propria durata nel flusso del clock.

Lo skip invia i normali rilasci alle note del sequencer precedentemente tenute,
anche nel caso TIE. Le code degli inviluppi e del riverbero continuano il loro
normale decorso: 0% significa nessun nuovo attacco, non azzeramento forzato di
tutto l’audio. La riproduzione riprende allo step successivo che passa il filtro.

## Prove eseguite

I dettagli, gli indirizzi e gli eventuali confini modellati sono in
`reports/patch_verification.json`.

- Matrice di 10.100 casi: tutte le percentuali da 0 a 100 contro tutti i risultati
  0–99. Il solo PRNG è sostituito in questa matrice per imporre ogni risultato.
- 10.000 passaggi al 50% con il PRNG nativo effettivamente eseguito; confronto
  di ogni decisione e dello stato finale con una formula indipendente.
- Confronti tra originale e patch al 100%, con accordi, gate, TIE, mute e pause:
  eventi, stato applicativo, registri preservati e stack.
- Ripresa dopo uno step saltato, rilascio TIE e scorrimento ACTIVE STEP.
- Conservazione di una nota MIDI dal vivo mentre le note interne vengono saltate.
- 16 pattern con valori distinti attraverso SysEx e journal NOR, con riavvio simulato.
- Editor di profili su pattern raw, SysEx corrente e SysEx di locazione salvata.
- 64 passaggi con probabilità miste attraverso il percorso nativo fino a FM,
  chorus, riverbero e uscita software. I 32.768 frame stereo coincidono con
  l’originale configurato, in ogni passaggio, con la corrispondente maschera mute.
- Le 15 suite funzionali del dossier originale eseguite sull’immagine modificata,
  con probabilità non configurata: tutte superate.
- Ricezione FSK, staging, installazione modellata, reset e caricamento del codice
  aggiunto, poi prova 0%/100% nella stessa istanza CPU.

La verifica di rilascio usa come installata l'immagine originale 1.12 effettiva,
non un minor sintetico. Il file WAV beta ha intestazione e applicazione 1.13.
Il ripristino ha intestazione di trasporto 1.14 e payload originale 1.12.
I controlli nativi confrontano la versione di trasporto con il minor presente
nella flash: entrambe le direzioni sono accettate. Una normale intestazione
1.12 su beta 1.13 e la beta 1.13 su se stessa restano rifiutate con ERR_VER.

I due WAV su disco vengono decodificati in modo indipendente e attraversano
le istruzioni ARM native di ricezione FSK, parser, staging, instradamento SPI,
confronto/erase/scrittura flash, reset e inizializzazione CPU. Il pannello e
lo step 0%/100% vengono provati dopo l'installazione nella stessa CPU.
Il payload installato osservato viene usato come immagine di partenza del
ripristino. Al termine tutti i 196.608 byte coincidono con l'originale 1.12.
I settori interni cancellati sono controllati; il settore del bootloader resta
identico e non viene cancellato. Le destinazioni SPI non raggiungono l'area dei
dati utente. Le temporizzazioni/errori fisici di flash/SPI restano fuori modello.

## Confine della consegna

È un prototipo del comportamento e della sua integrazione ARM, verificato con
Unicorn e periferiche modellate. Non sono state eseguite programmazione del
FM2, prove analogiche, misure di carico/interrupt in tempo reale sui comandi fisici
del pannello. I due WAV nella radice sono destinati al collaudo sperimentale;
il binario logico nella cartella build è per analisi e riproduzione tecnica.

La prova della patch è distinta dai 23 gruppi che in precedenza riguardavano
soltanto il firmware originale: qui vengono eseguiti i nuovi byte ARM e
verificato il comportamento probabilistico aggiunto.


## Integrazione pannello beta 1.13

Il codice pannello viene assemblato a `0x00002400`. Il manifest registra la
dimensione e i byte di ogni modifica. Una tabella di sei salti espone gli ingressi
per tastiera, pulsanti, ADC, display, encoder e LED. Lo stato scrivibile di 16 byte
si trova a `0x00003F00`: flag pagina, step scelto e maschere dei tasti. Il builder
controlla che codice e stato sostituiscano esclusivamente FF originali e non si
sovrappongano. Il boot copia l'intera sezione FF11, compresi gli zeri iniziali.

| Aggancio originale | Intervento |
|---|---|
| Literal del veneer `0x0020FC1C` | Tastiera raw, attraverso il convertitore originale della matrice |
| Literal del veneer `0x0020FAA4` | Pulsanti dopo il debounce nativo a tre scansioni |
| Literal del veneer `0x0020FB24` | Encoder: consumo degli eventi durante la pagina |
| Prologo `0x002059D0` | Il parametro ADC 3 modifica la probabilità durante la pagina |
| Prologo `0x0020591C` | Richieste di testo mantengono la schermata modale |
| Prologo `0x0020548C` | Selezione del LED lampeggiante attraverso le maschere native |

I prologhi e i literal originali sono confrontati byte per byte prima della
modifica. Fuori dalla pagina vengono eseguite le istruzioni originali e si
riprende al corretto confine d'istruzione. Le chiamate fra ITCM e codice nella
SRAM usano indirizzi Thumb completi e BLX; i salti diretti sono entro portata.

La pagina entra quando EDIT (id nativo 4) viene premuto nella modalità FUNC
`0x12` (FUNC è id 0). Rilasciare la combinazione non esce. FUNC oppure EDIT
chiudono la pagina e richiamano il ridisegno nativo. I tasti ancora tenuti vengono
filtrati fino al rilascio per evitare nuovi attacchi al rientro. PLAY conserva il
normale start/stop. La pagina usa lo stato UI `0x49`; il suo flag ITCM rimane il
riferimento anche se lo stop nativo ripristina lo stato UI zero.

L'ADC quantizzato 0..127 diventa `(v*100+63)//127`; tutti i 101 valori sono
raggiungibili. Il primo edit ricrea i metadati se non sono validi, quindi aggiorna
il singolo step e FNV. Entrata, selezione e uscita restano in sola lettura sul
pattern. Il display genera nove caratteri, per esempio `05 P050  `, usando la
conversione ASCII/glyph originale. La prova confronta anche le otto righe del
buffer di segmenti nativo e le maschere LED, senza sostituire tali routine.

Quattro nuovi gruppi di prove verificano tutti i 16 step, tutte le 128 posizioni
del cursore, ingresso/debounce/rilascio/uscita, ADC attraverso il polling nativo,
PLAY, mantenimento della pagina, comportamento fuori pagina, metadati corrotti,
NOR con riavvio simulato e arrivo del valore al sequencer ARM. Il test completo
ripete anche le regressioni V1 e il percorso FSK/installazione/boot sulla nuova
immagine. L'I/O fisico del pannello e la temporizzazione degli interrupt non
sono simulati elettricamente.


## Correzioni per il collaudo e risorse

Il valore sentinella raw 0x80000000 viene ignorato solo se è l'intero frame;
i frame con quel bit e tasti presenti vengono invece elaborati come il codice
nativo. La sorgente MIDI usa r2=1 nel setter parametri: l'intercettazione della
probabilità richiede r2=0. Il MIDI CC41 continua quindi a modificare velocity,
anche con la pagina aperta. Entrambi i casi hanno prove ARM dedicate.

La beta cambia solo il minor applicativo a offset 0x420D, oltre ai cambiamenti
dichiarati dal builder. Tutti i 16 KiB iniziali della flash sono identici alla
base originale. Restano 9.392 byte di riempimento ITCM nell'immagine, detraendo
184 byte di probabilità, 828 byte di pannello e 16 byte di stato dal riempimento
originale di 10.420 byte. Questa è una misura statica, non una certificazione
completa di RAM libera o delle scadenze audio in tempo reale.

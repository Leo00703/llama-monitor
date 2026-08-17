# Specifica: pannello di controllo web per llama-server

## 1. Ruolo e obiettivo

Sei uno sviluppatore full-stack incaricato di costruire un pannello di controllo web leggero per gestire un server `llama-server` (llama.cpp) in esecuzione su una macchina locale. Il pannello deve permettere di avviare/fermare/riavviare il server, modificare i suoi parametri tramite un'interfaccia grafica invece che a riga di comando, vedere i log in tempo reale, e monitorare le risorse hardware (CPU, RAM, GPU, temperature) durante l'inferenza.

## 2. Contesto hardware (ambiente reale in cui girerà)

- **Server** (dove gira sia llama-server che questo pannello): Ryzen 5 3600, doppia GPU NVIDIA (RTX 3060 Ti 8GB + RTX 5060 Ti 16GB, indici CUDA 0 e 1), 32GB RAM DDR4 (in futuro 64GB). Attualmente Windows 11, **in futuro passerà a Linux** — il codice deve funzionare su entrambi fin da subito.
- **Client**: un portatile Windows (e in futuro forse un MacBook) si collegano via Tailscale, solo tramite browser — su questi dispositivi non gira nessun componente backend, solo il frontend nel browser.
- Il numero di GPU non va mai assunto fisso a 2: il codice deve rilevare dinamicamente quante ce ne sono (via `nvidia-smi`) e generare i controlli di conseguenza.
- Per ora si usa **solo llama.cpp** (non vLLM, non sGLang). In futuro il server Linux sarà condiviso da più utenti contemporaneamente, ma questo è fuori scope adesso: si progetta per un solo processo llama-server alla volta, gestito da un solo utente amministratore tramite il pannello.

## 3. Stack tecnologico richiesto

- **Backend**: Python 3, FastAPI + uvicorn, supporto WebSocket nativo
- **Frontend**: HTML/CSS/JavaScript vanilla — niente framework (no React/Vue), niente build step (no npm/webpack/vite)
- **Percorsi file**: usa sempre `pathlib.Path`, mai stringhe concatenate a mano — deve funzionare identico su Windows e Linux
- **Persistenza dati**: file JSON su disco per preset/impostazioni (nessun database esterno necessario). Per lo storico Analytics (punto 4.10) usa invece **SQLite** (modulo `sqlite3` della libreria standard, un solo file su disco, nessuna dipendenza esterna) — è lo strumento giusto per le query di aggregazione su molti record nel tempo, cosa che JSON gestirebbe male
- Librerie Python da usare: `psutil` (CPU/RAM), `subprocess` per gestire il processo `llama-server` e leggerne stdout/stderr, chiamate a `nvidia-smi` (via subprocess, parsing dell'output `--query-gpu`) per le metriche GPU

## 4. Funzionalità richieste

### 4.1 Gestione del processo server
- Avvia, ferma, riavvia `llama-server` come processo figlio
- Cattura stdout/stderr del processo e trasmettili al frontend via WebSocket in tempo reale (log live nell'interfaccia)
- Mostra lo stato corrente (in esecuzione / fermo / in errore) sempre visibile

### 4.2 Monitoraggio risorse in tempo reale
- CPU: percentuale di utilizzo, per-core se possibile
- RAM: usata/totale
- GPU (per ciascuna GPU rilevata, non solo la prima): utilizzo %, VRAM usata/totale, temperatura, potenza, clock core e memoria
- Aggiornamento continuo via WebSocket (polling ogni 1-2 secondi lato server)

### 4.3 Sistema di preset/profili
- Un preset = un insieme completo di impostazioni per un modello specifico (può essere lo stesso modello con parametri diversi per task diversi, oppure modelli completamente diversi)
- CRUD completo: crea, modifica, duplica, elimina preset
- I preset vanno salvati come **impostazioni semantiche strutturate**, MAI come stringhe di flag CLI grezze (es. salva `"context_size": 100000`, non `"-c 100000"`) — servirà un layer di traduzione separato che converte le impostazioni semantiche nei flag CLI reali al momento del lancio, per motivi spiegati al punto 4.4

### 4.4 Resilienza agli aggiornamenti di llama.cpp
- Prima di lanciare il server, esegui `llama-server --help`, fai il parsing dell'elenco di flag effettivamente supportati dalla versione installata
- Confronta con le impostazioni richieste dal preset attivo: se un'impostazione non ha corrispondenza nei flag attualmente disponibili, **non bloccare l'avvio** — segnalalo chiaramente nell'interfaccia (es. banner di avviso) e prosegui senza quel parametro
- Mantieni la mappa "impostazione semantica → flag CLI reale" in un unico posto facilmente modificabile (es. un dizionario/file di configurazione separato dal resto della logica), così un cambio di sintassi futuro (è già successo: `--no-mmap`/`--mlock` sono diventati `--load-mode`) richiede una sola modifica, non la riscrittura di ogni preset

### 4.5 Portabilità dei percorsi
- Impostazioni d'ambiente separate dai preset, configurabili una sola volta da una pagina "Impostazioni": percorso dell'eseguibile `llama-server`, cartella radice dei modelli
- Tutti i preset riferiscono i file modello con percorso **relativo** alla cartella radice — mai percorsi assoluti hardcoded

### 4.6 Selezione modello e supporto vision
- File browser che scandisce ricorsivamente la cartella radice dei modelli e mostra i file `.gguf` disponibili
- Quando l'utente seleziona un modello, cerca automaticamente nella stessa cartella un file che matcha il pattern `mmproj*.gguf` e proponilo come proiettore vision opzionale da collegare
- Se l'utente ha impostato un file mmproj E contemporaneamente seleziona MTP come tipo di speculative decoding, mostra un avviso bloccante: le due cose non sono compatibili nella versione attuale di llama.cpp, l'utente deve scegliere l'una o l'altra

### 4.7 Speculative decoding (MTP / DFlash / altri)
- Un unico selettore "tipo di speculative decoding" (nessuno / MTP / DFlash / altri tipi supportati da `--spec-type`)
- **MTP**: non richiede file aggiuntivi, usa la testa integrata nel modello target stesso
- **DFlash**: richiede un file GGUF "drafter" separato — quando selezionato, mostra un campo/file-picker aggiuntivo per questo file
- Quando si seleziona MTP o DFlash, forza automaticamente il numero di slot paralleli a 1 (`-np 1`), non lasciarlo modificabile in quel caso
- Campo modificabile per `--spec-draft-n-max` (non fissarlo a un default silenzioso: il valore ottimale varia molto per modello e va testato dall'utente)

### 4.8 Parametri di lancio del server (richiedono riavvio — fanno parte del preset)

Il form "Parametri server" deve coprire come minimo:

**Modello e memoria**
- Percorso modello (`-m`), alias (`-a`), percorso mmproj opzionale (`--mmproj`)
- Context size (`-c`)
- GPU layers da offloadare (`-ngl`)
- Offload esperti MoE su CPU (`--n-cpu-moe N`, `--override-tensor`) — necessario per modelli MoE come Qwen3.6-35B-A3B quando non entrano interamente in VRAM, anche se col modello denso attuale non serve
- Quantizzazione cache KV (`--cache-type-k`, `--cache-type-v`: f16/f32/q8_0/q4_0/ecc.)
- Flash attention (`-fa`: on/off/auto)
- Modalità di caricamento (`--load-mode`: none/mmap/mlock/mmap+mlock/dio)

**Multi-GPU**
- Tensor-split (valori proporzionali, generato dinamicamente per N GPU rilevate, non hardcoded a 2)
- Main GPU (`--main-gpu`)
- Split mode (`--split-mode`: none/layer/row — evita di esporre "tensor" per ora, è incompatibile con la cache KV quantizzata)

**CPU e batching**
- Thread di generazione (`-t`), thread di batch (`-tb`)
- Batch size logico (`-b`), micro-batch/batch fisico (`-ub`)
- Cache reuse (`--cache-reuse`)

**Speculative decoding**
- Tipo (`--spec-type`: none/draft-mtp/dflash/ngram-cache/ngram-simple/altri)
- Modello drafter esterno, campo visibile solo se il tipo scelto lo richiede (`--spec-draft-model`/`-md`) — MTP non lo richiede, DFlash sì
- Numero massimo/minimo token di bozza (`--spec-draft-n-max`, `--spec-draft-n-min`)
- Forza automaticamente slot paralleli a 1 (`-np 1`) quando il tipo scelto è diverso da "none", campo non modificabile manualmente in quel caso

**Rete e osservabilità**
- Host (`--host`), porta (`--port`), API key opzionale (`--api-key`)
- Endpoint metriche e slot (`--metrics`, `--slots`) — vanno sempre abilitati di default, servono alla dashboard stessa per funzionare
- Jinja template (`--jinja`), preservazione reasoning (`--reasoning-preserve`)
- Flag di performance opzionali: merge QKV (`--merge-qkv`), graph reuse (`-gr`), fitting automatico memoria on/off (`-fit`)
- Campo "flag extra" testuale libero come scappatoia per parametri non ancora coperti dal form

### 4.9 Parametri di generazione (NON richiedono riavvio — applicati per-richiesta via API)

Distinzione architetturale importante: questi NON sono flag di lancio del processo, sono campi del corpo JSON inviato a ogni richiesta `/completion` o `/v1/chat/completions`. Il pannello deve poterli modificare **senza fermare/riavviare il server**, applicandoli alla richiesta successiva — è un errore implementativo trattarli come i parametri del punto 4.8. Possono comunque essere salvati come default dentro un preset per comodità (un preset "coding" può voler default diversi da uno "creativo").

Organizzali in due sotto-categorie, coerenti con l'interfaccia ufficiale allegata negli screenshot (che ha tab separati "Sampling" e "Penalties"):

**Sampling**
- `temperature`, `dynatemp_range`, `dynatemp_exponent`
- `top_k`, `top_p`, `min_p`, `typical_p`, `top_n_sigma`
- `xtc_probability`, `xtc_threshold`
- `mirostat` (0/1/2), `mirostat_tau`, `mirostat_eta`
- `seed`
- `samplers` (stringa ordine, default: `penalties;dry;top_n_sigma;top_k;typ_p;top_p;min_p;xtc;temperature`)

**Penalties**
- `repeat_penalty`, `repeat_last_n`
- `presence_penalty`, `frequency_penalty`
- DRY: `dry_multiplier`, `dry_base`, `dry_allowed_length`, `dry_penalty_last_n`, `dry_sequence_breakers`

**Altri controlli di generazione**
- `max_tokens`/`n_predict`, `n_keep`, `n_discard`
- `ignore_eos`, `stop` (sequenze di stop)
- `grammar`/`json_schema` (output strutturato)
- `logit_bias`

I valori di default esatti vanno letti dall'endpoint del server che espone `default_generation_settings` — usali come riferimento invece di inventare default arbitrari.

### 4.10 Analytics e storico d'uso
- Ogni intervallo di generazione va registrato in uno storico persistente con: timestamp, modello/preset attivo, token di prompt processati, token generati, velocità di prompt processing, velocità di generazione, e — se lo speculative decoding è attivo — token di bozza proposti e accettati
- **Fonte dati confermata**: l'oggetto `timings` nella risposta di ogni `/completion` include `draft_n`/`draft_n_accepted` quando `timings_per_token` è abilitato; l'endpoint `/metrics` espone anche contatori cumulativi equivalenti, inclusi i token accettati per posizione di bozza
- **Architettura consigliata**: NON costruire un proxy delle richieste di inferenza (aggiungerebbe un punto di fallimento sul percorso critico). Interroga periodicamente `/metrics` e `/slots` (stesso polling del punto 4.2), calcola i delta tra un'interrogazione e la successiva, registrali nello storico etichettati con il modello/preset attualmente caricato — il server esegue un modello alla volta, quindi l'etichettatura è già inequivocabile
- Aggregazioni da calcolare: giornaliera, settimanale, mensile, annuale, totale storico
- Classifica dei modelli per token totali generati/processati
- Velocità media (tok/s generazione e prompt processing) per modello/preset
- Percentuale media di accettazione bozze per modello/preset, solo dove applicabile

### 4.11 Stima costo energetico
- Usa il consumo istantaneo delle GPU già raccolto per il monitoraggio (punto 4.2, campo `power.draw` di `nvidia-smi`) per stimare l'energia consumata durante ogni sessione di generazione
- Formula: energia (kWh) = potenza media GPU (kW) × tempo di generazione (h); costo per 1M token = (energia consumata / token generati) × 1.000.000 × prezzo €/kWh
- Prezzo dell'energia come impostazione modificabile (non hardcoded), default **0,30 €/kWh** (media nazionale tutto compreso, riferimento ARERA III trimestre 2026 — non esiste una tariffa regionale Veneto distinta, la regolazione è sostanzialmente nazionale)
- Nota esplicativa da mostrare nell'interfaccia: la stima copre solo il consumo delle GPU, non l'intero sistema (CPU, RAM, dispersione dell'alimentatore) — è una stima per difetto. Campo opzionale "overhead di sistema stimato (W)" per chi vuole includere un contributo fisso per il resto della macchina

### 4.10 Analytics e storico

Richiede una **pagina dedicata**, propria voce nella sidebar (aggiornare punto 5.2). A differenza del monitoraggio in tempo reale (punto 4.2, che mostra lo stato attuale), qui si mostra l'**andamento storico** — serve persistenza dedicata, non solo dati in memoria.

**Come raccogliere i dati per ogni richiesta, senza costruire un reverse proxy**: llama-server stampa già, per ogni richiesta completata, una riga di log strutturata e facilmente analizzabile nel formato:
```
slot print_timing: id 0 | task N | prompt eval time = X ms / Y tokens ( ..., Z tokens per second)
eval time = A ms / B tokens ( ..., C tokens per second)
total time = D ms / E tokens
```
Il log del processo è già intercettato e trasmesso al frontend (punto 4.1) — aggiungi semplicemente un parser che riconosce questo pattern nello stream già catturato, estraendo token di prompt, token generati, tempo/velocità di entrambe le fasi. Non serve un proxy per intercettare le richieste API: il log contiene già tutto il necessario. Ogni riga riconosciuta diventa un record nel database, taggato con il preset/modello attivo in quel momento (il backend lo sa già, essendo lui ad aver lanciato il processo).

**Acceptance rate dello speculative decoding**: se MTP/DFlash sono attivi, verifica nei log o nell'endpoint `/metrics` la presenza di un contatore di token di bozza proposti/accettati — il nome esatto del campo va confermato osservando l'output reale del server con speculative decoding attivo (può differire tra build). Se non è recuperabile in modo affidabile per una richiesta, ometti il dato invece di stimarlo.

**Collegare i consumi energetici al costo**: il monitoraggio del punto 4.2 campiona già la potenza (Watt) di ogni GPU ogni 1-2 secondi — mantieni un piccolo buffer temporaneo di questi campioni con timestamp. Quando arriva una riga `print_timing`, calcola la potenza media nella finestra temporale di quella richiesta, convertila in Wh (potenza media × durata in ore, sommata su tutte le GPU), e salvala nello stesso record. Da qui si derivano Wh per token generato e, con un prezzo €/kWh configurabile, il costo stimato per 1M di token.

**Prezzo dell'energia**: campo configurabile dalle Impostazioni, con default iniziale **0,316 €/kWh** (prezzo ARERA tutto compreso, III trimestre 2026, mercato di maggior tutela — è un riferimento nazionale, non esiste un prezzo distinto per il Veneto su questa componente). Se sei sul mercato libero il valore reale può differire sensibilmente (indicativamente 0,12-0,30 €/kWh secondo l'offerta) — aggiornalo con quello della tua bolletta per una stima precisa.

**Grafici e viste richieste nella pagina**:
- Token totali generati: oggi, settimana, mese, anno, totale storico — con andamento a barre/linee per periodo
- Ripartizione per modello/preset (quali hanno generato più token — grafico a torta o barre orizzontali)
- Velocità media tok/s (generazione e prompt processing), andamento nel tempo — utile per verificare se una modifica ai parametri ha davvero migliorato le prestazioni nel tempo, non solo in un test isolato
- Acceptance rate medio dello speculative decoding nel tempo, quando disponibile
- Costo stimato: oggi/settimana/mese/anno/totale, più costo stimato per 1M token per ciascun modello/preset

**Suggerimenti aggiuntivi da valutare per la pagina**:
- Confronto diretto tra preset/modelli sulla stessa metrica (tabella affiancata tok/s medio + costo per 1M token) — coerente con il modo in cui hai già confrontato le tue configurazioni durante questa conversazione
- Velocità di picco raggiunta per modello/preset, per capire se una modifica di tuning ha davvero alzato il tetto massimo, non solo la media
- Export dei dati storici in CSV per analisi esterne
- Conteggio richieste fallite/errori, come indicatore base di affidabilità

## 5. Design dell'interfaccia

Replica lo stesso linguaggio visivo della WebUI ufficiale di llama.cpp (screenshot allegati come riferimento):

- Tema scuro, sfondo quasi nero
- Elementi principali (barra di input, pillole di selezione) con angoli arrotondati, leggero effetto vetro sfocato/frosted-glass, bordo sottile semi-trasparente
- Tipografia sans-serif pulita, molto spazio bianco, palette di colori sobria (grigi/bianchi, uso minimo di colori d'accento)
- Componenti di form (checkbox, radio, input, textarea) tutti coerenti nello stile scuro-bordato-arrotondato

### 5.1 Header (sempre visibile, in cima)
- Stato del server con indicatore visivo chiaro (in esecuzione / fermo / in errore / in avvio-riavvio)
- Versione di llama.cpp in uso (leggila da `llama-server --version` o dall'endpoint `/props` se disponibile a runtime)
- Indicatore sintetico dello stato del PC host (es. online/raggiungibile)
- Pulsanti azione sempre accessibili: Avvia, Ferma, Riavvia

### 5.2 Sidebar sinistra (comprimibile, a icone+etichetta, stile identico agli screenshot allegati)
Voci di menu:
- Dashboard principale
- Analytics (storico, punto 4.10)
- Parametri di generazione (sampling/penalties, punto 4.9)
- Parametri server (punto 4.8)
- Selezione modelli (file browser GGUF/mmproj, punto 4.6)
- Impostazioni (percorso binario, cartella modelli, prezzo energia, punto 4.5)

### 5.3 Dashboard principale (contenuto centrale)
Pannelli/card in tempo reale, con grafici ad andamento (sparkline o simili) non solo numeri statici:
- **Una card per ciascuna GPU rilevata** (dinamico, non fisso a 2): VRAM usata in GB e in %, utilizzo %, temperatura, e consumo in Watt — `nvidia-smi` espone il consumo istantaneo tramite il campo `power.draw` insieme al limite `power.limit`, includilo con sicurezza, non è un dato incerto
- **Card RAM**: usata/totale in GB e in %
- **Card CPU**: utilizzo % (per-core se possibile)
- **Card metriche di inferenza**: velocità di generazione (tok/s), velocità di prompt processing (tok/s), contesto attualmente occupato sul totale disponibile. Per il dettaglio "chi sta usando quanto contesto": richiede il flag `--slots` attivo sul server, che espone l'endpoint `/slots` con lo stato di ogni slot attivo — nota che con MTP/DFlash attivi lo slot è forzato a 1 (punto 4.7), quindi questa vista mostrerà un solo utente finché in futuro non si passerà a `-np` maggiore di 1; costruiscila comunque fin da subito, pensata per scalare a più slot
- **Pannello log del terminale**: sotto le card sopra, con un toggle per nasconderlo/mostrarlo e liberare spazio quando non serve consultarlo

## 6. Flusso di lavoro Git/GitHub

Il progetto va versionato con git e pubblicato su GitHub fin dall'inizio. Segui queste pratiche standard:

- Inizializza il repository al primo commit utile, con un `.gitignore` appropriato per Python (ambiente virtuale, `__pycache__`, file di configurazione locale con percorsi/chiavi specifiche della macchina — questi ultimi vanno tracciati come file di esempio, es. `config.example.json`, non come file live dell'utente)
- **Prima di ogni commit**: verifica che il codice non contenga errori di sintassi e che l'applicazione si avvii correttamente (un controllo minimo va bene: import puliti, avvio del server FastAPI senza eccezioni, nessun errore evidente)
- Scrivi commit atomici e descrittivi (un commit = una modifica logica coerente, messaggio che spiega il cosa e il perché, non solo "fix" o "update")
- Mantieni un `README.md` aggiornato ad ogni funzionalità significativa aggiunta: cosa fa il progetto, requisiti, istruzioni di installazione e avvio, struttura delle cartelle
- Se aggiungi altri documenti (es. note di architettura, changelog), tienili aggiornati insieme al codice, non come attività separata da fare "dopo"
- Struttura il progetto in modo convenzionale e leggibile (separazione chiara tra backend, frontend, file di configurazione/preset), non tutto in un unico file monolitico oltre una certa dimensione

## 7. Fuori scope per questa fase

- Supporto vLLM/sGLang
- Gestione multi-utente concorrente
- Script di auto-aggiornamento di llama.cpp (aggiornamento manuale per ora)

## 8. Approccio di sviluppo suggerito

Costruisci per fasi incrementali, ognuna testabile prima di passare alla successiva. Applica il flusso Git del punto 6 fin dalla Fase 1, non solo alla fine:

1. **Fase 1**: backend minimo con avvio/stop/riavvio del processo + streaming log via WebSocket, frontend che mostra solo questo
2. **Fase 2**: sistema preset completo (CRUD, salvataggio JSON, layer di traduzione flag)
3. **Fase 3**: monitoraggio risorse (CPU/RAM/GPU, incluso consumo Watt) in tempo reale, con grafici ad andamento
4. **Fase 4**: file browser modelli + supporto mmproj + speculative decoding + parametri di generazione (punto 4.9)
5. **Fase 5**: Analytics — parser dei log per i timing, database SQLite, correlazione con i consumi energetici, pagina con i grafici storici (punto 4.10)
6. **Fase 6**: header con stato/versione/controlli, sidebar comprimibile, rifinitura del design secondo il punto 5

## Appendice: comando llama-server attualmente in uso (riferimento)

```
llama-server ^
  -m "C:\Users\leoga\.lmstudio\models\unsloth\Qwen3.8-27B-GGUF\Qwen3.8-27B-Q4_K_S.gguf" ^
  -a "Qwen3.8 27B Q4_K_S" ^
  -c 100000 ^
  -ngl 99 ^
  --tensor-split 8,16 ^
  --main-gpu 1 ^
  --split-mode layer ^
  -fa on ^
  --cache-type-k q8_0 --cache-type-v q8_0 ^
  --spec-type draft-mtp --spec-draft-n-max 2 ^
  -np 1 ^
  --load-mode mlock ^
  -t 6 ^
  -tb 12 ^
  -ub 1024 ^
  --cache-reuse 256 ^
  --jinja ^
  --host 0.0.0.0 ^
  --port 8080 ^
  --metrics ^
  --slots
```

Tutti questi parametri devono essere rappresentabili come impostazioni semantiche nel sistema di preset descritto al punto 4.3. `--slots` è stato aggiunto rispetto al comando originale: serve alla dashboard per il dettaglio di utilizzo del contesto per slot (punto 5.3).

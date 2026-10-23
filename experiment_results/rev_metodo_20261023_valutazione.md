# Valutazione di `rev_metodo.DOCX` (2026-10-23)

Documento valutato: `rev_metodo.DOCX` (root, 50.516 byte, scritto 23/10 21:56),
revisione metodologica esterna firmata da un altro LLM sul metodo di misura
**in regime LHM power-integration**. Letto integralmente (116 paragrafi +
2 tabelle, estratto con la ricetta zipfile/UTF-8).

Regola di lettura: il testo è spunto, non autorità; ogni claim qui sotto è
confermato, confutato o accettato contro file:riga o misure eseguite.

## 0. Il documento è parzialmente datato: descrive il metodo PRE-EMI

La revisione è scritta quando il metodo principale era
`power-integration` (LHM + integrazione trapezoidale). Dal commit `3b45a72`
il principale su Windows è `emi-counter` (contatore cumulativo, nessuna
integrazione, nessun token elevato), con LHM declassato a fallback
(`d7d1fce`). Questo sposta la priorità di diversi suoi punti:

- **"La cadenza reale è 3 Hz, non 20 Hz" (§2)** — era vero per LHM
  (intervallo PI osservato 0,280–0,340 s; 1 Hz nella lettura pulita del
  23/10), ed è il motivo metrologico per cui siamo usciti dall'integrazione.
  Riesaminando con `tools/emi_cadenza_analysis.py` i 4 CSV del probe committati
  oggi (800+2000+800+2000 letture a 50 ms e 10 ms): il registro EMI cambia
  valore E timestamp a ogni lettura — 0 timestamp duplicati su ~11.200
  transizioni consecutive, solo 2 `v0` identici; la cadenza arriva a 100 Hz
  senza che il polling sia il collo di bottiglia. **Il limite di cadenza non
  si applica al principale.** Il costo vero osservato e' un altro: nel probe
  live a 20 Hz la cadenza del sampler passa da 0,0506 s mediana (idle) a
  0,0770 s (spin 1 thread, +27 ms/lettura) — il thread del sampler, sotto
  carico, e' esso stesso carico di osservazione. Distribuzione completa in
  `emi_cadenza_distribuzione_20261023.md`.
- **"Non sostituirei ora LHM con un driver personalizzato" (Verdetto finale)**
  — superata dai fatti e dalla direzione già decisa: EMI non è un driver
  custom, è il canale ACPI documentato da Intel (Beyer & Wendler, LNCS 12079),
  letto via `ctypes` senza codice kernel, e la sua adozione è avvenuta con
  confronto a finestra uguale (rapporti 0,9947–1,0082) + rollback
  `CW_PRIMARY_CHANNEL=lhm`. LHM resta, quindi la premessa della frase non è
  mai stata "sostituire".
- **Sensibilità alla fase di campionamento dell'integrale (§2)** — per il
  principale è eliminata alla radice: la somma del residuo di una funzione di
  stato (contatore cumulativo) non dipende dai campioni intermedi, mentre
  l'integrale trapezoidale di una potenza istantanea sì. Il buffer (t, cum)
  @0,05 s serve solo a leggere i bordi di finestra, non a integrare.
  Il "test di sensibilità" proposto al §2 per LHM non è più la priorità; lo è
  il freeze del protocollo v4.

## 1. Impostazione complessiva: corretta e già nostra

La separazione in tre proprietà distinte — validità della misura, validità
della stima incrementale, validità dell'attribuzione a Ollama — è esattamente
come `local_energy.py` già etichetta (campi metodo separati per riga CSV,
[casualwatt_csv_export.py:63](../cwEnergyModular/casualwatt_csv_export.py):
`cpu_attribution_method`, `measurement_boundary`). Anche §6 è d'accordo con
verdetti già presi e committati:

- EMI/LHM "se leggono entrambe RAPL il confronto valida coerenza, non
  accuratezza assoluta" — è la nostra regola `same-counter ≠ validazione
  indipendente`, già scritta nella memoria di progetto e nei report; la scala
  assoluta resta non arbitrata (wattometro / Linux+PSYS nel backlog).
- SRUM 0,9946 — la lettura severa del reviewer ("valida il parser ctypes
  contro la decodifica Microsoft, non l'accuratezza fisica") è la stessa
  conclusione a cui eravamo arrivati da soli (commit 580c796).
- Righe `manual_override` separate dal dataset principale: già fatto
  (audit b760cbd: 2 righe valide su 9, verdict dichiarato).

## 2. Punti veri e operativi che NON abbiamo ancora implementato

Questi quattro sono il valore residuo del documento.

a) **Baseline: pre/post con criterio di accettazione (§3, §7.3).** Oggi
   calibriamo una `P_idle` per sessione e la trattiamo come costante nella
   finestra. Il reviewer propone: misurare la baseline prima E dopo ogni
   benchmark, registrare l'eventuale deriva, definire a priori la soglia
   oltre cui il run è "instabile" (non corretto a posteriori), e valutare in
   sensibilità una baseline interpolata lineare tra le due letture. Coerente
   con l'evidenza che abbiamo già: baseline 13,39→12,19 W fra run v3, e
   derivata ∂e_token/∂P_idle = −T/N verificata numericamente (−0,0766/−0,1134
   J/token/W). Va messo nel verbale di protocollo v4 come campi
   `baseline_start_w`, `baseline_end_w`, `deriva_baseline_w_s`,
   `run_stabile_si_no`.

b) **Decomposizione in tre campi con geometria temporale dichiarata (§4).**
   I campi esistono già, con i nomi reali `package_energy_j` (lorda),
   `active_energy_j` (incrementale dopo il fondo), `ollama_active_energy_j`
   (quota attribuita) + `cpu_time_share`;
   [casualwatt_csv_export.py:32-33](../cwEnergyModular/casualwatt_csv_export.py).
   ma il denominatore `Δt_cpu_ollama/Δt_cpu_busy` è definito sull'intera
   finestra. La critica "la quota va definita rispetto allo stesso intervallo
   temporale della misura energetica, normalizzata alla capacità realmente
   disponibile" è fondata: vanno dichiarati nel CSV la finestra del rapporto
   e il valore di capacità (n. core), e il rapporto va calcolato sulla stessa
   sottofinestra della richiesta (già così per le righe, da verificare per la
   calibrazione).

c) **Campi "source" vs "calculation" (§ registro diagnostico).** Il reviewer
   nota che `cpu_energy_source_method` ([casualwatt_csv_export.py:166](../cwEnergyModular/casualwatt_csv_export.py))
   rischia di far credere che la sorgente fornisca un contatore energetico
   quando il percorso LHM integra una potenza. Su `emi-counter` il problema è
   in parte rientrato (le note per riga dicono "cumulative EMI counter buffer
   (no integration)", `local_energy.py:cpu_attribution_method`), ma la
   colonna esplicita di *come* si ottiene l'energia non esiste. Aggiungerla
   (`energy_calculation_method`) è a costo quasi zero e toglie l'ambiguità
   anche sulle righe storiche.

d) **HWiNFO non va escluso prima di aver risolto err=2 (§6).** Condiviso: è
   nel backlog, e il manuale locale (p.14 Settings>General/UI) indica dove
   cercare. Nessuna azione adesso.

## 3. Una correzione al documento

"Chiudere la GUI non elimina tutto l'overhead di LHM" è giusto e ci riguarda
adesso in un punto diverso: il nostro sampler EMI legge il device ogni 0,05 s
in un thread dedicato *sempre attivo*, e il costo dell'osservatore che abbiamo
arbitrato (0,2–0,9 W, commit d06eea0) era quello della GUI LHM, non del thread
EMI. Prima della v4 serve lo stesso A-B-A col reader EMI attivo/inattivo, e
una prima risposta e' arrivata dalla cadenza: riesaminando i 4 CSV del probe
a 50/10 ms committati oggi, il registro EMI cambia valore e timestamp a OGNI
lettura (0 timestamp duplicati su ~11.200 transizioni, 2 soli `v0` identici),
quindi il refresh non e' il limite — il "3 Hz" del §2 riguardava LHM. Ma nel
probe live a 20 Hz la fase spin 1 thread allunga la cadenza del sampler da
0,0506 a 0,0770 s mediana (+27 ms/lettura): il thread del sampler SOTTO
CARICO e' esso stesso un carico di osservazione. Distribuzione completa e
azione proposta in `emi_cadenza_distribuzione_20261023.md` (harness
`cwEnergyModular/tools/emi_cadenza_analysis.py`).

## 4. Cosa NON cambia

La scala assoluta resta non arbitrata; i protocolli v2/v3 pubblicati restano
pre-fix e pre-EMI, confrontabili solo fra loro; il rilancio v4 (n. richieste
fisso, geometria a·N_in + b·N_out, keep_alive dichiarato) è la priorità e il
documento, al §5, fornisce le condizioni di confrontabilità da elencare nel
verbale (modello, quantizzazione, richieste, token, keep_alive, warm-up,
finestra, baseline, config).

## Azioni proposte (in ordine, ciascuna un commit)

1. `energy_calculation_method` nel CSV (puntuale, basso rischio).
2. Verbale protocollo v4 con i campi baseline pre/post + criterio di
   accettazione + elenco di confrontabilità del §5.
3. A-B-A sul costo in W del thread sampler EMI (sampler attivo/inattivo sulla
   stessa trace). L'effetto sulla sola *cadenza* e' gia' misurato nel §3;
   manca il numero in watt, che e' quello che entra nella baseline.
4. HWiNFO err=2 (backlog, non bloccante).

# AGENTS.md — regole vincolanti per chi lavora in questo repository

CasualWatt misura l'energia di una singola inferenza LLM locale su Windows,
leggendo il contatore energetico del package CPU. Il repository contiene insieme
il codice di produzione, i dati sperimentali e una tesi di laurea; le regole qui
sotto esistono perche' ognuna di esse corrisponde a un errore gia' commesso o a
una decisione gia' presa e documentata.

I numeri e gli ancoraggi di questo file sono verificati al **24-10-2026**; i tre
conteggi (suite di test, script `.py` di radice, file di `experiment_results/`) sono
riverificati al **26-10-2026** perche' erano stantii, e il conteggio della suite
e gli ancoraggi di `local_energy.py`/`energy_session.py` sono riverificati al
**27-10-2026** dopo l'uscita di LHM dall'implementazione (D18, 8 test rimossi) e
di nuovo al **28-10-2026** dopo NVML, AMD SMI, le tre colonne per token, il
controllo di timestamp del contatore AMD, il fallback `pawnio-counter` e il flag
`external_counter` (D14). Il conteggio della suite, le righe dei tre schemi CSV
e le coordinate dei campi di `local_energy.py` sono riverificati al
**02-11-2026** dopo `cd881e6b` (provenienza dei token ed energia firmata) e
`9fa9a44c` (finestre con contatore incoerente non valide): la suite e' a **528**
e `CSV_COLUMNS` a **174** nomi. Il conteggio della suite e le coordinate dei
nuovi helper GPU di `energy_session.py` sono riverificati al **03-11-2026** dopo
la selezione del dispositivo GPU (13 test nuovi, `482 + 59 = 541`): `CSV_COLUMNS`
resta a **174** nomi perche' la selezione passa per `notes`, non per una colonna.
Il **04-11-2026** e' riverificato il pacchetto di ancoraggi che la tesi cita dallo
`schema CSV` in poi (nomi e righe di `casualwatt_csv_export.py`, durate di fase,
scorporo del giudice, enumerazione per richiesta, salto del ramo cloud, template
di record) e la suite produce gli stessi **541** node id (`538 + 3`); con l'ingresso
del criterio robusto del valutatore (`cf6aca71`, `6b1dccb8`), lo stesso giorno, la
raccolta e' a **577** node id (`574 + 3`), 482 in `tests/` e 95 alla radice; sulla
selezione GPU la docstring di `_open_gpu_monitor` ora dice cosa arriva davvero nella
riga --
`gpu_device_index` e la nota in `notes` -- perche' `device_selection` e' un
attributo del monitor, letto dai test, e non finisce nel CSV. Nello stesso giorno
il conteggio dei file tracciati sotto `experiment_results/` e' riverificato a
**219** ($218$ in radice, $1$ in `codecarbon_four_way/`): il $210$ del 26-10 era
stantio di nove file entrati fra il 28 e il 29-10.
Il conteggio della suite e' riverificato la **sera del 04-11-2026**, dopo i tre
interventi di codice che l'audit tecnico dello stesso giorno ha chiesto e che sono
stati applicati come commit separati (`b3b12ffe` registro PKG fermo, `86bba6a8`
delta de-clampato sul percorso a campioni, `4b922db6` ragione dell'N/A per
`gpu_process_energy_j`): la raccolta e' a **587** node id (`584 + 3`), **492** in
`tests/` e 95 alla radice. `CSV_COLUMNS` resta a **174** nomi, perche' nessuno dei
tre tocca lo schema: il primo scrive `counter-invalid` in una colonna che esiste
gia', il secondo cambia il segno di un valore che la colonna gia' accetta, il terzo
passa per `notes`.
La raccolta e' riverificata nella **notte del 04-11-2026** (commit delle 22:04,
22:11, 22:20 e 22:28), dopo i quattro fix minimi chiesti dalla revisione del
valutatore (`98ec5972` tolleranza derivata, `8a91e16c` registrazione degli
argomenti inviati al tool, `40f6c619` declassamento di `acc_comp`, `5f23853d`
incertezza a livello di task): **608** node id (`605 + 3`), **493** in `tests/` e
**115** alla radice. `CSV_COLUMNS` resta a **174** nomi anche qui, per la stessa
ragione: la tolleranza e' un campo del contratto gia' accettato da
`robust_evaluator.validate_contract`, gli argomenti passano per `args` nel passo
gia' presente in `notes`, `acc_comp` si declassa attraverso le note di riga e il
bootstrap aggiunge chiavi al riepilogo JSON, non al CSV. I tre salti **non**
stanno in `test_rapl_zone.py`, come questo file ha affermato fino ad ora: stanno
in `tests/test_rapl.py` (`test_rapl_basic`, `test_rapl_readings`,
`test_rapl_idle_window`, la cui docstring chiede un host Linux; il quarto,
`test_rapl_diagnostics`, passa anche qui). Correzione di un ancoraggio stantio,
rilevata rigenerando l'Appendice D, non cambio di comportamento.
Gli altri due conteggi di quella riga sono riverificati dopo `244d1c2f` (23:05 dello
stesso 04-11, la sonda Monte Carlo di P6.4): gli script `.py` tracciati alla radice
sono **36** (erano 35, e il nuovo e' `montecarlo_protocollo_p64_probe.py`), e i file
tracciati sotto `experiment_results/` sono **220** ($219$ in radice, $1$ in
`codecarbon_four_way/`), perche' lo stesso commit porta la sua analisi accanto alla
sonda. La suite resta a **608**: quel commit non aggiunge test.
La suite e' riverificata al **05-11-2026**, dopo i test del valutatore entrati su
`emenda-8` con `52e1d77c` e `180f8638` (id parametrizzati) e dopo i due punti GPU
del backlog EMInote: `calibrate_gpu_idle` (`energy/energy_session.py`, che assegna
`idle_gpu_power_w`, il campo che `energy/local_energy.py:931` legge e che nessun
percorso di produzione riempiva) e il termine GPU condizionale di `settle_idle`
(stessa sessione, con la dichiarazione in `notes` dal runner). La raccolta e' a
**822** node id (`819 + 3`), **801** dei quali preesistevano a questi due punti --
misurati su un worktree distaccato a `180f8638`, non dedotti per aritmetica. Il
delta misurato e' **+21**: **9** in `tests/test_gpu_idle_baseline.py` e **12** in
`tests/test_settle_idle_gpu.py`, contati eseguendo i due file. I **608** delle
righe sopra restano storia datata al 04-11; fra il 04-11 e il 05-11 la suite e'
cresciuta di 193 node id per i test del criterio robusto del valutatore. La
ripartizione misurata il 05-11 e' **514** in `tests/` e **308** alla radice
(`test_answer_type_evaluation.py` 168, `test_robust_evaluator.py` 59,
`test_mudilab_adapter.py` 26, `test_evaluation_runner.py` 23,
`test_validazione_valutazione.py` 22, `test_tool_provenance.py` 8,
`test_synthetic_window.py` 2); i conteggi per file del paragrafo «I test stanno
in due posti» restano datati al 04-11 e non si aggiornano a memoria.
La suite e' riverificata la **notte del 05-11-2026**, dopo le quattro fasi di
verifica e correzione chieste sul ramo `emenda-8`: FASE 1 (ramo TTFT di
`local_energy.py` -- `active_energy_j`/`active_energy_raw_j` ricalcolati dopo
la sovrascrittura di `package_energy_j`, sub-baseline scalata sulla FRAZIONE
di tempo monotono cosi' che la somma delle due quota e' esattamente la
baseline di riga, nota di deriva oltre 1e-3 J fra il delta dei bordi e la
somma delle parti), FASE 2 (`benchmark_v4.py::infer_v4_stream` -- un chunk
finale assente non produce piu' `prefill_duration_s = 0.0` e
`decoding_duration_s = 0.0`, bensi' `None` con la nota `stream_incomplete`;
il costo di una IOCTL in piu' per riga e' dichiarato nella docstring di
`read_ttft_edge`), FASE 3 (`gui/benchmark_panel.py` -- il messaggio "nessun
contatore GPU attivo" e' sostituito da `_gpu_idle_missing_message`, che
distingue `gpu_mon is None` / `available=False` (nessun monitor) da
`available=True` / `energy_counter=False` (monitor presente, contatore
assente, la riga resta in sovrastima dichiarata con
`gpu_idle_provenance='missing'`)). La raccolta e' a **845** node id, con
**842 passati e 3 saltati** e **0 falliti** (eseguita alle 9,97 s dalla
radice con `pytest cwEnergyModular -q`). Il delta sui **822** del mattino
e' **+23**, tutti contati con `pytest --collect-only -q` e non per
aritmetica: 2 in `tests/test_edge_window.py` (timestamp non crescenti e
coerenza `dt_W_s`/`duration_s` nei tre rami di base temporale), 2 gia'
presenti in `tests/test_shared_components_v4.py` (`infer_v4_stream_registra_ttft`
e `infer_v4_stream_senza_primo_token`), **11** nel nuovo
`tests/test_ttft_split.py` (sub positive, una sub negativa, entrambe
negative, somma a zero, `dt_W_s != dt`, contatore assente su una sub,
bordo fuori finestra a destra, bordo uguale a `t_start`, deriva sopra e
sotto soglia, invarianza di `cpu_time_share`/`ollama_active_energy_j`
fra rami con e senza TTFT), **3** in `tests/test_shared_components_v4.py`
dalla FASE 2 (`senza_done_lascia_durate_none`,
`done_legge_prefill_e_decode`, `prefill_zero_umelegibile_da_none`) e
**5** nel nuovo `tests/test_gpu_skew_and_gui_message.py` (denominatore
monotono non device-clock, timestamp fermo con delta positivo, e i tre
messaggi GPU del pannello: nessun monitor, monitor presente senza
contatore, monitor non disponibile). Il generatore `tools/dump_tests_latex.py`
conferma: `node id raccolti: 845`, `Copertura delle docstring: 845 righe
documentate su 845`, nessun `\textbf{fallito}` ne `\textbf{errore}`; i tre
salti restano i tre di `tests/test_rapl.py:43` (lo dichiara il generatore
nella propria sezione "Motivi dei salti"), non di `test_rapl_zone.py`. I
conteggi del parser, sulla stessa regola delle appartenenze usata qui dal
04-11 mattina: **610** funzioni per `(percorso, classe, nome)`, **609**
ignorando la classe, **570** monoriga + **275** righe parametrizzate come le
stampa il parser (`_spezza_node_id` con `prm = ""` per l'istanza `[]`), **53**
file; **537** node id stanno in `tests/` e **308** alla radice di
`cwEnergyModular/`. Il delta $822 \to 845 = +21 + 2$ (ventuno entrati con le
tre fasi, due gia' presenti nel file dei componenti condivisi prima della
FASE 2) si chiude senza ammanchi ne' righe scomparse: nessun test esistente
e' stato rinominato o rimosso.
Lo **schema dei metadati** e' riverificato al **06-11-2026**, dopo la chiusura del
bug `keep_alive` sulla forma che il motore accetta davvero (il numero, non la
stringa): `CSV_COLUMNS` resta a **174** nomi perche' lo schema P5 congelato non si
tocca, mentre `RUN_METADATA_COLUMNS` resta a **30** nomi: la colonna
`ollama_version` promessa in quel giorno non e' mai entrata nel codice
(`casualwatt_csv_export.py:343-357` la conta oggi, e il generatore
`tools/dump_schema_latex.py --macros` restituisce `nColonneMetadati=30`); le
coordinate dei quattro schemi sono righe 17-204 / 212-227 / 229-237 /
343-361. L'Appendice A rigenerata lo stesso giorno da
`tools/dump_schema_latex.py` porta $174$ + $30$, $77$ di riga + $1$ di metadato
`nuova`, $28$ `vuota`, header $99$ e $29$: le $174$ + $30$ e l'$1$ di metadato
`nuova` della riga datata 04-11 restano in piedi come storia datata, non vengono
riscritte.
Lo stesso 06-11, dopo, quei sette numeri hanno smesso di essere scritti a mano.
`python tools/dump_schema_latex.py --macros` stampa un file di `newcommand`
(`nColonneRiga`, `nColonneMetadati`, `nNuoveRiga`, `nNuoveMetadati`, `nCampiVuoti`,
`nHeaderRiga`, `nHeaderMetadati`) che `main.tex` legge in preamble con
`\input{generated/numeri_schema}` e che cap.\,4, cap.\,5 e l'Appendice A citano come
matematica inline; lo stesso generatore, nella stessa invocazione, produce anche la
tabella, e i due output escono dalla medesima funzione di conteggio che etichetta le
celle. Per questo il corpo e l'appendice sono allineati senza riscrivere numeri:
il commento di `cap04:553-558`, la prosa di `cap04:~597` e l'elenco di
`cap05:112-116` dicono tutti $30$, e il generatore conferma `nColonneMetadati=30`.
Nello stesso colpo l'ancoraggio `:340-354` di cap.\,4, che era stantio di tre righe
anche prima di questa colonna, e' $343$-$361$, e la voce del verbale in cap.\,5
distende le colonne **nel file** (`nHeaderMetadati`, $29$) da quelle **nel codice**
(`nColonneMetadati`, $30$) e nomina le due accodate dopo l'ultimo run. Il file generato sta in
`Tesi-latex/`, quindi fuori da git, e va rigenerato insieme alla tabella.
Il conteggio della suite NON e' riverificato da questo intervento, e le due
fotografie qui sotto sono dello stesso giorno con lo stesso albero sporco del
backlog GPU: la raccolta si muove mentre si misura. All'ultima riesecuzione del
mattino, **871** node id con **854 passati, 14 falliti e 3 saltati**; alla
misurazione delle 12:04, **888** node id con **871 passati, 14 falliti e 3
saltati** -- cioe' $+17$ node id entrati nel frattempo e quattro cadute in meno:
i tre `tests/test_ttft_split.py` e `tests/test_settle_idle_gpu.py:137` che quel
primo conteggio annoverava fra i falliti ora passano, e la loro assenza dal
elenco e' misurata, non dedotta. Le quattordici rimaste stanno tutte sul nuovo
contratto di identita' GPU e si dividono in tre forme, contate eseguendo i file:
**5** sollevano `RuntimeError: calibrazione idle GPU non conservata ...
(prima=None, dopo=None)` in `tests/test_gpu_idle_baseline.py` perche' il fake non
dichiara l'identita' e `energy/energy_session.py` non riceve un `uuid`; **6**
asseriscono che la baseline non e' stata sottratta (cinque `1000.0 != 800.0` fra
`tests/test_gpu_nvml_energy.py:244`, `tests/test_gpu_amdsmi.py:325` e i due
parametri di `A2` piu' `test_energy_corrections.py`, e un `600.0 != 480.0` di
`B2`); **3** sono i `P2` della provenienza, che vedono `identity-unavailable`
lì dove il test e il vocabolario detto alla GUI (FASE 3) aspettano `missing`.
La causa del gate e' confermata: `calibrate_gpu_idle` e `_gpu_identity` esistono
solo sull'albero sporco -- a HEAD `180f8638` il `grep` di `calibrate_gpu_idle`,
`_gpu_identity`, `get_uuid`, `get_amd_uuid`, `get_bdf`, `identity-unavailable`
da' **zero** colpi sotto `cwEnergyModular/energy/` -- e nessuna fixture della
suite dichiara l'identita', quindi la calibrazione raise, `gpu_idle_provenance`
finisce `identity-unavailable` e la riga sottrae $0$ invece dei 200 J di baseline
(`energy/local_energy.py:1090`, con `baseline_valid` che dipende da
`_gpu_idle_identity`). E' un cambio di contratto non propagato alle fixture, non
un bug di calcolo, e non riguarda ne' lo streaming ne' `keep_alive`. Resta aperta
una conseguenza di vocabolario che i tre `P2` stanno esattamente testando: con
l'identita' illeggibile il token `missing` non e' piu' prodotto, e con esso lo
stato legittimo "mai calibrato" -- la FASE 3 del pannello GUI e la prosa che
distingue "nessun monitor" da "monitor senza contatore" vanno rilette quando quel
lavoro si chiude. Gli **845** raccolti con **0 falliti** del 05-11
restano la fotografia di un altro albero, finche' quel lavoro non e' chiuso e il
conteggio non e' rigenerato. La tesi e' ricompilata due volte il 06-11: dopo la
rigenerazione dell'Appendice A (`pdflatex`, `biber`, `pdflatex` x2) il log da'
**195 pagine, 0 `Overfull \hbox`, 0 riferimenti indefiniti** -- lo stesso numero
ancorato il 04-11 -- e dopo l'allineamento dei capitoli con le macro **196** con
gli stessi **0** e **0**; i due `main.toc` non sono stati confrontati, quindi la
pagina in piu' non e' localizzata e resta una misurazione, non un diff.
Se un ancoraggio non torna, il file e' stantio: va corretto, non ignorato.

Fonti primarie, in ordine di autorita':

1. `experiment_results/protocollo_v4_20261024.md` — decisioni congelate P1-P4,
   formulario consolidato F.0-F.17 e sezione preparatoria P6 (derivata, senza
   decisioni);
2. il codice in `cwEnergyModular/`;
3. gli artefatti tracciati in `experiment_results/`;
4. questo file.

---

## Regole dure

- **Mai `git push`** se non richiesto esplicitamente. Il lavoro e' locale.
- **Mai toccare `.casualwatt_keys.json`**: non crearlo, non leggerlo, non
  scriverlo, non forzarne l'aggiunta, non rimuovere la sua riga da `.gitignore`.
  Al 04-11-2026 **esiste sul disco** in `cwEnergyModular/`, non e' tracciato e la
  sua riga sta in `.gitignore:18`: la regola non cambia, cambia il fatto che la
  frase precedente descriveva.
- **Un commit per punto.** Ogni punto del protocollo congelato, e ogni modifica
  concettualmente unitaria, ha il suo commit con messaggio che dice cosa e'
  cambiato e perche'.
- **Se c'e' un problema, fermarsi.** Riportare il problema invece di aggirarlo.
  Nessun workaround silenzioso, nessun test disattivato, nessuna soglia spostata.
- **Mai `git add -A` ne' `git add .`**: aggiungere i percorsi esplicitamente. Alla
  radice ci sono materiali dell'utente (`.DOCX`, `.txt`), archivi e directory
  sottoposte ad audit che non devono entrare nel repo.
- **Un claim e' valido solo se ancorato**: `file:riga`, artefatto tracciato, o
  fonte esterna verificata alla fonte primaria con la data della verifica. Il
  materiale fornito dall'utente e le descrizioni prodotte da altri LLM sono
  **spunti, non evidenza**: vanno verificati prima di entrare in un documento.
- **Non sostituire il metodo in produzione senza evidenza sperimentale.**
  Tenere l'attuale finche' un esperimento non dimostra che l'alternativa e'
  migliore. Confrontare non significa adottare.

## Stato corrente del lavoro

P1 (baseline), P2 (token e terminazione), P3 (geometria e modello), P4
(incertezza e validazione) e P5 (schema CSV e runner, 2026-10-26) sono
**congelati**. P6 (esecuzione e analisi) e' **aperto**. P6 contiene P6.1
(pavimento di tempo a muro) e P6.2 (obblighi del pilota), derivati, e tre
requisiti adottati come
vincolanti: P6.3 (audit idle), P6.4 (simulazione Monte Carlo) e P6.6 (prova di
attribuzione ripetibile, 2026-10-25). Per la banda di concordanza di P6.6 e'
stata adottata l'Option C (pre-pilota di ripetibilita', 2026-11-06): la banda
si congela dopo un run di calibrazione su configurazione fissa con R repliche e
fasi >= 5 bucket, non prima del primo run in senso assoluto (emendamento
esplicito al protocollo). Pre-pilota completato: 3 fasi valide (prep-r3, prep-r5, prep-r6). Banda congelata: B_abs=0.6, B_rel=1.1 (margine 20%). Piano: prep_plan_frozen.json.

Esecuzione P6 (2026-11-06): P6.1 aritmetica documentata (2h33min pavimento). P6.2 pilota eseguito (qwen2.5:0.5b + gemma2:9b, 6 record, 0 errori). P6.3 audit idle eseguito (seconda run con 120s assestamento): 5 finestre, range 0.86 W < 1.0 W soglia -> macchina STAZIONARIA, campagna sbloccata. P6.4 sonde Monte Carlo eseguite (5/5 verifiche ciascuna). P6.6 pre-pilota completato, banda congelata. Prova completa: 10 configurazioni x 3 prompt, 0 errori. Confronto CodeCarbon eseguito (0.000304 kg CO2eq). Fixture GPU allineate al contratto di identita' (UUID): 73 test GPU verdi; suite a **943** node id raccolti, **940 passati** e **4 saltati** (3 RAPL, 1 modulo ecologits), 0 falliti (misurato la sera del 07-11, dopo i **+37** node id di `tests/test_s_epi_phase.py` (22) e `tests/test_geometry.py` (15); il totale eseguito e' 944 perche' lo skip di modulo non compare in `--collect-only`; i **906** con **903 passati** sono la fotografia del 07-11 dopo P6.5, eseguita 907). P6.5 (risolutore QR/SVD della superficie predittiva) e' **chiuso sul lato analisi il 2026-11-07**: `cwEnergyModular/surface_fit.py` implementa F.7/F.9 con QR sul disegno standardizzato e β in unità P3.3, con 14 node id in `tests/test_surface_fit.py`; la riga di P5 fa fede sulla collocazione (analisi, non runner) e la sonda storica di P6.4 resta sulle equazioni normali per non spostare i propri artefatti, come dichiarato nel protocollo.

Allineamento del pilota (2026-11-07, sera). `s_epi_phase.py` e' promosso da
harness di radice a modulo di analisi (`cwEnergyModular/s_epi_phase.py`, con
`git mv`) e legge la finestra di fase e i due tempi di assestamento dalle colonne
del runner v4 (`timestamp_start`/`timestamp_end`, `settle_pre_s`/`settle_post_s`),
non dalla forma dei bucket SRUM: un valore assente resta vuoto con la sua
provenienza (`settle_source`) e un flag non bloccante, mai dedotto dai bucket.
`cwEnergyModular/geometry.py` promuove la metrica di F.13 (`hull_margin_tok`,
distanza perpendicolare euclidea dallo spigolo, coordinate grezze, negativa
fuori) con due inviluppi e la fascia piu' conservativa. Il pilota P6.2 e'
aggregato da `cwEnergyModular/tools/aggregate_p62_pilot.py` in
`experiment_results/p62_pilot_aggregated.json`: il file che il mandato indicava
(`experiment_results/prep_after6.csv`) e' un dump SRUM del pre-pilota P6.6 e non
ha colonne di baseline, e il CSV del pilota del 06-11 (6 record) e' stato
sovrascritto dai run successivi, quindi le terne sopravvissute sono le 8
esecuzioni di blocco del runner v4 del 06-11 sera (`half_range_pre_w` fra
0,302665 e 2,256709 W, mediana 0,865126; `u_within_b` nullo perche' `m = 1`).
Su quei dati `experiment_results/prep_plan_frozen.json` porta la decisione
datata `C = 10`, `R = 3`, con la regola (la terna di P4.12 vuole tre
osservazioni) e il numero dichiarato (errore proxy 0,0639 = 10,6% di `B_abs`,
banda larga 9,4 errori proxy).

Criterio del gate e blocco di controllo (07-11-2026, notte). Il blocco di
controllo di P4.4 e' nel runner da `1be804bb3` (`control_wait_s`,
`_run_control_window`, `run_block(..., control=True)`); la notte del 07-11
entrano i due pezzi mancanti, come commit separati. `cwEnergyModular/control_gate.py`
applica F.12 come modulo di sola analisi, con lo stesso registro di
`surface_fit.py` e `geometry.py`: filtro assoluto `pre_range_w <= 1,0 W` e
`|dP| <= 1,0 W`, verdetto per blocco su `budget_base_j`, `bias_w` come rapporto
delle somme sui soli controlli utilizzabili, quorum `ceil(2/3 * n_coppie)` e
`chain_status = bias_declared` sotto quorum; non calcola `u_bias,b` (chiede la
campagna principale) e non promuove nessuna riga a `validated`. I suoi **18**
node id stanno in `tests/test_control_gate_p45.py`. Il secondo punto fissa che
il riepilogo del controllo entra nello schema P5 **senza allargarlo**: le
quantita' `control_*` non hanno una colonna, `BLOCK_SUMMARY_COLUMNS` resta a 34
nomi e `block_kind`/`pair_id` identificano il blocco nel file consegnato
(`tests/test_controllo_p44_v4.py`). Il terzo chiude il contratto fra i due
moduli: sei blocchi passati per `run_block` vero, con la sola identita' di
coppia rietichettata, alimentano `evaluate_gate` e danno `pass` con
`bias_w = 0,1 W` contro la soglia 0,223607 W -- se un nome di campo divergesse
(`control_e_net_j`, `control_dt_w_s`, `pre_range_w`, `dP`, `budget_base_w`) il
gate si dichiarerebbe non eseguibile **dopo** aver misurato le sei coppie. La
suite e' a **977** node id raccolti, **974 passati** e **4 saltati** (3 RAPL, 1
modulo ecologits), 0 falliti; eseguita 978 perche' lo skip di modulo non
compare in `--collect-only`. **Il gate non e' stato eseguito**, e non per un
difetto di codice: P4.4 requisito 5 vuole `dt_nominal_s` fissato prima della
campagna, e le durate delle richieste del pilota P6.2 sono state sovrascritte
dai run successivi (righe sopra); le 8 durate sopravvissute in
`cwEnergyModular/results/casualwatt_v4_results.csv` (file ignorato da git, 8
righe, prompt `c-001`) -- mediana 0,4102935 s, tre volte 1,2308805 s -- sono
esecuzioni di blocco di un altro run del 06-11 sera, non il pilota che il
requisito nomina. Il numero c'e', la sua provenienza no, e una durata inventata
sarebbe un disegno diverso da quello congelato scoperto solo dopo i dati.

Eccezione dichiarata al congelamento, ora **chiusa** da Emenda 8 (2026-10-26):
la **forma di combinazione** di `budget_base_w` e' la **quadratura**
(`hypot` di `half_range_pre_w` e `half_drift_w`, `energy/benchmark_v4.py::block_baseline`),
adottato come covarianza/semi-ampiezze combinate, non come limite massimo
garantito — e **non** la somma aritmetica. L'impegno verso la campagna principale
era rinviato ai dati del pilota P2.9; il pilota e' eseguito (0,000304 kg CO2eq
confronto CodeCarbon) e la forma e' congelata; blocco della formula non si tocca
nel frattempo. La sola apertura metodologica che resta e' la loro
interpretazione come proxy di incertezza standard, non un incertezza assoluta
(P1.7, P1.13).

**Il codice sorgente di produzione e' sbloccato dal congelamento di P5**
(2026-10-26): la v4 si implementa contro il protocollo congelato, non contro la
descrizione che ne dava questo file. Lo stato aggiornato e' nella tabella in
testa al protocollo, non qui.

---

## Metodologia congelata

Le formule sono tutte in `protocollo_v4_20261024.md`, sezione *Formulario
consolidato* (F.0-F.17), con applicazione e giustificazione per ciascuna. Qui
stanno solo le regole che un agente puo' violare senza accorgersene.

- **Nessun fallback silenzioso.** La catena locale e' corta e va dichiarata: su
  Windows il contatore EMI (`emi-counter`), poi il contatore MSR del package
  letto via PawnIO (`pawnio-counter`, fallback dichiarato dal 28-10-2026), poi
  `unavailable`. LibreHardwareMonitor e' fuori dall'implementazione dal
  2026-10-27 (D18, metodo provato e superato) e non torna; su Linux i contatori
  RAPL. `CW_ENERGY_FILE` (DEV/TEST) ha precedenza su tutto. Non esiste piu'
  `CW_PRIMARY_CHANNEL`. **Il fallback non e' un secondo canale da sommare ne' una
  validazione di EMI**: `0x611` e `0xC001029B` sono lo stesso registro che legge
  EMI, quindi un accordo a finestra uguale e' coerenza di implementazione. La
  lettura via PawnIO **richiede un processo elevato**: da token UAC filtrato o
  SAFER `pawnio_open` risponde `0x80070005` e la ragione e' `access_denied`
  (misurato il 28-10-2026). EMI non ha questo requisito. Il canale va scritto per
  riga in `energy_calculation_method` (`energy/local_energy.py:151`), la finestra
  in `package_window_source` (`exact-counter | samples-fallback | counter-invalid
  | unavailable`, `:140-141`; `counter-invalid` dal 02-11-2026, `9fa9a44c`, e con un
  **secondo** trigger dal 04-11-2026 -- `b3b12ffe`, vedi la regola del registro fermo),
  l'origine della baseline in `idle_provenance` (`:142`) e, dalla v4, in
  `baseline_backend` — campo del protocollo P1.3, non ancora presente nel codice.
  Il flag `external_counter` (`:156`, D14) dice se quel numero viene da un canale
  **esterno** alla catena: vero solo per `energy-file` (`CW_ENERGY_FILE`), falso
  per EMI, PawnIO, RAPL e per le catene GPU. Serve a escludere le righe
  dell'override con un filtro booleano, non confrontando l'etichetta.
  Mai presentare un fallback come un contatore, ne' un integrale come un
  contatore.
- **Sulla GPU il token dice quale percorso ha prodotto il numero.**
  `gpu_attribution_method` comincia sempre con `nvml-energy` (delta del
  contatore cumulativo NVML, mJ) o `nvml-power-integral`, oppure con
  `amdsmi-energy` / `amdsmi-power-integral` sulla catena AMD. Il contatore si usa
  solo con delta non negativo e senza sottofinestre escluse, che un delta non
  sa sottrarre; un integrale non si presenta come contatore. Su AMD SMI la
  risoluzione si legge dall'API (`accumulator * resolution` in microjoule) e se
  manca o e' zero il contatore non si usa: non si assume. Il `timestamp` del
  device (1 ns, solo AMD SMI) e' un controllo di avanzamento, non una durata:
  timestamp fermo = lettura non valida, timestamp che avanza con contatore
  immobile = zero legittimo. Un delta negativo e' un reset o un avvolgimento e
  si copre con l'integrale, **mai clampato a zero**. La potenza dichiara
  `power=<campo> [W]` (su AMD `socket_power` prima, poi
  `current_socket_power`, poi `average_socket_power`) e il contesto
  `platform=gpu_bm_linux` quando vale. Il monitor GPU si seleziona **per
  vendor**: NVML per NVIDIA, AMD SMI per AMD; non esiste una catena
  NVML -> AMD SMI per la stessa scheda, e i due non girano mai in parallelo.
  **La scheda dentro un backend si seleziona per indice, e l'indice 0 non e'
  una scelta implicita** (dal 03-11-2026): `_gpu_indice_richiesto`
  (`energy/energy_session.py:1471`) legge argomento esplicito, poi
  `CW_GPU_INDEX`, poi "non dichiarato"; `_selezione_device` (`:1496`) apre
  l'indice richiesto e, se e' fuori intervallo, **non apre la scheda 0** —
  misurare una scheda e scrivere la riga come se fosse quella richiesta e' un
  numero attribuito male, non un degrado. Con un solo device l'indice 0 non e'
  un'assunzione e non produce nota; con piu' device e nessuna selezione la riga
  lo dice per via sua (`device_note`, appendice in `notes`,
  `energy/local_energy.py:851-853`, lo schema P5 resta 174 nomi). Un
  `CW_GPU_INDEX` non numerico e' un errore dichiarato, non un "non dichiarato".
  L'indice e' una **posizione nell'elenco del backend che ha risposto**
  (`nvmlDeviceGetHandleByIndex`, `amdsmi_get_processor_handles`), non un ID del
  produttore: lo stesso numero su vendor diversi non e' lo stesso silicon. Il
  runner non ha un flag per l'indice — la via di produzione oggi e'
  `CW_GPU_INDEX`, perche' la sessione chiama `_open_gpu_monitor()` senza
  argomento (`energy_session.py:765`).
  **Il ramo per processo non ha una durata da usare, e deve dirlo.**
  `gpu_process_energy_j` vale N/A nella quasi totalita' dei casi, perche' il
  binding NVML installato espone i campioni di `nvmlDeviceGetProcessUtilization`
  come `(pid, timeStamp, smUtil, memUtil, encUtil)` -- **nessun intervallo per
  processo** (`pynvml.py:1755-1761`, letto il 04-11-2026). Senza durata non
  esiste frazione del tempo di finestra da scalare all'energia board: **non si
  inventa un intervallo** e non si sposta il ramo su un'altra unita' di misura.
  Ogni `None` di `process_energy_j` (`energy_session.py:1648`) scrive la **propria**
  ragione in `process_energy_reason` (inizializzata a `:1569, :1683`) e
  `local_energy.py:989` porta quella stringa nella riga: una formula fissa per
  tutti i rami era falsa, perche' il ramo piu' frequente non e' un problema di
  NVML bensi' `_last_window_board_active_j`, letto via `getattr` e mai assegnato
  da nessun percorso. Il campo resta **informativo**: non entra in
  `gpu_energy_attributed_j` e non sostituisce l'attribuzione whole-device. Limite
  dichiarato del ramo che funziona: i campioni vengono dagli **ultimi 10 s** di
  storia NVML, non da `[t_start, t_end]`, quindi la frazione non e' sulla finestra
  della riga quando la finestra non dura 10 s.
  Le due catene sono **[I]** (implementate, provate con `pynvml` e `amdsmi` finti,
  28-10-2026) con **[V] da fare**: su questa macchina non c'e' ne' una NVIDIA
  ne' una AMD, quindi l'esecuzione su GPU reale e' ancora da registrare. Qui
  `[P]` non significa "implementato ma non provato su hardware": significa
  "progettato e non implementato". `pawnio-counter` invece e' **[I] con [V] su
  questo host** (Intel, 28-10-2026: rapporto 1,000578 e 1,000576 contro EMI a
  finestra uguale); restano **[V] da fare** il ramo AMD e riporto/reset reali.
- **Solo i token di canale reali.**
  `MEASURED_METHODS = ("emi-counter", "pawnio-counter", "power-integration",
  "librehardwaremonitor-energy", "energy-file", "rapl")`
  (`energy/energy_session.py:73-74`). La lista dice **quali righe portano un
  numero**, non cosa sa fare il codice oggi: `power-integration` e
  `librehardwaremonitor-energy` restano per i CSV archiviati in
  `experiment_results/` (v1-v3, four-way, A-B-A) misurati con quei canali, e
  nessun percorso di produzione li produce piu'. **CasualWatt non ha un percorso
  di stima TDP**: quello e' il percorso di CodeCarbon, usato nella tesi come
  contrasto. Non inventare un canale `estimated`.
- **PawnIO non si somma a EMI e non si carica da un blob qualunque.** La catena
  e' una cascata: se EMI risponde, PawnIO non viene aperto. Il modulo deve essere
  la release 0.2.11 con SHA-256 pinnato; un hash diverso non si carica. Con HVCI
  attivo **o non determinabile** il firmatario del driver deve essere Microsoft
  (`fail closed`); con HVCI disattivo un terzo valido e' ammesso ma la riga lo
  dichiara. Nessuna scrittura di MSR: l'IOCTL di scrittura esiste e non si usa.
- **Nessun doppio conteggio.** PP0 e PP1 sono sottoinsiemi di PKG: non sommare
  `PKG+PP0+PP1` e non sommare `PKG+DRAM` (`energy/emi_backend.py:32-34`, `:580`;
  `DOMAIN_NAMES = ("pkg", "dram", "pp0", "pp1")` a `:116`). PP1 alimenta
  `igpu_energy_j`, informativo.
- **Baseline = mediana, non media.**
  `baseline_pre_w = mediana(P_rep,1..3)` su tre finestre da 30 s (P1.3). Con
  `n = 3` una finestra contaminata sposta la media ma non la mediana (P1.14).
  Si applica `P_pre`; `P_post` e' diagnostica (`dP`), mai applicata. La ragione e'
  causale: la richiesta e' l'intervento, quindi il post e' una grandezza
  post-trattamento e condizionarvi l'estimatore renderebbe la correzione
  dipendente dall'esito che deve correggere (P1.14, motivazione causale).
- **Un registro fermo ai bordi non e' una finestra da 0 J.** Il record EMI porta
  il timestamp del contatore in unita' da 100 ns (`energy/emi_backend.py:31`,
  esposto come `ts_100ns` a `:588`; solo EMI lo ha -- PawnIO risponde `None`,
  `energy/energy_session.py:888` e `:903`). Se i due bordi leggono **lo stesso
  record** (`ts_edge1 <= ts_edge0`, `energy/local_energy.py:461-471`, da
  `b3b12ffe` del 04-11-2026) l'incremento nullo non e' una misura: e' una lettura
  non avanzata, e la finestra va `counter-invalid` con `active_valid = False`, non
  `exact-counter` con `package_energy_raw_j = 0.0`. Nello stesso colpo la riga non
  degrada al buffer a 0,05 s. Con il timestamp **assente** (PawnIO, o un canale
  che non lo espone) la domanda non e' decidibile e il bordo vale: `None` non e'
  un "fermo". Su questo host la guardia non invalida righe reali, perche' il
  registro non e' mai rimasto fermo nelle letture campionante: 0 timestamp
  identici su 11.192 transizioni consecutive
  (`experiment_results/emi_cadenza_distribuzione_20261023.md:74`, `:79-81`,
  misurato il 23-10-2026); rimuove un numero che non deve esistere, non un numero
  che esiste.
- **Nessun troncamento.** Gli incrementi negativi si conservano: sul ramo CPU il
  flag di riga e' `active_valid` con i valori grezzi `package_energy_raw_j` e
  `active_energy_raw_j` (`energy/local_energy.py:603-604`, `:622-633`; colonne
  nel schema a `casualwatt_csv_export.py:118`), e a livello di blocco resta il
  flag `negative_increment` (`benchmark_v4.py:1694`, colonna di riepilogo). **Il
  debito di metodo dichiarato il 24-10 e' chiuso al 02-11-2026 da `cd881e6b`**:
  i tre clamp a zero che la produzione applicava (`:512`, `:530`, `:548`
  nell'antesistema) non esistono piu' — l'integrale di fallback somma `cur -
  prev` senza `max` (`local_energy.py:578-581`), `package_energy_j` e' il valore
  firmato (`:603`) e `active = active_raw` (`:621`), con la nota che nomina il
  negativo quando c'e' (`:634-639`). **Anche il quarto clamp, quello del percorso
  a campioni, cade il 04-11-2026 con `86bba6a8`**:
  `package_energy_exact_between` (`energy/energy_session.py:1188`) restituiva
  `max(base, 0.0)` -- e lo applicava anche dopo la sottrazione delle
  sottofinestre escluse, quindi un reset fra i campioni diventava una finestra da
  `+X` J invece che da `-X` J -- e ora restituisce il delta firmato in entrambi i
  rami. **Le coordinate di questo elenco sono del 04-11 (sera), dopo i ~40 righe
  di guardie aggiunte da `b3b12ffe` e `86bba6a8`**: i valori citati a `:539`,
  `:561`, `:579`, `:592-597`, `:620`, `:637`, `:672`, `:683-684` dell'ancoraggio
  del 02-11 sono gli stessi codici piu' su di quelle righe, e chi corregge di
  nuovo le guardie deve re-indirizzarli. Resta clampato cio' che **non e' energia**:
  i delta di tempo CPU (`:662`, `:665`, `:679`) perche' un contatore di secondi che
  torna indietro e' un reset, e la quota dove viene usata (`:726`) perche' il
  rapporto grezzo `share_raw` e' conservato a `:746-747` con le anomalie dichiarate
  (`:712-718`, `:725`). La regola non nasce con la v4: era gia' DP-A nella
  specifica `METODI_E_FORMULE.md` del 21-10
  (`Ê_att = E_pkg^raw − E_base`, "firmata, mai clampata"), documento che sta in
  `Tesi-latex/` e quindi **fuori da git**: la
  citazione e' di provenienza, non e' un riferimento consultabile nel repo. Su
  questo punto il codice non e' piu' in ritardo di una generazione rispetto alla
  specifica; la frase che lo affermava era stantia ed e' stata sostituita da
  questa dichiarazione. Uno zero legittimo e' dichiarato, non inventato: baseline non
  calibrata -> `baseline_energy_j = 0` con `idle_provenance = "uncalibrated"`
  (`energy/local_energy.py:380-390`).
- **Linguaggio dell'incertezza.** "Semi-range conservativi", mai "deviazione
  standard": con `n = 3` non si stima una varianza. Nessun `sqrt(...)` del
  protocollo e' una propagazione di varianza: sono combinazioni in quadratura di
  budget conservativi. Ogni numero pubblicato esce con il suo `budget_pred` e con
  la sua fascia di copertura; la copertura e' un campo (`coverage_tier`,
  `hull_margin_tok`), non un aggettivo nel testo.
- **La quadratura non e' un limite conservativo garantito.** Per due termini non
  negativi, `sqrt(a^2+b^2)/(a+b)` sta fra `1/sqrt(2)` e `1`: la somma aritmetica
  e' fra 1,00 e 1,41 volte la quadratura, qualunque siano i valori. La forma scelta e'
  provvisoria (P1.7): si scrive "budget", non "limite superiore garantito", e non
  si presenta la quadratura come se fosse la scelta scientificamente obbligata. La
  scelta dipende da cosa rappresenta il budget — incertezze standard combinabili
  sotto un'ipotesi probabilistica, oppure limiti assoluti senza compensazione — e
  non da quanto e' grande il numero.
- **Nessuna colonna di deviazione standard a `n = 3`** (P4.12). Non e' una stima
  utilizzabile di varianza ed e' ridondante: la terna `(min, med, max)` **e'** la
  terna delle osservazioni riordinata, quindi `sd` ne e' una funzione
  deterministica. Si registrano i tre valori, la mediana, il minimo, il massimo e
  il range. Un indicatore ridondante suggerisce che esista una sigma stimata.
- **`acc_comp` non e' un'accuratezza.** E' un indice descrittivo a pesi su tre
  componenti di natura eterogenea (`acc_links`, `judge/5`, coseno nel regime A) e
  la sua scala non e' omogenea: il numeratore di `ece_per_joule` mischia un
  punteggio 0-1 con una media su scala 0-5. L'accuratezza primaria resta
  `is_correct` (1/0/N/A) e in ogni ramo si determina **prima** di `acc_comp`
  (`evaluator.py:400` e `:406`, `:507` e `:508`, `:535` e `:537`, `:580-597` e
  `:610`, `:665` e `:667`). Il nome storico "accuracy composita" era ambiguo e la
  rinomina **non** ha toccato lo schema P5: il ruolo della riga sta in `notes`
  (`RUOLO_COMPOSITO` / `RUOLO_BINARIA`, `evaluator.py:238-245`, appese a `:414`,
  `:524`, `:548`, `:617`, `:673`) e nelle etichette dei grafici
  (`genera_grafici_tesi.py`), non in una colonna nuova. Sui rami `number` e
  `short_text` `acc_comp` **coincide** con `float(is_correct)`: non e' un'eccezione
  da annotare, e' la definizione del ramo.
- **L'unita' statistica di un benchmark ripetuto e' il task, non la riga.**
  Ripetere la stessa richiesta a temperatura zero non aggiunge un grado di
  liberta'; la variabilita' da coprire e' fra task diversi. Accanto all'intervallo
  di Wilson a livello di riga si pubblica un **bootstrap a livello di task**
  (percentile 2,5-97,5, 2000 ricampioni, seed `20261104`:
  `evaluation_runner.py:14-20`, chiave `accuracy_cluster_bootstrap_95` a `:169`, e
  `robust_evaluator.py:490-510`, dove `task_ids` arriva come argomento perche'
  `EvaluationResult` non porta l'identita' del task). Nei tre casi in cui non e'
  calcolabile l'intervallo resta **`None` con la ragione dichiarata**: identita'
  del task non registrata, un solo task distinto (varianza zero per costruzione non
  e' evidenza), righe senza id escluse dal ricampiono ma conteggiate nella nota. Se
  il bootstrap a cluster risulta piu' largo di Wilson, le righe non erano prove
  indipendenti. Il confronto fra due sistemi sullo stesso task **non** si fa per
  sovrapposizione di intervalli: resta una McNemar appaiata.
- **Un accordo fra due letture dello stesso registro NON e' una validazione
  indipendente.** EMI, LibreHardwareMonitor (oggi fuori dall'implementazione) e
  SRUM leggono tutti
  `MSR_PKG_ENERGY_STATUS` (0x611): concordano per costruzione anche se la scala
  fosse sbagliata. La scala assoluta resta **non arbitrata** senza un wattmetro
  AC/DC esterno. Questo caveat va scritto prima dei numeri, non in nota.
- **"Validata" e' una parola sola.** Si scrive solo se tutti e sei gli anelli di
  P4.9 passano (`chain_status = validated`). Altrimenti si scrive quale anello ha
  ceduto. Dal 28-10-2026 il token ha un produttore (`validation_chain.py`), che
  applica le soglie congelate e restituisce l'etichetta del **primo** anello che
  cede; non promuove nulla e nessuna riga e' `validated` finche' una campagna non
  passa tutti e sei.
- **Le soglie sono congelate prima dei dati.** 1,0 W, 10%, 20%, `err_rel <= 10%`,
  2 token, fattore 2: nessuna si sposta dopo aver visto il risultato.

---

## Comandi di verifica

```
pytest cwEnergyModular          # 977 raccolti: 974 passati, 4 saltati, 0 falliti
                                # (07-11 notte; eseguito 978 per lo skip di
                                # modulo, che non compare in --collect-only)
                                # storia datata: 976 raccolti / 973 passati (07-11
                                # notte, prima del test di contratto); 943 raccolti / 940 passati
                                # (07-11 sera); 906 raccolti / 903 passati
                                # (07-11, dopo P6.5); 845 raccolti (notte 05-11);
                                # 888 raccolti, 871 passati, 14 falliti (identita'
                                # GPU), 3 saltati (albero sporco, 06-11 alle 12:04)
```

**Mai `pytest` nudo dalla radice**: la raccolta viene interrotta da 6 errori in
`cpuepower/` e `cpuepower2/` (`ModuleNotFoundError: No module named
'cpuepower.attribution'`).

Ogni modifica al codice va accompagnata dall'output di pytest incollato per
intero, non riassunto.

La tesi si compila con MiKTeX in `Tesi-latex/qoder-bozza/`:

```
pdflatex main && biber main && pdflatex main && pdflatex main
```

**`biber`, non `bibtex`**: il documento usa biblatex e `bibtex main` fallisce con
"I found no \citation commands", azzera `main.bbl` e produce un PDF senza
bibliografia. Requisiti di compilazione: 0 overfull hbox, 0 riferimenti
indefiniti.

I numeri dello schema che il corpo della tesi cita non si scrivono piu' a mano:
si rigenerano dalla cartella `cwEnergyModular/` **insieme** all'Appendice A, con

```
python tools/dump_schema_latex.py > ..\Tesi-latex\qoder-bozza\generated\schema_appA.tex
python tools/dump_schema_latex.py --macros > ..\Tesi-latex\qoder-bozza\generated\numeri_schema.tex
```

`main.tex` legge il secondo file in preamble con `\input{generated/numeri_schema}`
e capitoli e appendice usano i `newcommand` come matematica inline. Se un numero
del corpo diverge dall'appendice la causa non e' una frase da correggere: e' che la
seconda rigenerazione non e' stata fatta, perche' tabella e macro escono dalla
stessa lettura dello schema.

Il motore va controllato **prima** di una campagna, non dopo: dalla cartella
`cwEnergyModular/`

```
python tools/smoke_keep_alive.py --model qwen2.5:0.5b
```

spedisce al motore reale il payload che `payload_v4` costruisce oggi, in forma
numerica, e chiede a `infer_v4`, `infer_v4_stream` e `/api/version` se la forma e'
ancora quella accettata -- la firma `400 time: missing unit in duration "-1"`
di Ollama 0.33.1 e' esattamente il tipo di cosa che un aggiornamento riporta
indietro. Esce `2` se il motore non risponde e `1` se una verifica fallisce: con
quei codici la campagna non si lancia. Non misura energia e non scrive righe,
quindi non produce dati da citare. `--keep-alive 0` scarica i pesi dalla memoria
del motore al termine della chiamata: usare `-1`, il default, quando dopo il
controllo segue un run.

---

## Struttura dei file

- `cwEnergyModular/` — codice di produzione. `energy/emi_backend.py` (contatore
  EMI via ctypes/SetupAPI, con selezione del device CPU e del canale PKG dal
  metadato), `energy/pawnio_backend.py` (contatore MSR del package via driver
  PawnIO: sonda del driver e del modulo, unita' derivata, fallback dichiarato di
  EMI), `energy/energy_session.py` (canali, integrazione di
  finestra, interpolazione ai bordi), `energy/local_energy.py` (campi per riga),
  `casualwatt_csv_export.py` (`CSV_COLUMNS`, righe 17-204 — 174 nomi;
  `BLOCK_SUMMARY_COLUMNS`, 212-227; `POINT_SUMMARY_COLUMNS`, 229-237;
  `RUN_METADATA_COLUMNS`, 343-361 — **30** nomi (la colonna
  `ollama_version` promessa il 06-11 non e' mai entrata nel codice; il generatore
  `tools/dump_schema_latex.py --macros` conta 30, e il CSV di riferimento ne ha
  29 nell'header); nessuna migrazione perche'
  l'header dei metadati e' scritto una volta sola), e il
  runner v4 `benchmark_v4.py` (sequenza di blocco di P1.5). Il risolutore della
  superficie predittiva sta a parte, sul lato analisi (P6.5, 2026-11-07):
  `surface_fit.py` aggrega i blocchi con F.7, standardizza i predittori e risolve
  F.9 con QR/SVD, restituendo β in unità P3.3; non è chiamato dal runner di
  misura e non tocca lo schema CSV. Dalla stessa giornata due moduli di sola
  analisi stanno accanto: `geometry.py` (la metrica di copertura di F.13,
  `hull_margin_tok` perpendicolare su coordinate grezze e la fascia più
  conservativa dei due inviluppi) e `s_epi_phase.py` (l'harness di P6.6,
  promosso dalla radice con `git mv`), che legge finestra di fase e
  `settle_pre_s`/`settle_post_s` dalle colonne del runner v4 invece che dai
  bucket SRUM. Un terzo modulo di sola analisi entra la notte del 07-11-2026:
  `control_gate.py` (il criterio F.12 del gate load-versus-control, P4.5), che
  legge i riepiloghi di blocco che il runner scrive e restituisce l'esito del
  gate; non esegue misura. Nessuno dei tre è chiamato dal percorso di misura.
- **Il valutatore della risposta sta nello stesso modulo**: `evaluation_runner.py`
  (aggregati con intervallo di Wilson a livello di riga, bootstrap a cluster a
  livello di task, rifiuto dei valori non finiti),
  `mudilab_adapter.py` (ponte MUDILAB: un tool call non verificabile rende la
  riga `indeterminate`), `robust_evaluator.py` (secondo criterio: numero univoco
  o marcatore finale, probabilita' condizionate a tutti gli stadi, controfattuale
  su entrambi i limiti) e `mudilab_eval.py`; i tre `test_*.py` alla radice li
  coprono con **51** test (36 fino alla mattina del 04-11, +15 dai quattro fix
  della notte). Il criterio robusto e' **secondario**:
  `MUDILAB_run/benchmark/valuta.py` e `_confronta` di
  `MUDILAB_run/benchmark/genera.py` restano il riferimento ufficiale delle misure
  pubblicate il 02-11-2026, e il criterio non tocca ne' il valore misurato ne' la
  scala del contatore. Le tre note di metodo stanno in `cwEnergyModular/docs/`
  (`EVALUATION_FRAMEWORK.md`, `ROBUST_EVALUATOR.md`,
  `RELAZIONE_VALUTATORE_ROBUSTO.md`).
- **I test stanno in due posti**: `cwEnergyModular/tests/` (493 raccolti la notte
  del 04-11; 482 al 03-11, +4 di `b3b12ffe` e +1 di `86bba6a8` e +5 di `4b922db6`
  e +1 del declassamento di `acc_comp`)
  e direttamente in `cwEnergyModular/` (`test_answer_type_evaluation.py`, 40;
  `test_synthetic_window.py`, 2; `test_validazione_valutazione.py`, 22;
  `test_robust_evaluator.py`, 19; `test_mudilab_adapter.py`, 26;
  `test_evaluation_runner.py`, 6); 493 + 115 = 608. Gli ultimi tre sono il criterio
  robusto del valutatore, entrato il 04-11 con `cf6aca71` e `6b1dccb8`: e' il
  secondo criterio di quella valutazione, non un dominio nuovo della misura, e non
  tocca ne' il valore misurato ne' la scala del contatore. Diciotto delle loro
  trentasei docstring sono state scritte il 04-11 mattina leggendo i corpi (11 in
  `test_robust_evaluator.py`, 5 in `test_mudilab_adapter.py`, 2 in
  `test_evaluation_runner.py`), le altre diciotto accompagnavano il test; le
  quindici entrate la notte (8 in `test_mudilab_adapter.py` dai due fix sul ramo
  MUDILAB, 3 in `test_robust_evaluator.py` e 4 in `test_evaluation_runner.py` dal
  bootstrap) accompagnano il test loro. La provenienza e' dichiarata, non
  mascherata. Ogni test ha una docstring che
  dice *perche'* esiste e quale relazione matematica o fisica verifica, non solo
  cosa fa. Al 28-10-2026 la norma non era rispettata da nove funzioni (13 node
  id, tutte scritte il 27-28/10): otto in `tests/test_pawnio_backend.py`, una in
  `tests/test_diagnostics_pmi.py`. **Debito chiuso il 03-11-2026 con `9d4ce024`**:
  le nove docstring sono scritte alla fonte, nessuna parafrasi del generatore, e
  l'AST ora conta zero funzioni `test_` senza docstring su tutto il tree. Il
  generatore continua a stampare "nessuna docstring" invece di mascherare, e su
  questa suite oggi non stampa quella riga per nessuna delle 608 righe.
  **La fotografia al 07-11-2026 (sera) non e' piu' quella**: l'Appendice D
  rigenerata su 943 node id stampava `Copertura delle docstring: 935 righe
  documentate su 943`, e le otto scoperte stavano tutte in
  `tests/test_paired_mcnemar.py`, entrato con `c33a7846c`: `test_basic_table_counts`,
  `test_indecis_when_no_discordant`, `test_small_discordant_uses_exact`,
  `test_large_discordant_computes_chi2`, `test_indeterminate_excluded_and_counted`,
  `test_length_mismatch_raises`, `test_no_chance_correction` e
  `test_record_verdict_coercion` non hanno docstring (misurato con l'AST sul
  file, 8 funzioni `test_` su 8). Le 608 righe della frase sopra
  restano storia datata; il debito e' aperto da un commit precedente a questo
  allineamento, non e' stato creato qui, e si chiude in un punto suo -- non
  allungando i test di oggi ne' correggendo la riga per far tornare il conteggio.
  La rigenerazione della notte del 07-11-2026, sui 977 node id che includono i
  tre punti di P4.4 e P4.5, stampa `Copertura delle docstring: 969 righe
  documentate su 977`, e le scoperte sono le stesse otto di
  `tests/test_paired_mcnemar.py`: i punti nuovi portano la loro docstring e
  non spostano il debito.
  Dal 27-10-2026 la cartella contiene anche `tests/test_rapl_zone.py`
  (8, logica RAPL su un finto sysfs), `tests/test_diagnostics_pmi.py` (7,
  sonda PMI/WMI) e `tests/test_emi_selezione.py` (16, metadati EMI sintetici:
  metadato V2, scelta del device CPU, canale PKG per nome, V1 scartato): girano
  su Windows, senza host Linux. Dal 28-10-2026 ci sono
  `tests/test_gpu_nvml_energy.py` (8 il 28-10, 16 dal 03-11 con la selezione del
  device, 21 dal 04-11 (sera) con le cinque ragioni dell'N/A per processo; catena `nvml-energy` ->
  `nvml-power-integral` con `pynvml` finto), `tests/test_gpu_amdsmi.py` (19 il
  28-10, 24 dal 03-11;
  catena `amdsmi-energy` -> `amdsmi-power-integral`, conversione da microjoule,
  timestamp come controllo di avanzamento, delta negativo, provenienza di
  potenza e piattaforma, precedenza di NVML, con `amdsmi` finto) e
  `tests/test_metriche_per_token.py`
  (4, le tre colonne per token accodate al CSV) e
  `tests/test_external_counter.py` (6, D14: `external_counter` vero solo per
  `energy-file`, falso per `emi-counter`, `pawnio-counter`, `rapl` e per una
  riga con GPU `nvml-energy`) e `tests/test_chain_status.py` (17, il produttore
  di `chain_status` di P4.9: ordine degli anelli, confini delle soglie, quorum
  del test load-versus-control, vocabolario chiuso). Dal 28-10-2026 ci sono anche
  `tests/test_pawnio_backend.py` (25, catena `pawnio-counter`: sonda HVCI e
  firma con i due firmatari, hash del modulo, ramo Intel e ramo AMD mai su
  `0x611`, unita' derivata, riporto, reset, `access_denied`) e
  `tests/test_pawnio_selezione.py` (9, precedenza EMI -> PawnIO nella sessione,
  nessuna somma dei due canali) e `tests/test_diagnostics_pawnio.py` (4, la
  diagnostica dichiara `pawnio-counter` solo quando il contatore risponde,
  `unavailable` con la ragione altrimenti, e `CW_ENERGY_FILE` ha la precedenza).
  Nello stesso giorno `tests/test_cw_energy_file_override.py` (3) fissa il
  significato di quella precedenza: con un file valido la catena si ferma e
  EMI/PawnIO non vengono tentati, mentre file assente o valore non numerico
  lasciano proseguire la selezione di piattaforma.
  L'Appendice D della tesi e' stata rigenerata il 2026-10-28 con
  `cwEnergyModular/tools/dump_tests_latex.py`: 526 node id, 523 passati, 3
  saltati, docstring 513/526 (le nove funzioni senza docstring elencate sopra).
  **Rigenerata di nuovo il 2026-11-03, dopo `cd881e6b` e `9fa9a44c`: 528 node id,
  525 passati, 3 saltati, docstring 515/528.** Il diff e' di due sole righe nuove
  (`test_cpu_attribution.py::test_c_reset_contatore_ai_bordi_non_degrada_al_fallback`
  e `test_metriche_per_token.py::test_token_stimati_non_entrano_nelle_metriche_scientifiche`)
  piu' una docstring riscritta: nessun fallimento, nessuna riga sparita.
  **Rigenerata una terza volta il 03-11-2026 (sera)**: 541 node id, 538 passati,
  3 saltati, docstring 541/541 -- le nove funzioni elencate sopra le hanno tutte
  (`9d4ce024`). Il diff dalle 528 del mattino e' di 13 righe, tutte e 13 dentro i
  due file GPU della selezione del device: nessun fallimento, nessuna riga sparita.
  **Rigenerata una quarta volta il 04-11-2026, sull'albero che porta il criterio
  robusto del valutatore**: 577 node id, 574 passati, 3 saltati, docstring 577/577;
  le intestazioni di modulo in corsivo sono 45 su 48, perche' i tre file nuovi non
  ne hanno una. Il diff dalle 541 e' di 36 righe, tutte dentro
  `test_robust_evaluator.py` (16), `test_mudilab_adapter.py` (18) e
  `test_evaluation_runner.py` (2): nessun fallimento, nessuna riga sparita.
  Diciotto delle loro trentasei docstring sono state scritte il 04-11 leggendo i
  corpi, le altre diciotto accompagnavano il test. I conteggi della prosa sono
  rifatti col parser dello stesso generatore (`raccogli` e `nome_e_parametri`),
  non per aritmetica: 483 funzioni per `(percorso, classe, nome)`, 482 ignorando
  la classe, 459 monoriga + 118 righe da 24 famiglie parametrizzate in 12 file,
  48 file; delta $294 \to 577 = +288 - 8 + 3$. Il testo dei capitoli e
  dell'Appendice D che dichiarava 541 node id, 447 funzioni, 423 monoriga e 45
  file e' riscritto con questi numeri.
  **Rigenerata una quinta volta la sera del 04-11-2026, sull'albero dei tre
  interventi dell'audit** (`b3b12ffe`, `86bba6a8`, `4b922db6`): **587** node id,
  584 passati, 3 saltati, docstring 587/587, nessuna riga `\textbf{fallito}`,
  `\textbf{errore}` o `n/eseguito` -- ogni node id raccolto ha un esito eseguito.
  I tre salti, qui attribuiti a `test_rapl_zone.py`, stanno in realta' in
  `tests/test_rapl.py:43` (lo dichiara il generatore stesso nella sezione
  "Motivi dei salti"): l'attribuzione di questa riga era stantia, il conteggio
  no. Il diff
  dalle 577 e' di 10 righe: 4 in `test_cpu_attribution.py` (bordi sullo stesso
  record, timestamp che regrada, assenza di timestamp non decidibile, delta
  negativo del percorso a campioni), 1 in `test_emi_backend.py` (il segno del
  reset attraversa `package_energy_exact_between`) e 5 in
  `test_gpu_nvml_energy.py` (le ragioni dell'N/A per processo). Nessun fallimento,
  nessuna riga sparita. I conteggi della prosa, di nuovo col parser del generatore
  e non per aritmetica: **493** funzioni per `(percorso, classe, nome)`, 492
  ignorando la classe, **469** monoriga + 118 righe da 24 famiglie parametrizzate
  in 12 file, 48 file; delta $577 \to 587 = +10$.
  Una nota sul metodo, perche' il 27-28 ottobre ha gia' visto un conteggio a
  memoria: le dieci righe nuove sono tutte monoriga e le famiglie restano 24,
  quindi il parser del generatore -- che tratta l'istanza parametrizzata con
  ``id`` stringa vuota come ``param`` falso -- stampa 471 ``monoriga`` e 116 righe
  parametrizzate. Le due righe ``[]`` (``test_riferimento_non_valido...`` e
  ``test_stato_non_di_misura_produce_none``) appartengono a famiglie da 7 e da 3
  istanze: contate per appartenenza si ottengono i 469 + 118 di questo file, che
  e' la stessa regola usata per i 459 + 118 del 04-11 mattina e per i 423 + 118
  del 03-11. La somma dei due tagli e' 577 e 587 in entrambi i casi; cambia solo
  dove si mettono due righe, e va detto quale regola si sta usando.
  **Rigenerata una sesta volta la notte del 04-11-2026, sull'albero dei quattro
  fix del valutatore** (`98ec5972`, `8a91e16c`, `40f6c619`, `5f23853d`): **608**
  node id, 605 passati, 3 saltati, docstring 608/608, intestazioni di modulo in
  corsivo 45 su 48 (i tre file senza restano `test_robust_evaluator.py`,
  `test_mudilab_adapter.py`, `test_evaluation_runner.py`), nessuna riga
  `\textbf{fallito}`, `\textbf{errore}` o `n/eseguito` -- contato sul file
  generato, non dichiarato. Il diff dalle 587 e' di **+21** righe: 8 in
  `test_mudilab_adapter.py` (4 sulla tolleranza derivata dai decimali stampati, 4
  sulla registrazione degli argomenti), 5 in `test_answer_type_evaluation.py` (il
  ruolo di `acc_comp` nei due regimi a pesi e nei due rami binari), 1 in
  `tests/test_cloud_energy_none_preservato.py` (il numeratore di
  `ece_per_joule` nominato nella nota), 4 in `test_evaluation_runner.py` e 3 in
  `test_robust_evaluator.py` (bootstrap a cluster). Il confronto e' fatto per
  **conteggio per file** contro i numeri registrati in questo file (35, 18, 16, 2,
  492), non per diff testuale: `Tesi-latex/` sta fuori da git e la versione
  precedente del generato e' stata sovrascritta, quindi la scomparsa di una riga
  sarebbe visibile solo come ammanco nell'aritmetica -- che qui chiude a
  $8+5+1+4+3=21$. I tre salti sono gli stessi tre di `tests/test_rapl.py`.
  I conteggi della prosa, di nuovo col parser del generatore e non per
  aritmetica: **514** funzioni per `(percorso, classe, nome)`, **513** ignorando
  la classe, **492** monoriga + **116** righe parametrizzate come le stampa il
  parser, che sono **490 + 118** con la regola delle appartenenze usata in questo
  file (le due righe ``[]`` tornano nelle famiglie da 7 e da 3); famiglie 24 in
  12 file, 48 file; delta $587 \to 608 = +21$.
  **Il 03-11 anche il testo della tesi e' stato allineato a quel conteggio**: i
  paragrafi che dichiaravano $294$ node id, $291$ verdi, $237$ funzioni,
  ``ventisei file``, la decomposizione per file e l'ancoraggio di
  `test_energy_corrections.py` a 19 test (oggi 14, con gli otto rami LHM tolti da
  D18) sono riscritti con i numeri verificati il 03-11 col parser dello stesso
  generatore, non a memoria -- $541$ node id, $447$ funzioni per
  `(percorso, classe, nome)`, $423$ monoriga + $118$ da $24$ famiglie parametrizzate
  in $12$ file, $45$ file tutti tracciati, delta $294 \to 541 = +252 - 8 + 3$.
  Le riesecuzioni del 03-11 sulla raccolta da 541: dalla radice $538$ passati e
  $3$ saltati senza avvisi in $7{,}06$ s, $7{,}53$ s e $7{,}39$ s; il generatore
  dalla cartella del modulo gli stessi $538$ e $3$ in $6{,}94$ s. Due invocazioni
  della stessa giornata avevano la stessa raccolta e lo stesso esito in $10{,}9$ s:
  la durata non e' un ancoraggio citabile, il conteggio si'.
  Il documento compila: **195 pagine, 0 riferimenti indefiniti, 0 `Overfull \hbox`**
  (notte del 04-11-2026: `pdflatex`, `biber`, `pdflatex` x2, poi due `pdflatex`
  ancora dopo la correzione di un accento nel glossario; il `.bbl` porta **65**
  voci prima e dopo, nessuna citazione aggiunta o rimossa). I sei pagine sopra il
  PDF da 189 sono localizzate confrontando i due `main.toc`: $+2$ dentro
  `sec:valutatore` (la prosa dei quattro fix, che prima era una sezione di solo
  titolo), $+1$ nella prosa dei conteggi di `sec:validazione-software`, $+1$ nel
  paragrafo di `sec:statistica` sull'unita' statistica, $+1$ fra l'Appendice C e
  la prosa dell'Appendice D, $+1$ nella tabella generata (le $31$ righe nuove fra
  la quinta e la sesta rigenerazione). Le conteggi precedenti restano storia
  datata: 186 prima della riconciliazione dell'Appendice D con l'albero di
  integrazione, 183 prima della prosa sulla selezione del device GPU, 184 prima
  del riallineamento dello schema CSV, 189 prima di questa.
  **Il passo che queste righe dichiaravano non fatto e' fatto**: la tesi e'
  riallineata all'albero da 608 node id nei capitoli 3-6, nell'Appendice C,
  nell'Appendice D e nel glossario. Il testo che dichiarava $577$ node id e'
  riscritto con i conteggi verificati col parser del generatore, non per
  aritmetica; la declassazione di `acc_comp`, la tolleranza derivata, la
  registrazione degli argomenti e l'incertezza a livello di task hanno ora prosa
  ancorata (cap.\,4 `sec:valutatore`, cap.\,3 `sec:metriche-derivate`, cap.\,5
  `sec:statistica`, cap.\,6 sviluppo 6), e il glossario non spiega piu' `ECE`
  come ``Executive Capacity Evaluation'': lo sviluppo non compare nel codice, che
  usa la sigla e basta (`benchmark_unified.py:15`, `:562`, `:666`). I tre PNG
  citati dalla tesi sono rigenerati la stessa notte
  (`genera_grafici_tesi.py --input results/semantic_evaluation_results.csv`, 2
  righe su 9 sopravvivono al filtro) con le etichette entrate con `40f6c619`, e
  copiati in `Tesi-latex/qoder-bozza/figure/`; restano non tracciati perche'
  `cwEnergyModular/results/` non tiene i PNG.
  Lo stesso 04-11 l'Appendice A e' rigenerata con
  `cwEnergyModular/tools/dump_schema_latex.py` e porta i numeri dello schema vivo:
  $174$ colonne di riga + $30$ di metadato, $77$ di riga + $1$ di metadato ancora
  `nuova` rispetto al CSV di riferimento, $28$ campi `vuota`, header del dataset
  $99$ nomi e header dei metadati $29$. **Quei numeri sono la fotografia del
  04-11 e sono stati riguadagnati il 06-11-2026**: lo stesso generatore, sugli
  stessi file di riferimento (`results/semantic_evaluation_results.csv`
  del 20-10 e `results/casualwatt_run_metadata.csv` del 19-10, che non hanno
  migrazione), porta ora $174$ colonne di riga + $30$ di metadato, $77$ di riga +
  $1$ di metadato ancora `nuova`, $28$ campi `vuota`, header del dataset $99$ e
  header dei metadati $29$ — invariati questi ultimi due perche' il delta e'
  solo una colonna accodata. Il diff fra le due rigenerazioni e' di due righe,
  entrambe commenti dei conteggi: la colonna `ollama_version` promessa in quel
  giorno non e' mai entrata nel codice (`casualwatt_csv_export.py:343-357` ha
  30 nomi, e il generatore conta 30), quindi la riga `31 & ollama_version & - &
  nuova` non esiste piu'. La forma di `keep_alive` che il motore accetta
  dipende dalla sua versione: Ollama 0.33.1 risponde `400 time: missing unit in
  duration "-1"` alla forma stringa e accetta il numero (misurato il 05-11-2026,
  e confermato il 06-11 dal percorso di produzione `payload_v4` -> `infer_v4` /
  `infer_v4_stream`, con `/api/ps` che dice `UNTIL Forever` e `CONTEXT 8192`),
  quindi un verbale senza versione non dice su quale forma il run era valido.
  `CSV_COLUMNS` non si muove: lo schema P5 congelato resta a 174 nomi, e la
  colonna nuova e' di metadato, non di riga.
  Il testo dei capitoli che parlava di $113$
  colonne \`e allineato a $174$ (cap.\,5, sezione costo in euro), e con lui gli
  ancoraggi di `benchmark_unified.py` spostati dalla crescita del runner: durate di
  fase `:189-190, 238-239`, conversione e scorporo del giudice `:430-456, 941-970`,
  enumerazione per richiesta `:914-915` (con `energy_session.py:814-824`), metriche
  derivate `:605-684` e gate `f1_triples` `:674-682`, template cloud `:515, 549`
  (nota `:541-548`, etichetta scritta dal branch `:1267-1269, 1279`), salto del
  ramo cloud `:1113-1115`. La correzione del template cloud ha ora anche
  l'ancoraggio storico del commit `1f55ca90` (23-10-2026) accanto a quello di
  riga.
  I cinque boxes che stavano nel log del 03-11 (4 in
  `capitoli/cap04_architettura_implementazione.tex` righe 125-141, i token
  `librehardwaremonitor-energy`, `nvml-power-integral`, `amdsmi-power-integral`,
  `igpu-included-in-package` dentro le celle di `tab:backend-fallback`; 1 in
  `capitoli/cap06_conclusioni_sviluppi.tex` riga 122) sono corretti con lo stesso
  meccanismo del generatore -- `-\allowbreak{}` nei token -- piu' l'allargamento
  della terza colonna e il ribilanciamento delle altre a
  `p{0.15} p{0.19} p{0.23} p{0.16} p{0.20}`: il solo punto di capo non bastava,
  perche' `librehardwaremonitor-` e' un frammento di 21 caratteri e nessuna
  sillabazione lo spezza. Quei cinque non erano dell'appendice: erano dei capitoli
  scritti a mano fra il 28-10 e il 02-11. **La lacuna di sostanza che era aperta e'
  chiusa il 04-11**: la regola di selezione del device GPU ora sta in prosa nei
  capitoli, non solo nel codice, nei 13 test e nell'appendice generata -- due
  paragrafi in `cap03_metodologia_misura.tex` (sezione 3.8, dopo `eq:gpu`: i due
  livelli della scelta, per vendor e poi per posizione, e le due condizioni che ne
  discendono), un `\paragraph` in `cap04_architettura_implementazione.tex` (dopo
  `tab:backend-fallback`: dove arriva la richiesta, cosa finisce nella riga, perche'
  `CSV_COLUMNS` resta a 174 nomi, perche' la via di produzione e' `CW_GPU_INDEX`) e
  una frase in `cap06_conclusioni_sviluppi.tex` (riga 162: il ramo multi-device e'
  [I] con [V] da fare, provato solo contro `pynvml` e `amdsmi` finti). Le tre
  aggiunte non introducono claim nuovi: ripetono in prosa ancoraggi gia' nel codice
  (`energy_session.py:1471-1493`, `:1496-1515`, `:1559`, `:1783-1787`, `:1804`,
  `:765`, `local_energy.py:851-853`, `casualwatt_csv_export.py:35`) -- e sono
  quelle del 04-11 (sera), perche' i ~70 righe aggiunte da `4b922db6` dentro
  `_GPUMonitor` hanno spostato in basso tutto il ramo AMD: le coordinate del 04-11
  mattina (`1465-1487`, `1490-1509`, `1553`, `1716-1720`, `1737`, `809-811`)
  indicano lo stesso codice.
  I conteggi non si aggiornano a mano: si rigenera dopo ogni test aggiunto, rimosso
  o rinominato. La verifica del conteggio al 28-10 e' in
  `experiment_results/appD_conteggio_20261028.md`.
  Il file generato (`Tesi-latex/qoder-bozza/generated/test_suite_appD.tex`) sta
  fuori da git, come tutto `Tesi-latex/`.
  I 17 test di `tests/test_protocollo_p4_geometry.py` (2026-10-26, quinto turno
  di revisione esterna) congelano la geometria di copertura di P4.7 e la scala
  di `budget_pred`
  di P4.6 senza hardware né dati: sono i test da eseguire quando qualcuno propone
  di cambiare i vertici dell'inviluppo o la formula del budget.
- **Alla radice del repo stanno 36 script `.py` tracciati** (35 fino a `244d1c2f`,
  che ha portato `montecarlo_protocollo_p64_probe.py`; `s_epi_phase.py` li aveva
  portati a 37 il 06-11 e il 07-11 e' uscito con `git mv` verso
  `cwEnergyModular/s_epi_phase.py`, quindi 36 e' di nuovo il conteggio e l'ultimo
  ingresso alla radice resta `montecarlo_protocollo_p64_probe.py`): sono gli harness
  degli esperimenti (`emi_50ms_probe.py`, `emi_resolution_check.py`,
  `four_way_test.py`, `srum.py`, `srum_emi_cross.py`, `observer_cost_probe.py`,
  `idle_floor_sensitivity.py`, `four_way_pi_audit.py`, ...). Questa e' la
  convenzione reale: **un harness il cui output e' citato dalla tesi o dal
  protocollo va tracciato**, perche' un'analisi non tracciata e' un numero che
  nessuno puo' rigenerare. Le sonde usa-e-getta non citate da nulla sono in
  `.gitignore`.
- `cwEnergyModular/tools/` — 11 file tracciati: i generatori del materiale LaTeX
  (Appendici A, D, E), l'analisi di cadenza EMI, la validazione HWiNFO e le tre
  sonde PawnIO (`fetch_pawnio_modules.py` scarica e verifica i moduli della
  release con hash pinnato, `pawnio_probe.py` confronta il contatore con EMI e
  misura il costo di osservazione A-B-A, `pawnio_priv_probe.py` misura i
  privilegi invece di dedurli). Il decimo file della cartella,
  `smoke_keep_alive.py`, e' **nuovo il 06-11-2026**:
  controllo pre-campagna sulla forma di `keep_alive` contro il motore reale
  (percorso di produzione `payload_v4` -> `infer_v4` / `infer_v4_stream`, piu'
  `/api/version` perche' la forma accettata dipende dalla versione); parametrizzato
  per host e modello perche' chi lo riceve non deve spostare cartelle ne' editing di
  percorsi; esce `2` se il motore non risponde, e questo NON e' un controllo
  superato. L'undicesimo, `aggregate_p62_pilot.py`, e' **nuovo il 07-11-2026**:
  aggrega le terne di `baseline_pre_w` del pilota, ricalcola `half_range_pre_w`
  e confronta il ricalcolo con le colonne del runner; scrive
  `experiment_results/p62_pilot_aggregated.json` e non calcola `u_within,b`
  quando il blocco ha `m = 1`, perche' un semi-range su una richiesta sola e'
  zero per costruzione. Il conteggio di questa riga e' `git ls-files`, non un
  elenco a vista.
- `experiment_results/` — dati sperimentali e analisi, tracciati (220 file: 219 in
  radice, 1 in `codecarbon_four_way/`; riverificati il 04-11-2026, dopo `244d1c2f`,
  che porta l'analisi Monte Carlo di P6.4). I
  protocolli congelati stanno qui. Un artefatto nuovo entra con il proprio commit
  e con la propria analisi. Il gruppo `pawnio_probe_20261028*` (due run di
  confronto, due A-B-A, tre token di privilegio, l'analisi) e' l'evidenza sotto
  `pawnio-counter`: senza quei file il token non si cita.
- `cpuepower/`, `cpuepower2/` — toolkit sottoposto ad audit: i suoi numeri erano
  mock, la CLI crasha, la mappa MSR era sbagliata. **Banca di esperimenti, non un
  backend di misura.** Non importarlo, non citarlo come risultato.
- **Archivi fuori dal repo** — `../casualwattMetUni/` (verificata il 27/10/2026)
  e le cartelle sorelle con la stessa struttura contengono prototipi storici su
  pythonnet + `LibreHardwareMonitorLib` (`energy_tracker*.py`,
  `consumi_ollama*.py`, `test_ollama_energy.py`). Non sono il backend di
  produzione, non si importano e i loro numeri non sono confrontabili con una
  riga `emi-counter`: misurano una potenza gia' derivata dallo stesso registro
  0x611. La dichiarazione sta nel loro `README.md`, non qui. Resta in questo repo
  solo `consumi_ollama.py` alla radice, strumento legacy a stima TDP/WMI, anch'esso
  fuori dal percorso di misura.
- `Tesi-latex/` — **fuori da git**, ora anche in `.gitignore`. Compilazione
  locale, mai push. `\include` per i capitoli, `\input` per le appendici; nei
  capitoli gli accenti italiani sono ASCII-escapati (`\`e` per "e'", `\'e` per
  "é"), non Unicode.
- `.casualwatt_keys.json` — vedi Regole dure.
- CSV: `cwEnergyModular/results/*.csv` e' ignorato. I CSV di benchmark sotto
  `Tesi-latex/test-emi/` seguono la regola della tesi e restano fuori. Cio' che la
  tesi cita va in `experiment_results/` e viene committato.
- **Non esiste una directory `Temp/`** e non esiste questa convenzione: non
  inventarla.

---

## Scrittura accademica

- Usare le chiavi esistenti di `references.bib`; **mai inventare una citazione**.
  Le voci marcate `IN VERIFICA` (`dalerci2026move`) non vanno
  citate finche' non sono verificate alla fonte primaria. Ogni voce ha una `note`
  con gli ancoraggi e la data della verifica. `mlenergy2025` **non e' piu' IN
  VERIFICA**: verificata 26-10-2026 alla fonte primaria (Chung et al.,
  arXiv:2505.06371, NeurIPS 2025 D&B Spotlight). Attenzione alla confusione
  gia' commessa: `mlenergy2025` e' il *ML.ENERGY Benchmark* (J/token in steady
  state, misura con Zeus), `tschand2025mlperfpower` e' *MLPerf Power*
  (arXiv:2410.12032, J/campione, strumentazione certificata) e non fornisce
  J/token.
- Mantenere distinta in ogni tabella l'energia **misurata** da quella
  **attribuita**: l'attribuzione e' una procedura con una sua assunzione
  dichiarata (quota di tempo CPU come proxy della quota di energia), non una
  lettura del contatore.
- Terminologia unica: **baseline** per la stima della potenza idle del package.
  "Idle floor" compare una sola volta come sinonimo dichiarato; "fondo" non si usa
  come sostantivo tecnico.
- Le fonti non peer-reviewed (preprint, white paper, blog, repository) sono
  etichettate come tali nel testo, mai presentate come letteratura.
- Italiano formale nella tesi; identificatori di codice e token in inglese cosi'
  come compaiono nel sorgente.

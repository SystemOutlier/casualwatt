Avvio l'audit. È un lavoro ampio: delego quattro letture indipendenti in parallelo e nel frattempo verifico io i punti critici.

## 1. Percorso di acquisizione

- **GUID e enumerazione**: `{45bd8344-7ed6-49cf-a440-c276c933b053}` (`emi_backend.py:84-87`); SetupAPI con `DIGCF_PRESENT|DIGCF_DEVICEINTERFACE` = `0x12` (`:357`), ciclo su max 16 interfacce (`:362`), dettaglio `SetupDiGetDeviceInterfaceDetailW` con `cbSize` 8 su x64 e path a offset 4 (`:369-380`). Nessun path hardcoded salvo override `CW_EMI_DEVICE` (`:394-400`), che però **non salta la verifica del metadato** (`:396-397`).
- **Apertura**: `CreateFileW(path, 0x80000000, share=3, OPEN_EXISTING=3, 0x80)` (`:418`).
- **Protocollo**: `GET_VERSION` (0x00224000) → `GET_METADATA_SIZE` (…004) → `GET_METADATA` (…008) → lettura `0x0022400C` (`:95-98`, `:476-501`).
- **Nessun memory-mapping**: solo `DeviceIoControl` (`:504-524`); nessun `MapViewOfFile` nel file.
- **Selezione device CPU**: un device è CPU solo se un canale ha token `PKG` e unità pWh (`:241-251`); due nomi PKG distinti = `ambiguous_domain`, scartato (`:252-257`); PKG omonimi = contatore specchiato, letto una volta e dichiarato (`:258-261`). Zero o più device CPU → nessuna scelta automatica (`choose_single`, `:266-285`).
- **Canale PKG**: scelto per nome, mai "il primo" (`pkg_channel`, `:309-315`); indice nel record dal metadato (`:133-144`).
- **Device assente/apertura fallita**: note con la ragione, `available=False` (`:402-407`, `:432-442`); se il **primo** IOCTL fallisce dopo la selezione, il backend degrada e azzera canali/metadato (`:450-460`). `read_raw` tenta **una** riapertura se l'handle è invalido (`:550-561`). A valle: EMI → PawnIO → `unavailable` (`energy_session.py:139-164`).

## 2. Contatori e domini

- Domini: `pkg, dram, pp0, pp1` (`emi_backend.py:110`, `:116`), mappati dal **nome** (`RAPL_Package0_PKG/_DRAM/_PP0/_PP1`), non dalla posizione (`:158-167`, `:591-624`).
- Energia del package = canale `pkg` (`:563-575`); DRAM/PP0 esposti ma non usati per il package; **PP1 → `igpu_energy_j` informativo** (`energy_session.py:470-506`, test `test_igpu_pp1_emi.py:145-160`).
- **Doppio conteggio evitato per costruzione**: PP0/PP1 ⊂ PKG, PKG+DRAM ≠ tutto, i campi non si sommano (`emi_backend.py:32-34`, `:577-589`); un solo backend attivo per volta (`energy_session.py:259-266`).

## 3. Unità e conversioni

- Unità grezza **pWh** dichiarata dal metadato; unico valore documentato `UNIT_PWH=0` (`:104-106`); unità diversa per PKG → device scartato (`:247-251`).
- Fattore `PWH_TO_J = 3.6e-9` (`:112-113`), applicato **nel backend** (`:575`, `:623`); il grezzo pWh resta esposto come terzo campo (`:607-610`).
- Record: 8 × `uint64` little-endian, 16 byte per canale (`:526-548`); nessuna maschera, **nessuna gestione di wrap** nel lettore: il calo del cumulativo è trattato come **reset** (buffer svuotato, `energy_session.py:327-331`) oppure, ai bordi, come finestra invalida (`local_energy.py:440-449`, `:1151-1152`). Il riporto a 32 bit è gestito solo nel ramo PawnIO (`pawnio_backend.py:21-23`, `:103`, `:592`).

## 4. Campionamento e finestra

- Cadenza sampler **0,05 s** (`energy_session.py:103-107`), thread `cw-emi-sampler` avviato in `start()` e non all'import (`:343-350`, `:1056-1063`).
- **Una IOCTL per tick** alimenta PKG e PP1 dallo stesso record (`:268-303`; test `test_igpu_pp1_emi.py:163-174`).
- **Nessuna integrazione**: il contatore è già energia; i bordi si **interpolano linearmente** sul cumulativo, con arretrato massimo 1 s e nessuna estrapolazione oltre (`:361-382`; grezzi `:384-407`).
- Prima/ultima lettura: sotto i 2 campioni → `None` (`:494-500`); bordo fuori copertura → `None` (`:512-519`). Sottofinestre (giudice) sottratte ai bordi (`:507-521`).
- Percorso P5 preferito: differenza **diretta** fra le due IOCTL di bordo, `emi_edge_source=direct-ioctl` (`local_energy.py:438-472`).
- Contatore fermo: PKG → delta 0 J accettato (`:1151-1153`); **solo PP1** ha il controllo di avanzamento del timestamp per dominio (`energy_session.py:434-448`, `:501-506`).

## 5. Errori, sentinelle, provenienza

- Sentinella unica: `None`, mai 0 J inventato (`:563-575`, test `test_emi_backend.py:78-83`, `:141-152`); `read_idle_window_j` richiede `e_end >= e_start` (`:684`).
- Campi per riga: `energy_calculation_method` = `emi-counter` (`local_energy.py:151`, `:401`); `package_window_source ∈ {exact-counter, samples-fallback, counter-invalid, unavailable}` (`:140-141`, `:443`, `:498`, `:527`, `:548`); `idle_provenance` (`:142`); `raw_start/raw_end/raw_unit/domain/sampling_interval_observed_s/backend_version` (`energy_session.py:1129-1185`).
- **Privilegi**: EMI **non** richiede elevazione — CreateFileW+IOCTL riusciti da processo non Admin il 23/10 (`emi_backend.py:14-16`, nota `:463-473`); PawnIO invece sì, `0x80070005` → `access_denied` (`pawnio_backend.py:37-39`, `:486-491`).

## 6. Limiti

- Dipende dal **driver/device EMI del PAC ACPI** esposto dal firmware: se l'interfaccia non c'è, `unavailable` dichiarato (`:402-407`). **Nessun controllo di vendor** nel backend EMI: il gate è il nome del canale, non il produttore.
- Firmware/OEM possono omettere canali (DRAM spesso 0 su client, `:24`) o non aggiornare PP1 (`energy_session.py:434-448`).
- Cadenza reale degradabile sotto carico (mediana 0,0506→0,0770 s documentata a `:81-83`); la finestra resta corretta perché è un delta, ma il bordo è collocabile solo entro un tick.
- Sospensione/ripresa o driver ricaricato = reset del cumulativo (buffer svuotato, `:327-331`).
- Un PKG con timestamp fermo non è distinguibile da uno zero legittimo (manca il watchdog PKG, presente solo su PP1).
- **Non verificabile dal codice**: politica di accumulo/wrap del driver; presenza del device su altre piattaforme/Windows 11 specifiche; correttezza della **scala assoluta** (stesso MSR 0x611, nessun arbitro indipendente — `:8-13`).

## 7. Natura del dato

- È **energia misurata da un contatore cumulativo** (accumulatore pWh), non una potenza né una stima TDP: `read_package_energy` non integra nulla (`energy_session.py:268-273`, `:595-658`). Una stima TDP moltiplicherebbe un budget per il tempo; qui si legge il registro e si fa una differenza.
- Il dominio è **PKG del package 0 dichiarato dal metadato** (`RAPL_Package0_PKG`), non DRAM né PP0/PP1; su host multi-package il lettore non sceglie (`:266-285`).

## Osservazioni collaterali (non difetti di produzione)

- `tools/emi_cadenza_analysis.py:91-92` chiama `_open()` dopo il costruttore già aperto: possibile handle duplicato non chiuso; `:110-111` legge `v[0]/v[1]` assumendo PKG in posizione 0 — assunzione che la produzione ha eliminato (`emi_backend.py:309-315`).
- `emi_window_energy_j` chiude con `round(max(total, 0.0), 6)` (`energy_session.py:521`): difensivo (i segmenti sono già non negativi per il controllo `cb < ca`), ma il clamp esiste a livello di finestra.

## Verifica del conteggio (solo lettura)

Conteggio con `grep -c "^def test_\|^    def test_"`: **403 funzioni in `cwEnergyModular/tests/` + 80 alla radice = 483**, coerente con l'ancoraggio AGENTS (483 funzioni, 482 ignorando la classe). I **577 node id** derivano da 24 famiglie `parametrize` (+94 casi): ho verificato le 7 famiglie dei file qui sotto (sommano +41), non tutte le 24 una per una. I **3 skip** sono in `test_rapl.py` (`_backend_or_skip`, `:39-43`): senza `/sys/class/powercap` su Windows si saltano basic/readings/idle_window, resta `test_rapl_diagnostics` (`:122`). Base: `C:/Users/Massimo/Documents/CasualWatt/CWProject/cwEnergyModular/`.

## EMI Windows

- `tests/test_emi_backend.py` — 10, **backend finto** (`FakeEMI :22`, `monkeypatch`): pWh→J (`:61`), bordi esatti di finestra (`:127`), guardie (`:141`), `read_power/package` dal contatore (`:184`). Nessuna chiamata reale a SetupAPI/IOCTL.
- `tests/test_emi_selezione.py` — 16, **logica pura su metadati sintetici** costruiti con `struct` (`_blob :40-60`): scelta del device CPU fra batteria/GPU (`:98`), canale PKG per nome (`:172`), V1 dichiarato (`:223`), metadato illeggibile senza canali a metà (`:241`).
- `tests/test_igpu_pp1_emi.py` — 12, backend finto: quattro domini con timestamp per dominio (`:36`), PP1 fermo ≠ 0 J (`:76`), PP1 non contamina il package (`:102`).
- `tests/test_reset_contatore.py` — 5, letture sintetiche: PKG decrescente svuota il buffer (`:46`), valore uguale non è reset (`:57`), finestra a cavallo del reset non produce delta (`:82`).
- `tests/test_provenienza_contatore.py` — 7, sorgente finta/`tmp_path`: grezzi pWh (`:98`), RAPL µJ unwrapped (`:136`), migrazione header (`:195`).
- `tests/test_edge_window.py` (2), `test_busy_single_read.py` (3), `test_measurement_edge.py` (5): session/bordi sintetici.

## PawnIO

- `tests/test_pawnio_backend.py` — 19 funzioni / **27 node id** (`parametrize` 2+5+4), **`FakeLib` ctypes + moduli in `tmp_path`**: Intel 0x606/0x611 e quantum derivato (`:129`), AMD mai su 0x611 (`:150`), riporto 32-bit (`:201`), calo senza riporto = reset non energia (`:216`), HVCI come congiunzione (`:234-272`), hash (`:324`), `access_denied` (`:403`).
- `tests/test_pawnio_selezione.py` — 9, `FakePawnio`: EMI ha precedenza e PawnIO non si apre (`:94`), PawnIO solo se EMI manca (`:103`), PP1 assente dichiarato (`:140`).
- `tests/test_diagnostics_pawnio.py` — 4: fallback dichiarato solo se risponde (`:82`), `energy-file` prevale (`:115`).

## RAPL Linux

- `tests/test_rapl_zone.py` — 8, **sysfs finto su `tmp_path`** (file reali creati da `_zone :28-36`): solo zone package (`:45`), due socket sommati (`:57`), riporto ricostruito (`:81`) e non inventato senza max (`:96`), PSYS≠package (`:116`).
- Nessun run su Linux reale in `experiment_results/`.

## NVML / AMD SMI

- `tests/test_gpu_nvml_energy.py` — 16, **modulo `pynvml` finto** (`_fake_nvml :34`): contatore usato (`:64`), indice fuori intervallo non apre la 0 (`:125`), `CW_GPU_INDEX` non numerico non apre nulla (`:164`), delta di contatore vs integrale (`:230`), decremento = reset dichiarato (`:248`), sottofinestra esclusa → integrale (`:262`).
- `tests/test_gpu_amdsmi.py` — 24, **`amdsmi` finto** (`_fake_amdsmi :46`): µJ×resolution (`:89`), risoluzione nulla non è contatore (`:106`), precedenza `socket_power`/`current`/`average` (`:124-152`), contesto piattaforma (`:163`), timestamp fermo/in avanti (`:338-346`), delta negativo non clampato (`:354`); `sys.platform` monkeypatchato.

## chain_status, CSV/schema

- `tests/test_chain_status.py` — 17, **logica pura su dict**: primo anello che cede (`:75`), `negative_increment` invalida (`:95`), quorum 2/3 (`:120`,`:146`), confine 10% incluso (`:132`), vocabolario chiuso (`:214`), righe CSV equivalenti ai dict del runner (`:224`).
- `tests/test_csv_schema_p5.py` — 4 (`tmp_path`): coda nello stesso ordine (`:77`), nessun duplicato (`:82`), migrazione che non disallinea righe (`:86`). **Il totale 174 non è asserito**: solo coda e unicità.
- `tests/test_metodo_per_riga.py` — 7/12; `test_metodo_ammissibile.py` — 4/11 (`MEASURED_METHODS` = 6, `energy_session.py:73`); `test_external_counter.py` — 6 (`energy-file` unico esterno, `:78-140`); `test_metriche_per_token.py` — 5; `test_filtro_p6_invalidati.py` — 15 funzioni/25 node id (disaccordi riga-riepilogo sollevano, `:225-295`).

## Baseline e attribuzione CPU

- `tests/test_block_baseline.py` — 5: mediana/min/max/range (`:71`), post non sposta pre (`:93`), <3 repliche cella vuota (`:102`), non finiti scartati (`:116`).
- `tests/test_baseline_ordine_v4.py` — 11/18: ordine P1.5 (`:218`), pre/post non scambiati (`:228`), media aritmetica di blocco (`:259`), nessun budget zero per delta mancante (`:342`).
- `tests/test_protocollo_p4_geometry.py` — 15/17, **matematica pura** (inviluppo `:166`, `budget_pred :312`).
- `tests/test_cpu_attribution.py` — 12, `_FakeSession` e `psutil` monkeypatchato: quota su tempo busy (`:119`), energia attiva negativa conservata (`:140`), PID riusato (`:250`), albero per discendenza (`:287`); `test_cpu_share_window.py` 4, `test_tree_change_invalidates_share.py` 3, `test_shared_components_v4.py` 5.
- `tests/test_energy_corrections.py` — 12/14, profili analitici (`FakeSession`): coda inattiva (`:88`), GPU indipendente dall'utilizzo (`:101`).

## Evidenza reale (host MINI_IT13, i9-13900HK, Windows 11)

- **EMI**: `emi_probe_50ms_10ms_20261023_analisi.md:3-6`, 4 CSV `emi_50ms_probe_20261023_*`, `four_way_20261023_120830_analisi.md:1-20` (EMI contatore, LHM, CodeCarbon, HWiNFO assente), `srum_emi_cross_20261023_analisi.md` (0,9946 a finestra identica, stesso registro), `harness_overhead_*`, `observer_cost_*`, `additivity_*`.
- **PawnIO**: `pawnio_probe_20261028_analisi.md:52-64` (594/593 letture, rapporto 1,000578/1,000576), `pawnio_aba_20261028*`, tre `pawnio_priv_20261028_*`.
- **LHM (archiviato, fuori produzione)**: `lhm_validation_v1-v3_*`, `lhm_emi_trace_*`, `four_way_finestra_uguale_20261023_analisi.md`.
- **HWiNFO**: solo `hwinfo_idle_20261023_011237.csv` (idle/PL1-PL2); `tools/validate_hwinfo.py` non ha output committato e nei four-way la shared memory è `err=2` (`four_way_20261023_120830_analisi.md:20-22`).
- **RAPL, NVML, AMD SMI: zero artefatti** in `experiment_results/`.

## Non coperto / test mancanti

- **Accuratezza assoluta**: nessun wattmetro AC/DC; EMI, LHM, SRUM, PawnIO leggono lo stesso 0x611, quindi ogni accordo è coerenza di implementazione (`pawnio_probe_20261028_analisi.md:66-72`). HWiNFO non ha arbitrato nulla.
- **Ripetibilità**: esistono run ripetuti (two-run four-way, due run PawnIO), ma nessun test di stabilità run-to-run né banda preregistrata P6.6.
- **Reset/wrap reali**: coperti solo in simulazione (PawnIO `:201/:216`, AMD `:354`, EMI `test_reset_contatore`); la sonda PawnIO registra 0 riporti/0 reset in 30 s.
- **Multi-device reale**: nessun host dual-socket o multi-GPU; selezione indice provata solo su `pynvml`/`amdsmi` finti.
- **GPU reale e Linux reale**: assenti; RAPL gira solo su sysfs finto.
- **Validazione scientifica mancante**: catena P4.9 end-to-end su campagna reale (nessuna riga `validated`), prova di attribuzione ripetibile P6.6, Monte Carlo P6.4, taratura baseline su canale di produzione, test di riproducibilità dell'intera campagna.
- **Cautela**: ogni test con backend finto prova il contratto logico, non l'accuratezza né il comportamento dell'hardware.

# Audit in sola lettura — baseline, energia incrementale, attribuzione, perimetro

Branch verificato: `emenda-8`, HEAD `9f937366`. Nessun file toccato.

## 1. Baseline
- **Calibrazione**: `calibrate_idle()` fa 3 ripetizioni passive (sleep) di ≥30 s, ognuna `P_rep = ΔE_contatore/Δt_reale`, poi **mediana di 3** (`energy/energy_session.py:1415,1421,1440,1448`; floor 30 s `:1386-1389`). Contatore decrescente → `RuntimeError`, non clamp (`:1435-1439`). Scrive `idle_power_w`/`idle_provenance="calibrated"` (`:1456-1458`).
- **Blocco**: `baseline_pre_w = mediana(P_replica,1..3)`, `pre_range`, `dP = mediana(post) − pre`, `budget_base_w = hypot(half_range_pre, half_drift)` (`benchmark_v4.py:686-759`, mediana `:733`). Sequenza: settle → calibrazione **pre** → m richieste → settle → **post** diagnostica (`:1413-1415`, `:1601-1603`).
- **Applicazione: solo pre**. `baseline_pre_w` sostituisce lo stato di sessione (`local_energy.py:370-379`); `P_post` non è mai sottratto (`benchmark_v4.py:1384-1385`, `:1633-1639`).
- **Non calibrata**: `P_idle=0`, `baseline_energy_j=0`, `idle_provenance="uncalibrated"`, nota esplicita (`local_energy.py:380-390`); `active_valid=False` (`:582-591`). Nessuna micro-calibrazione a metà run.
- **Campi CSV**: `idle_power_w`, `baseline_energy_j`, `idle_provenance`, `baseline_pre_w`, `baseline_post_w`, `pre_windows_w`, `post_windows_w`, `pre_range_w`, `dP`, `half_range_pre_w`, `half_drift_w`, `budget_base_w`, `budget_base_j`, `settle_pre_s/post_s` (`casualwatt_csv_export.py:32-33,143-147,216-218`).
- **Baseline = misura**, non stima: delta di contatore su finestra passiva. Cosa rappresenta (PKG idle dell'intera macchina) è dichiarato, non verificabile dal codice.

## 2. Energia incrementale
- `E_package` = **differenza del contatore ai due bordi** (una IOCTL per bordo), `package_window_source="exact-counter"` (`local_energy.py:438-472,497-498`); senza bordi, buffer/interpolazione (`:483-496`, token `buffer-interp`), poi `samples-fallback` (`:519-540`), poi `unavailable` (`:546-555`). Token in `:140-141,443,527,548`.
- `E_attiva = E_package − P_idle·dt_W` (`:573-574,578`). Baseline e integrale sulla **stessa** finestra (`dt_W_s`, da timestamp 100 ns del contatore, `:1107-1130`).
- **Segno conservato**: `package_energy_j = package_energy_raw_j = e_package` (`:561-562`), `active = active_raw`, nessun clamp (`:578-581`); nota se negativo (`:592-597`). Delta negativo ai bordi → `counter-invalid`, **nessun fallback** (`:440-449`). `active_valid` falso se raw<0, idle mancante, contatore invalido o canale assente (`:586-591`). A livello blocco: `negative_increment` (`benchmark_v4.py:1656-1661,1694`).
- `package_energy_j` = dominio PKG sulla finestra; `active_energy_j` = quota sopra idle. Nessuna delle due è energia "del processo".
- **Residui di clamp non dichiarati (energia)**: `energy_session.py:1223` e `:1231` (`max(…,0.0)` nel ramo a campioni, che è il percorso di produzione **RAPL** e `energy-file`), `:623,654` (energy-file); `judge_energy_j` clampato a 0 con grezzo in nota (`benchmark_v4.py:1229,1234,1562-1566`). Contraddicono localmente la regola "nessun troncamento": su RAPL un contatore decrescente diventa 0 in silenzio.

## 3. Attribuzione CPU
- `s = d_ollama / d_busy` (`local_energy.py:627-639,672`). Numeratore: cpu_times user+system dell'**albero** del motore, identità `(pid, create_time)`, radici per nome + discendenti (`energy/worker_tree.py:178-210`; `energy_session.py:814-843`). Denominatore: busy **di sistema** = totale−idle per-core (`energy_session.py:782-803`), letto agli stessi bordi quando possibile (`local_energy.py:600-623`).
- È quota sul **tempo BUSY**, non sulla capacità (`core × finestra`): `:18-19`, test `tests/test_cpu_attribution.py:119-136`. `cpu_share_window_s`, `cpu_busy_capacity_cores`, `cpu_share_source`, `cpu_time_share_valid` dichiarano il denominatore (`local_energy.py:661-666,704-723`).
- Anomalie dichiarate, non nascoste: `share_raw` grezzo, clamp a [0,1] solo su `cpu_time_share`, `share_anomaly ∈ {d_busy=0, d_busy>capacita', d_ollama>d_busy}` (`:667-684`); `d_busy>capacita'` invalida (`:718-723`); albero cambiato → quota non calcolata, zero convenzionale e flag (`:686-702`).
- `E_ollama = E_attiva · s`, **stima** (token `"ESTIMATE"` in `cpu_attribution_method`, `:514-518,726-729`): il contatore conosce PKG, non il PID; l'equivalenza tempo↔energia è assunzione dichiarata. Clamp di tempo (non energia): `worker_tree.py:197,199`, `local_energy.py:620`.
- Test: `test_cpu_share_window.py` (denominatore), `test_baseline_ordine_v4.py:244-263` (post diagnostico), `test_energy_corrections.py:88-147` (coda inattiva, judge, GPU), `test_shared_components_v4.py:114-145` (ogni campo v4 esiste nello schema).

## 4. Attribuzione GPU
- **Non esiste un'attribuzione per processo utilizzabile.** `gpu_process_energy_j` è calcolato da `nvmlDeviceGetProcessUtilization`, ma `board_active = getattr(self, "_last_window_board_active_j")` (`energy_session.py:1673`) non è **mai assegnato** nel sorgente → sempre `None` → campo sempre `N/A` (`local_energy.py:928-947`). Inoltre la query è "ultimi 10 s", non la finestra della richiesta, e `frac` è clampato a 1 (`energy_session.py:1657-1672`). Su AMD il metodo non esiste.
- Ciò che si riporta è **whole-device**: `gpu_energy_attributed_j = board_j − P_idle_gpu·dt` (`local_energy.py:889-913`), con `gpu_board_energy_j` da delta contatore (`nvml-energy`/`amdsmi-energy`, `:826-870`) o integrale trapezoidale (`:871-888`). `gpu_utilization_share` è **solo diagnostico**, non moltiplica (`:69-72,895-904`).
- `P_idle_gpu` non è mai calibrato in produzione (`idle_gpu_power_w` solo letto, `local_energy.py:889`): `gpu_idle_provenance="missing"` e attribuito = potenza totale della scheda, sovrastima dichiarata (`:923-927`).
- Ragione fisica: i contatori sono per device; NVML/AMD SMI non espongono energia per PID. Un'attribuzione per processo sarebbe una seconda stima sopra una stima.

## 5. Energia complessiva
- `local_energy_j = ollama_active_energy_j + gpu_energy_attributed_j` (`benchmark_v4.py:1552-1554`; `benchmark_unified.py:1074,1281-1285`). `end_to_end = local + network + cloud`, con componente mancante → `N/A`, mai 0 (`benchmark_unified.py:578-597`); in modalità locale `network_energy_j=0`, `cloud_energy_j=0` **per boundary** (`:509-524`; `benchmark_v4.py:1554`).
- **Incluso**: quota attribuita del dominio PKG attivo (che include già l'iGPU) + GPU dedicata intera.
- **Escluso**: baseline idle (sottratta), iGPU separata (`igpu_energy_j` solo informativo, `local_energy.py:948-976`; solo EMI, `energy_session.py:1254`), **DRAM** (dominio letto, `emi_backend.py:23-34,116,587`, ma mai esportato: nessuna colonna), energia degli altri processi, rete/cloud in locale, PSU/display/dischi/ventole. PP0/PP1 **mai sommati** a PKG (`emi_backend.py:32-34`).
- Il "totale" **non è l'intero computer**: è il perimetro `client-host system boundary` (`local_energy.py:1033-1035`). Quali sottodomini copra esattamente PKG non è verificabile dal codice (semantica del registro).

## 6. Natura di ciascuna grandezza
- **Misurata dal contatore**: `package_energy_j` (EMI/PawnIO ai bordi), `igpu_energy_j` (PP1/EMI), `gpu_board_energy_j` (delta NVML/AMD SMI), `idle_power_w` (delta/Δt su 3×30 s).
- **Integrata da campioni**: `package_energy_j` in `samples-fallback`/`buffer-interp`, `gpu_board_energy_j` in `*-power-integral`.
- **Stimata per attribuzione**: `cpu_time_share`/`ollama_active_energy_j` (quota di tempo), `gpu_energy_attributed_j` (whole-device meno idle, oggi idle assente), `local_energy_j`, `end_to_end_energy_j`, e tutti i derivati per token/carbonio (`energy_per_output_token_j` ecc., `benchmark_unified.py:623-684`) — ereditano l'attribuzione, non la misura.

## Non verificabile / da segnalare
1. `gpu_process_energy_j` strutturalmente non producibile (attributo mai assegnato).
2. `idle_gpu_power_w` mai impostato in produzione: attribuzione GPU = scheda intera.
3. Clamp silenziosi residui su energia: `energy_session.py:1223,1231` (RAPL/file), `:623,654`; nessun flag.
4. L'override `baseline_pre_w` non aggiorna `idle_provenance` (`local_energy.py:368-375`): con sessione non calibrata la riga resterebbe `active_valid=False` anche con P_pre valido (nel runner v4 non accade perché `calibrate_idle` precede).
5. Docstring stantia in `tests/test_cpu_attribution.py:22` ("active_energy_j troncato"): il corpo verifica −5 J firmato (`:147-148`).
6. Copertura fisica del dominio PKG (DRAM inclusa o no) non deducibile dal codice.

## 1. RAPL / powercap

- **Percorsi**: radice `/sys/class/powercap` (`rapl_backend.py:82`), per zona `energy_uj` (`:147`, lettura `:186-187`), `name` (`:150`), `max_energy_range_uj` (`:168-175`). Enumerazione **non ricorsiva** (`iterdir()` a `:131`): le sottozone annidate (`core`, `dram`, `uncore`) non vengono nemmeno viste, quindi il doppio conteggio per annidamento non è possibile per costruzione.
- **Domini**: si tengono solo i nomi con prefisso `package-` (`:85`, `:151`); `psys`/`dram`/`core` finiscono in `_skipped` e in `notes` (`:152`, `:98-102`). Zone omonime = canali specchiati, contate una volta (`:154-159`). Più package distinti si **sommano** (`:222`), ed è corretto: sono contatori diversi (`tests/test_rapl_zone.py:57-67`).
- **Unità**: `energy_uj` è intero in µJ, conversione `/1e6` → J (`:206-207`). La potenza è delta diviso tempo monotono (`:243-262`).
- **Wrap**: se il valore decresce e `max` è leggibile, `wraps += 1` e `total = wraps*max + (current-base)` (`:193-206`). Se `max` manca, `_Unreliable` → `None` con ragione: **non si assume 2³²** (`:194-199`, `:22-25`; test `test_rapl_zone.py:96-103`).
- **Intervallo massimo fra letture: non esiste un guard**. Con 2³² µJ ≈ 4295 J il giro dura ~107 s a 40 W: un campionamento a 0,5 s (`energy_session.py:41`, `:750`) è largamente dentro, ma nulla lo verifica; `read_idle_window_j` (`:270-299`) dorme e legge solo i due estremi, quindi può ricostruire **un solo** wrap.
- **Reset vs wrap non distinguibili**: qualunque decremento è trattato come avvolgimento, quindi un reset del driver (ricarica modulo) **gonfia il cumulato di `max`** (`:193-204`). Non c'è rimedio nel codice.
- **Bug latente**: `read_power_w` sul ramo wrap aggiorna `last_uj` ma **non incrementa `wraps`** (`:247-261`) → mescolando `read_power_w` e `read_cumulative_energy_j` il cumulato perde un giro e può diventare negativo. Oggi non è raggiungibile in produzione: `read_power_w` è chiamato solo da `tests/test_rapl.py:83`; la produzione passa da `read_cumulative_energy_j` (`energy_session.py:614-616`, `:645-647`).
- **Nessun lock**: `RAPLBackend` muta `last_uj`/`wraps` senza sincronizzazione; durante la calibrazione idle il sampler è attivo (`energy_session.py:1391-1393`) e chiama `read_cumulative_energy_j` (`:1027`) mentre `read_idle_window_j` legge gli stessi campi (`:1421`) → corsa critica, con possibile doppio conteggio del wrap.
- **Troncamento nella finestra**: `package_energy_exact_between` applica `max(...,0.0)` due volte sul ramo RAPL (`energy_session.py:1223`, `:1231`): un delta negativo di finestra diventa 0, in contrasto con la regola "nessun troncamento" del ramo CPU. `:435-439` invece rifiuta esplicitamente un delta negativo in calibrazione.
- Zone mancanti → `unavailable` con causa (`:96-109`; `test_rapl_zone.py:106-122`); i test di misura sono **skip dichiarato** senza host Linux (`test_rapl.py:39-48`).

## 2. NVML

- **Apertura**: `nvmlInit`, `nvmlDeviceGetCount`, `nvmlDeviceGetHandleByIndex` (`energy_session.py:1536-1557`). Indice: argomento → `CW_GPU_INDEX` → "non dichiarato" (`:1465-1487`); fuori intervallo = errore, **non** apre la scheda 0 (`:1506-1509`); >1 device senza selezione = indice 0 **con nota** (`:1501-1505`).
- **Contatore**: sonda con lettura reale all'apertura (`:1564-1590`); `nvmlDeviceGetTotalEnergyConsumption` in **mJ**, "since last reset", "does not overflow" (`:1592-1607`). Nessun timestamp del device: `read_energy` restituisce `(mJ, None)` (`:1607`).
- **Potenza**: `nvmlDeviceGetPowerUsage` mW/1000 (`:1617-1620`).
- **Uso in finestra** (in `local_energy.py`): contatore solo con ≥2 campioni e **nessuna** sottofinestra esclusa (`:826-828`); `d_mj = last-first`, `span = last.t-first.t` (`:830-831`); delta negativo o span ≤ 0 → integrale, **mai clampato** (`:850-861`); delta nullo → zero legittimo con nota (`:866-870`, ma il testo parla di timestamp che avanza, che per NVML non esiste: etichetta imprecisa).
- **Integrale**: **trapezoidale**, `((p_prev+p_cur)/2)*seg_dt` (`:877-882`), con `seg_dt` dai timestamp monotoni dei campioni di sessione (0,5 s, `energy_session.py:1018-1029`), non dal device; sottofinestre escluse rimosse per segmento (`:875-879`).
- **Bordi**: il contatore copre `[primo, ultimo campione]`, non `[t_start,t_end]`: fino a 0,5 s per lato, a differenza del buffer EMI a 0,05 s (`energy_session.py:454`).

## 3. AMD SMI

- **Implementato**: `amdsmi_get_processor_handles` (lista, indice = posizione, `:1737-1751`); `amdsmi_get_energy_count` → `accumulator * counter_resolution` µJ, convertito in mJ (`:1788-1807`); risoluzione **sondata** e nulla ⇒ nessun contatore (`:1770-1786`); `timestamp` dalla stessa lettura (`:1801-1805`), usato **solo** come controllo di avanzamento, mai come durata (`local_energy.py:832-849`).
- **Potenza**: ordine `socket_power` → `current_socket_power` → `average_socket_power`, campo e unità scritti nel token (`:1820-1827`; `local_energy.py:883-888`). `platform=gpu_bm_linux` se Linux (`:1760-1767`).
- **Manca**: attribuzione per processo (esiste solo NVML, `:1640-1678`); nessun uso di `amdsmi_get_gpu_metrics`; nessuna prova su hardware (`tests/test_gpu_amdsmi.py:28-29`).

## 4. Comune alle due GPU

- Delta negativo = reset/avvolgimento → integrale, nessun clamp (`local_energy.py:850-859`); timestamp AMD fermo → lettura non valida → integrale (`:845-849`); zero con timestamp che avanza = zero legittimo (`:866-870`); timestamp assente su AMD → controllo non applicato, dichiarato (`:838-841`).
- **Idle GPU mai calibrato in produzione**: `idle_gpu_power_w` è **solo letto** (`local_energy.py:889`) e non viene mai assegnato fuori dai test (grep su tutto il repo: nessuna assegnazione in `energy/`). Quindi `gpu_idle_provenance="missing"` sempre, nessuno scorporo (`:894`, `:901`), attribuito = energia totale board, sovrastima dichiarata (`:923-927`). I test che verificano lo scorporo (es. `test_gpu_nvml_energy.py:230-235`) esercitano un ramo che la produzione non raggiunge.
- **Selezione backend**: `_open_gpu_monitor` prova NVML e poi AMD (`:1862-1870`); su macchina con iGPU AMD + dGPU NVIDIA vince sempre NVIDIA e la scheda AMD non è selezionabile per vendor: la scelta è "il primo che risponde", non una selezione dichiarata.

## 5. Natura del dato

- **Contatore misurato**: RAPL `energy_uj`; NVML total energy (mJ); AMD SMI accumulator×resolution (µJ). Token: `rapl`, `nvml-energy`, `amdsmi-energy` (`local_energy.py:863`, `:909`).
- **Integrale di potenza campionata** (non contatore): trapezoidale a 0,5 s su potenza già mediata dal driver; token `nvml-power-integral` / `amdsmi-power-integral` (`:887`).
- **Stima**: nessuna. Non esiste percorso TDP né nel ramo RAPL né GPU; `gpu_utilization_share` è diagnostico e non moltiplica (`:895-904`).
- **Non verificabile dal codice**: comportamento reale di NVML/AMD SMI e scala assoluta (nessuna GPU su questo host, `test_gpu_nvml_energy.py:18-19`; `test_gpu_amdsmi.py:29`); semantica hardware del wrap RAPL e dei reset; unità/risoluzione AMD reali dipendono dalla doc citata, non da un test su device; assenza di RAPL su questo host (test in skip).

I quattro rapporti sono coerenti tra loro. Verifico ora di persona le affermazioni più delicate, soprattutto quelle che suonano come difetti.

I'll finish the targeted verification reads before writing the report.

# Audit tecnico in sola lettura — `emenda-8` (HEAD `9f937366`)

Non ho modificato nulla: nessun file scritto, nessun commit, nessun push/merge/rebase. Il worktree contiene modifiche non mie (`MUDILAB_run/traduzione_controllata.py` e directory non tracciate): le ho lasciate intatte. Ho letto il codice a HEAD e gli artefatti tracciati in `experiment_results/`. **Non ho rieseguito pytest** in questa sessione per rispettare il vincolo di non scrittura: i conteggi citati sono quelli dell'Appendice D rigenerata il 04-11 (`577 = 574 + 3`) e li ho ricontrollati staticamente per singolo file dove serviva.

---

## 1. Windows 11 — contatore EMI

### 1.1 File e funzioni

| Elemento | Ancoraggio |
|---|---|
| Device discovery/selection | `energy/emi_backend.py:325-384`, `:386-470` |
| Regola «è un device CPU» | `:226-263` (`select_cpu_device`) |
| Regola «uno solo» | `:266-285` (`choose_single`) |
| Metadati | `:476-524` |
| Record di misura | `:526-548` (`_ioctl_raw`), `:550-561` (`read_raw`) |
| Conversione e domini | `:563-575`, `:591-624` (`read_domains`) |
| Sampler 20 Hz | `energy/energy_session.py:107`, `:268-312` |
| Buffer e reset | `:314-341` |
| Interpolazione ai bordi | `:361-408` |
| Finestra = delta del contatore | `:450-521` (`emi_window_energy_j`) |
| Bordi diretti (una IOCTL per bordo) | `:857-955`, `energy/local_energy.py:1042-1153` |

### 1.2 Percorso di acquisizione

1. Enumerazione SetupAPI sull'interfaccia `{45bd8344-7ed6-49cf-a440-c276c933b053}` (`emi_backend.py:80-87`, chiamata a `:357`), fino a 16 interfacce (`:362`).
2. `CreateFileW` in `GENERIC_READ`, `FILE_SHARE_READ|WRITE`, `OPEN_EXISTING` (`:418`); **nessun token elevato** (verificato il 23-10, `:15-16`).
3. Contratto del driver: `GET_VERSION` → `GET_METADATA_SIZE` → `GET_METADATA` (`:95-97`, `:476-524`); la prima `ENERGY_READ` è la validazione d'apertura (`:450-461`).
4. Un device è accettato se espone un canale di nome contenente `PKG` **in pWh** (`:241-250`); più canali PKG distinti = `ambiguous_domain`, nessuna scelta automatica (`:252-257`); canali PKG omonimi = stesso contatore specchiato, letto una volta (`:258-261`).
5. A regime un solo thread campiona il cumulativo ogni 0,05 s, **senza integrare** (`energy_session.py:268-312`); una sola IOCTL per tick porta PKG e PP1 (`:286-307`).
6. La finestra di una richiesta è la **differenza del contatore** fra i due bordi: `E = c(t_end) − c(t_start)`, con `c(t)` interpolato linearmente sul buffer a 0,05 s (`:361-382`, `:507-520`). Il percorso preferito legge i bordi con una IOCTL diretta (`local_energy.py:455-472`, `1133-1153`) e degrada in modo dichiarato al buffer o ai campioni (`:473-482`, `:519-545`).

### 1.3 API, contatori, domini, unità

- IOCTL: `0x00224000`, `0x00224004`, `0x00224008`, `0x0022400C` (`emi_backend.py:95-98`).
- Record: `16·n` byte, `n` canali, `2n` interi `uint64` (`energia`, `timestamp 100 ns`) — `:542-548`.
- Domini dai token del nome: `PKG→pkg`, `DRAM→dram`, `PP0→pp0`, `PP1→pp1` (`:110`, `:116`).
- Unità dichiarata: `EmiMeasurementUnitPicowattHours` (`UNIT_PWH = 0`, `:106`), conversione `PWH_TO_J = 3.6e-9` (`:113`), applicata a `:575` e `:623`.

**Formula.** Con `r` valore grezzo in pWh

```
E_J = r · 3.6e-9
E_finestra = Σ_k [ c(b_k) − c(a_k) ]        (segmenti tenuti, sottofinestre giudice rimosse alla fonte)
c(t) = c_0 + (c_1 − c_0)·(t − t_0)/(t_1 − t_0)   fra due campioni consecutivi
Δt_W = (ts_100ns(e_1) − ts_100ns(e_0)) / 1e7      (local_energy.py:1121-1122)
```

**Natura del dato.** Misurato (contatore cumulativo del package, differenza esatta ai bordi o interpolazione dichiarata sul buffer a 0,05 s). Nessuna integrazione, nessun modello TDP, nessuna moltiplicazione per un duty cycle.

### 1.4 Conversioni, letture iniziali/finali, errori, disponibilità

- Il contatore è **cumulato da boot** (`:563-565`), quindi il valore assoluto non è usato: solo delta.
- Errore di lettura: `last_error` con il codice (`DeviceIoControl … got=…`, `:504-524`); un solo tentativo di riapertura (`:550-561`).
- Disponibilità: `True` solo dopo apertura **e** prima lettura riuscite (`:450-461`); altrimenti la catena passa a PawnIO e poi a `unavailable` (`energy_session.py:139-164`).
- Decremento del cumulativo: il buffer viene svuotato (`energy_session.py:327-331`); ai bordi un delta negativo produce `package_window_source = counter-invalid` e **non** si usa il fallback (`local_energy.py:440-449`). Non esiste una ricostruzione software di riporto: per un contatore a 64 bit in pWh il riporto è a `2^64 · 3.6e-9 J ≈ 6,64·10^10 J` (≈ 18,4 MWh), fuori scala rispetto ai run; la gestione del **reset** è un'invalidazione dichiarata, non un recupero.
- In `emi_window_energy_j` c'è un `max(total, 0.0)` a `:521`, difensivo: non può scattare perché `cb < ca` restituisce `None` a `:513-519`.

### 1.5 Cosa c'è di nuovo rispetto a una stima di potenza

Il numero non è `P·t`: è la differenza di un accumulatore di energia. Le scelte ingegneristiche che lo distinguono da una stima sono: bordi letti con IOCTL diretta (nessuna interpolazione necessaria sulla finestra), buffer a 20 Hz per collocare finestre brevi, timestamp per dominio per distinguere «zero» da «registro vecchio» (solo PP1, v. §8), provenienza persistita (`raw_start/raw_end/raw_unit`, `sampling_interval_observed_s`, `backend_version`: `local_energy.py:411-425`), incrementi firmati e invalidazione esplicita. Non è una novità metrologica: è lo stesso registro che RAPL, LHM e SRUM leggono (§8, P6).

### 1.6 Limiti hardware/firmware/OS

- Serve l'interfaccia ACPI EMI esposta dal firmware; su questo host c'è (23-10). Su una macchina senza, la catena degrada dichiaratamente.
- Granularità nominale 1 pWh, ma la **cadenza di aggiornamento è del firmware/EC**: sul probe del 23-10 nessuna quantizzazione sopra i 10 ms (`experiment_results/emi_probe_50ms_10ms_20261023_analisi.md`); su un altro firmware non è garantito.
- I domini esposti dipendono dal metadato: `DRAM`, `PP0` possono mancare; qui `PP1` c'è ed è usato solo come campo informativo (`local_energy.py:948-976`).
- Multi-package: nessuna somma automatica; serve `CW_EMI_DEVICE` (`emi_backend.py:266-285`, `:394-400`).
- Il campionamento è un thread Python a 20 Hz con una IOCTL per tick: il costo dell'osservatore entra in `E_pkg` e riduce lievemente la quota attribuita (è tempo busy di sistema, non di Ollama). Non è quantificato per riga.
- Nessuna arbitratura della scala assoluta: tutti i canali Windows leggono `MSR_PKG_ENERGY_STATUS` (0x611) o un suo equivalente dichiarato.

### 1.7 È davvero il package della CPU?

Sì, nel senso stretto del dominio dichiarato: il canale è selezionato per **nome `PKG`** e unità pWh, non per posizione (`emi_backend.py:309-315`, `:241-261`), e il valore è un accumulatore di energia con timestamp. È il package del processore — core + uncore + iGPU — **non** i soli core (`PP0` è un sottoinsieme), **non** la DRAM (dominio separato, non sommato) e **non** la presa (mancano VRM, PSU, dischi, display). La conferma che non è una temperatura o una potenza derivata è strutturale: unità pWh, record `(energia, tempo)` per dominio, accordo a finestra uguale con il registro MSR. La corrispondenza con il dominio RAPL `package-0` è per costruzione su Intel; su AMD l'interfaccia ACPI è implementata dal vendor e **non è stata esercitata** su questo host.

### 1.8 Test esistenti

`tests/test_emi_backend.py` 10 (FakeEMI), `tests/test_emi_selezione.py` 16 (metadati sintetici: V1/V2, scelta device, canale PKG per nome), `tests/test_igpu_pp1_emi.py` 12, `tests/test_reset_contatore.py` 5, `tests/test_provenienza_contatore.py` 7, `test_edge_window.py` 2, `test_metodo_per_riga.py` 7, `test_metodo_ammissibile.py` 4, `test_external_counter.py` 6. Sono tutti su driver simulato: verificano il **contratto** (record, canale, unità, invalidazione), non l'accuratezza dell'hardware.

---

## 2. Windows — fallback `pawnio-counter`

- File: `energy/pawnio_backend.py`; etichetta `METHOD_LABEL = "pawnio-counter"` (`:62`), versione `:66`, hash dei moduli 0.2.11 (`:75`), MSR `0x611` Intel / `0xC001029B` AMD (`:89`, `:95`), regola di riporto a 32 bit (`:103`, `:578-600`).
- Richiede **processo elevato**: da token filtrato `pawnio_open` risponde `0x80070005` → `access_denied` (`:488`). Con HVCI attivo o non determinabile il firmatario deve essere Microsoft (`fail closed`, `:536-552`).
- Formula: `E = counts · quantum`, con `quantum` derivato da `MSR_RAPL_POWER_UNIT`; i conteggi sono srotolati a 32 bit (`:578-600`). Nessuna scrittura di MSR.
- Natura: **misurato**, stesso registro di EMI; non si somma mai a EMI (una sola sorgente attiva, `energy_session.py:259-266`).
- Test: `test_pawnio_backend.py` 17 funzioni (27 node id per parametrizzazione), `test_pawnio_selezione.py` 9, `test_diagnostics_pawnio.py` 4 — tutti su `FakeLib`.
- Evidenza reale: `experiment_results/pawnio_probe_20261028*` (rapporti 1,000578 / 1,000576 a finestra uguale contro EMI), più A-B-A e priv probe. Restano non esercitati su hardware reale il ramo AMD e i riporti/reset reali.

---

## 3. Linux — RAPL/powercap

### 3.1 File, funzioni, percorso

`energy/rapl_backend.py`: radice `POWERCAP_ROOT` (`:82`), prefisso `package-` (`:85`), scoperta `:128-183`, cumulativo `:190-207`, potenza `:230-268`, finestra idle `:270-299`. L'attivazione è in `energy_session.py:228-257`, il campionamento usa il sampler di sessione a 0,5 s (`config.py:334`) attraverso `read_package_j → read_cumulative_energy_j` (`energy_session.py:595-617`).

### 3.2 Unità, riporto, intervallo massimo

```
E_cum = [ wraps · max_energy_range_uj + (current − base_uj) ] / 1e6    [J]   (rapl_backend.py:206-207)
```
`energy_uj` in µJ, `max_energy_range_uj` letto alla scoperta (`:168-180`). Decremento con `max_uj` noto → `wraps += 1` e nota (`:198-205`); senza `max_uj` → `_Unreliable` e lettura dichiarata non affidabile (`:193-199`).

**Non esiste alcun controllo dell'intervallo massimo**: nessun confronto fra tempo trascorso e periodo di riporto, nessuna verifica che `energy_uj` sia avanzato. Con `max_energy_range_uj` tipico di 2,62·10^8 µJ (262 kJ) e 50 W, il riporto arriva in ~87 min: un run lungo può attraversarlo senza che nulla lo dichiari come «lungo». Un **reset** (ricarica del driver, sospensione) è indistinguibile da un riporto e viene contato come riporto, sovrastimando di un `max_energy_range_uj`.

### 3.3 Domini e doppio conteggio

La scoperta è **non ricorsiva** (`iterdir()`, `:131`), filtra per nome `package-` (`:151`) e deduplica per nome i canali specchiati (`:154-159`). `psys`, `core`, `dram` non sono sommati e finiscono in `_skipped` (`:96-108`). Quindi: niente doppio conteggio `package + core + dram`, ma anche **niente PSYS**, cioè niente perimetro di piattaforma.

### 3.4 Contatori mancanti o anomali

`energy_uj` assente/illeggibile → zona scartata; nessuna zona → `available = False` con la ragione (`:96-109`). Un file congelato (permessi, driver) produce `current == last_uj` → delta 0 J **senza alcuna nota**: indistinguibile da un idle vero. Non c'è lock: il sampler di sessione e `calibrate_idle` possono leggere `energy_uj` in parallelo sullo stesso stato `_Zone.last_uj/wraps` (§8, P5).

### 3.5 Test

`tests/test_rapl_zone.py` 8 su sysfs finto (riporto, max assente, dedupe, domini scartati); `tests/test_rapl.py` 4 funzioni, di cui 3 **saltate** su Windows per assenza di `/sys/class/powercap` (sono le 3 skip della suite). Nessun artefatto RAPL in `experiment_results/`: la catena Linux è **[I] software, [V] assente**.

---

## 4. GPU

### 4.1 NVIDIA — NVML

- Apertura e selezione: `energy/energy_session.py:1512-1562`, indice da argomento → `CW_GPU_INDEX` → «non dichiarato» (`:1465-1487`), device fuori intervallo **non** apre la scheda 0 (`:1490-1509`), nota in `notes` se multi-device (`local_energy.py:809-811`).
- Contatore: `nvmlDeviceGetTotalEnergyConsumption` in **mJ**, cumulativo dal reset, una sonda reale all'apertura (`:1564-1590`), lettura `:1592-1609`. **NVML non espone un timestamp del contatore** (`:1593-1599`).
- Potenza: `nvmlDeviceGetPowerUsage` in **mW** → /1000 (`:1611-1620`), campionata a **0,5 s** dal sampler di sessione (`:1018-1046`, `config.py:334`), non a 0,05 s.

**Formule** (`local_energy.py:818-906`)

```
E_board = (C_end − C_start) / 1000                        [J]   se delta ≥ 0, span > 0
E_board = Σ_k ((P_{k−1} + P_k)/2) · Δt_k                  [J]   altrimenti (trapezi)
E_gpu   = E_board − P_idle,gpu · Δt_gpu                   [J]
```

Il contatore si usa solo senza sottofinestre escluse (`:826-827`); delta negativo o span nullo → integrale, **senza clamp** (`:850-859`); delta nullo accettato come zero legittimo (`:866-870`).

### 4.2 AMD — AMD SMI

`_AMDGPUMonitor` (`:1684-1836`): `amdsmi_get_energy_count` restituisce `accumulator`, `counter_resolution`, `timestamp` (`:1688-1700`); `E_mJ = accumulator · resolution / 1000` (`:1788-1807`). Risoluzione mancante o zero → contatore non usato (`:1778-1786`). Timestamp a 1 ns usato **solo come controllo di avanzamento** (`local_energy.py:832-849`): fermo → lettura non valida; che avanza con contatore fermo → zero legittimo. Potenza: `socket_power`, poi `current_socket_power`, poi `average_socket_power` (`:1818-1824`), contesto `platform=gpu_bm_linux`.

Selezione del backend: NVML prima, AMD SMI dopo, **un solo lettore** (`:1846-1870`). NVML non è un fallback di AMD SMI: su una macchina AMD senza NVIDIA, NVML conta 0 device e passa la mano.

### 4.3 Attribuzione GPU → processo

`local_energy.py:928-947` chiama `process_energy_j`, che esiste (`energy_session.py:1640-1678`) e userebbe `nvmlDeviceGetProcessUtilization` per stimare una frazione di tempo GPU e applicarla all'energia board. **Ma `_last_window_board_active_j` non viene mai assegnato in produzione** (unica occorrenza: lettura a `:1673`). Quindi `gpu_process_energy_j` è **strutturalmente N/A**, anche con NVML sano. Non è un numero sbagliato: è un campo che non può esistere.

### 4.4 Natura, ipotesi, limiti

- Contatore: misurato. Integrale: integrato (potenza campionata a 0,5 s). Attribuzione: `E_board` meno un idle che **in produzione vale sempre 0** (`idle_gpu_power_w` non è mai assegnato; unica lettura a `local_energy.py:889`) → **l'energia GPU è l'intera scheda**, non l'incremento. `gpu_idle_provenance` è quindi sempre `missing` e la nota lo dichiara (`:889-894`, `:923-927`).
- `gpu_utilization_share` è solo diagnostico, non moltiplicatore (`:895-904`).
- Il confine è whole-device: include gli altri processi GPU. Sommato a `E_ollama`, attribuisce a Ollama tutta l'energia della scheda nella finestra.
- Nessun artifact NVML/AMD SMI in `experiment_results/`: **[I] con [V] da fare**, provato solo con `pynvml` e `amdsmi` finti.

### 4.5 Test

`tests/test_gpu_nvml_energy.py` 16, `tests/test_gpu_amdsmi.py` 24. Coprono catena contatore→integrale, unità, timestamp, delta negativo, provenienza di potenza, precedenza NVML, selezione del device. Non provano nulla su silicio reale.

---

## 5. Baseline e attribuzione CPU

### 5.1 Formule effettive

Calibrazione (`energy_session.py:1362-1459`): 3 finestre, `P_rep = ΔE/Δt`, `P_idle = mediana(P_1..3)` (`:1440`, `:1448`), durata con floor a 30 s (`:1389`), decremento → `RuntimeError` (`:1435-1439`).

Blocco (`benchmark_v4.py:686-759`)

```
P_pre        = mediana(P_rep,1..3)
pre_range    = max − min;   half_range = pre_range/2
dP           = mediana(P_post) − P_pre;   half_drift = |dP|/2
budget_base_w= sqrt(half_range² + half_drift²)
budget_base_j= Δt_W · budget_base_w
```

`P_post` è diagnostica e non entra mai in `P_pre` (`:699`, `:739-746`). Nel runner la calibratura è eseguita **prima e dopo ogni blocco** (`:1413-1425`, `:1601-1625`), e i valori post/drift/budget sono scritti su ogni riga (`:1633-1639`).

Riga (`energy/local_energy.py`)

```
E_base = P_idle · Δt_W                                     (:573-574)
E_att  = E_pkg − E_base            firmata, mai clampata   (:578-581)
s      = Δt_CPU(Ollama)/Δt_busy(sistema)                   (:672)
E_ollama = E_att · clamp(s, 0, 1)                          (:684, :726-729)
```

`active_valid` richiede `E_att ≥ 0`, baseline calibrata, contatore non invalido e sorgente disponibile (`:586-591`). La quota è dichiarata non valida se l'albero cambia (`:686-702`) o se `d_ollama > d_busy` / `d_busy > capacità` (`:713-723`); il rapporto grezzo resta in `cpu_time_share_raw` (`:663-676`).

### 5.2 Natura dei dati

| Grandezza | Natura |
|---|---|
| `package_energy_j` | misurata (contatore) |
| `baseline_energy_j` | **modellata** (P_idle × Δt) |
| `active_energy_j` | misurata meno modellata, firmata |
| `ollama_active_energy_j` | **stimata** (quota di tempo CPU applicata all'energia attiva) |
| `gpu_energy_attributed_j` | misurata meno idle (idle = 0 in produzione) → board intera |
| `gpu_process_energy_j` | non implementata operativamente |

### 5.3 Ipotesi e limiti

- La quota di tempo CPU busy è un **proxy** della quota di energia (dichiarato nella stringa di attribuzione, `:514-517`).
- Energia non-CPU della finestra (iGPU, altri processi) viene rimossa **in proporzione al tempo CPU**, non misurata: lavoro grafico con poco CPU time è sotto-attribuito.
- Baseline: mediana di 3, scelta causale pre-only; `n = 3` non consente una stima di varianza (P4.12).
- `budget_base_w` è un proxy conservativo, forma **provvisoria** (P2.9), non un limite garantito (`benchmark_v4.py:702-715`).
- Il percorso `CW_IDLE_WINDOW_S` può abbassare il floor sotto i 30 s (`energy_session.py:1384-1389`): lecito per collaudi, ma la durata effettiva delle finestre non finisce nel CSV, quindi un run non conforme non è distinguibile a posteriori.

### 5.4 Test

`test_block_baseline.py` 5, `test_baseline_ordine_v4.py` 11, `test_cpu_attribution.py` 12, `test_cpu_share_window.py` 4, `test_tree_change_invalidates_share.py` 3, `test_shared_components_v4.py` 5, `test_energy_corrections.py` 12, `test_protocollo_p4_geometry.py` 15 (17 node id), `test_metriche_per_token.py` 5, `test_chain_status.py` 17, `test_filtro_p6_invalidati.py` 15. Verificano formule, ordine causale, invalidazioni e soglie: non l'accuratezza del proxy.

---

## 6. Energia totale e perimetro

```
local_j = ollama_active_energy_j + gpu_energy_attributed_j        (benchmark_v4.py:1552-1554)
e2e_j   = local_j + network_j + cloud_j                           (benchmark_unified.py:597)
```
Se una componente è `None`, `end_to_end_energy_j` è `"N/A"`, mai zero inventato (`benchmark_unified.py:578-595`). In modalità locale rete e cloud sono `0.0` **per confine** (regola 12.1), non perché misurati nulli.

**Incluso:** energia del package CPU (core + uncore + iGPU) attribuita per quota di tempo; energia dell'intera scheda GPU discreta meno un idle che oggi è zero.

**Escluso:** DRAM (dominio EMI disponibile e non usato), altri processi CPU (rimossi solo per proporzione), altri processi GPU (inclusi nella board), dischi, display, perdite VRM/PSU, rete e cloud nel run locale, PSYS.

**Fattibilità «intero computer»:** non implementata. Servirebbe un riferimento di piattaforma (PSYS su Linux, wattmetro AC/DC su Windows) più i domini oggi scartati. Il perimetro attuale è «package CPU + scheda GPU», non «computer».

---

## 7. Test suite — quadro complessivo

- **577 node id = 574 passati + 3 saltati** (Appendice D rigenerata il 04-11; 482 in `tests/`, 95 alla radice; 48 file; docstring 577/577; 483 funzioni per `(percorso, classe, nome)`).
- Le 3 skip sono `tests/test_rapl.py` su Windows.
- **Tutti i test dei backend sono su hardware simulato**: `FakeEMI`, metadati sintetici, `FakeLib` PawnIO, sysfs finto, `pynvml`/`amdsmi` finti. È corretto che ci siano; non sono prova di accuratezza.
- L'unica prova su hardware reale sta fuori dalla suite: `emi_probe_50ms_10ms_20261023_analisi.md`, `four_way_20261023_120830_analisi.md`, `four_way_finestra_uguale_20261023_analisi.md`, `srum_emi_cross_20261023_analisi.md`, `pawnio_probe_20261028_analisi.md`, `pawnio_aba_20261028*`, `lhm_validation_v3*`.
- `tests/test_csv_schema_p5.py` (4) non asserisce il **totale** delle colonne: ho verificato eseguendo il modulo che `CSV_COLUMNS` è 174, `BLOCK_SUMMARY_COLUMNS` 36, `POINT_SUMMARY_COLUMNS` 19. Un cambio di schema che aggiungesse una colonna senza aggiornare il conteggio non farebbe fallire nulla.

**Test mancanti rispetto a ciò che il metodo promette:** stall del contatore PKG; reset all'interno di una finestra EMI con percorso `counter-invalid` completo; riporto RAPL su host reale e con `max_uj` assente; concorrenza sampler/calibrazione RAPL; idle GPU e sua provenienza; `gpu_process_energy_j` (un test che lo eserciti davvero evidenzierebbe il campo morto); multi-package con `CW_EMI_DEVICE`; accuratezza, ripetibilità e robustezza (non unit test: esperimenti).

---

## 8. Problemi trovati

**S1 — Numeri silenziosamente sbagliati**

1. **Nessun watchdog di stallo sul PKG EMI.** Solo PP1 ha il controllo sul timestamp (`energy_session.py:434-448`, applicato a `:501-506`). Per il PKG un registro fermo produce `Δ = 0 J`, accettato (`local_energy.py:1151-1153`, `j1 == j0` valido). Su un driver che smette di aggiornare, la riga dichiara zero energia invece di «lettura non valida». Il campo `ts_100ns` è già nel record e nella provenienza: manca solo il controllo.
2. **RAPL: reset indistinguibile dal riporto e stallo indistinguibile dallo zero.** Senza `max_uj` la lettura diventa `_Unreliable` (bene); con `max_uj` un reset viene contato come riporto e sovrastima di ~262 kJ. Un `energy_uj` congelato dà 0 J senza nota (`rapl_backend.py:190-207`).
3. **Clamp silenziosi sul percorso a campioni.** `package_energy_exact_between` applica `max(..., 0.0)` a `:1223` e `:1231`; `read_package_j` per `energy-file` restituisce `fv` se `fv < base` (`:623`). È il percorso usato da RAPL/energy-file e dal fallback EMI/PawnIO quando il buffer non copre la finestra. Contraddice localmente la regola «incrementi negativi conservati»: il valore firmato è conservato sul percorso ai bordi, non qui.
4. **RAPL senza lock fra sampler e calibrazione.** Con la sessione già avviata, `calibrate_idle` legge `energy_uj` mentre il sampler di sessione fa lo stesso (`energy_session.py:1421`, `:1027`); lo stato `last_uj/wraps` è condiviso e non protetto. Un riporto può essere perso o contato due volte.
5. **Errori del thread EMI non registrati.** `_emi_loop` cattura l'eccezione e mette `cum = None` (`:308-310`) senza chiamare `_record_read_error`; un guasto persistente dell'IOCTL diventa un buco nel buffer, non una causa scritta.

**S2 — Sovrastime o proxy dichiarati**

6. **Idle GPU mai calibrato.** `idle_gpu_power_w` non è assegnato in produzione; l'attribuzione GPU è l'intera scheda (`local_energy.py:889-901`). Dichiarato in campo e note, ma sperimentalmente è una sovrastima non quantificata.
7. **Nessuna arbitratura della scala assoluta.** EMI, PawnIO, LHM e SRUM leggono lo stesso registro: l'accordo a finestra uguale è coerenza di implementazione, non validazione. Manca un wattmetro.
8. **Quota CPU come proxy dell'energia** (`local_energy.py:672-729`): dichiarata `ESTIMATE`, ma non confrontata con un ground truth di energia per processo.

**S3 — Latenti o non raggiungibili nel runner v4**

9. **Attribuzione GPU per processo morta**: `_last_window_board_active_j` mai assegnato (`energy_session.py:1673`).
10. **Override baseline senza aggiornamento di provenienza**: con `baseline_pre_w` passato, `idle_proven` resta quello di sessione (`local_energy.py:370-379`). Nel runner v4 non è raggiungibile (la calibrazione precede sempre), ma un altro chiamante può ottenere `active_valid=False` pur avendo applicato una baseline.
11. **`read_power_w` RAPL non incrementa `wraps`** (`rapl_backend.py:247-261`): un riporto visto da questa funzione non entra nel cumulativo, che poi sottostima di un `max_energy_range_uj`. Oggi `read_power_w` è usata solo dai test, quindi è latente.
12. **Durata delle finestre idle non registrata nel CSV**: `CW_IDLE_WINDOW_S` può scendere sotto 30 s senza traccia nella riga.

---

## 9. Verifiche sperimentali necessarie (in ordine di priorità)

1. **Riferimento assoluto indipendente**: wattmetro AC/DC (o DC bench sulla linea CPU) contro EMI a finestra uguale, carico noto e stabile. Senza questo, la scala resta non arbitrata e nessuna riga può essere `validated`.
2. **Iniezione di guasto sul contatore**: sospensione del device / stop del driver durante una finestra; verificare che il PKG non produca zero silenzioso (richiede prima il watchdog del punto S1.1). Ripetere per RAPL con un sysfs finto e poi reale.
3. **Ripetibilità**: stesso carico, `n ≥ 30` richieste, CV per fase e per J/token, con la stessa baseline o con baseline ricalibrata — separare la varianza del contatore da quella della baseline.
4. **Host Linux reale**: riporto attraversato (run ≥ 2 h), reset simulato, `max_energy_range_uj` assente, sampler e calibrazione concorrenti, PSYS come confronto di perimetro (non da sommare).
5. **GPU reale NVIDIA e AMD**: contatore vs wattmetro, 0,5 s vs campionamento più fine, calibrazione idle a scheda ferma, selezione multi-device con `CW_GPU_INDEX`.
6. **Ground truth dell'attribuzione**: carico a un solo processo con tempo CPU noto, confronto fra `E_ollama` e l'energia di un carico sintetico equivalente; poi carico con iGPU attiva per misurare la sotto-attribuzione del proxy.
7. **Multi-package Windows**: host a due socket, verifica di `ambiguous_domain` e di `CW_EMI_DEVICE`.
8. **Correzione dei punti S1.3, S1.5, S3.9, S3.11** prima della campagna: sono interventi di codice, non esperimenti.

---

## 10. Matrice di classificazione

Classi: **A** implementato e verificato a livello software; **B** implementato ma non validato sperimentalmente; **C** parzialmente implementato; **D** non implementato. La classe riguarda la *funzione*, non l'accuratezza: la scala assoluta ha una riga sua.

| Componente | Classe | Base |
|---|---|---|
| Scoperta/selezione device EMI | A | SetupAPI + metadati, 26 test sintetici; esercitata su host reale |
| Lettura contatore EMI e finestra ai bordi | A | delta pWh, IOCTL diretta, 10+2 test; probe e four-way reali |
| Accuratezza assoluta EMI | B | accordo solo con lo stesso registro (SRUM/LHM/PawnIO), nessun wattmetro |
| Watchdog di stallo PKG | C | esiste solo per PP1 (`energy_session.py:434-448`) |
| Riporto/reset EMI | C | reset = invalidazione dichiarata; riporto non modellato (irrilevante a 64 bit) |
| Sonda e sicurezza PawnIO | A | HVCI, firma, hash, access_denied; 17+9+4 test |
| Contatore PawnIO e riporto 32 bit | A/B | logica software provata; hardware reale solo Intel, ramo AMD non esercitato |
| Scoperta e domini RAPL | B | solo sysfs finto; nessun host Linux |
| Contatore RAPL, riporto e reset | C | riporto implementato; reset/stallo/intervallo massimo non gestiti |
| Percorso RAPL nella sessione | C | funziona via campioni, ma con clamp silenziosi e senza lock |
| Contatore NVML | B | 16 test con `pynvml` finto, nessuna GPU |
| Integrale di potenza NVML | B | trapezi a 0,5 s, nessuna GPU |
| AMD SMI (energia e potenza) | B | 24 test con `amdsmi` finto, nessuna GPU AMD |
| Selezione device GPU | A/B | 13 test; nessun host multi-GPU |
| Attribuzione GPU whole-device | B | formula implementata; idle mai calibrato → board intera |
| Attribuzione GPU per processo | D | campo morto: `_last_window_board_active_j` mai assegnato |
| Calibrazione baseline CPU | A/B | 3×30 s, mediana, test; stabilità sperimentale solo su pochi run |
| Applicazione `P_pre` e `P_post` diagnostico | A | runner v4, test su ordine e formule |
| Budget `budget_base_w` | B | formula provvisoria P2.9, forma da chiudere sui dati |
| Attribuzione CPU → processo | B | proxy di tempo CPU dichiarato `ESTIMATE`, senza ground truth |
| Energia locale totale | B | composizione corretta, perimetro ristretto; DRAM e altri processi esclusi |
| End-to-end locale + rete + cloud | C | nel run locale rete/cloud sono 0 per confine; il ramo cloud vive altrove |
| Energia dell'intero computer | D | manca PSYS/wattmetro e i domini di piattaforma |

**Sintesi.** Il nucleo Windows è la parte realmente costruita e provata: EMI è **A** come percorso, **B** come metrologia, perché nessuna misura è ancora arbitrata da un riferimento esterno. PawnIO è solido lato software e parziale lato hardware. RAPL e GPU sono implementati contro documentazione e simulacri, ma non hanno mai visto il proprio hardware: sono **B/C**, non **A**. L'attribuzione per processo su GPU è **D**; l'attribuzione CPU è un proxy **B**; il computer intero è **D**. Prima del protocollo definitivo, i tre interventi che cambiano la natura del dato — watchdog PKG, clamp sul percorso a campioni, idle GPU — vanno chiusi, altrimenti alcune righe continueranno a dichiarare zero o attribuire l'intera scheda senza che il numero lo dica.
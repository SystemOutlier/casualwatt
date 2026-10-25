# Associazione telemetria-richieste-contatore EMI, 25/10/2026

Verifica di software correctness del legame fra tre sorgenti registrate nello
stesso run:

1. la telemetria di `monitor_ollama.py` (campioni a 0,5 s);
2. la tabella delle richieste dello stesso harness (finestre monotone);
3. il contatore EMI PKG letto da `emi_clock_probe.py` a 50 ms.

L'artefatto **non e' un risultato di protocollo**. La sonda non e' un canale di
misura, non sottrae baseline, non interpola il contatore e non entra in
`MEASURED_METHODS`. Le energie qui sotto sono lorde, sulla sotto-finestra
coperta dagli incrementi contenuti: servono a dire se la regola di
associazione produce finestre coerenti, non a stimare l'energia di una
richiesta.

## Comandi

I due processi sono stati lanciati dalla stessa shell, perche' lanciarli in due
chiamate separate ha prodotto un primo tentativo in cui la sonda (30 s) era
partita ~12 s prima dell'harness e finiva dentro la terza richiesta: la
finestra r003 aveva zero incrementi contenuti e 1227,6 ms scoperti. Quel run
e' stato scartato e non e' fra i file elencati in fondo.

```
python emi_clock_probe.py --seconds 30 --interval 0.05 \
    --output experiment_results/telemetry_association_20261025_probe.csv &
sleep 1
python monitor_ollama.py --interval 0.5 --requests 3 --request-interval 2.5 \
    --tail 2 --model llama3.2:1b \
    --prompt "Scrivi una frase breve sul mare." \
    --options-json '{"num_predict":24,"temperature":0}' --keep-alive 5m \
    --run-id telemetry_association_20261025 \
    --output experiment_results/telemetry_association_20261025_telemetry.csv \
    --requests-output experiment_results/telemetry_association_20261025_requests.csv \
    --meta-output experiment_results/telemetry_association_20261025_meta.json
wait
python emi_clock_probe.py --analyze \
    experiment_results/telemetry_association_20261025_probe.csv \
    --requests experiment_results/telemetry_association_20261025_requests.csv
```

## Ambiente

| Campo | Valore | Fonte |
|---|---|---|
| Piattaforma | Windows-11-10.0.26200-SP0 | meta `platform` |
| Python | 3.14.5 | meta `python_version` |
| psutil | 7.2.2 | meta `psutil_version` |
| CPU logiche | 20 | meta `logical_cpus` |
| Osservatore | pid 14024, escluso dal conteggio | meta `observer_pid` |
| Albero Ollama | 3 processi: `server_app`, `server`, `runner` | telemetria `ollama_server_roles` |
| Client Ollama | pid 33444, `ollama run huihui_ai/deepseek-r1-abliterated:32b-qwen-distill`, inattivo e **non** sommato | telemetria `ollama_client_*` |

Il client e' una sessione interattiva preesistente, non avviata da questo run:
compare in tutte le righe come client e resta fuori dalle somme del server,
come previsto dalla convenzione dell'harness.

## Configurazione delle richieste

| Campo | Valore |
|---|---|
| Modello richiesto / restituito | `llama3.2:1b` / `llama3.2:1b` in tutte e tre |
| Prompt | `Scrivi una frase breve sul mare.` (32 caratteri) |
| SHA-256 del prompt | `b55777e510bfa99c8520f2ef7546716adea22c145547e692ddcc18187452582b` |
| Opzioni | `{"num_predict":24,"temperature":0}` |
| `keep_alive` inviato | `5m` |
| Streaming | `true` (necessario per il primo token) |
| Intervallo fra richieste | 2,5 s |
| Campionamento telemetria | 0,5 s richiesti, 0,504 s mediani osservati, 0 deadline perse |
| Sonda EMI | 50 ms richiesti, 0,0500 s mediani (min 0,0490, max 0,0642) |

## Regola applicata

- campione di telemetria nella finestra se
  `t_send_mono_ns <= monotonic_ns < t_end_mono_ns`;
- incremento EMI `[t_i, t_{i+1})` nella finestra se `t_send <= t_i` e
  `t_{i+1} <= t_end`; `t_i` e' il punto medio fra `mono_before_ns` e
  `mono_after_ns` della lettura;
- incrementi che attraversano un bordo: esclusi e contati;
- incrementi negativi: conservati e contati (nessuno in questo run).

## Risultati

| Richiesta | Stato | Finestra s | TTFT s | Token prompt | Token eval | `done_reason` | Campioni telem. | Gap max s | Incrementi EMI | Span coperto s | Energia lorda J | Potenza media W | Straddling | Scoperto ai bordi ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r001 | ok | 1,579876 | 0,094314 | 33 | 24 | length | 3 | 0,506860 | 30 | 1,500 | 42,012 | 28,00 | 2 | 79,6 |
| r002 | ok | 1,292300 | 0,088471 | 33 | 24 | length | 2 | 0,506878 | 24 | 1,200 | 38,210 | 31,84 | 2 | 92,3 |
| r003 | ok | 1,405231 | 0,146006 | 33 | 24 | length | 3 | 0,504056 | 27 | 1,350 | 38,763 | 28,72 | 2 | 55,7 |

Letture:

- i token riportati dal server sono coerenti fra le tre richieste (33 di prompt,
  24 di eval = `num_predict`), con `done_reason = length`: la finestra contiene
  esattamente la generazione richiesta;
- il primo token arriva in 0,088-0,146 s; il server dichiara
  `load_duration` 0,010-0,014 s, `prompt_eval_duration` 0,054-0,081 s ed
  `eval_duration` 1,20-1,44 s: i pesi erano gia' caricati e la finestra e'
  dominata dal decode;
- le tre risposte sono identiche (`response_sha256` uguale, 73 caratteri) con
  `temperature: 0`: la finestra non e' influenzata da una lunghezza diversa;
- il campione di telemetria a 0,5 s da' 2-3 campioni per finestra e un gap
  massimo di ~0,50 s, cioe' circa un terzo della finestra: la telemetria
  descrive lo stato dei processi, **non** misura l'energia. Per l'energia
  servono gli incrementi del contatore, letti a 50 ms;
- ogni finestra ha 2 incrementi al bordo esclusi; l'energia indicata per gli
  straddling e' quella dell'incremento intero (2,334-2,746 J), non la sola
  parte che cade nel bordo. Il tempo scoperto ai bordi e' 55,7-92,3 ms, pari a
  1-2 intervalli di sonda;
- l'energia lorda non e' confrontabile con `package_energy_j` di produzione:
  manca la baseline, la cadenza e' diversa e il percorso e' la sonda, non
  `energy_session`.

## Offset fra i due orologi

| Traccia | Coppie | Offset mediano `mono - ts/1e7` | Drift |
|---|---|---|---|
| Questa (25/10, 50 ms) | 600 | **16,571370 s** | 0,451 ms |
| `four_way_20261023_145041.csv` (23/10, 1 s) | 112 | **14,391844 s** | 17,435 ms |

La differenza fra le due sessioni e' 2,180 s. L'offset **non e' una costante
dell'impianto**: va rimisurato su ogni traccia con letture accoppiate e
dichiarato, come fa la sonda. Un valore assunto (per esempio zero, oppure
quello di ieri) sposterebbe la finestra di oltre due secondi, cioe' piu' di
una richiesta intera.

L'offset `utc_minus_mono_ms` registrato dall'harness e' un'altra grandezza:
mediana 1792096983839,61 ms, drift 1,191 ms su 23 campioni. Serve a rilevare
salti dell'orologio a muro, non a collegare EMI e richieste.

## Verdetto

- **Correttezza del software**: la regola produce per ogni richiesta una
  finestra con incrementi contenuti contigui, bordi contati e copertura
  dichiarata; nessuna interpolazione. Il run scartato mostra che la sonda
  accorcia la copertura invece di inventarla (0 incrementi, 1227,6 ms
  scoperti).
- **Validita' sperimentale**: token, TTFT, `done_reason` e finestre sono
  coerenti fra le tre richieste; la configurazione e' quella scritta nel meta,
  non ricostruita.
- **Accuratezza fisica**: non affrontata qui. Senza baseline e senza un
  riferimento indipendente, l'energia lorda della sonda non e' un risultato e
  non va citata come tale.

## Limiti

- una sola sessione, un solo modello, tre richieste;
- la sonda e l'harness girano insieme e si contendono la CPU: il costo
  dell'osservatore non e' misurato in questo artefatto (e' il task A-B-A
  separato);
- 50 ms di sonda non bastano a eliminare gli incrementi al bordo: 2 per
  finestra, esclusi e contati;
- la produzione usa `stream=false` (`benchmark_unified.py:135`): qui la finestra
  e' end-to-end con streaming, quindi il confronto con la produzione riguarda
  il metodo di associazione, non la durata;
- l'incremento al bordo e' escluso per intero, non ripartito: la scelta e'
  dichiarata e non produce stime.

## File

- `emi_clock_probe.py` — sonda e analizzatore (radice del repo).
- `monitor_ollama.py` — harness di telemetria e richieste (radice del repo).
- `telemetry_association_20261025_probe.csv` — 600 letture EMI a 50 ms.
- `telemetry_association_20261025_telemetry.csv` — 23 campioni di telemetria.
- `telemetry_association_20261025_requests.csv` — 3 finestre di richiesta.
- `telemetry_association_20261025_meta.json` — configurazione, orologi,
  regola di associazione e conteggi.

# Confronto fra le due campagne del gate P4.4 (2026-11-08)

Analisi descrittiva datata, scritta dopo l'esecuzione della seconda campagna.
Non modifica alcun criterio: F.12 resta quello congelato e i verdetti delle due
campagne sono entrambi **fail**, riportati come deciso dalla Tredicesima emenda
(`experiment_results/protocollo_v4_20261024.md`, punto 6: «Entrambe le campagne
si riportano qualunque sia l'esito»). Nessun artefatto delle due campagne è
stato sovrascritto.

## Le due campagne in una tabella

| grandezza | prima (2026-11-07) | seconda (2026-11-08) |
|---|---|---|
| verdetto F.12 | fail | fail |
| `bias_w` | 0,479571 W | 0,125171 W |
| soglia `mediana_c(budget_base_w,c)` | 0,262324 W | 0,117995 W |
| scarto relativo oltre la soglia | +82,8% | +6,1% |
| controlli utilizzabili / quorum | 4/6, quorum 4 | 6/6, quorum 4 |
| `background_load` prima/dopo dei controlli | 5 su 6 con macchina carica | 6 su 6 False/False |
| precondizione di quiete | assente | attiva: 12 blocchi, attesa 9 s ciascuno, 3 letture |
| finestra dei controlli | `exact-counter` 6/6 | `exact-counter` 6/6 |
| `git_head` | `c326d4646` | `39a34a9ab` |
| `runner_sha256` | `a8a35078…` | `99846365…` |

Fonti: `experiment_results/p44_gate_20261107/analysis.json` e
`experiment_results/p44_gate_20261108/analysis.json` (entrambi congelati);
flag della prima campagna verificati sulle note di
`cwEnergyModular/results/casualwatt_run_metadata.csv` e registrati nella
Tredicesima emenda, punto 5 (il CSV è ignorato da git).

## Cosa è cambiato e cosa no

1. **Il bias è sceso del 73,9%** (0,479571 → 0,125171 W): la preparazione della
   macchina e la precondizione di quiete hanno tolto la componente rumorosa.
   La diagnosi della prima campagna («il problema è la macchina durante il
   run») è confermata dai dati, non solo dai flag.
2. **Anche la soglia è scesa del 55,0%** (0,262324 → 0,117995 W): una macchina
   quieta ha `pre_range_w` piccoli (0,033–0,695 W nella seconda campagna),
   quindi `budget_base_w` piccoli. Il criterio si è stretto insieme al
   miglioramento: il fail della seconda campagna è marginale (0,0072 W oltre
   la soglia) ma resta un fail, e la soglia non si sposta.
3. **Il residuo non è spiegabile come rumore di fondo.** L'intervallo al 95%
   della media fra blocchi è `[−0,113; +0,363]` W (n=6, t di Student, dal
   report della seconda campagna) e include lo zero: con sei blocchi la media
   non è statisticamente distinguibile da zero. Il criterio F.12 però non è
   un test di significatività: confronta il bias aggregato con la mediana dei
   budget, e quel confronto cede.

## Diagnostica della seconda campagna (non criterio)

- **ctrl-1 domina l'aggregato**: `E_net = 1,657777 J` su una somma di
  2,201627 J = **75,3%** del numeratore del bias. È il primo controllo dopo
  il primo carico, con `cooldown_timeout='true'` e `P_pre_ref` propagata
  4,529809 W contro una baseline propria di 3,710856 W
  (`p44_gate_20261108/p44_gate_report.md`, sezione cooldown). La serie di
  potenza grezza (`control_power_series.json`) mostra nella sua finestra
  3,45–4,51 W con il primo campione a `cpu_percent=8,3%`, contro 3,38–4,00 W
  e 0,4–1,5% degli altri cinque: è il transitorio termico del primo carico
  che non ha finito di rientrare.
- **Ipotesi diagnostica, non esclusione**: togliendo ctrl-1 dal calcolo (cosa
  che il criterio non fa e questo documento non propone) il bias sarebbe
  0,037104 W contro una mediana di 0,033178 W: **ancora fail**, di poco. Il
  fail quindi non è del solo outlier: sui controlli quieti il budget è
  0,024–0,033 W e le derive residue di 0,025–0,092 W lo superano. Questo è
  il punto della «scala dei tempi» della decisione 6: il budget deriva da
  finestre di 30 s, la finestra di controllo dura 2,93 s.
- I `block_pass=False` di ctrl-3, ctrl-5 e ctrl-6 sono su budget piccolissimi
  (0,070–0,097 J): il criterio per blocco è riportato e, come dichiara F.12,
  non decide lo status del gate.

## Stato delle decisioni della Tredicesima emenda

- Decisioni 1–5 e 7: eseguite e registrate (criterio invariato, precondizione
  attiva, macchina preparata, entrambe le campagne riportate, report
  arricchito).
- **Decisione 6: condizione verificata.** «Solo se anche la seconda campagna
  fallisce in ambiente quieto: aumenta le coppie (con 12 il quorum sale a 8)
  e rivedi la scala dei tempi». La seconda campagna è fallita in ambiente
  quieto verificato (12 blocchi su 12 con `background_load=False/False`).
  La decisione è registrata e **non ancora adottata**: richiede una nuova
  emenda (Quattordicesima), un nuovo piano e una terza campagna. Con 12
  coppie il quorum è `ceil(2/3 · 12) = 8` (`control_gate.py::quorum_for`,
  già generico sul numero di coppie).

## Tracciabilità

- Artefatti della seconda campagna: `analysis.json`,
  `gate_result_frozen.json` (identici per contenuto), `blocks_controllo.json`,
  `control_power_series.json`, `p44_gate_report.md`, `plan.json` in
  `experiment_results/p44_gate_20261108/`; CSV in
  `cwEnergyModular/results/p44_gate_20261108/` (ignorati da git).
- Piano della seconda campagna committato con `39a34a9ab`; Tredicesima emenda
  con `b937605a4`. Il `git_head` registrato negli artefatti è `39a34a9ab`,
  coerente con il piano.
- Aritmetica riverificata il 2026-11-08: somma `E_net` = 2,201627 J, somma
  `dt_W` = 17,588918 s, rapporto 0,125171 W; mediana dei sei `budget_base_w`
  = 0,117995 W; quota di ctrl-1 75,3%; ipotesi senza ctrl-1 0,037104 W contro
  mediana 0,033178 W.
"""Definizioni del benchmark e delle metriche. **Dataset non ancora generato.**

Perche' esiste. Oggi il riferimento e' fatto di 12 query, 8 mappature su 12
marcate `review` e una sola query provata end-to-end: non basta per un claim di
accuratezza, ne' per un confronto con un modello di frontiera. Questo modulo
fissa il contratto *prima* di generare i dati e prima di vedere un risultato,
cosi' le soglie non si spostano dopo (regola del progetto: le soglie si congelano
prima dei dati).

Come deve essere fatto il dataset (da implementare):
  - query generate **dalla rete** con template e seed fisso, cosi' la mappatura
    query -> (etichetta, evidenza, target) e' non ambigua per costruzione e non
    va confermata a mano una per una;
  - 150-200 query, 30-50 per ramo misurabile, piu' il caso di riferimento
    storico (CP1, 0.212) come prima riga per continuita' con le misure gia' fatte;
  - una **variante con CPT perturbate** (seed fisso, righe rinormalizzate): la
    rete Insurance e' l'esempio del libro e un modello di frontiera puo'
    ricordarne le CPT, quindi senza perturbazione il tool potrebbe essere
    superfluo e il confronto misurerebbe la memoria, non l'inferenza;
  - split sviluppo / held-out: si sceglie la variante sullo sviluppo e si
    riporta sull'held-out, altrimenti il vincitore su sette varianti guardate
    sullo stesso insieme e' gonfiato.

Metriche per ramo (il numero non e' la stessa cosa in tutti i rami):
  - cond_prob  -> P(target | evidenza), oracolo **indipendente**: posterior di
                  pyAgrum calcolato direttamente, non passant per cau_inference;
  - inter      -> P(target | do(x)), oracolo indipendente: doIntervention +
                  posterior, non il ramo della pipeline;
  - coherence  -> decisione a soglia SOGLIA_COHERENCE **e** probabilita': il
                  ramo risponde "compatible / NOT strongly compatible", quindi
                  si valuta la decisione, non solo il numero;
  - counterfactual -> intervallo [lower, upper]: si valutano **due** estremi.
                  L'oracolo qui NON e' indipendente: e' la stessa formula di
                  Tian-Pearl implementata in cobound, quindi questa parte del
                  benchmark misura l'instradamento, non la formula. La formula
                  e' stata verificata a parte (verifica_py.py, 500 modelli);
  - influence  -> **fuori dal benchmark quantitativo**: il ramo non calcola
                  nulla, restituisce un prompt sugli archi del grafo
                  (consegna/tools_corretto.py:392-411). Va trattato come caso
                  qualitativo con criteri dichiarati, non come accuratezza.

Accettazione. TOLL e' assoluta e si applica al numero **stampato** dal ramo
(3-4 decimali), non al valore pieno: e' la stessa convenzione di
verifica_ground_truth.py, e va dichiarata cosi' perche' "12/12 a 5e-4" non e'
un'accuratezza al 99% su valori non arrotondati.

Energia. Il numero da riportare e' **J per risposta corretta**, non J per query:
una variante che sbaglia meta' delle risposte non e' economica, e' rotta. La
misura deve essere quella del protocollo v4 (baseline calibrata, n. richieste
fisso, caldo/freddo separati); i run MUDILAB del 29-31/10 dichiarano
`idle_provenance=uncalibrated` e non sono a quel livello.
"""

# Tolleranza assoluta sul numero stampato dal ramo. Congelata: non si sposta
# dopo aver visto i risultati.
TOLL = 5e-4

# Soglia del ramo coherence, quella presente nel codice della relatrice
# (consegna/tools_corretto.py:376). Non e' una scelta del benchmark.
SOGLIA_COHERENCE = 0.60

# Tipo di query -> etichetta che il classificatore deve emettere.
ETICHETTA = {
    "cond_prob": "backward_reasoning",
    "inter": "intervention",
    "coherence": "coherence",
    "counterfactual": "counterfactual",
}

RAMI_MISURABILI = tuple(ETICHETTA)
RAMO_QUALITATIVO = "influence"

# Obiettivi di generazione, da congelare con il dataset.
N_PER_RAMO = 40
SEED = 7

# Colonne minime del CSV che l'harness legge.
COLONNE_HARNESS = ("task_id", "query")

# Colonne del ground truth, oltre a quelle dell'harness.
COLONNE_GT = (
    "ramo", "etichetta_attesa", "evidence_json", "intervention_json",
    "target_variable", "target_state", "expected_probability",
    "expected_lower", "expected_upper", "expected_decision",
    "oracole", "rete", "split",
)
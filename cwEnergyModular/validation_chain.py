# -*- coding: utf-8 -*-
"""P4.9 — l'esito della catena di validazione e' un token, non un aggettivo.

"Validata" e' una parola sola: si assegna solo se **tutti** gli anelli passano
(`experiment_results/protocollo_v4_20261024.md`, §P4.9). Fino a oggi
`chain_status` esisteva soltanto come nome di colonna in
`POINT_SUMMARY_COLUMNS` (`casualwatt_csv_export.py:231`): nessun codice la
scriveva, quindi nessuna riga poteva portare `validated` e la regola di
`AGENTS.md` era inapplicabile. Questo modulo e' il produttore.

Le soglie sono quelle congelate e non se ne introduce nessuna: ogni costante
qui sotto cita il punto che la congela. L'ordine degli anelli e' quello della
tabella di P4.9: l'esito e' l'etichetta del **primo** anello che cede, perche'
la catena e' forte quanto il suo anello piu' debole e "quale ha ceduto" e'
l'unica informazione utile. Un anello rotto non si compensa con gli altri:
nessun confronto fra due letture dello stesso registro sostituisce l'anello 4,
e nessun test di sottrazione sostituisce la conferma su geometrie mai entrate
nel fit.

**Anello 1 (token e terminazione, pilota P2.9).** Non ha un'etichetta di
`chain_status`: se il pilota non passa non esiste campagna, quindi non esiste
una riga a cui assegnare uno stato -- il protocollo scrive "campagna non
eseguibile: si corregge il pilota, non i dati". Il modulo non prende l'anello
1 in ingresso e non inventa un token per lui.

**Granularita'.** L'esito e' della CAMPAGNA: gli anelli 5 e 6 parlano del fit
e dei punti di conferma, non del singolo punto. Il `point_summary` riporta
percio' lo stesso token su tutte le righe della campagna; un valore per punto
sarebbe una seconda tassonomia dello stesso oggetto, che il progetto ha gia'
deciso di non avere (`revisione_esterna_20261026_quinto_turno_valutazione.md`
§2, punto 2).

**Ingressi.** Le righe arrivano dall'analisi (P6) e possono essere sia dict
del runner sia righe lette dal CSV: i booleani si leggono come
"true"/"True"/1, i numeri come stringhe. Un campo necessario ma **vuoto**
(vuoto = "analisi non ancora eseguita", per il contratto dello schema) non
produce uno stato: solleva `ValueError`, perche' un `chain_status` calcolato
su un anello che nessuno ha valutato sarebbe una dichiarazione inventata.
"""
from fractions import Fraction
from math import ceil
from statistics import median
from typing import Mapping, Sequence

#: Riferimento P1.6, criterio dell'anello 3: un blocco e' stabile se
#: `r_A <= 10%`; servono almeno 2 blocchi stabili su 3 per punto.
BASELINE_R_A_MAX = 0.10
BASELINE_BLOCKS_MIN = 2

#: Riferimento P4.4 requisito 7 / F.12: filtro di stabilita' del controllo.
#: Entrambe le disuguaglianze sono non strette (1,0 W incluso).
CONTROL_PRE_RANGE_MAX_W = 1.0
CONTROL_DP_MAX_W = 1.0

#: Riferimento F.12: quorum dei controlli utilizzabili,
#: `>= ceil(2/3 * n_coppie)`. Con sei coppie e' 4, ma la frazione e' la regola.
CONTROL_QUORUM = Fraction(2, 3)

#: Riferimento P3.9 / anello 5: lack-of-fit NON significativo se
#: `p_lof_perm >= 0,05`.
LOF_P_MIN = 0.05

#: Riferimento P3.10 / anello 6: entrambi i punti di conferma con
#: `err_rel <= 10%` e dentro l'intervallo; servono due punti, non uno.
ERR_REL_MAX = 0.10
CONFIRMATION_POINTS = 2

VALIDATED = "validated"
COUNTER_INVALID = "counter_invalid"
BASELINE_UNSTABLE = "baseline_unstable"
BIAS_DECLARED = "bias_declared"
MODEL_INADEQUATE = "model_inadequate"
VALIDATION_FAILED = "validation_failed"
REDUCED_DESIGN = "reduced_design"

#: Vocabolario chiuso delle etichette (P4.9, piu' i due token che il protocollo
#: aggiunge: `pred_nonpositive` resta un flag della previsione e non un
#: secondo esito). Nessun'altra stringa esce da questo modulo.
STATUS_LABELS = (VALIDATED, COUNTER_INVALID, BASELINE_UNSTABLE, BIAS_DECLARED,
                 MODEL_INADEQUATE, VALIDATION_FAILED, REDUCED_DESIGN)


def _flag(value) -> bool:
    """Booleano da un campo che puo' arrivare dal runner o dal CSV."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "si")


def _num(row: Mapping, key: str, where: str) -> float:
    """Numero obbligatorio: un campo vuoto non e' uno zero."""
    value = row.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(
            f"{where}: campo {key!r} vuoto (analisi non ancora eseguita). "
            "Lo stato della catena non si assegna su un anello non valutato")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{where}: campo {key!r} non numerico ({value!r})")


def counter_invalid(blocks: Sequence[Mapping]) -> bool:
    """Anello 2 (P4.9): un blocco con delta negativo, reset o lettura non finita.

    Il blocco che ha ceduto per guasto tecnico e stato **sostituito** non
    invalida la campagna: Emenda 8 (P1.6) esiste proprio perche' un guasto
    del contatore non diventi un buco nel disegno. La copertura di quel
    blocco e' nel sostituto, che si valuta per conto suo: se anche il
    sostituto cede, il suo `invalid_reason` e' ancora li' e l'anello fallisce.
    """
    sostituiti = {str(b.get("replaced_block_id") or "").strip()
                  for b in blocks}
    sostituiti.discard("")
    for block in blocks:
        block_id = str(block.get("block_id") or "").strip()
        if block_id and block_id in sostituiti:
            continue
        if _flag(block.get("negative_increment")):
            return True
        if str(block.get("invalid_reason") or "").strip():
            return True
    return False


def baseline_unstable(blocks: Sequence[Mapping]) -> bool:
    """Anello 3 (P1.6): `r_A <= 10%` in almeno 2 blocchi su 3 per punto.

    Due blocchi marcati su tre invalidano la campagna, non solo il punto; con
    la regola "2 stabili su 3" un punto con un solo blocco stabile non passa,
    anche se i blocchi disponibili fossero meno di tre. `r_A` e' un campo di
    analisi: se e' vuoto l'anello non e' valutato e il modulo si ferma invece
    di contarlo come stabile.
    """
    per_punto = {}
    for block in blocks:
        point_id = str(block.get("point_id") or "").strip()
        if not point_id:
            raise ValueError(
                f"blocco {block.get('block_id')!r} senza point_id: i blocchi "
                "non si raggruppano per punto")
        per_punto.setdefault(point_id, []).append(
            _num(block, "r_A", f"blocco {block.get('block_id')!r}"))
    for point_id, valori in per_punto.items():
        stabili = sum(1 for r_a in valori if r_a <= BASELINE_R_A_MAX)
        if stabili < BASELINE_BLOCKS_MIN:
            return True
    return False


def bias_declared(controls: Sequence[Mapping], n_pairs: int) -> bool:
    """Anello 4 (P4.4/P4.5, F.12): il test load-versus-control dentro il budget.

    Tre condizioni, tutte congelate:

    * un controllo e' **utilizzabile** se `pre_range_w <= 1,0 W` e
      `|dP| <= 1,0 W`; sotto il quorum `ceil(2/3 * n_coppie)` il gate non e'
      eseguibile e il bias si dichiara;
    * ogni controllo utilizzabile deve stare nel proprio `budget_base_j`;
    * `bias_w = sum(E_net,c) / sum(dt_W,c)` deve stare dentro
      `mediana_c(budget_base_w,c)`.

    Non c'e' un caso "controllo scartato": un controllo instabile e' escluso
    dal calcolo del bias ed e' registrato dal chiamante con
    `control_unstable`, che e' un flag di blocco e non un esito di catena.
    """
    if n_pairs <= 0:
        raise ValueError("n_pairs deve essere positivo: il quorum dipende da lui")
    usabili = []
    for control in controls:
        pre_range = _num(control, "pre_range_w", "controllo")
        drift = _num(control, "dP", "controllo")
        if pre_range <= CONTROL_PRE_RANGE_MAX_W and abs(drift) <= CONTROL_DP_MAX_W:
            usabili.append(control)
    if len(usabili) < ceil(CONTROL_QUORUM * n_pairs):
        return True
    somma_j = 0.0
    somma_dt = 0.0
    budgets_w = []
    for control in usabili:
        e_net = _num(control, "e_net_j", "controllo")
        dt_w = _num(control, "dt_w_s", "controllo")
        if dt_w <= 0.0:
            return True
        if abs(e_net) > _num(control, "budget_base_j", "controllo"):
            return True
        somma_j += e_net
        somma_dt += dt_w
        budgets_w.append(_num(control, "budget_base_w", "controllo"))
    bias_w = somma_j / somma_dt
    return abs(bias_w) > median(budgets_w)


def model_inadequate(p_lof_perm: float) -> bool:
    """Anello 5 (P3.9): lack-of-fit significativo, `p_lof_perm < 0,05`.

    Il `p_lof_asint` non decide: e' indicativo e si riporta accanto.
    """
    p_lof = _num({"p_lof_perm": p_lof_perm}, "p_lof_perm", "anello 5")
    return p_lof < LOF_P_MIN


def validation_failed(points: Sequence[Mapping]) -> bool:
    """Anello 6 (P3.10): entrambi i punti di conferma dentro 10% e nell'intervallo.

    Un `E_pred <= 0` e' fallimento (`pred_nonpositive`), non un punto da
    rifittare: il modello non si aggiusta sui dati di conferma. Servono due
    punti: con uno solo il caso non e' valutato, e un denominatore ridotto in
    silenzio renderebbe piu' facile passare.
    """
    if len(points) != CONFIRMATION_POINTS:
        return True
    for point in points:
        if _flag(point.get("pred_nonpositive")):
            return True
        if _num(point, "e_pred_j", "punto di conferma") <= 0.0:
            return True
        if _num(point, "err_rel", "punto di conferma") > ERR_REL_MAX:
            return True
        if not _flag(point.get("inside_interval")):
            return True
    return False


def chain_status(*, blocks: Sequence[Mapping],
                 controls: Sequence[Mapping], n_pairs: int,
                 p_lof_perm: float,
                 confirmation_points: Sequence[Mapping],
                 reduced_design: bool = False) -> str:
    """Il token di P4.9 a partire dai dati della campagna.

    L'ordine e' quello della tabella: il primo anello che cede da' il nome.
    `reduced_design` (un punto escluso dal fit primario per `r_B > 20%`) si
    aggiunge alle etichette ma non copre un anello rotto: un disegno ridotto
    con un anello rotto resta l'anello rotto. `validated` richiede quindi sei
    anelli puliti **e** il disegno intero.
    """
    if counter_invalid(blocks):
        return COUNTER_INVALID
    if baseline_unstable(blocks):
        return BASELINE_UNSTABLE
    if bias_declared(controls, n_pairs):
        return BIAS_DECLARED
    if model_inadequate(p_lof_perm):
        return MODEL_INADEQUATE
    if validation_failed(confirmation_points):
        return VALIDATION_FAILED
    if reduced_design:
        return REDUCED_DESIGN
    return VALIDATED

# -*- coding: utf-8 -*-
"""Simulazione Monte Carlo del protocollo v4 -- requisito P6.4.

Perche' esiste questo file
--------------------------
`experiment_results/protocollo_v4_20261024.md:2421-2469` (P6.4) adotta questa
simulazione come **requisito vincolante** il 2026-10-24, non piu' come proposta, e
le congela attorno cinque decisioni che oggi non hanno dati. Il protocollo la
colloca **dopo** la chiusura di P5 (2026-10-26, chiusa) e **prima** della
pubblicazione degli intervalli della campagna: non e' un prerequisito
dell'esecuzione, sono i numeri pubblicati che la aspettano.

I cinque punti, e dove finiscono in questo file:

1. la **concentrazione dei pesi** `w_b = 1/budget_fit_b^2` al variare del rapporto
   `rho = u_base/u_within` (punto 1 del requisito);
2. la **potenza e la circolarita' del gate di P4.5**, cioe' la probabilita' che
   dichiari `bias_declared` su una macchina corretta solo perche' il filtro
   scarta troppi controlli, e che passi su una macchina che bias ce l'ha
   (punto 2);
3. la **copertura nominale del fattore 2** di P3.10, di cui oggi nessuno conosce
   il valore reale (punto 3);
4. la **forma di combinazione** di `budget_base_w`, quadratura contro somma
   aritmetica, rinviata in P1.7, con il suo effetto su pesi, bootstrap e gate
   (punto 4);
5. la **copertura reale degli intervalli bootstrap** di P4.8 -- parametrico e
   predittivo, con e senza la correzione di leva `1/sqrt(1 - h_b)` -- e la
   coerenza della soglia operativa del 10% sullo scarto fra i due (punto 5).

La superficie nota, i coefficienti scelti entro l'ordine di grandezza atteso e il
rumore campionato dalle distribuzioni di v3 sono esattamente la specifica del
requisito (`:2437-2441`), non un'interpretazione.

Cosa verifica
-------------
Cinque verifiche autoportanti, ciascuna con un numero **gia' pubblicato** che
deve rigenerarsi. Le tre ancore di disegno non sono ricalcolate qui: sono
prodotte dal codice dei tre probe tracciati che le hanno pubblicate
(`condizionamento_disegno_probe.py`, `inviluppo_e_budget_pred_probe.py`,
`semi_range_concentrazione_pesi_probe.py`), caricati per percorso. Se un probe
cambia, questo file cambia i suoi numeri: un'ancora duplicata e' un'ancora che
invecchia in silenzio.

1. **Concentrazione a `rho = 0`**: quota media 0,373 e p95 0,816 della tabella
   sez. 3.2, ed ESS medio 7,30 su 33 blocchi, rigenerati dalle funzioni del probe.
2. **Leve del disegno**: `h_max = 0,2852` sui tre blocchi (512,256), media
   `0,121212 = 4/33`, fattore `1/sqrt(1 - h_max) = 1,1828` (protocollo:2104,
   :2114, :3213-3215), piu' l'identita' di traccia `sum h_b = p = 4` sia per le
   leve OLS sia per quelle pesate di F.14.
3. **I quattro margini pubblicati** `1,33 / 64,0 / 21,24 / 107,7` e la fascia A
   di (12,32) con `thin_support` per margine sotto 2 token (P4.7).
4. **Il gate guidato dalla produzione**: `validation_chain.bias_declared` deve
   rispondere False a sei controlli tutti usabili, dentro il budget, con bias
   nullo; True sotto il quorum di `ceil(2/3 * 6) = 4`; True con un `E_net` fuori
   dal proprio `budget_base_j`. Verifica che l'harness chiama l'anello 4 vero,
   non una sua riscrittura.
5. **Il bootstrap su un modello esatto**: azzerato il rumore, il fit WLS deve
   restituire i coefficienti generativi e il ricampionamento stratificato dei
   residuali deve produrre intervalli che li contengono. Se questa cade, la
   procedura di F.14 e' implementata male e nessun numero dei punti 3 e 5 e'
   leggibile.

Cosa NON dimostra
------------------
* **La scala assoluta.** Vincolo di metodo del requisito, testuale: "la
  simulazione **non** puo' validare la scala assoluta, perche' genera essa stessa
  l'energia" (`:2466-2468`). Qui si controlla la procedura statistica, non la
  misura; e' la dichiarazione da portare in tesi, non una nota a pie' pagina.
* **I coefficienti della superficie.** `E0, a, b, c` non sono congelati da
  nessuna parte del protocollo, e nemmeno la loro forma (il protocollo F.8 fissa
  la struttura, non i valori). Sono assunti qui e nominati come assunti; i
  verdetti dei punti 1, 3, 4 e 5 si leggono come funzioni di `rho`, non come
  numeri secchi, proprio per questo.
* **`rho` misurato.** Il protocollo lo dice due volte: "finche' `rho` non e'
  misurato resta una funzione, non una tabella" (`:2446`) e "`u_within,b` ... e'
  il denominatore del primo `rho` misurato -- senza di esso P6.4 resta una
  funzione non ancorata" (`:2390-2392`). `u_within` non esce da qui: esce dal
  pilota P6.2/P2.9. Questa simulazione copre la griglia `rho` e dice cosa
  succede lungo di essa.
* **Le distribuzioni di idle e deriva come misure v4.** Sono i valori di v3
  post-fix (`lhm_validation_v3_postfix_20261023_analisi.md:50,58`: gli otto
  `P_base` per run e `sd(P_base) = 1,29 W`), che e' l'unico dato di baseline
  esistente, e il protocollo lo usa come rischio ancorato (`:2400-2403`). Una
  v4 con `keep_alive=-1` e tre finestre da 30 s puo' dare una dispersione
  diversa; il piloto la misurera'.
* **Nessun numero di campagna.** Non c'e' Ollama, non c'e' contatore EMI, non
  c'e' alcun run: e' calcolo numpy su dati sintetici generati da questo file.
"""

import importlib.util
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.join(HERE, "cwEnergyModular")

# ---------------------------------------------------------------------------
# Caricamento della produzione e dei tre probe tracciati.
#
# Il gate (verifica 4 e punto 2) NON viene riscritto: si importa l'anello 4
# vero. La baseline di blocco (budget_base_w, pre_range_w, dP) e la media delle
# durate (F.11) pure. Se uno di questi import fallisce l'harness si ferma e lo
# dice: una reimplementazione locale divergerebbe in silenzio dal codice che la
# campagna usera' davvero, che e' esattamente il difetto che P6.4 esiste per
# evitare.
# ---------------------------------------------------------------------------


def _carica_produzione():
    if MODULE_DIR not in sys.path:
        sys.path.insert(0, MODULE_DIR)
    import benchmark_v4                      # noqa: F401  (block_baseline, budget_base_j)
    import validation_chain                  # noqa: F401  (bias_declared e le soglie)
    return benchmark_v4, validation_chain


def _carica_probe(nome, file):
    percorso = os.path.join(HERE, file)
    specifica = importlib.util.spec_from_file_location(nome, percorso)
    modulo = importlib.util.module_from_spec(specifica)
    sys.modules[nome] = modulo
    specifica.loader.exec_module(modulo)
    return modulo


try:
    V4, CHAIN = _carica_produzione()
except Exception as errore:                                # pragma: no cover
    print("ERRORE: impossibile importare il codice di produzione:")
    print("  benchmark_v4 / validation_chain da %s" % MODULE_DIR)
    print("  %s: %s" % (type(errore).__name__, errore))
    print("L'harness non reimplementa il gate ne' la baseline di blocco: si ferma.")
    sys.exit(2)

COND = _carica_probe("_condizionamento_disegno_probe", "condizionamento_disegno_probe.py")
INVIL = _carica_probe("_inviluppo_e_budget_pred_probe", "inviluppo_e_budget_pred_probe.py")
SRANGE = _carica_probe("_semi_range_concentrazione_pesi_probe",
                       "semi_range_concentrazione_pesi_probe.py")

# ---------------------------------------------------------------------------
# Disegno -- P3.5, P3.10, P4.4. Ogni costante porta la riga del protocollo.
# ---------------------------------------------------------------------------

PUNTI_FIT = COND.PUNTI                       # 33 blocchi su 10 punti (P3.5:998-1012)
N_FIT = len(PUNTI_FIT)
M = 3                                         # richieste per blocco (P1.5, F.7:1631)
PUNTI_CONFERMA = ((12, 32), (256, 192))       # mai entrati nel fit (P3.5:1005-1009)
N_CONFERMA_PER_PUNTO = 3
N_COPPIE_GATE = 6                             # 12 blocchi di controllo (P4.4:1452, P4.5:1518)
QUORUM = math.ceil(CHAIN.CONTROL_QUORUM * N_COPPIE_GATE)   # = 4, P4.5

STRATI = {}                                   # indice di blocco -> chiave del punto
for _i, _p in enumerate(PUNTI_FIT):
    STRATI.setdefault(_p, []).append(_i)
N_STRATI = len(STRATI)                        # 10 punti di disegno

DT_TICK_S = 0.30          # cadenza del contatore, misurata 0,28-0,34 s (P4.6:1763-1770;
                          # stesso valore di u_edge_interpolazione_probe.py:71)
FATTORE_CONFERMA = 2.0    # P3.10/F.10: intervallo_conf allargato di 2 * u_conf
SOGLIA_DIVERSITA_BOOT = 0.10   # F.14:2119-2121, 3217: 10% fra leva e PRIMARIO
SOGLIA_H_MAX = 0.40             # F.14:2128-2131, :3219: sopra 0,40 la sensibilita' e' primaria
B_BOOT = 2000             # repliche bootstrap, congelato (protocollo:2036, :3193)
SEED_BOOT = 20261104      # registrato come bootstrap_seed (P4.8:2036)
N_REP = 400               # ripetizioni esterne: NON congelato dal protocollo.
                          # E' un'assunzione di questo harness; l'errore
                          # standard di una copertura stimata su 400 repliche
                          # e' ~2,4 punti percentuali e viene stampato.
SEED_MC = 20261104
RHO_GRID = (0.0, 0.10, 0.25, 0.50, 1.00)   # griglia del probe sez. 3.2

# ---------------------------------------------------------------------------
# Superficie generativa -- assunta, NON congelata (vedere "Cosa NON dimostra").
#
# Il vincolo di scala viene dai dati v3 post-fix: segnale differenziale
# dP = 16,78 W (`lhm_validation_v3_postfix_20261023_analisi.md:22`) e una
# finestra che dura qualche secondo. La superficie e' quindi generata dal
# prodotto dP * durata, con la durata affine nei token a cadenze dichiarate:
# prefill 125 tok/s, decode 30 tok/s (ordine di grandezza di
# `research_metodo_docx_valutazione` e dei 3,60 s a (12,3 / 31,8) di run v3).
# ---------------------------------------------------------------------------

DP_W = 16.78              # W, segnale differenziale misurato in v3 post-fix
T0_S = 0.50               # s, costo fisso della richiesta
ALFA_IN = 0.008           # s/token di prefill  (125 tok/s)
BETA_OUT = 0.033          # s/token di decode   (30 tok/s)
GAMMA_CROSS = 2.0e-5      # s/token^2, termine di interazione assunto

E0_VERO = DP_W * T0_S                 # 8,39 J
A_VERO = DP_W * ALFA_IN               # 0,134 J/token
B_VERO = DP_W * BETA_OUT              # 0,5538 J/token
C_VERO = DP_W * GAMMA_CROSS           # 3,356e-4 J/token^2
THETA_VERO = np.array([E0_VERO, A_VERO, B_VERO, C_VERO])

P_IDLE_W = 11.55          # W, baseline media di v3 post-fix (analisi:20)
SD_IDLE_RUN_W = 1.29      # W, sd(P_base) fra gli otto run (analisi:58)


def superficie(theta, n_in, n_out):
    """F.8: `E_act = E0 + a*N_in + b*N_out + c*N_in*N_out`."""
    return theta[0] + theta[1] * n_in + theta[2] * n_out + theta[3] * n_in * n_out


def durata_ideale_s(n_in, n_out):
    return T0_S + ALFA_IN * n_in + BETA_OUT * n_out + GAMMA_CROSS * n_in * n_out


def matrice_blocco(punto):
    """riga di F.7 nell'ordine (1, N_in, N_out, N_in*N_out).

    Entro il blocco la geometria e' fissa, quindi la media del prodotto e' il
    prodotto delle medie: `x12_b = mean_i(N_in,i * N_out,i) = N_in * N_out`. Il
    vincolo del protocollo (F.7) e' che `x12_b` sia la media dei prodotti e non
    il prodotto delle medie; qui coincidono per costruzione e la distinzione va
    comunque calcolata, non assunta."""
    n_in, n_out = float(punto[0]), float(punto[1])
    return np.array([1.0, n_in, n_out, n_in * n_out])


# ---------------------------------------------------------------------------
# Generazione di un blocco
# ---------------------------------------------------------------------------


def genera_blocco(rng, punto, sigma_E, sigma_P, bias_w=0.0, carico=True):
    """Un blocco di P1.5: tre finestre pre, m richieste, tre finestre post.

    `sigma_E` (J) e' il rumore della singola richiesta, `sigma_P` (W) la
    dispersione delle finestre di baseline. Il rapporto fra i due, perche'
    `u_base = dP_t * budget_base_w` e `u_within = semi-range(E_act,i)` sono la
    stessa statistica di tre normali su scale diverse, e' cio' che realizza il
    `rho` richiesto: qui imposto `sigma_P`, il `rho` osservato viene fuori e
    viene stampato, non dichiarato.

    `carico=False` e' il blocco di controllo di P4.4: nessuna richiesta inviata,
    quindi nessun gradino `DP_W`; l'energia che resta dopo la sottrazione della
    baseline e' `E_net,control`, la grandezza su cui lavora l'anello 4.
    """
    n_in, n_out = float(punto[0]), float(punto[1])
    e_atteso = superficie(THETA_VERO, n_in, n_out)
    dt_ideale = durata_ideale_s(n_in, n_out) if carico else durata_ideale_s(32, 32)

    p_giro = P_IDLE_W + rng.normal(0.0, SD_IDLE_RUN_W)   # deriva fra blocchi, da v3
    reps_pre = list(p_giro + rng.normal(0.0, sigma_P, M))
    deriva = rng.normal(bias_w, sigma_P)
    reps_post = list(p_giro + deriva + rng.normal(0.0, sigma_P, M))

    dt = dt_ideale * (1.0 + rng.normal(0.0, 0.02, M))
    gradino = DP_W if carico else 0.0
    e_gross = (p_giro + bias_w + rng.normal(0.0, sigma_P, M) + gradino) * dt
    e_base = np.median(reps_pre) * dt
    e_att = e_gross - e_base                              # F.2, firmata: nessun clamp
    if carico:
        e_att = e_att + rng.normal(0.0, sigma_E, M)

    stat = V4.block_baseline(reps_pre, reps_post)
    media_dt, motivo = V4.block_mean_duration_s(
        [{"duration_s": float(v)} for v in dt], M)
    if media_dt == "":
        raise RuntimeError("durata di blocco non calcolabile: %s" % motivo)
    d_t_bar = float(media_dt)

    half_range = float(stat["half_range_pre_w"])
    half_drift = float(stat["half_drift_w"])
    out = {
        "punto": punto,
        "reps_pre": reps_pre,
        "reps_post": reps_post,
        "baseline_pre_w": float(stat["baseline_pre_w"]),
        "pre_range_w": float(stat["pre_range_w"]),
        "dP": float(stat["dP"]),
        "half_range_pre_w": half_range,
        "half_drift_w": half_drift,
        "budget_base_w_quad": float(stat["budget_base_w"]),   # produzione: quadratura
        # L'unica eccezione dichiarata al congelamento (P1.7) e' la FORMA: la
        # somma aritmetica delle stesse due semi-ampiezze si calcola da qui, e
        # il punto 4 di P6.4 confronta le due.
        "budget_base_w_somma": half_range + half_drift,
        "dt_w_s": d_t_bar,
        "e_att": list(e_att),
        "e_bar": float(np.mean(e_att)),
        "x": matrice_blocco(punto),
        "x12_b": float(np.mean([n_in * n_out] * M)),
        "u_within": SRANGE.semi_range(np.array(e_att)),      # P3.8: non / sqrt(m)
    }
    out["p_peak_w"] = max(reps_pre) + gradino     # potenza TOTALE di picco, non
                                                  # la netta (protocollo:3040-3041)
    out["u_edge"] = out["p_peak_w"] * DT_TICK_S              # F.11: P_peak * dt_tick
    return out


def completa_budget(blocco, forma, bias_w, gate_passa):
    """`budget_fit_b^2 = u_base^2 + u_within^2` (F.9, protocollo:1669) e
    `budget_pred_b^2 = budget_fit_b^2 + u_edge^2 + u_bias^2` (:1670).

    `u_bias,b = |bias_w| * dP_t_W,b` **e vale zero se il gate di P4.5 passa**
    (:1675, e la stessa regola in P4.5:1585-1589): non e' una correzione
    sottratta dai dati, e' un contributo di incertezza che entra quando il bias
    e' dichiarato. `u_edge,b = 2 * P_peak,b * dt_edge,b` con `dt_edge = dt_tick/2`
    (:1674), che si riduce a `P_peak * dt_tick` (F.11:2991). I due termini non
    toccano i pesi: `w_b = 1/budget_fit_b^2` resta (:1681-1683).
    """
    bbw = blocco["budget_base_w_" + forma]
    u_base = blocco["dt_w_s"] * bbw                          # F.11: u_base,b
    bf = math.sqrt(u_base ** 2 + blocco["u_within"] ** 2)
    u_bias = 0.0 if gate_passa else abs(bias_w) * blocco["dt_w_s"]
    bp = math.sqrt(bf ** 2 + blocco["u_edge"] ** 2 + u_bias ** 2)
    blocco["u_base"] = u_base
    blocco["u_bias"] = u_bias
    blocco["budget_fit"] = bf
    blocco["budget_pred"] = bp
    blocco["budget_base_j"] = V4.budget_base_j(blocco["dt_w_s"], bbw)
    return blocco


def fit_wls(X, Y, w):
    """F.9: `beta_hat = (X'WX)^-1 X'W Ybar`. Ritorna anche `A = (X'WX)^-1 X'W`,
    che e' la matrice 4 x n: il bootstrap di F.14 ricampiona i residuali e non
    la geometria, quindi X e W sono fissi e ogni replica e' un prodotto matrice
    - vettore, non un nuovo solve."""
    W = np.diag(w)
    XtWX = X.T @ W @ X
    A = np.linalg.solve(XtWX, X.T @ W)
    beta = A @ Y
    h = w * np.einsum("ij,jk,ik->i", X, np.linalg.inv(XtWX), X)   # F.14: leva pesata
    return beta, A, h, XtWX



# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def riga_audit(numero, descrizione, esito):
    print("  [%s] verifica %d: %s" % ("OK " if esito else "FAIL", numero, descrizione))
    return bool(esito)


def _p(v):
    print("    " + v)


def verifica_1_concentrazione():
    print("\n--- Verifica 1: concentrazione dei pesi a rho = 0 (ancora tab. 3.2) ---")
    rng = np.random.default_rng(SRANGE.SEED_CONC)
    u_dentro = SRANGE.semi_range(
        rng.standard_normal((SRANGE.N_REP_CONC, SRANGE.N_BLOCCHI, 3)))
    w = 1.0 / u_dentro ** 2
    quota = SRANGE.quota_massima(w)
    ess = (w.sum(axis=-1) ** 2) / (w ** 2).sum(axis=-1)
    media, mediana, p95 = (float(quota.mean()), float(np.median(quota)),
                           float(np.percentile(quota, 95)))
    pub = SRANGE.PUB_TAB[0.00]
    _p("quota media %6.4f  (pubblicata %.3f) | mediana %6.4f  (%.3f) | p95 %6.4f  (%.3f)"
       % (media, pub[0], mediana, pub[1], p95, pub[2]))
    _p("ESS medio %5.2f su 33 blocchi (pubblicato 7,30)" % float(ess.mean()))
    ok = (abs(media - pub[0]) < 0.005 and abs(mediana - pub[1]) < 0.005
          and abs(p95 - pub[2]) < 0.02 and abs(float(ess.mean()) - 7.30) < 0.05)
    _p("l'ancora del protocollo P6.4:2445-2447 (37,3% medio, 82,7% al p95, "
       "ESS 7,30/33) si rigenera dal probe che l'ha pubblicata")
    return riga_audit(1, "concentrazione a rho = 0 rigenerata", ok)


def verifica_2_leve():
    print("\n--- Verifica 2: leve del disegno di P3.5 (protocollo:2104, :2114) ---")
    X = COND.matrice_disegno(4)
    h_ols = COND.leve(X)
    h_max = float(h_ols.max())
    media = float(h_ols.mean())
    n_max = int((h_ols > h_max - 1e-12).sum())
    _p("h_max OLS %.4f su %d blocchi (pubblicato 0,2852 su 3 blocchi (512,256))"
       % (h_max, n_max))
    _p("media %.6f = 4/33 = %.6f (pubblicato 0,121212)" % (media, 4.0 / 33.0))
    _p("traccia: sum h_b = %.6f, pari a p = 4" % float(h_ols.sum()))
    _p("fattore 1/sqrt(1 - h_max) = %.4f (pubblicato 1,1828)"
       % (1.0 / math.sqrt(1.0 - h_max)))
    pesi_uguali = np.ones(N_FIT)
    beta, A, h_p, _ = fit_wls(X, np.arange(1.0, N_FIT + 1.0), pesi_uguali)
    ok_val = (abs(h_max - 0.2852) < 0.0005 and abs(media - 4.0 / 33.0) < 1e-5
              and abs(h_ols.sum() - 4.0) < 1e-6
              and abs(n_max - 3.0) < 0.5)
    ok_traccia_p = abs(float(h_p.sum()) - 4.0) < 1e-6
    _p("le leve PESATE di F.14 a pesi uguali coincido con le OLS e sommano a "
       "%.6f (identita' di traccia)" % float(h_p.sum()))
    return riga_audit(2, "leve e traccia rigenerate dal probe del disegno",
                      ok_val and ok_traccia_p)


def verifica_3_margini():
    print("\n--- Verifica 3: margini d'inviluppo pubblicati (P4.7) ---")
    vertici = INVIL.VERTICI_DICHIARATI
    attesi = INVIL.MARGINI_PUBBLICATI
    ok = True
    for punto, atteso in attesi.items():
        m = INVIL.margine((float(punto[0]), float(punto[1])), vertici)
        scarto = abs(m - atteso)
        ok &= scarto < 0.05
        _p("margine di (%4s,%4s) = %8.4f token   pubblicato %8.2f   scarto %.4f"
           % (punto[0], punto[1], m, atteso, scarto))
    fascia = INVIL.fascia((12.0, 32.0), vertici)
    margine_12_32 = INVIL.margine((12.0, 32.0), vertici)
    thin = margine_12_32 < INVIL.SOGLIA_THIN_SUPPORT_TOK
    _p("(12,32): fascia %s, margine %.4f token -> thin_support %s (soglia %.1f)"
       % (fascia, margine_12_32, thin, INVIL.SOGLIA_THIN_SUPPORT_TOK))
    return riga_audit(3, "i quattro margini 1,33 / 64,0 / 21,24 / 107,7 rigenerati", ok)


def verifica_4_gate_produzione():
    print("\n--- Verifica 4: il gate di P4.5 e' quello di validation_chain ---")
    print("  soglie lette dal modulo di produzione, non duplicate: "
          "pre_range_max=%.1f W, |dP|_max=%.1f W, quorum=ceil(%s*n_coppie)=%d"
          % (CHAIN.CONTROL_PRE_RANGE_MAX_W, CHAIN.CONTROL_DP_MAX_W,
             CHAIN.CONTROL_QUORUM, QUORUM))

    def controllo(pre_range, dp, e_net, dt, budget_w):
        return {"pre_range_w": pre_range, "dP": dp, "e_net_j": e_net,
                "dt_w_s": dt, "budget_base_j": V4.budget_base_j(dt, budget_w),
                "budget_base_w": budget_w}

    sei_buoni = [controllo(0.40, 0.10, 0.02, 20.0, 0.25) for _ in range(6)]
    tre_instabili = [controllo(1.60, 0.10, 0.02, 20.0, 0.25) for _ in range(3)]
    tre_buoni = [controllo(0.40, 0.10, 0.02, 20.0, 0.25) for _ in range(3)]
    # budget_base_j di un controllo con dt=20 s e budget_base_w=0,25 W vale 5,00 J
    fuori_budget = [controllo(0.40, 0.10, 5.01, 20.0, 0.25)] + \
                   [controllo(0.40, 0.10, 0.02, 20.0, 0.25) for _ in range(5)]
    esatto_al_budget = [controllo(0.40, 0.10, 5.00, 20.0, 0.25)] + \
                       [controllo(0.40, 0.10, 0.02, 20.0, 0.25) for _ in range(5)]

    a = CHAIN.bias_declared(sei_buoni, N_COPPIE_GATE)
    b = CHAIN.bias_declared(tre_instabili + tre_buoni, N_COPPIE_GATE)
    c = CHAIN.bias_declared(fuori_budget, N_COPPIE_GATE)
    d = CHAIN.bias_declared(esatto_al_budget, N_COPPIE_GATE)
    _p("sei controlli usabili, dentro il budget, bias nullo -> bias_declared %s "
       "(atteso False)" % a)
    _p("tre controlli su sei scartati dal filtro -> bias_declared %s "
       "(atteso True: ne restano 3 < quorum %d)" % (b, QUORUM))
    _p("un E_net = 5,01 J contro budget_base_j = 5,00 J -> bias_declared %s "
       "(atteso True)" % c)
    _p("un E_net = 5,00 J ESATTO contro budget_base_j = 5,00 J -> bias_declared %s: "
       "la prova e' `>` stretto, non `>=` (validation_chain.py:187)" % d)
    ok = (a is False) and (b is True) and (c is True) and (d is False)
    return riga_audit(4, "l'anello 4 importato risponde come P4.4/P4.5 prescrive", ok)


def verifica_5_bootstrap_senza_rumore():
    print("\n--- Verifica 5: F.14 sul modello esatto, poi con residui fittizi ---")
    X = np.array([matrice_blocco(p) for p in PUNTI_FIT])
    w = np.ones(N_FIT)

    Y = X @ THETA_VERO
    beta, A, h, _ = fit_wls(X, Y, w)
    residui = Y - X @ beta
    scarto = float(np.max(np.abs(beta - THETA_VERO)))
    _p("fit WLS esatto: max |beta_hat - beta_vero| = %.3e" % scarto)
    _p("somma pesata dei residui = %.3e (identita' dei minimi quadrati)"
       % float(residui.sum()))

    # Con i residui esatti il ricampionamento stratificato non puo' che
    # restitungere il centro: la distribuzione bootstrap degenera in beta_hat.
    esatti = np.array([A @ (X @ beta) for _ in range(50)])
    amp_deg = float(np.max(np.abs(esatti - beta)))
    _p("50 ricampionamenti dei residui esatti: scarto massimo = %.3e" % amp_deg)

    # Ora un residuo fittizio non degenere, con la stessa geometria e pesi uguali.
    residuo_fittizio = 0.02 * Y * np.sin(np.arange(N_FIT, dtype=float))
    Y_rotto = X @ beta + residuo_fittizio
    beta_r, A_r, h_r, _ = fit_wls(X, Y_rotto, w)
    budget_r = np.full(N_FIT, 1.0)
    z_r = (Y_rotto - X @ beta_r) / budget_r
    z_leva = (Y_rotto - X @ beta_r) / (budget_r * np.sqrt(np.maximum(1.0 - h_r, 1e-12)))
    strati = strati_di_punto()
    rng = np.random.default_rng(SEED_BOOT)

    def ricampiona(z_pool, B=400):
        out = np.empty((B, 4))
        for j in range(B):
            sel = np.concatenate([rng.choice(idx, size=len(idx), replace=True)
                                  for idx in strati])
            out[j] = A_r @ (X @ beta_r + budget_r * z_pool[sel])
        return out

    st = ricampiona(z_r)
    st_l = ricampiona(z_leva)
    dentro = []
    piu_larga = []
    for k in range(4):
        lo, hi = np.percentile(st[:, k], [2.5, 97.5])
        dentro.append(lo <= beta_r[k] <= hi)
        lo_l, hi_l = np.percentile(st_l[:, k], [2.5, 97.5])
        piu_larga.append((hi_l - lo_l) >= (hi - lo) - 1e-12)
    _p("gli intervalli percentili 2,5 / 97,5 contengono la stima di partenza: "
       "%s (4 coefficienti)" % all(dentro))
    _p("la correzione di leva `1/sqrt(1 - h_b)` allarga, non restringe: %s "
       "(h_max = %.4f, fattore %.4f)"
       % (all(piu_larga), float(h_r.max()),
          1.0 / math.sqrt(max(1.0 - float(h_r.max()), 1e-12))))
    ok = (scarto < 1e-9 and abs(residui.sum()) < 1e-6 and amp_deg < 1e-9
          and all(dentro) and all(piu_larga))
    return riga_audit(5, "il ricampionamento stratificato di F.14 e' consistente", ok)


# ---------------------------------------------------------------------------
# Campagna sintetica: un'estrazione completa di 33 + 6 + 12 blocchi
# ---------------------------------------------------------------------------


def strati_di_punto():
    """I dieci strati di F.14: 3 blocchi per punto, 6 per il centro."""
    return [idx for idx in STRATI.values()]


def campagna(rng, sigma_E, sigma_P, forma, bias_reale=0.0):
    blocca_fit = [genera_blocco(rng, p, sigma_E, sigma_P) for p in PUNTI_FIT]
    controlli = [genera_blocco(rng, (32, 32), sigma_E, sigma_P,
                               bias_w=bias_reale, carico=False)
                 for _ in range(2 * N_COPPIE_GATE)]
    conferme = []
    for p in PUNTI_CONFERMA:
        conferme += [genera_blocco(rng, p, sigma_E, sigma_P)
                     for _ in range(N_CONFERMA_PER_PUNTO)]

    vettori = [{"pre_range_w": c["pre_range_w"], "dP": c["dP"],
                "budget_base_w": c["budget_base_w_" + forma],
                "dt_w_s": c["dt_w_s"],
                "e_net_j": float(np.mean(c["e_att"])),
                "budget_base_j": V4.budget_base_j(c["dt_w_s"],
                                                  c["budget_base_w_" + forma])}
               for c in controlli]
    dichiarato = CHAIN.bias_declared(vettori, N_COPPIE_GATE)
    usabili = [v for v in vettori
               if v["pre_range_w"] <= CHAIN.CONTROL_PRE_RANGE_MAX_W
               and abs(v["dP"]) <= CHAIN.CONTROL_DP_MAX_W]
    bias_w = (sum(v["e_net_j"] for v in usabili)
              / sum(v["dt_w_s"] for v in usabili)) if usabili else 0.0
    # Il rapporto che decide la seconda condizione di `bias_declared`: un
    # controllo sfora il proprio `budget_base_j` se il modulo del suo `E_net`
    # supera la soglia. E' la statistica che fa il ~96% di falsi fallimenti, e
    # va misurata per controllo, non solo per campagna.
    ratio = [abs(v["e_net_j"]) / v["budget_base_j"] if v["budget_base_j"] > 0.0
             else float("inf") for v in usabili]
    gate_passa = not dichiarato
    for b in blocca_fit:
        completa_budget(b, forma, bias_w, gate_passa)
    for c in conferme:
        completa_budget(c, forma, bias_w, gate_passa)
    return {"fit": blocca_fit, "controlli": controlli, "conferme": conferme,
            "bias_declared": dichiarato, "bias_w": bias_w,
            "controlli_usabili": len(usabili), "controlli_ratio": ratio}


def analysis_of(camp, rng, B=B_BOOT):
    """Fit + bootstrap di F.14 sui 33 blocchi, e le risposte dei punti 1, 3, 5."""
    fit = camp["fit"]
    X = np.array([b["x"] for b in fit])
    Y = np.array([b["e_bar"] for b in fit])
    budget_fit = np.array([b["budget_fit"] for b in fit])
    u_within = np.array([b["u_within"] for b in fit])
    u_base = np.array([b["u_base"] for b in fit])
    w = 1.0 / budget_fit ** 2                              # F.9: i pesi congelati

    beta, A, h, XtWX = fit_wls(X, Y, w)
    rho_realizzato = float(np.median(u_base / np.where(u_within > 0, u_within, np.nan)))
    quota = float(w.max() / w.sum())
    ess = float(w.sum() ** 2 / (w ** 2).sum())

    residui = Y - X @ beta
    z = residui / budget_fit                               # F.14: standardizzati
    z_leva = residui / (budget_fit * np.sqrt(np.maximum(1.0 - h, 1e-12)))
    Y_modello = X @ beta
    strati = strati_di_punto()
    # ordine delle colonne dopo la concatenazione per strato: e' una permutazione
    # dei 33 blocchi, e serve per rimettere i prelievi nell'ordine dei blocchi.
    colonne = np.concatenate([np.asarray(idx) for idx in strati])
    if B > 0:
        assert sorted(colonne.tolist()) == list(range(N_FIT)), \
            "gli strati non coprono i 33 blocchi esattamente una volta"

    def ricampiona(z_pool, strati_locali=None):
        """F.14: `Y*_b = f(x_b; beta_hat) + budget_fit_b * z*_b`, con i `z*`
        prelevati con sostituzione ENTRO il punto di disegno (10 strati: 3
        blocchi, 6 per il centro) e nuovo fit con gli STESSI pesi. X e W non
        cambiano, quindi le B repliche sono un solo prodotto di matrici: la
        geometria resta quella congelata e solo i residuali si muovono.

        `strati_locali=None` e' il vincolo congelato. Con una lista di UN SOLO
        strato da 33 il ricampionamento diventa quello globale, che NON e' la
        procedura di F.14 e non la si propone: serve solo come controprova per
        la colonna `b/v` del punto 5, perche' la giustificazione di F.14 elenca
        fra le tre cose su cui poggia il 95% proprio "l'approssimazione del
        ricampionamento stratificato". Se la copertura cambia fra i due, quella
        voce e' arbitrata dai numeri e non piu' dichiarata."""
        strati_usati = strati if strati_locali is None else strati_locali
        prelievi = np.empty((B, N_FIT), dtype=int)
        for idx in strati_usati:
            arr = np.asarray(idx)
            prelievi[:, arr] = rng.choice(arr, size=(B, len(arr)), replace=True)
        Y_star = Y_modello + budget_fit * z_pool[prelievi]
        return Y_star @ A.T

    st_para = ricampiona(z)
    st_leva = ricampiona(z_leva)
    # Controprova: un solo strato = pool globale dei 33 z, senza preservare la
    # numerosita' di cella. Non sostituisce il primario, serve a diagnosticare.
    st_globale = ricampiona(z, [list(range(N_FIT))])

    def quantile_coppia(st, funzione):
        v = funzione(st)
        return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))

    # Le cinque quantita' di P4.8/F.14 sono tutte funzionali LINEARI di theta:
    # `b + c*N_in,ref` e' `(0,0,1,128) . theta`. Scritte come vettori servono sia
    # ai quantili del bootstrap sia all'ampiezza HC3, che e' `x' Sigma x` e non
    # ha una controperte per funzioni arbitrarie. La coordinata di riferimento
    # e' quella congelata in F.14 (`N_in,ref` per dE/dN_out, `N_out,ref` per
    # dE/dN_in) e l'ordine e' quello chiuso il 2026-10-25 (tabella dei difetti:
    # `b + c*N_in,ref` e' `partial E / partial N_out`, non `partial E / partial N_in`).
    funzionali = {"dE/dN_out | N_in=128": np.array([0.0, 0.0, 1.0, 128.0]),
                  "dE/dN_in | N_out=128": np.array([0.0, 1.0, 0.0, 128.0]),
                  "J/token (32,32)": matrice_blocco((32, 32)) / 64.0,
                  "J/token (128,128)": matrice_blocco((128, 128)) / 256.0,
                  "E_attesa (32,32)": matrice_blocco((32, 32))}
    verita = {k: float(v @ THETA_VERO) for k, v in funzionali.items()}

    # Diagnostica congelata di F.14: "gli errori standard HC3 si riportano
    # accanto come approssimazione lineare; se le due ampiezze differiscono di
    # piu' di un fattore 2, il bootstrap resta primario e la discrepanza si
    # dichiara". HC3 sul modello pesato: (X'WX)^-1 X'W diag(r^2/(1-h)^2) WX
    # (X'WX)^-1, che con A = (X'WX)^-1 X'W e' A diag(r^2/(1-h)^2) A'.
    Sigma_hc3 = A @ np.diag(residui ** 2 / np.maximum(1.0 - h, 1e-12) ** 2) @ A.T
    # Terza scala, e non e' una diagnostics di comodo: e' l'ipotesi che F.14
    # dichiara come primo appoggio del 95% ("poggia sulla proporzionalita' dei
    # budget alle varianze vere"). Se si prende budget_fit_b per l'incertezza
    # standard di E_bar_b, l'ampiezza lineare di theta' e' A diag(budget^2) A'.
    # Confrontarla con la diffusione reale sulle campagne dice se i pesi F.9 sono
    # proporzionali alle varianze, o no.
    Sigma_budget = A @ np.diag(budget_fit ** 2) @ A.T

    # "budget_pred del blocco nuovo": il blocco nuovo e' quello alla geometria di
    # riferimento della quantita' pubblicata, non un blocco medio del disegno. Per
    # i due costi marginali la geometria di riferimento e' il centro (128,128),
    # perche' e' li' che si legge il numero; e' una scelta dichiarata, perche'
    # F.14 non la nomina.
    _geo_rif = {"dE/dN_out | N_in=128": (128, 128),
               "dE/dN_in | N_out=128": (128, 128),
               "J/token (32,32)": (32, 32),
               "J/token (128,128)": (128, 128),
               "E_attesa (32,32)": (32, 32)}

    para, leva, pred, bp_rif = {}, {}, {}, {}
    sd_boot, sd_hc3, scarto_leva, ampiezza_pred = {}, {}, {}, {}
    sd_globale, sd_budget = {}, {}
    stime = {}
    for k, v in funzionali.items():
        vp, vl = st_para @ v, st_leva @ v
        vg = st_globale @ v
        para[k] = (float(np.percentile(vp, 2.5)), float(np.percentile(vp, 97.5)))
        leva[k] = (float(np.percentile(vl, 2.5)), float(np.percentile(vl, 97.5)))
        stime[k] = float(beta @ v)
        sd_globale[k] = (float(np.percentile(vg, 97.5))
                         - float(np.percentile(vg, 2.5))) / (2.0 * 1.96)
        ampiezza = max(para[k][1] - para[k][0], 1e-12)
        # La soglia del 10% di F.14 e' fra i quantili della variante di leva e
        # quelli del PRIMARIO. Non fra predittivo e parametrico: il predittivo e'
        # un altro oggetto e il suo scarto non ha soglia congelata.
        scarto_leva[k] = max(abs(leva[k][0] - para[k][0]),
                             abs(leva[k][1] - para[k][1])) / ampiezza
        sd_boot[k] = ampiezza / (2.0 * 1.96)      # 3,92 sd sotto normalita'
        sd_hc3[k] = float(math.sqrt(max(v @ Sigma_hc3 @ v, 0.0)))
        sd_budget[k] = float(math.sqrt(max(v @ Sigma_budget @ v, 0.0)))
        vals = [b["budget_pred"] for b in fit if b["punto"] == _geo_rif[k]]
        bp_rif[k] = float(np.median(vals)) if vals else float("nan")
        # Il predittivo di F.14 e' "lo spread parametrico di f(x; theta*)
        # allargato con il budget_pred del blocco nuovo", ed e' l'intervallo
        # "con cui si confronta una misura". Ha quindi senso sulle quantita' che
        # SONO una misura attesa a una geometria (E in J, J/token = J diviso i
        # token totali di quel blocco), non sui costi marginali: un costo
        # marginale non e' il valore di un blocco nuovo, e dividere il suo budget
        # per i token sarebbe un'unita' inventata. Qui resta `None` e si dichiara.
        if k.startswith("E_attesa"):
            bp = bp_rif[k]
        elif k.startswith("J/token"):
            bp = bp_rif[k] / (64.0 if k == "J/token (32,32)" else 256.0)
        else:
            bp = None
        pred[k] = None if bp is None else (para[k][0] - bp, para[k][1] + bp)
        ampiezza_pred[k] = float("nan") if bp is None else pred[k][1] - pred[k][0]

    div_key = "J/token (128,128)"
    div = ampiezza_pred[div_key] / max(
        para[div_key][1] - para[div_key][0], 1e-12)

    # P3.10/F.10: i sei blocchi di conferma, con il fattore 2 congelato
    confermo = []
    for c in camp["conferme"]:
        x_conf = matrice_blocco(c["punto"])
        u_conf = c["u_within"]
        l, u = quantile_coppia(st_para, lambda s, xc=x_conf: s @ xc)
        li, ui = l - FATTORE_CONFERMA * u_conf, u + FATTORE_CONFERMA * u_conf
        vera = superficie(THETA_VERO, float(c["punto"][0]), float(c["punto"][1]))
        confermo.append({"punto": c["punto"], "dentro": bool(li <= vera <= ui),
                         "dentro_senza_fattore": bool(l <= vera <= u),
                         "larghezza": ui - li, "larghezza_senza2": u - l})

    return {"beta": beta, "h": h, "w": w, "rho_realizzato": rho_realizzato,
            "quota_peso": quota, "ess": ess, "para": para, "leva": leva,
            "pred": pred, "divergenza": div, "verita": verita, "stime": stime,
            "sd_boot": sd_boot, "sd_hc3": sd_hc3, "scarto_leva": scarto_leva,
            "sd_globale": sd_globale, "sd_budget": sd_budget,
            "bp_rif": bp_rif, "conferme": confermo,
            "bias_declared": camp["bias_declared"], "bias_w": camp["bias_w"],
            "controlli_usabili": camp["controlli_usabili"]}


# ---------------------------------------------------------------------------
# I cinque punti di P6.4
# ---------------------------------------------------------------------------


def run_punto(numero, titolo):
    print("\n" + "=" * 74)
    print("PUNTO %d DI P6.4 -- %s" % (numero, titolo))
    print("=" * 74)


def risposte():
    rng_master = np.random.default_rng(SEED_MC)

    # scala del rumore della richiesta: 2% dell'energia di blocco, ancorata al
    # CV 8,99% di v3 post-fix (analisi:20) come ordine di grandezza, non come
    # misura di u_within.
    sigma_E_ref = 0.02 * superficie(THETA_VERO, 128.0, 128.0)

    for forma in ("quad", "somma"):
        run_punto(4, "forma di combinazione di budget_base_w (%s)" %
                  ("quadratura, quella di produzione" if forma == "quad"
                   else "somma aritmetica, l'eccezione aperta di P1.7"))
        print("  rho    |  rho oss. | quota max w | ESS/33 | gate dich. | "
              "copr. 95% | scarto leva")
        for rho in RHO_GRID:
            sigma_P = 0.0 if rho == 0.0 else rho * sigma_E_ref / 20.0
            cover = []
            gate = []
            quota = []
            ess_list = []
            rho_oss = []
            div = []
            for _ in range(N_REP):
                camp = campagna(rng_master, sigma_E_ref, sigma_P, forma)
                ana = analysis_of(camp, rng_master)
                cover.append(ana["para"]["dE/dN_out | N_in=128"][0]
                             <= ana["verita"]["dE/dN_out | N_in=128"]
                             <= ana["para"]["dE/dN_out | N_in=128"][1])
                gate.append(ana["bias_declared"])
                quota.append(ana["quota_peso"])
                ess_list.append(ana["ess"])
                rho_oss.append(ana["rho_realizzato"])
                # la colonna che interessa al punto 4 e' la regola del 10% fra la
                # variante di leva e il primario (F.14), perche' e' l'unica soglia
                # di F.14 che i pesi possono spostare.
                div.append(ana["scarto_leva"]["dE/dN_out | N_in=128"])
            c = float(np.mean(cover))
            se = math.sqrt(max(c * (1 - c), 1e-12) / N_REP)
            print("  %4.2f  |   %6.3f   |    %5.1f%%   | %5.2f  |   %5.1f%%    | "
                  "%4.1f%% +-%.1f | %5.1f%%"
                  % (rho, float(np.median(rho_oss)), 100 * float(np.mean(quota)),
                     float(np.mean(ess_list)), 100 * float(np.mean(gate)),
                     100 * c, 100 * se, 100 * float(np.mean(div))))

    print("\n  Lettura del punto 4: le due tabelle differiscono per la quota del")
    print("  blocco piu' pesante e per l'ESS, non per il gate. La forma non e'")
    print("  arbitrata dai dati del pilota (P2.9/P6.2 non girati): qui si vede")
    print("  QUANTO pesa la scelta, che e' la domanda di P1.7.")
    print("  Come si legge la colonna `rho`: il protocollo chiede di attraversare")
    print("  il RAPPORTO fra le scale dei due termini di budget, non di imporlo")
    print("  per via. Qui si imposta `sigma_P = rho * sigma_E / 20` (la /20 porta")
    print("  le due scale nello stesso ordine di grandezza del pilota) e il")
    print("  rapporto REALIZZATO `u_base/u_within` si stampa: e' la colonna")
    print("  `rho oss.`, che non raggiunge il valore nominale perche' i due")
    print("  termini vengono da statistiche diverse. A rho = 0 il gate")
    print("  dich. 0,0% non e' potenza: la riga di commento al punto 2 lo dice.")

    run_punto(1, "concentrazione dei pesi contro rho")
    print("  E' la colonna 'quota max w' delle due tabelle sopra, e il suo")
    print("  pendant in blocchi equivalenti (ESS). A rho = 0 coincide con")
    print("  l'ancora del probe (tab. 3.2: 0,373 media, 0,816 p95, ESS 7,30/33).")
    print("  Il protocollo (P6.4:2445-2450) dice che la quota e' indipendente")
    print("  da rho per cancellazione esatta quando u_base = rho * u_within")
    print("  dello STESSO blocco: qui u_base e u_within vengono da statistiche")
    print("  diverse (budget di baseline contro semi-range di m richieste),")
    print("  quindi l'indipendenza NON vale e la tabella e' una funzione.")

    run_punto(2, "potenza e falsi del gate P4.5")
    rng2 = np.random.default_rng(SEED_MC + 1)
    rng4 = np.random.default_rng(SEED_MC + 3)
    # Il gate ha DUE meccanismi distinti e il punto 2 di P6.4 chiede l'uno e
    # l'altro: (i) il filtro `pre_range_w <= 1,0 W` e `|dP| <= 1,0 W` con il
    # quorum di `ceil(2/3 * 6) = 4` controlli utilizzabili, e (ii) la prova per
    # controllo `|E_net,c| > budget_base_j,c`, che scatta alla prima occorrenza.
    # Il primo dipende dalla SCALA di sigma_P fra le finestre di baseline, il
    # secondo NO, perche' `E_net` e `budget_base_w` sono la stessa sigma_P per
    # due strade diverse. Per questo qui sigma_P si attraversa APERTAMENTE, non
    # come sottoprodotto del `rho` delle tabelle del punto 4.
    print("  sigma_P  | usabili/12 | quorum non | un controllo |  gate  |  gate")
    print("     (W)   |  media     |   raggiunt |  sfora (q) | bias 0 | bias 0,30")
    for sigma_P in (0.01, 0.05, 0.10, 0.30, 0.60, 1.00):
        usab, sotto_quorum, dich0, dich_b, q = [], [], [], [], []
        for bias_reale in (0.0, 0.30):
            for _ in range(N_REP):
                camp = campagna(rng4, sigma_E_ref, sigma_P, "quad",
                                bias_reale=bias_reale)
                (dich0 if bias_reale == 0.0 else dich_b).append(
                    camp["bias_declared"])
                if bias_reale == 0.0:
                    usab.append(camp["controlli_usabili"])
                    sotto_quorum.append(camp["controlli_usabili"] < QUORUM)
                    q += camp["controlli_ratio"]
        q_emp = float(np.mean([x > 1.0 for x in q]))
        # La forma chiusa che il Monte Carlo deve confermare. Con tre normali di
        # scarto sigma_P: E[range]/2 = 0,8463 sigma_P (ancora del semi-range, gia'
        # nel probe), Var(mediana di 3) = 0,5235 sigma_P^2, e `dP` somma due
        # mediane piu' la deriva, quindi sd 1,4307 sigma_P e
        # E[|dP|]/2 = 0,5715 sigma_P. Da cui budget_base_w ~ 1,022 sigma_P, mentre
        # l'errore di `E_net/dt` e' sqrt(1/3 + 0,5235) = 0,9257 sigma_P.
        scala_budget = math.hypot(0.8463, 0.5715)
        scala_rete = math.sqrt(1.0 / 3.0 + 0.5235)
        kappa = scala_rete / scala_budget
        q_teo = 2.0 * (1.0 - 0.5 * (1.0 + math.erf((1.0 / kappa) / math.sqrt(2.0))))
        if sigma_P > 0.0:
            print("  %6.2f   |   %5.2f    |    %5.1f%%   |   %5.1f%%   | %5.1f%% |"
                  "  %5.1f%%" % (sigma_P, float(np.mean(usab)),
                                 100 * float(np.mean(sotto_quorum)), 100 * q_emp,
                                 100 * float(np.mean(dich0)),
                                 100 * float(np.mean(dich_b))))
            _p("forma chiusa: |E_net|/budget = %.3f di sigma_P su entrambi i"
               " lati -> kappa = %.3f, q = %.1f%% (misurato %.1f%%);"
               % (scala_rete, kappa, 100 * q_teo, 100 * q_emp))
            _p("  1 - (1-q)^12 = %.1f%% contro il %.1f%% misurato a bias 0. La"
               " prova per controllo e' un test da ~%.2f sigma, e la catena"
               " li ANDa dodici volte: il falso fallimento NON dipende dalla"
               " scala del rumore."
               % (100 * (1 - (1 - q_teo) ** (2 * N_COPPIE_GATE)),
                  100 * float(np.mean(dich0)), 1.0 / kappa))
    print("  A sigma_P >= 0,60 W la forma chiusa sottostima: il filtro di")
    print("  P4.4 (pre_range <= 1,0 W e |dP| <= 1,0 W) non e' neutro, perche'")
    print("  le due quantita' che filtra SONO i due termini di")
    print("  budget_base_w. Tenere solo i controlli con range e drift piccoli")
    print("  assottiglia il denominatore, mentre il numeratore conserva la")
    print("  componente di rumore delle singole finestre di richiesta, che il")
    print("  filtro non tocca. Il rapporto quindi SALE con sigma_P (27% -> 43%")
    print("  -> 62%) e il falso fallimento peggiora dove la macchina e' meno")
    print("  stabile: non e' un difetto della forma chiusa, e' l'effetto di")
    print("  scegliere sui denominatori. Va dichiarato come limite del gate,")
    print("  perche' la colonna 'gate bias 0' non scende mai sotto ~95%.")
    print("  A sigma_P = 0 il gate NON E' ESEGUIBILE in senso forte: le tre")
    print("  finestre di baseline sono identiche, quindi `pre_range_w = 0`,")
    print("  `budget_base_w = 0`, `E_net = 0` e la prova `>` stretto di")
    print("  validation_chain.py:187 e' `0 > 0` = False. Il 0,0% di")
    print("  dichiarazione a rho = 0 nelle tabelle del punto 4 non e' potenza:")
    print("  e' un anello che non ha materia da testare, e va dichiarato come")
    print("  tale, non letto come 'il gate non da' falsi'.")
    print("  Il quorum di quattro controlli utilizzabili su sei coppie e' la")
    print("  soglia che il punto 2 chiede di verificare: sulle scale reali di")
    print("  sigma_P la colonna 'quorum non raggiunto' dice se il filtro scarta")
    print("  abbastanza controlli da far dichiarare il bias da solo; la colonna")
    print("  'gate bias 0' dice che il falso fallimento arriva prima, dalla")
    print("  prova per controllo.")
    print("  La potenza a bias 0,30 W e' ~100% su tutta la griglia, e non e'")
    print("  un risultato informativo: con un bias reale l'anello 4 non puo'")
    print("  che dichiararsi.")
    print("  Cio' che il punto 2 arbitrava era il costo in falsi, non il")
    print("  guadagno in potenza.")

    run_punto(3, "copertura del fattore 2 di P3.10")
    dentro2 = []
    dentro1 = []
    larghezze = []
    for _ in range(N_REP):
        camp = campagna(rng2, sigma_E_ref, sigma_E_ref / 20.0, "quad")
        ana = analysis_of(camp, rng2)
        for c in ana["conferme"]:
            dentro2.append(c["dentro"])
            dentro1.append(c["dentro_senza_fattore"])
            larghezze.append((c["larghezza"], c["larghezza_senza2"]))
    c2 = float(np.mean(dentro2))
    c1 = float(np.mean(dentro1))
    se2 = math.sqrt(max(c2 * (1 - c2), 1e-12) / len(dentro2))
    ampl = float(np.mean([a / b if b > 0 else float("nan") for a, b in larghezze]))
    print("  copertura CON il fattore 2 (F.10 congelato)  : %.1f%% +-%.1f su %d casi"
          % (100 * c2, 100 * se2, len(dentro2)))
    print("  copertura SENZA il fattore 2 (parametrico)   : %.1f%% su %d casi"
          % (100 * c1, len(dentro1)))
    print("  amplificazione media della larghezza per il 2: x%.3f" % ampl)
    print("  Il fattore 2 di F.10 non e' un 95%: il protocollo lo scrive, e qui")
    print("  esce il numero che mancava (P6.4 punto 3).")

    run_punto(5, "copertura bootstrap: parametrico, predittivo, leva")
    chiavi = ("dE/dN_out | N_in=128", "dE/dN_in | N_out=128",
              "J/token (32,32)", "J/token (128,128)", "E_attesa (32,32)")
    tab = {k: {"para": [], "leva": [], "pred": [], "sotto": [], "sopra": [],
               "stima": [], "sd_boot": [], "sd_hc3": [], "sd_glob": [],
               "sd_budget": [], "scarto_leva": []} for k in chiavi}
    hmax = []
    e_bar_per_blocco = []
    budget_fit_per_blocco = []
    sd_riga_per_blocco = []
    for _ in range(N_REP):
        camp = campagna(rng2, sigma_E_ref, sigma_E_ref / 20.0, "quad")
        ana = analysis_of(camp, rng2)
        e_bar_per_blocco.append([b["e_bar"] for b in camp["fit"]])
        budget_fit_per_blocco.append([b["budget_fit"] for b in camp["fit"]])
        sd_riga_per_blocco.append([float(np.std(b["e_att"], ddof=1))
                                   for b in camp["fit"]])
        for k in chiavi:
            verita_k = ana["verita"][k]
            lo, hi = ana["para"][k]
            tab[k]["para"].append(lo <= verita_k <= hi)
            tab[k]["sotto"].append(verita_k < lo)
            tab[k]["sopra"].append(verita_k > hi)
            lo, hi = ana["leva"][k]
            tab[k]["leva"].append(lo <= verita_k <= hi)
            if ana["pred"][k] is None:
                tab[k]["pred"].append(None)
            else:
                lo, hi = ana["pred"][k]
                tab[k]["pred"].append(lo <= verita_k <= hi)
            tab[k]["stima"].append(ana["stime"][k])
            tab[k]["sd_boot"].append(ana["sd_boot"][k])
            tab[k]["sd_hc3"].append(ana["sd_hc3"][k])
            tab[k]["sd_glob"].append(ana["sd_globale"][k])
            tab[k]["sd_budget"].append(ana["sd_budget"][k])
            tab[k]["scarto_leva"].append(ana["scarto_leva"][k])
        hmax.append(float(ana["h"].max()))

    print("  quantita'                     primario    con leva   predittivo  "
          "|  fuori sotto/sopra")
    for k in chiavi:
        r = tab[k]
        pred_vals = [x for x in r["pred"] if x is not None]
        pred_txt = ("%6.1f%%" % (100 * float(np.mean(pred_vals)))) if pred_vals \
            else "    n/d "
        print("  %-26s   %6.1f%%    %6.1f%%   %s  |  %4.1f%% / %4.1f%%"
              % (k, 100 * float(np.mean(r["para"])), 100 * float(np.mean(r["leva"])),
                 pred_txt, 100 * float(np.mean(r["sotto"])),
                 100 * float(np.mean(r["sopra"]))))

    print("\n  Perche' copre meno del nominale: il confronto fra le quattro scale")
    print("  dell'ampiezza, sulle %d campagne." % N_REP)
    print("  %-24s %8s %8s %8s %8s %8s %6s %6s %6s %6s"
          % ("quantita'", "sd vero", "sd boot", "sd HC3", "sd glob",
             "sd bud", "b/v", "H/v", "g/v", "B/v"))
    # Il valore vero di ogni quantita' non dipende dalla campagna (e' la superficie
    # assunta per generare), quindi una sola lettura vale per tutte.
    VERITA = ana["verita"]
    rapporti_Bv = []
    for k in chiavi:
        r = tab[k]
        stime = np.array(r["stima"])
        verita_k = VERITA[k]
        sd_vero = float(stime.std(ddof=1))
        bias = float(stime.mean() - verita_k)
        sd_b = float(np.mean(r["sd_boot"]))
        sd_h = float(np.mean(r["sd_hc3"]))
        sd_g = float(np.mean(r["sd_glob"]))
        sd_bu = float(np.mean(r["sd_budget"]))
        print("  %-24s %9.5f  %9.5f  %9.5f  %9.5f  %9.5f %6.3f %6.3f %6.3f %6.3f"
              % (k, sd_vero, sd_b, sd_h, sd_g, sd_bu, sd_b / sd_vero,
                 sd_h / sd_vero, sd_g / sd_vero, sd_bu / sd_vero))
        rapporti_Bv.append(sd_bu / sd_vero)
        _p("   scarto medio della stima dal vero: %+.5f (%.1f%% di sd vero); "
           "scarto quantili leva/primario mediano %.1f%% (soglia 10%%, F.14)"
           % (bias, 100 * abs(bias) / max(sd_vero, 1e-12),
              100 * float(np.median(r["scarto_leva"]))))
    _p("lettura delle quattro colonne di rapporto, tutte divise per la")
    _p("  diffusione REALE di theta' sulle %d campagne (`sd vero`):" % N_REP)
    _p("  b/v = il primario congelato di F.14;  H/v = l'approssimazione lineare")
    _p("  HC3 che F.14 stesso chiede di riportare accanto;  g/v = il CONTROLLO")
    _p("  con pool GLOBALE dei %d z, senza stratificazione (non e' una proposta:"
       % N_FIT)
    _p("  la stratificazione e' congelata e questa riga non la sostituisce);")
    _p("  B/v = l'ampiezza che si otterrebbe PRENDENDO budget_fit_b PER")
    _p("  incertezza standard di E_bar_b, cioe' l'ipotesi che F.14 nomina come")
    _p("  primo appoggio del 95%: 'proporzionalita' dei budget alle varianze")
    _p("  vere' - e' la stessa ipotesi dei pesi F.9, e qui viene misurata.")
    _p("Le tre cose su cui F.14 dichiara che poggia il 95% escono in tre colonne")
    _p("  diverse: la proporzionalita' dei budget (B/v), l'adeguatezza del")
    _p("  modello (la riga `scarto medio`, che qui e' piccola PER COSTRUZIONE:")
    _p("  la superficie generata e' quella fitata, quindi questa simulazione NON")
    _p("  arbitra il modello inadeguato, lo esclude), e l'approssimazione del")
    _p("  ricampionamento stratificato (b/v contro g/v).")
    _p("Il deficit di b/v e' piu' grande di quanto i due meccanismi noti")
    _p("  prevedano: i residuali in-campionamento tolgono al piu' un fattore")
    _p("  radice((n-p)/n) = radice(29/33) = %.3f, e la stratificazione dentro"
       % math.sqrt(29.0 / 33.0))
    _p("  celle da tre toglie l'errore delle MEDIE di cella (i tre z di una")
    _p("  cella hanno somma pesata nulla per le equazioni di score, quindi un")
    _p("  prelievo entro la cella non puo' generare uno scarto della media di")
    _p("  cella piu' grande dello scarto fra i suoi tre z: fattore chiuso ~")
    _p("  radice(2/3) = 0,816). Il pool globale risale solo a ~0,5-0,7, non a")
    _p("  0,94, e nessun dei due arriva a 1: la causa completa NON e' arbitrata")
    _p("  da queste colonne, e va detta come lacuna aperta dell'harness, non")
    _p("  come spiegazione. Cio' che e' arbitrato e' il FATTO, con il numero:")
    _p("  l'intervallo pubblicato da F.14 e' ~2 volte piu' stretto della")
    _p("  diffusione reale, su tutte e cinque le quantita', e l'HC3 no.")

    # --- cosa vale davvero `budget_fit_b` come scala dell'errore di `E_bar_b` ---
    # Il fit di F.9 pesa con `w_b = 1/budget_fit_b^2`, cioe' TRATTA budget_fit
    # come l'incertezza standard di `E_bar_b`. Se il semi-range a m = 3 (che per
    # forma chiusa vale 0,8468 sigma) e' piu' grande della sd reale di `E_bar_b`
    # (che e' sigma/radice(3) = 0,5774 sigma), la scala dei residui standardizzati
    # e' sbagliata di un fattore noto a priori: 0,8468 / 0,5774 = 1,4666. E'
    # l'aritmetica che il probe dei semi-range anticipava (fattore 1,27 fra medie,
    # che qui diventa il rapporto fra scale), ed e' cio' che copre o scoperchia
    # l'intervallo bootstrap.
    EB = np.array(e_bar_per_blocco)
    BF = np.array(budget_fit_per_blocco)
    SR = np.array(sd_riga_per_blocco)
    sd_reale = EB.std(axis=0, ddof=1)
    bf_med = np.median(BF, axis=0)
    rapporto = bf_med / sd_reale
    atteso_analitico = 0.8468 / (1.0 / math.sqrt(3.0))
    _p("sd reale di `E_bar_b` fra le %d campagne, mediana sui 33 blocchi: %.3f J"
       % (N_REP, float(np.median(sd_reale))))
    _p("`budget_fit_b` mediano sui 33 blocchi: %.3f J" % float(np.median(bf_med)))
    _p("rapporto budget_fit / sd(E_bar) = %.3f (mediana sui blocchi); il fattore"
       " atteso" % float(np.median(rapporto)))
    _p("  dalle forme chiuse del semi-range e' 0,8468 / (1/sqrt(3)) = %.4f"
       % atteso_analitico)
    _p("sd per richiesta osservata: %.3f J, e sigma/radice(3) = %.3f J"
       % (float(np.median(SR)), float(np.median(SR)) / math.sqrt(3.0)))
    _p("attenzione al rapporto qui sopra, perche' ha due effetti OPPOSTI e va")
    _p("  detto quale e' quale. Nel ricampionamento `budget_fit` si CANCELLA per")
    _p("  costruzione (`Y* = f + budget_fit*(r/budget_fit)*`), quindi l'ampiezza")
    _p("  bootstrap NON dipende dalla scala dei budget: il deficit di b/v non e'")
    _p("  il fattore 1,395. Nella forma lineare invece il budget entra DUE volte,")
    _p("  una nei pesi e una nella varianza, con esponenti opposti: se")
    _p("  budget = kappa*sigma vera, allora A e' kappa^-2 e diag(budget^2) e'")
    _p("  kappa^2, quindi l'ampiezza lineare viene kappa^-1 = %.3f volte la vera."
       % (1.0 / float(np.median(rapporto))))
    _p("  E' esattamente la colonna B/v (%.2f-%.2f sulle cinque quantita'),"
       % (min(rapporti_Bv), max(rapporti_Bv)))
    _p("  e questo e' il numero che")
    _p("  arbitra la prima delle tre ipotesi di F.14: la proporzionalita' dei")
    _p("  budget alle varianze vere NON e' solo mancante di un fattore, e' che")
    _p("  il fattore lavora al contrario nei pesi. HC3, che usa i residuali")
    _p("  osservati e non i budget, e' l'unica delle quattro scale a stare a 1.")

    print("  h_b massima del fit pesato: mediana %.4f (soglia di sensibilita' "
          "0,40, protocollo:2128-2131)" % float(np.median(hmax)))
    print("  La copertura dichiarata 'nominale e non arbitrata' in P4.8 e'")
    print("  arbitrata da queste colonne. Sotto 95% significa che il")
    print("  95% non si puo' pubblicare con la procedura di F.14 cosi' com'e';")
    print("  le due tabelle sopra dicono se la colpa e' della stima (bias),")
    print("  dell'ampiezza bootstrap (ricampionamento) o dei pesi (proporzionalita').")


def main():
    print("=" * 74)
    print("P6.4 -- Simulazione Monte Carlo del protocollo v4")
    print("=" * 74)
    print("host: %s | python %s | numpy %s | %d ripetizioni x %d repliche bootstrap"
          % (os.environ.get("COMPUTERNAME", "?"),
             ".".join(str(v) for v in sys.version_info[:3]),
             np.__version__, N_REP, B_BOOT))
    print("\n--- Assunzioni dichiarate (nessuna di queste e' congelata) ---")
    print("  superficie F.8: E0=%.3f J, a=%.5f, b=%.5f, c=%.6f J/token^2,"
          % (E0_VERO, A_VERO, B_VERO, C_VERO))
    print("    generata da dP=%.2f W x durata affine (t0=%.2f s, %.3f s/token prefill,"
          % (DP_W, T0_S, ALFA_IN))
    print("    %.3f s/token decode, %.1e s/token^2)" % (BETA_OUT, GAMMA_CROSS))
    print("  idle: media %.2f W, sd fra blocchi %.2f W (v3 post-fix, analisi:20,:58)"
          % (P_IDLE_W, SD_IDLE_RUN_W))
    print("  rumore di richiesta: %.1f%% dell'energia al centro del disegno"
          % (100 * 0.02))
    print("  N_REP=%d NON congelato dal protocollo; B=%d e seed %d si' (F.14:2036)"
          % (N_REP, B_BOOT, SEED_BOOT))
    print("  dt_tick=%.2f s (P4.6, misurato 0,28-0,34), fattore conferma=%.0f (F.10)"
          % (DT_TICK_S, FATTORE_CONFERMA))
    print("  disegno: %d blocchi di fit su %d punti, %d blocchi di conferma su %d"
          " punti,\n           %d controlli (%d coppie) per il gate"
          % (N_FIT, N_STRATI, len(PUNTI_CONFERMA) * N_CONFERMA_PER_PUNTO,
             len(PUNTI_CONFERMA), 2 * N_COPPIE_GATE, N_COPPIE_GATE))
    print("  import di produzione: block_baseline, budget_base_j, "
          "block_mean_duration_s,\n           bias_declared + le sue soglie "
          "(nessuna soglia duplicata)")

    esiti = [verifica_1_concentrazione(), verifica_2_leve(), verifica_3_margini(),
             verifica_4_gate_produzione(), verifica_5_bootstrap_senza_rumore()]

    print("\n" + "=" * 74)
    print("LE CINQUE DOMANDE DI P6.4 (sotto: i verdetti, non le verifiche)")
    print("=" * 74)
    risposte()

    print("\n" + "=" * 74)
    print("Vincolo di metodo (P6.4:2467-2469): la simulazione NON puo' validare")
    print("la scala assoluta, perche' genera essa stessa l'energia. Controlla la")
    print("procedura statistica, non la misura.")
    print("=" * 74)
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())

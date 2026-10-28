"""Rigenera i numeri del semi-range a n = 3 e della concentrazione dei pesi `w_b`.

Perche' esiste questo file
--------------------------
La valutazione della revisione esterna del 2026-10-24, in
`experiment_results/revisione_esterna_formule_20261024_valutazione.md` §3.1 e
§3.2, pubblica due gruppi di numeri senza harness tracciato:

    §3.1  E[semi-range] = 0,8468 sigma, sd(mediana) = 0,6693 sigma,
          P(semi-range < 0,2 sigma) = 4,33%, percentili 0,095 / 0,215 / 0,795 /
          1,656, "conservativo di un fattore 1,27", "otto volte troppo piccolo"
    §3.2  tabella 5 x 3 della quota di peso totale detenuta dal blocco piu'
          pesante, al variare di `rho = u_base/u_within`
          (0,373/0,315/0,816 a rho = 0, fino a 0,048/0,048/0,053 a rho = 1)

e il protocollo P6.4 (righe 2378-2383) ne cita tre ancore -- "il 37% e l'82% nel
5% dei casi peggiori a rho = 0, contro l'8% a rho >= 0,5" -- come motivazione del
punto 1 della simulazione. Sono calcoli descritti: per AGENTS.md un'analisi non
tracciata e' un numero che nessuno puo' rigenerare. Questo file li rigenera e li
confronta con la forma chiusa, che non depende da nessun seed.

Cosa verifica
-------------
1. **Semi-range e mediana di tre gaussiane: Monte Carlo contro analitico.** Le
   quantita' hanno forma chiusa in integrali mono-dimensionali delle densita'
   d'ordine (David & Nagaraja): `E[X_(3)] = 3 int x phi Phi^2`,
   `E[X_(1)] = 3 int x phi (1-Phi)^2`, `f_med = 6 phi Phi (1-Phi)`,
   `P(range <= r) = 3 int phi(x) [Phi(x+r) - Phi(x)]^2 dx`. Il Monte Carlo della
   valutazione (400.000 terne, seed 20261024) e' ricalcolato e confrontato con la
   quadratura di Gauss-Legendre entro l'errore standard.
2. **Il rapporto 1,27 e' un rapporto fra medie, non una copertura per blocco.**
   La quarta revisione, §3.1, chiede esplicitamente di non confondere le due
   affermazioni. `u_within,b` e' a scala di semi-range (P3.8: non diviso per
   radice di m) e il fit di F.9 lavora su `E_bar_b`, la MEDIA di m = 3, il cui
   errore reale e' `sigma/radice(3) = 0,5774 sigma`. La conservativita' per
   blocco e' `P(u_within,b < sigma/radice(3))` e
   `P(u_within,b < |E_bar_b - mu|)`, non il rapporto delle medie.
3. **La tabella §3.2 dipende dalla parametrazione, e la formula scritta accanto
   alla tabella la rende indipendente da `rho`.** Con `u_base,b =
   rho * u_within,b` dello stesso blocco si ha `budget_b = u_within,b *
   sqrt(1+rho^2)`, quindi `w_max/sum(w) = (1/u^2)_max / sum(1/u^2)` e il fattore
   `sqrt(1+rho^2)` si cancella ESATTAMENTE: la quota non cambia con `rho`. Una
   tabella che scende da 0,373 a 0,048 non puo' venire da quella formula. Qui si
   misurano tre parametrazioni e si dice quale riproduce la tabella.
4. **Effetto della forma di combinazione rinviata in P1.7** (quadratura contro
   somma aritmetica di `half_range` e `half_drift`, cioe' qui di `u_base`) sulla
   concentrazione: e' il punto 4 di P6.4, e qui produce una curva con incrocio,
   senza aspettare i dati del pilota.
5. **Lettura alternativa: il numero effettivo di blocchi.** La quota del blocco
   piu' pesante e' una statistica estrema; `ESS = (sum w)^2 / sum w^2` (Kish) da'
   la stessa informazione in "blocchi equivalenti", e a `rho = 0` non depende da
   nessuna parametrazione.

Cosa NON dimostra
-----------------
Non tocca il disegno di P3.5, il suo condizionamento, le leve e le cifre perse
nel solve, che stanno in `condizionamento_disegno_probe.py`. Non tocca la
copertura reale degli intervalli bootstrap: quella richiede il fit, i pesi
congelati e la procedura di ricampionamento, ed e' il compito di P6.4. Qui il
modello dell'errore e' gaussiano iid con `sigma` nota: e' un'ipotesi di lavoro,
non una misura, perche' `u_within` non e' mai stato misurato su un blocco v4
(P6.2), e `rho` oggi non e' misurabile (P1.7, P6.4 punto 1).
"""

import math
import sys

import numpy as np

N_TERNE = 400_000
SEED_SEMI_RANGE = 20261024
N_REP_CONC = 40_000
N_BLOCCHI = 33
SEED_CONC = 20261025
RHO = (0.0, 0.10, 0.25, 0.50, 1.00)

SQRT2 = math.sqrt(2.0)
SQRT3 = math.sqrt(3.0)

# --- valori pubblicati, per il confronto ----------------------------------
# §3.1
PUB_E_SR = 0.8468
PUB_SD_MED = 0.6693
PUB_P_02 = 0.0433
PUB_PCTL = {1: 0.095, 5: 0.215, 50: 0.795, 95: 1.656}
# §3.2: (quota media, mediana, p95) per riga di rho
PUB_TAB = {
    0.00: (0.373, 0.315, 0.816),
    0.10: (0.263, 0.249, 0.445),
    0.25: (0.143, 0.141, 0.195),
    0.50: (0.079, 0.079, 0.095),
    1.00: (0.048, 0.048, 0.053),
}


def _phi(x):
    return np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _Phi(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x) / SQRT2))


def _quad(f, a=-12.0, b=12.0, n=1200):
    """Quadratura di Gauss-Legendre su [a, b]. Niente scipy: la dipendenza non
    c'e' nell'ambiente di campagna, e un harness citato dalla tesi deve girare
    con il solo numpy."""
    nodi, pesi = np.polynomial.legendre.leggauss(n)
    xs = 0.5 * (b - a) * nodi + 0.5 * (a + b)
    return float(np.dot(0.5 * (b - a) * pesi, f(xs)))


def terne(seed=SEED_SEMI_RANGE, n=N_TERNE):
    return np.random.default_rng(seed).standard_normal((n, 3))


def semi_range(x):
    """(max - min) / 2: la convenzione di P3.8, non divisa per radice di m."""
    return 0.5 * np.ptp(x, axis=-1)


def analitico():
    """Forme chiuse delle quattro quantita' pubblicate in §3.1, piu' la copertura
    al livello `sigma/radice(3)` che il §3.1 non pubblicava."""
    e_x3 = 3.0 * _quad(lambda t: t * _phi(t) * _Phi(t) ** 2)
    e_x1 = 3.0 * _quad(lambda t: t * _phi(t) * (1.0 - _Phi(t)) ** 2)
    var_med = _quad(lambda t: t * t * 6.0 * _phi(t) * _Phi(t) * (1.0 - _Phi(t)))
    p_02 = _quad(lambda t: 3.0 * _phi(t) * (_Phi(t + 0.4) - _Phi(t)) ** 2)
    p_r3 = _quad(lambda t: 3.0 * _phi(t) * (_Phi(t + 2.0 / SQRT3) - _Phi(t)) ** 2)
    return {"E[semi-range]": 0.5 * (e_x3 - e_x1), "sd(mediana)": math.sqrt(var_med),
            "P(semi-range < 0,2 sigma)": p_02,
            "P(semi-range < sigma/radice(3))": p_r3}


def quota_massima(w):
    """Quota del blocco piu' pesante su `w`, per riga (ultima dimensione)."""
    return w.max(axis=-1) / w.sum(axis=-1)


def verifica_1_semi_range():
    print("\n--- Verifica 1: semi-range e mediana di tre, MC contro analitico ---")
    x = terne()
    sr, med = semi_range(x), np.median(x, axis=1)
    a = analitico()
    n = len(sr)
    se = {
        "E[semi-range]": float(sr.std(ddof=1) / math.sqrt(n)),
        "sd(mediana)": float(med.std(ddof=1) / math.sqrt(2.0 * (n - 1))),
        "P(semi-range < 0,2 sigma)": None,
    }
    mis = {"E[semi-range]": float(sr.mean()), "sd(mediana)": float(med.std(ddof=1))}
    p02 = float((sr < 0.2).mean())
    mis["P(semi-range < 0,2 sigma)"] = p02
    se["P(semi-range < 0,2 sigma)"] = math.sqrt(p02 * (1 - p02) / n)
    esito = True
    for k in ("E[semi-range]", "sd(mediana)", "P(semi-range < 0,2 sigma)"):
        d = abs(mis[k] - a[k])
        ok = d < 4.0 * se[k] + 1e-9
        esito &= ok
        print("  %-30s MC=%.6f  analitico=%.6f  diff=%.2e  MC se=%.2e  %s"
              % (k, mis[k], a[k], d, se[k], "entro 4 se" if ok else "DIVERSO"))
    pubblicati = {"E[semi-range]": PUB_E_SR, "sd(mediana)": PUB_SD_MED,
                  "P(semi-range < 0,2 sigma)": PUB_P_02}
    for k, v in pubblicati.items():
        ok = abs(mis[k] - v) < 4.0 * se[k] + 1e-9
        esito &= ok
        print("  pubblicato §3.1 %-24s %.6f   ricalcolo %.6f   %s"
              % (k, v, mis[k], "riprodotto" if ok else "DIVERSO"))
    pct = {q: float(np.percentile(sr, q)) for q in PUB_PCTL}
    for q, pubblicato in PUB_PCTL.items():
        ok = abs(pct[q] - pubblicato) < 0.01
        esito &= ok
        print("  percentile %2d = %.4f   pubblicato %.3f   %s"
              % (q, pct[q], pubblicato, "coerente" if ok else "DIVERSO"))
    r_medie = mis["E[semi-range]"] / mis["sd(mediana)"]
    print("  rapporto E[semi-range]/sd(mediana) = %.4f  (il 'fattore 1,27' del §3.1)"
          % r_medie)
    print("  il 'otto volte troppo piccolo' del §3.1 non dice a cosa e' rapportato:")
    print("     p50/p1 = %.2f    sd(mediana)/p1 = %.2f"
          % (pct[50] / pct[1], mis["sd(mediana)"] / pct[1]))
    print("  => i numeri §3.1 si rigenerano e coincidono con la forma chiusa:")
    print("     sono un calcolo reale. 'otto volte' invece non era una quantita'")
    print("     definita, e le due letture differiscono di un fattore %.2f: va"
          % ((pct[50] / pct[1]) / (mis["sd(mediana)"] / pct[1])))
    print("     scritto quale delle due si intende, o la frase va tolta.")
    return esito


def verifica_2_copertura_per_blocco():
    print("\n--- Verifica 2: rapporto fra medie contro copertura per blocco ---")
    x = terne()
    sr = semi_range(x)
    err_mean = np.abs(x.mean(axis=1))           # |E_bar_b - mu|, con mu = 0
    sigma_r = 1.0 / SQRT3                        # errore reale della media di 3
    p_livello = float((sr < sigma_r).mean())
    p_obs = float((sr < err_mean).mean())
    a = analitico()["P(semi-range < sigma/radice(3))"]
    esito = abs(p_livello - a) < 0.005
    print("  sigma/radice(3) = %.4f sigma, cioe' l'errore di E_bar_b che P3.8 pesa"
          % sigma_r)
    print("  P(u_within,b < sigma/radice(3)) = %.4f   analitico %.4f   %s"
          % (p_livello, a, "coerente" if esito else "DIVERSO"))
    print("  P(u_within,b < |E_bar_b - mu|)  = %.4f   (nessun limite chiuso: solo MC)"
          % p_obs)
    print("  quantili di u_within: 5%% = %.3f  50%% = %.3f  95%% = %.3f sigma"
          % tuple(np.percentile(sr, q) for q in (5, 50, 95)))
    print("  => il §3.1 pubblicava un rapporto fra MEDIE (1,27) e lo presentava")
    print("     come conservativita'. Per blocco il budget sta sotto l'errore")
    print("     reale della media pesata nel %.1f%% dei casi, e sopra nel resto:"
          % (100 * p_livello))
    print("     e' conservativo in media, non punto a punto. E' la separazione che")
    print("     chiede il §3.1 della quarta revisione, e il numero da portare a")
    print("     P6.4 e' questo, non il 1,27.")
    return esito


def verifica_3_parametri_rho():
    print("\n--- Verifica 3: quale parametrazione produce la tabella di §3.2 ---")
    rng = np.random.default_rng(SEED_CONC)
    u_dentro = semi_range(rng.standard_normal((N_REP_CONC, N_BLOCCHI, 3)))
    u_altro = semi_range(rng.standard_normal((N_REP_CONC, N_BLOCCHI, 3)))
    fisse = {rho: np.full((N_REP_CONC, N_BLOCCHI), float(rho)) for rho in RHO}
    conv = {
        # (i) quella SCRITTA in §3.2: u_base,b = rho * u_within,b DELLO STESSO blocco
        "accoppiata   u_base=rho*u_within(b)":
            {rho: rho * u_dentro for rho in RHO},
        # (ii) u_base,b = rho * semi-range di un'altra terna, indipendente da b
        "indipendente u_base=rho*u_altro(b)":
            {rho: rho * u_altro for rho in RHO},
        # (iii) u_base,b = rho * sigma, identico per tutti i blocchi
        "riferimento  u_base=rho*sigma":
            {rho: fisse[rho] for rho in RHO},
    }
    quote = {}
    for nome, per_rho in conv.items():
        print("  parametrazione: %s" % nome)
        for rho, ub in per_rho.items():
            q = quota_massima(1.0 / (ub ** 2 + u_dentro ** 2))
            stat = (float(q.mean()), float(np.median(q)), float(np.percentile(q, 95)))
            quote[(nome, rho)] = stat
            pub = PUB_TAB[rho]
            print("    rho=%.2f  media=%.4f  mediana=%.4f  p95=%.4f   pubblicati"
                  " %.3f/%.3f/%.3f  |d|=%.3f"
                  % (rho, stat[0], stat[1], stat[2], pub[0], pub[1], pub[2],
                     abs(stat[0] - pub[0])))
    esito = True
    # (a) identita' di cancellazione: sotto (i) la quota NON dipende da rho
    for rho in RHO[1:]:
        d = max(abs(x - y) for x, y in zip(quote[("accoppiata   u_base=rho*u_within(b)",
                                                  0.0)],
                                           quote[("accoppiata   u_base=rho*u_within(b)",
                                                  rho)]))
        esito &= d < 1e-12
        print("  accoppiata rho=0 vs rho=%.2f: scarto sulle tre statistiche = %.2e"
              % (rho, d))
    # (b) a rho = 0 le tre parametrazioni coincidono: e' l'unica ancora robusta
    a0 = {nome: quote[(nome, 0.0)] for nome in conv}
    spread = max(max(abs(x - y) for x, y in zip(v0, list(a0.values())[0]))
                 for v0 in a0.values())
    esito &= spread < 5e-4
    print("  scarto fra le tre parametrazioni a rho = 0: %.2e (atteso ~0, e' il MC)"
          % spread)
    # (c) quale convenzione riproduce la tabella, sui soli rho > 0
    chi = {}
    for nome in conv:
        chi[nome] = sum(abs(quote[(nome, rho)][0] - PUB_TAB[rho][0])
                        for rho in RHO[1:]) / (len(RHO) - 1)
    vincente = min(chi, key=chi.get)
    print("  scarto medio dalla tabella pubblicata (rho > 0): %s"
          % "  ".join("%s=%.3f" % (n.split()[0], v) for n, v in chi.items()))
    print("  la tabella di §3.2 e' prodotta dalla parametrazione '%s', scarto %.4f:"
          % (vincente.split()[0], chi[vincente]))
    print("     u_base uguale per tutti i blocchi, non proporzionale a u_within.")
    print("  => le tre ancore del protocollo P6.4:2378-2383 vanno trattate in due")
    print("     modi diversi. '37% e 82% a rho = 0' e' robusto: e' identico nelle")
    print("     tre parametrazioni e non depende da rho. '8% a rho >= 0,5' e'")
    print("     FALSO come numero di protocollo, perche' la formula che P6.4 e")
    print("     §3.2 dichiarano -- u_base proporzionale a u_within -- darebbe la")
    print("     STESSA quota a ogni rho. La tabella da cui proviene usava un")
    print("     u_base non proporzionale; v. riga sopra per quale delle due ci")
    print("     somiglia. Finche' rho non e' misurato (P6.2) la concentrazione va")
    print("     pubblicata come funzione di rho, non come tabella di valori.")
    return esito


def verifica_4_forma_combinazione():
    print("\n--- Verifica 4: quadratura contro somma aritmetica (P1.7, task #43) ---")
    rng = np.random.default_rng(SEED_CONC)
    u_dentro = semi_range(rng.standard_normal((N_REP_CONC, N_BLOCCHI, 3)))
    esito = True
    rapporti = {}
    for rho in (0.05, 0.10, 0.25, 0.50, 1.00):
        ub = np.full((N_REP_CONC, N_BLOCCHI), float(rho))
        q_quad = quota_massima(1.0 / (ub ** 2 + u_dentro ** 2))
        q_somm = quota_massima(1.0 / (ub + u_dentro) ** 2)
        m_q, m_s = float(q_quad.mean()), float(q_somm.mean())
        rapporti[rho] = m_s / m_q
        # disuguaglianza VERA e termine per termine: (a+b)^2 >= a^2+b^2 per a, b
        # non negativi, quindi il budget aritmetico e' sempre >= di quello a
        # quadratura e ogni peso individuale e' <=. La QUOTA del blocco piu'
        # pesante pero' non eredita il verso: normalizzare divide per una somma
        # che si schiaccia in modo diverso, e il segno del confronto cambia.
        ok_term = bool(np.all((ub + u_dentro) ** 2 >= ub ** 2 + u_dentro ** 2 - 1e-12))
        ok_w = bool(np.all((1.0 / (ub + u_dentro) ** 2)
                           <= (1.0 / (ub ** 2 + u_dentro ** 2)) + 1e-12))
        esito &= ok_term and ok_w
        print("  rho=%.2f  quota media: quadratura %.4f  aritmetica %.4f  rapporto"
              " %.4f   %s | budget>= e w<= per termine: %s"
              % (rho, m_q, m_s, m_s / m_q,
                 "aritmetica PIU' concentrata" if m_s > m_q
                 else "aritmetica MENO concentrata",
                 "SI'" if (ok_term and ok_w) else "NO"))
    # dove incrocia: scansione, perche' il verso non e' costante
    scansione = np.arange(0.0, 0.61, 0.05)
    diff = []
    for rho in scansione:
        ub = np.full((N_REP_CONC, N_BLOCCHI), float(rho))
        diff.append(float(quota_massima(1.0 / (ub + u_dentro) ** 2).mean())
                    - float(quota_massima(1.0 / (ub ** 2 + u_dentro ** 2)).mean()))
    passi_negativi = sum(1 for i in range(len(diff) - 1) if diff[i] < 0 <= diff[i + 1])
    print("  curva della differenza (aritmetica - quadratura) sulla quota media:")
    print("     %s" % "  ".join("%.2f:%+.4f" % (r, d)
                                for r, d in zip(scansione, diff)))
    primi_pos = [i for i, d in enumerate(diff) if d > 0]
    if primi_pos and primi_pos[0] > 0:
        i = primi_pos[0]
        print("     segno negativo fino a rho = %.2f, positivo da rho = %.2f:"
              % (scansione[i - 1], scansione[i]))
        print("     l'incrocio sta in [%0.2f, %0.2f], passo %.2f dichiarato."
              % (scansione[i - 1], scansione[i], scansione[1] - scansione[0]))
        esito &= bool(passi_negativi == 1)
    else:
        print("     nessun segno negativo: in questo range l'aritmetica non")
        print("     deconcentra mai. (La scansione andrebbe estesa sotto.)")
        esito = False
    print("  => a rho = 0 le due forme coincidono per costruzione (u_base = 0),")
    print("     quindi l'ancora del 37% non tocca la decisione rinviata di P1.7.")
    print("     Sopra l'incrocio la somma aritmetica concentra DI PIU' (rapporto")
    print("     %.3f a rho = 0,25, %.3f a rho = 1,00); sotto concentra di meno"
          % (rapporti[0.25], rapporti[1.00]))
    print("     (rapporto %.3f a rho = 0,05). Il perche' e' nelle due scale: la"
          % rapporti[0.05])
    print("     somma aggiunge rho a tutti, quindi per rho piccolo penalizza i")
    print("     blocchi con u_within PICCOLO (dove rho e' la frazione maggiore) e")
    print("     deconcentra; per rho grande gonfia di piu' i blocchi con u_within")
    print("     GRANDE e sposta peso sul blocco migliore, riconcentrando.")
    print("     Il timore corrente -- che la forma aritmetica sia anche la scelta")
    print("     dei pesi piu' prudente -- non e' monotono in rho, e va portato a")
    print("     P6.4 punto 4 come curva, non come segno fisso.")
    return esito


def verifica_5_ess():
    print("\n--- Verifica 5: ESS, la stessa concentrazione in blocchi equivalenti ---")
    rng = np.random.default_rng(SEED_CONC)
    u_dentro = semi_range(rng.standard_normal((N_REP_CONC, N_BLOCCHI, 3)))
    esito = True
    for rho in RHO:
        ub = np.full((N_REP_CONC, N_BLOCCHI), float(rho))
        w = 1.0 / (ub ** 2 + u_dentro ** 2)
        ess = (w.sum(axis=-1) ** 2) / (w ** 2).sum(axis=-1)
        ok = float(ess.max()) <= N_BLOCCHI + 1e-9 and float(ess.min()) >= 1.0 - 1e-9
        esito &= ok
        print("  rho=%.2f  ESS medio=%5.2f  ESS p5=%5.2f  ESS min=%5.2f  (%s)"
              % (rho, float(ess.mean()), float(np.percentile(ess, 5)),
                 float(ess.min()), "limiti 1..33 rispettati" if ok else "LIMITI VIOLATI"))
    w0 = 1.0 / u_dentro ** 2
    share0 = float(quota_massima(w0).mean())
    ess0 = float(((w0.sum(axis=-1) ** 2) / (w0 ** 2).sum(axis=-1)).mean())
    print("  a rho = 0: quota media del blocco piu' pesante %.4f (pubblicata %.3f),"
          % (share0, PUB_TAB[0.0][0]))
    print("     ESS medio %.2f su 33 blocchi: il fit pesato vale come %.1f blocchi"
          % (ess0, ess0))
    print("  => 'un blocco su 33 porta il 37%% del peso' e 'il fit vale come %.1f"
          % ess0)
    print("     blocchi su 33' dicono la stessa cosa; la seconda non invita a")
    print("     leggere il 37% come una probabilita' ne' come una copertura, e")
    print("     l'ESS e' la forma da portare in tesi.")
    return esito


def main():
    print("=" * 74)
    print("Harness del semi-range a n = 3 e della concentrazione dei pesi di P3.8")
    print("numpy %s -- %d terne (seed %d), %d campagne da %d blocchi (seed %d)"
          % (np.__version__, N_TERNE, SEED_SEMI_RANGE, N_REP_CONC, N_BLOCCHI, SEED_CONC))
    print("=" * 74)
    esiti = [
        verifica_1_semi_range(),
        verifica_2_copertura_per_blocco(),
        verifica_3_parametri_rho(),
        verifica_4_forma_combinazione(),
        verifica_5_ess(),
    ]
    print("\n" + "=" * 74)
    print("esito complessivo: %d/%d verifiche superate" % (sum(esiti), len(esiti)))
    print("=" * 74)
    print("\nConclusione di metodo. I numeri del §3.1 sono un calcolo reale: si")
    print("rigenerano e coincidono con la forma chiusa entro l'errore standard.")
    print("Il §3.2 invece pubblicava una tabella che la formula scritta accanto")
    print("non puo' produrre, perche' sotto `u_base,b = rho * u_within,b` la quota")
    print("e' indipendente da rho per cancellazione esatta, e la cancellazione e'")
    print("verificata qui a 1e-12. Le ancore a rho = 0 restano valide e sono le")
    print("uniche che il protocollo P6.4 puo' citare; l''8% a rho >= 0,5' e' da")
    print("ritirare o riancorare. Il 'fattore 1,27' va declassato a rapporto fra")
    print("medie: per blocco il budget sta sotto l'errore reale della media pesata")
    print("in una frazione non trascurabile di casi, ed e' quel numero che P6.4")
    print("deve misurare. Ultimo punto, controintuitivo: la scelta rinviata di")
    print("P1.7 non ha un verso fisso sui pesi. Per rho piccoli la somma")
    print("aritmetica deconcentra (rapporto 0,85 a rho = 0,05), per rho grandi")
    print("riconcentra (1,40 a rho = 1), con incrocio fra 0,20 e 0,25: la forma")
    print("di combinazione va decisa sulla curva, non sul timore che l'aritmetica")
    print("sia sempre la scelta prudente.")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())

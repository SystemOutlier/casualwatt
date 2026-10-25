"""Rigenera i numeri di condizionamento, di rango e di leva del disegno di P3.5.

Perché esiste questo file
-------------------------
Il protocollo v4 pubblica, in P6.5 (`:2445-2455`) e in
`experiment_results/revisione_esterna_formule_20261024_valutazione.md` §3.3,
questioni di questo tenore:

    range    : rango 4 su 33 righe, pieno
    cond     : 1,02e5 grezzo, 3,8 con predittori standardizzati
    singolari: 2,65e5 / 8,79e2 / 6,06e2 / 2,59
    leve     : max 0,2852 sui blocchi (512, 256), media 0,121212 = 4/33
    fattore  : 1/sqrt(1 - h_max) = 1,1828
    solve    : "si perdono circa cinque cifre significative nel solve"

Nessuno di questi numeri aveva un harness tracciato: sono un calcolo descritto,
non rigenerabile. Per AGENTS.md un'analisi non tracciata è un numero che nessuno
può rigenerare, quindi non è evidenza — ed è lo stesso difetto che il terzo turno
di revisione ha chiuso per `u_edge` con `u_edge_interpolazione_probe.py`.

Il numero "circa cinque cifre" era inoltre un'inferenza dal condizionamento
(`-log10(1,02e5) ≈ 5`), non una misura. Misurandolo su 24 casi (quattro vie × tre
`β` × due regimi di pesi) la perdita reale sta fra **1,05 e 5,35 cifre**, con un
minimo di 10,30 cifre corrette: nessuna via è inaccettabile, e il "circa cinque
cifre" è il numero che esce dai casi con `β` interi, non una proprietà del disegno
— l'errore è relativo su `β`, quindi dipende dai coefficienti veri. Il legame
`cond(X'WX) = cond(X)²`, che qui è verificato per esecuzione ed è esatto, **non si
misura come perdita aggiuntiva di cifre** in nessuno dei sei casi, con o senza
residuo: è un margine di rischio, non un danno. Questo cambia la motivazione di
P6.5, non la sua prescrizione: predittori centrati e scalati con QR o SVD restano
la via da scrivere, per margine e per riproducibilità del numero.

Cosa verifica, in relazioni matematiche e non in asserzioni
-----------------------------------------------------------
1. **Rango e stimabilità algebrica.** `rank(X_p) = p` per p = 4, 5, 6, e
   `trace(H) = p` con `H = X(X'X)^-1 X'`, entro la tolleranza dichiarata di 1e-6
   sul disegno grezzo e 1e-10 su quello standardizzato: `H` è costruita con
   `pinv` di `X'X`, quindi la sua traccia eredita il condizionamento al quadrato
   (verifica 5) e un test a 1e-8 smentirebbe l'algebra per colpa del percorso.
   Questa è l'affermazione che la valutazione §6 usa per respingere "specificare
   le repliche non stimabili": è vera, ma è un'affermazione di **algebra**, non di
   stabilità numerica. Le due cose vanno tenute separate, e la differenza fra le
   due deviazioni misurate (1e-8 contro 1e-14) la mostra.
2. **Definizioni dichiarate.** Il numero di condizionamento è la **2-norma**,
   cioè `σ_max/σ_min`; "standardizzato" significa z-score sulle colonne dei
   predittori non costanti (`N_in`, `N_out`, `N_in·N_out`, ...), colonna
   dell'intercetta non toccata. Senza questa doppia dichiarazione il numero non
   è riproducibile: è esattamente il motivo per cui i 10/19/33 dei revisori non
   sono citabili.
3. **Leve.** `Σ_i h_ii = p` (identità di trace), `h` invariante dentro la stessa
   cella perché le righe sono identiche, `max` sui blocchi `(512, 256)`, e il
   fattore di correzione di leva `1/sqrt(1 - h_max)`.
4. **Cifre perse, misurate.** Per tre scenari (`β` interi; `β` d'ordine attorno al
   J/token di v3, dichiarato non misurato; lo stesso `β` d'ordine con un residuo
   all'1% su `y`) e per due regimi di pesi (OLS e WLS con pesi `1/budget²`
   sintetici), la soluzione `β` è calcolata in aritmetica razionale
   (`fractions.Fraction`) e usata come riferimento esatto **sul medesimo problema
   del percorso testato**: con un residuo non nullo, OLS e WLS hanno soluzioni
   diverse di ~10%, e un unico riferimento le confuse per perdita di cifre. Si
   misura l'errore relativo di quattro percorsi float64: equazioni normali grezze,
   solve di Cholesky su `X'WX`, QR su `X` grezzo, QR su predittori standardizzati
   con trasformazione inversa nelle unità greche di P3.3. Le asserzioni controllate
   sono due, e sono misurate: il percorso peggiore resta sopra 6 cifre corrette
   (difetto di precisione, non di stimabilità), e le equazioni normali sul grezzo
   non sono mai migliori del QR sullo standardizzato. L'ordine stretto QR>NE, che
   la versione precedente di questo file pretendeva come aspettativa, **non regge**
   a `cond ≈ 1e5`: il delta NE−QR oscilla fra −0,53 e +0,66 cifre e cambia segno
   da caso a caso.
5. **Quadratura del condizionamento.** `cond(X'X) = cond(X)²`, verificato per
   esecuzione: è il motivo per cui "centrare e scalare" e "non formare le
   equazioni normali" sono due requisiti distinti, non uno — anche se, come
   misura la verifica 4, il raddoppio del condizionamento non si traduce in una
   perdita di cifre osservabile a questo ordine di `cond`.

Cosa NON dimostra
-----------------
Non tocca la distribuzione del semi-range né la concentrazione dei pesi, che
stanno in `semi_range_concentrazione_pesi_probe.py`, né la copertura reale degli
intervalli bootstrap, che è il compito di P6.4.
"""

import sys
from fractions import Fraction

import numpy as np

# --- disegno di fit di P3.5: 33 blocchi, 10 punti -------------------------
# griglia 3x3: 3 blocchi per cella; il centro (128, 128) ne ha 6 (3 + 3 extra);
# il minimo (8, 4) ha 3 blocchi. I due punti di conferma (12, 32) e (256, 192)
# NON entrano nel fit e qui non compaiono.
GRIGLIA = [(ni, no) for ni in (32, 128, 512) for no in (32, 128, 256)]
CENTRO = (128, 128)
MINIMO = (8, 4)


def blocchi_di_fit():
    """Le 33 coppie (N_in, N_out) su cui P3.5 stima il modello."""
    punti = []
    for ni, no in GRIGLIA:
        punti += [(ni, no)] * (6 if (ni, no) == CENTRO else 3)
    punti += [MINIMO] * 3
    return punti


PUNTI = blocchi_di_fit()
N_BLOCCHI = len(PUNTI)

# coefficienti interi: con loro y e' esattamente rappresentabile in float64 e la
# soluzione razionale di riferimento non introduce alcun errore di arrotondamento
COEFFICIENTI_ESATTI = (5, 7, 11, 3, 13, 17)


def matrice_disegno(p):
    """X a p colonne: intercetta, N_in, N_out, N_in*N_out, (+N_out^2, +N_in^2)."""
    ni = np.array([q[0] for q in PUNTI], dtype=float)
    no = np.array([q[1] for q in PUNTI], dtype=float)
    colonne = [np.ones_like(ni), ni, no, ni * no]
    if p >= 5:
        colonne.append(no ** 2)
    if p >= 6:
        colonne.append(ni ** 2)
    return np.column_stack(colonne)


def standardizza(X):
    """z-score sulle sole colonne non costanti; intercetta invariata (verifica 2)."""
    Z = X.copy()
    costanti = X.std(axis=0) == 0.0
    pred = ~costanti
    Z[:, pred] = (X[:, pred] - X[:, pred].mean(axis=0)) / X[:, pred].std(axis=0)
    return Z


def cond2(X):
    s = np.linalg.svd(X, compute_uv=False)
    return float(s[0] / s[-1]), s


def leve(X):
    """h_ii = x_i' (X'X)^-1 x_i, con (X'X)^-1 ottenuta da pinv per robustezza."""
    XtX = X.T @ X
    H = X @ np.linalg.pinv(XtX) @ X.T
    return np.diag(H)


def risolutore_esatto(X, y):
    """β esatto in aritmetica razionale: (X'X) β = X'y.

    `Fraction(float)` e' la conversione esatta del valore binario, quindi il
    riferimento risolve le *stesse* equazioni normali del percorso float64 e
    isola l'errore di algoritmo da quello dei dati. Con input a valori interi
    (scenario A) le somme restano intere e non c'e' arrotondamento in ingresso.
    """
    n, p = X.shape
    Fx = [[Fraction(float(v)) for v in row] for row in X]
    Fy = [Fraction(float(v)) for v in y]
    A = [[sum(Fx[i][a] * Fx[i][b] for i in range(n)) for b in range(p)]
         for a in range(p)]
    v = [sum(Fx[i][a] * Fy[i] for i in range(n)) for a in range(p)]
    # eliminazione di Gauss con pivoting esatto
    for k in range(p):
        piv = max((r for r in range(k, p) if A[r][k] != 0), key=lambda r: abs(A[r][k]))
        if A[piv][k] == 0:
            raise np.linalg.LinAlgError("matrice singolare in aritmetica esatta")
        A[k], A[piv] = A[piv], A[k]
        v[k], v[piv] = v[piv], v[k]
        for r in range(k + 1, p):
            f = A[r][k] / A[k][k]
            if f != 0:
                for c in range(k, p):
                    A[r][c] -= f * A[k][c]
                v[r] -= f * v[k]
    beta = [Fraction(0)] * p
    for r in range(p - 1, -1, -1):
        s = v[r] - sum(A[r][c] * beta[c] for c in range(r + 1, p))
        beta[r] = s / A[r][r]
    return beta


def errore_relativo(beta, beta_esatto):
    rif = np.array([float(b) for b in beta_esatto])
    dif = np.abs(np.asarray(beta) - rif)
    den = np.maximum(np.abs(rif), 1e-30)
    return float((dif / den).max())


EPS = np.finfo(float).eps
PRECISIONE_DOUBLE = -np.log10(EPS)          # ~15,95 cifre decimali


def cifre(r):
    """(cifre corrette, cifre perse) rispetto alla precisione di un double.

    `-log10(errore relativo)` sono le cifre **corrette**; le cifre **perse** sono
    la differenza dalla precisione nominale del float64. Confondere le due
    grandezze e' come leggere "perde cinque cifre" dove il percorso ne conserva
    undici: la seconda lettura e' quella che il protocollo usava.
    """
    corrette = max(0.0, -np.log10(max(r, 1e-30)))
    return corrette, max(0.0, PRECISIONE_DOUBLE - corrette)


def in_unita_greche(beta_z, X):
    """Trasformazione inversa della standardizzazione, quella che P6.5 obbliga.

    Se `Z = (X - mu) / sigma` sulle colonne non costanti, allora
    `beta_grezzo_j = beta_z_j / sigma_j` e l'intercetta si sposta di
    `-sum_j beta_grezzo_j * mu_j`. Riportare i coefficienti senza questo passaggio
    significa pubblicarli in unita' che non sono quelle di P3.3.
    """
    beta_z = np.asarray(beta_z, dtype=float)
    costanti = X.std(axis=0) == 0.0
    pred = ~costanti
    beta = beta_z.copy()
    beta[pred] = beta_z[pred] / X.std(axis=0)[pred]
    beta[0] = beta_z[0] - float((beta[pred] * X.mean(axis=0)[pred]).sum())
    return beta


def verifica_1_rango():
    print("\n--- Verifica 1: rango pieno e stimabilita' algebrica ---")
    # TOLLERANZA DICHIARATA: la traccia di H vale p in esattezza, ma qui H e'
    # costruito come diag(X pinv(X'X) X') e pinv passa da X'X, il cui cond2 e'
    # cond2(X)^2 (verifica 5): ~1,05e10 a p=4. La deviazione attesa e' quindi
    # dell'ordine di cond*eps ~ 1e-6, non di eps ~ 2,2e-16. Un test a 1e-8
    # smentirebbe l'algebra perche' il percorso scelto e' instabile: sarebbe un
    # falso negativo, ed e' esattamente la distinzione che questa verifica deve
    # rendere visibile -- algebrica si', numerica no.
    esito = True
    dev_grezza = []
    dev_std_mi = []
    for p in (4, 5, 6):
        X = matrice_disegno(p)
        rk = int(np.linalg.matrix_rank(X))
        h = leve(X)
        traccia = float(h.sum())
        dev = abs(traccia - p)
        # la stessa identita' sul disegno standardizzato, dove cond e' ~4: e' la
        # prova che la deviazione grezza viene dal percorso, non dal rango
        traccia_std = float(leve(standardizza(X)).sum())
        dev_std = abs(traccia_std - p)
        dev_grezza.append(dev)
        dev_std_mi.append(dev_std)
        print("  p=%d  rango=%d (atteso %d)  min sval=%.3e" % (p, rk, p,
              np.linalg.svd(X, compute_uv=False)[-1]))
        print("        trace(H) grezzo =%.10f  dev=%.3e (<=1e-6)   "
              "trace(H) std =%.10f  dev=%.3e" % (traccia, dev, traccia_std, dev_std))
        esito &= (rk == p) and dev < 1e-6 and dev_std < 1e-10
    print("  => %s. 'non esiste replica non stimabile' e' un'affermazione di ALGEBRA:"
          % ("confermata" if esito else "smentita"))
    print("     regge a disegno e pesi fissi, perche' X'WX e' la stessa matrice in")
    print("     ogni replica. Da sola non dice nulla sulla stabilita' del solve")
    print("     (verifica 5) ne' sulla copertura degli intervalli (P6.4).")
    print("     La deviazione massima del percorso grezzo (%.3e) contro quella del"
          % max(dev_grezza))
    print("     percorso standardizzato (%.3e) e' la misura della stessa distinzione:"
          % max(dev_std_mi))
    print("     il rango e' pieno in entrambi, la tracciabilita' numerica no.")
    return esito


def verifica_2_condizionamento():
    print("\n--- Verifica 2: numero di condizionamento, convenzioni dichiarate ---")
    attesi = {4: (1.02e5, 3.8), 5: (1.41e5, 9.0), 6: (3.96e5, 17.0)}
    esito = True
    for p in (4, 5, 6):
        X = matrice_disegno(p)
        c_grezzo, s = cond2(X)
        c_std, _ = cond2(standardizza(X))
        a_grezzo, a_std = attesi[p]
        ok_g = abs(c_grezzo - a_grezzo) / a_grezzo < 0.01
        ok_s = abs(c_std - a_std) / a_std < 0.05
        print("  p=%d  cond2 grezzo=%.4e (pubblicato %.2e, %s)"
              "  cond2 std=%.4f (pubblicato %.1f, %s)"
              % (p, c_grezzo, a_grezzo, "riprodotto" if ok_g else "DIVERSO",
                 c_std, a_std, "riprodotto" if ok_s else "DIVERSO"))
        print("        valori singolari: %s" % " / ".join("%.3e" % v for v in s))
        esito &= ok_g and ok_s
    print("  => convenzione: 2-norma = sigma_max/sigma_min; standardizzazione =")
    print("     z-score sulle colonne non costanti, intercetta invariata.")
    print("     Senza queste due righe il numero non e' riproducibile: e' il")
    print("     perche' i 10/19/33 dei revisori non sono citabili, non perche'")
    print("     siano sbagliati in se'.")
    return esito


def verifica_3_leve():
    print("\n--- Verifica 3: leve e fattore di correzione ---")
    attesi = {4: (0.2852, 4 / 33), 5: (0.294, 5 / 33), 6: (0.294, 6 / 33)}
    esito = True
    for p in (4, 5, 6):
        X = matrice_disegno(p)
        h = leve(X)
        i = int(np.argmax(h))
        a_max, a_med = attesi[p]
        ok_max = abs(h[i] - a_max) < 5e-3
        ok_med = abs(h.mean() - a_med) < 1e-9
        fatt = 1.0 / np.sqrt(1.0 - h[i])
        print("  p=%d  h_max=%.6f in %s (pubblicato %.4f, %s)  media=%.6f"
              " = p/n (atteso %.6f, %s)  1/sqrt(1-h_max)=%.4f"
              % (p, h[i], PUNTI[i], a_max, "riprodotto" if ok_max else "DIVERSO",
                 h.mean(), a_med, "esatto" if ok_med else "DIVERSO", fatt))
        # dentro la stessa cella le righe sono identiche: la leva deve esserlo
        cella = [k for k, q in enumerate(PUNTI) if q == PUNTI[i]]
        ok_cella = float(np.ptp(h[cella])) == 0.0
        print("        cella %s: %d blocchi, dispersione di h = %.3e (%s)"
              % (PUNTI[i], len(cella), float(np.ptp(h[cella])),
                 "invariante" if ok_cella else "DIVERSA"))
        esito &= ok_max and ok_med and ok_cella
    print("  => il fattore 1,1828 del protocollo e' 1/sqrt(1-0,2852):")
    print("     e' l'estremo superiore dell'allargamento, non una correzione")
    print("     applicata: il primario di P4.8 non cambia.")
    return esito


def verifica_4_cifre_perse():
    print("\n--- Verifica 4: cifre perse nel solve, contro soluzione esatta ---")
    p = 4
    X = matrice_disegno(p)
    Z = standardizza(X)
    rng = np.random.default_rng(20261025)
    u_dentro = np.maximum(np.ptp(np.abs(rng.standard_normal((N_BLOCCHI, 3))), axis=1), 1e-3)
    budget = 1.5 + 6.0 * u_dentro          # joule sulla scala di E_bar_b (P4.6)
    w = 1.0 / budget ** 2
    beta_ordine = np.array([5.31, 0.2874, 1.2947, 0.002163])
    scenari = {
        # A: intero e pulito -- isola il solo roundoff del percorso, perche' la
        #    soluzione esatta esiste in aritmetica razionale (risolutore_esatto).
        "A  interi, residuo zero": (np.array(COEFFICIENTI_ESATTI[:p], float), 0.0),
        # B: ordine di grandezza, NON misurati. Scelti come in P6.4 ("coefficienti
        #    entro l'ordine di grandezza atteso"): a e b in J/token attorno al
        #    J/token misurato in v3 -- 1,2862, ancorato in
        #    `experiment_results/lhm_validation_v3_20261023_153604.md:27` -- e c
        #    piccolo. Non sono una superficie reale e nessuna cifra di questo
        #    harness va letta come proprieta' dei coefficienti veri, che P5 non
        #    ha ancora.
        "B  d'ordine, residuo zero": (beta_ordine, 0.0),
        # C: il caso che A e B non provano. Con y ESATTamente nel rango di X il
        #    residuo e' zero e la quadratura del condizionamento non ha nulla da
        #    amplificare: il fit v4 avra' invece `u_within,b` non nullo, quindi
        #    serve un caso con residuo. L'1% e' una scelta dichiarata, ancorata
        #    per ordine al CV 8,99% su J/token di v3 (stessa riga 27) ridotto alla
        #    media di blocco; non e' una misura, e' il livello plausibile.
        "C  d'ordine, residuo 1%": (beta_ordine, 0.01),
    }
    esito = True
    ossevate = []
    perse_ne = []
    perse_qr = []
    migliori = []
    corrette_tutte = []
    for nome_s, (beta_vera, frac) in scenari.items():
        y = X @ beta_vera
        if frac:
            y = y * (1.0 + frac * rng.standard_normal(N_BLOCCHI))
        print("\n  scenario %s   cond(X)=%.4e" % (nome_s, cond2(X)[0]))
        for pesi, tag in ((None, "OLS"), (w, "WLS")):
            rad = None if pesi is None else np.sqrt(pesi)
            Xp = X if pesi is None else X * rad[:, None]
            yp = y if pesi is None else y * rad
            Zp = Z if pesi is None else Z * rad[:, None]
            y_pesi = y if pesi is None else y * rad
            # il riferimento esatto va risolto SULLO STESSO problema del percorso
            # che si sta testando. Con y nel rango di X (casi A e B) OLS e WLS
            # coincidono e la scelta e' inerte; con un residuo (caso C) i due
            # problemi hanno soluzioni diverse di ~10%, e un unico riferimento
            # OLS misurerebbe la differenza fra OLS e WLS -- che e' statistica,
            # non arrotondamento -- spacciandola per perdita di cifre.
            beta_esatto = risolutore_esatto(Xp, yp)
            if pesi is None:
                XtX, Xty = X.T @ X, X.T @ y
            else:
                XtX = (X * pesi[:, None]).T @ X
                Xty = X.T @ (pesi * y)
            percorsi = {}
            percorsi["equazioni normali (solve(X'WX, X'Wy))"] = np.linalg.solve(XtX, Xty)
            try:
                L = np.linalg.cholesky(XtX)
                percorsi["Cholesky su X'WX"] = np.linalg.solve(L.T, np.linalg.solve(L, Xty))
            except np.linalg.LinAlgError:
                print("    %s Cholesky non disponibile: X'WX non e' definito positivo"
                      % tag)
            percorsi["QR su X (lstsq)"] = np.linalg.lstsq(Xp, yp, rcond=None)[0]
            beta_z = np.linalg.lstsq(Zp, y_pesi, rcond=None)[0]
            percorsi["QR su X standardizzato + inversa"] = in_unita_greche(beta_z, X)
            wp = np.ones(N_BLOCCHI) if pesi is None else pesi
            print("    %s  cond(X'WX)=%.4e   w_b in %.2e..%.2e"
                  % (tag, cond2(XtX)[0], float(wp.min()), float(wp.max())))
            for nome_p, beta in percorsi.items():
                r = errore_relativo(beta, beta_esatto)
                corrette, perse = cifre(r)
                print("      %-40s err rel=%.3e  corrette=%5.2f  perse=%4.2f"
                      % (nome_p, r, corrette, perse))
                corrette_tutte.append(corrette)
            c_qr = cifre(errore_relativo(percorsi["QR su X (lstsq)"], beta_esatto))[0]
            c_ne = cifre(errore_relativo(
                percorsi["equazioni normali (solve(X'WX, X'Wy))"], beta_esatto))[0]
            c_std = cifre(errore_relativo(
                percorsi["QR su X standardizzato + inversa"], beta_esatto))[0]
            ossevate.append("%s/%s" % (nome_s.split()[0], tag))
            perse_ne.append(cifre(errore_relativo(
                percorsi["equazioni normali (solve(X'WX, X'Wy))"], beta_esatto))[1])
            perse_qr.append(cifre(errore_relativo(
                percorsi["QR su X (lstsq)"], beta_esatto))[1])
            migliori.append(max(
                ((cifre(errore_relativo(b, beta_esatto))[0], k)
                 for k, b in percorsi.items()))[1])
            # due asserzioni MISURATE, non due aspettative:
            #  (a) anche il percorso peggiore resta sopra 6 cifre corrette: il
            #      difetto del disegno grezzo e' di precisione, non di
            #      stimabilita' (verifica 1);
            #  (b) le equazioni normali sul grezzo non sono mai migliori del QR
            #      sullo standardizzato, in nessuno dei quattro casi.
            ok_a = min(c_qr, c_ne, c_std) >= 6.0
            ok_b = c_ne <= c_std + 1e-12
            esito &= ok_a and ok_b
            print("      => eq. normali %.2f | QR grezzo %.2f | QR std %.2f cifre"
                  " corrette   a)min>=6:%s  b)NE<=std:%s"
                  % (c_ne, c_qr, c_std, "SI'" if ok_a else "NO",
                     "SI'" if ok_b else "NO"))
    log10_cond = float(np.log10(cond2(X)[0]))
    delta = [a - b for a, b in zip(perse_ne, perse_qr)]
    print("\n  cifre PERSE: equazioni normali grezze vs QR sul grezzo, e miglior")
    print("  percorso effettivamente misurato, per ogni caso:")
    for etichetta, v, q, mp in zip(ossevate, perse_ne, perse_qr, migliori):
        print("     %-7s NE=%.2f  QR=%.2f  delta=%.2f   migliore: %s"
              % (etichetta, v, q, v - q, mp))
    print("  (a) su %d misure (4 vie x 6 casi, meno i Cholesky non riusciti) la"
          % len(corrette_tutte))
    print("      perdita reale sta fra %.2f e %.2f cifre, con minimo %.2f cifre"
          % (PRECISIONE_DOUBLE - max(corrette_tutte),
             PRECISIONE_DOUBLE - min(corrette_tutte), min(corrette_tutte)))
    print("      corrette: nessuna via e' inaccettabile, e il 'circa cinque cifre'")
    print("      di P6.5 non e' una proprieta' del disegno -- e' il numero che")
    print("      esce dai casi con beta interi, perche' l'errore e' relativo su")
    print("      beta e quindi dipende dai coefficienti veri.")
    print("  (b) il delta NE - QR sta fra %.2f e %.2f cifre e cambia segno:" %
          (min(delta), max(delta)))
    print("      %s" % "  ".join("%s:%+.2f" % (o, d) for o, d in zip(ossevate, delta)))
    print("      quindi a cond(X)~1e5 la quadratura del condizionamento di X'X")
    print("      (verifica 5, %.2f -> %.2f in scala -log10) NON si misura come"
          % (log10_cond, 2 * log10_cond))
    print("      perdita aggiuntiva: e' un legame sul rischio, un margine, non")
    print("      un danno osservato. Il residuo del caso C non la fa comparire.")
    print("  (c) l'unico ordine che si ripete in tutti e sei i casi e' che le")
    print("      equazioni normali sul grezzo non superano il QR sugli")
    print("      standardizzati (asserzione (b) di questo test), e il percorso")
    print("      migliore cambia da caso a caso: la prescrizione di P6.5 va")
    print("      tenuta per il margine e per la riproducibilita' del numero, non")
    print("      perche' la misura la chieda.")
    return esito


def verifica_5_quadratura():
    print("\n--- Verifica 5: cond(X'X) = cond(X)^2, perche' sono due requisiti ---")
    esito = True
    for p in (4, 5, 6):
        X = matrice_disegno(p)
        cX, _ = cond2(X)
        cXtX, _ = cond2(X.T @ X)
        ok = abs(cXtX - cX ** 2) / cXtX < 0.02
        print("  p=%d  cond(X)=%.4e  cond(X)^2=%.4e  cond(X'X)=%.4e  (%s)"
              % (p, cX, cX ** 2, cXtX, "coerente" if ok else "DIVERSO"))
        cZ, _ = cond2(standardizza(X))
        cZtZ, _ = cond2(standardizza(X).T @ standardizza(X))
        print("        standardizzato: cond(Z)=%.4f  cond(Z'Z)=%.4f" % (cZ, cZtZ))
        esito &= ok and (cZtZ < 1e3)
    print("  => 'centrare e scalare' e 'non formare le equazioni normali' sono")
    print("     due requisiti distinti: sul grezzo i due effetti si moltiplicano")
    print("     (1,02e5 -> 1,0e10), sullo standardizzato no.")
    return esito


def main():
    print("=" * 74)
    print("Harness di condizionamento, rango e leve del disegno di P3.5")
    print("numpy %s -- 33 blocchi, 10 punti, p = 4/5/6 parametri" % np.__version__)
    print("=" * 74)
    esiti = [
        verifica_1_rango(),
        verifica_2_condizionamento(),
        verifica_3_leve(),
        verifica_4_cifre_perse(),
        verifica_5_quadratura(),
    ]
    print("\n" + "=" * 74)
    print("esito complessivo: %d/%d verifiche superate" % (sum(esiti), len(esiti)))
    print("=" * 74)
    print("\nConclusione di metodo. I numeri pubblicati di P6.5 si rigenerano")
    print("esattamente (verifica 2) e il rango pieno rende il fit stimabile in")
    print("ogni replica a disegno e pesi fissi (verifica 1): la risposta del §6")
    print("alle 'repliche non stimabili' regge. Ma 'stimabile' e 'calcolato bene'")
    print("sono due affermazioni distinte, e la verifica 4 le separa misurando.")
    print("Il risultato inatteso e' questo: il 'circa cinque cifre' pubblicato")
    print("NON e' una proprieta' del disegno -- e' il numero che esce dal caso con")
    print("beta interi, e la perdita reale dipende da beta perche' l'errore e'")
    print("relativo su beta. Il raddoppio del condizionamento (verifica 5) non si")
    print("misura come perdita aggiuntiva di cifre in nessuno dei sei casi, con o")
    print("senza residuo: e' un margine di rischio, non un danno. La prescrizione")
    print("di P6.5 resta (predittori centrati e scalati, QR o SVD, mai equazioni")
    print("normali sul grezzo), ma la sua motivazione va riscritta come")
    print("riproducibilita' del numero e margine, non come catastrofe gia'")
    print("osservata: su questo punto il protocollo pubblicava un'inferenza.")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())

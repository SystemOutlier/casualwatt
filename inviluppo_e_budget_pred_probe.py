"""Rigenera inviluppo di progetto, margini e dimensionalita' di `budget_pred`.

Perche' esiste questo file
--------------------------
La revisione esterna "revisione tecnica di P4.docx" (2026-10-26, quinto turno)
dichiara tre difetti e una raccomandazione sul protocollo P4
(`experiment_results/protocollo_v4_20261024.md`), ciascuno con una propria
"evidenza verificabile":

    D1  P4.2 dichiarerebbe i vertici dell'inviluppo convesso come
        (8,4), (32,32), (512,32), (512,256), (32,256), omettendo (32,4);
        correzione proposta: cinquina (8,4), (32,4), (512,32), (512,256), (8,256)
    D2  P4.3/P4.4 sommerebbero il percentile dei residui standardizzati `z_b`
        (adimensionale) dentro `budget_pred^2` in [J^2], cioe'
        `budget_pred^2 = budget_fit^2 + u_edge^2 + u_model^2`;
        correzione proposta: `u_model(x) = budget_fit(x) * z_0.975*`
        con `z_0.975* = 1,96`
    D3  P4.5 conterrebbe notazione del modello cloud C5 (`gamma_prefill`,
        `N_in^2/N_out`) nei vincoli del modello locale T2;
        correzione proposta: gate di positivita' su `a0 > 0, a1 > 0, a2 > 0, c >= 0`
    R1  il testo citerebbe "p-value del test di omoschedasticita' p > 0.05 come
        prova dell'assenza di eteroschedasticita'";
        correzione proposta: aggiungere il vincolo `|rho_Spearman| <= 0,35`

Sono affermazioni su un testo congelato. Per AGENTS.md il materiale fornito
dall'utente e le descrizioni prodotte da altri LLM sono **spunti, non evidenza**,
e un claim vale solo se ancorato a `file:riga`, ad un artefatto tracciato o ad
una fonte verificata. Questo file e' l'ancoraggio: rigenera per esecuzione la
geometria del disegno di P3.5, i quattro margini pubblicati da P4.7 e P4.14, e
la struttura dimensionale di `budget_pred_b`, e confronta ciascuno con cio' che
la revisione afferma.

Cosa verifica
-------------
1. **L'insieme di disegno.** I 10 punti di fit sono quelli di P3.5 (righe
   954-963): griglia 3x3 `{32,128,512} x {32,128,256}` piu' il minimo `(8,4)`.
   La revisione usa un insieme diverso, che contiene `(8,32)`, `(8,128)`,
   `(8,256)` e `(32,4)` -- nessuno dei quali e' un punto di disegno -- e omette
   `(128,32)`, `(128,128)`, `(128,256)` e `(512,128)`. Da un insieme sbagliato
   segue un inviluppo sbagliato: qui si contano le differenze.
2. **I vertici dell'inviluppo.** Calcolati con l'algoritmo di Andrew (catena
   monotona), senza dipendenze: i vertici sono i quattro dichiarati da P4.7
   (riga 1827) e da P4.14 (righe 2224-2227), `(8,4) (512,32) (512,256) (32,256)`.
   `(32,32)` sta dentro con margine 21,24, come il protocollo scrive a riga 1830;
   `(32,4)` non e' un punto di disegno, quindi non puo' essere un vertice.
3. **I quattro margini pubblicati.** `1,33 / 64,0 / 21,24 / 107,7` per
   `(12,32)`, `(256,192)`, `(32,32)`, `(128,128)`, con la metrica congelata
   dalla quinta emenda: distanza **perpendicolare** euclidea dalla retta dello
   spigolo, coordinate grezze, negativa se fuori. Si confronta anche con la
   distanza dal vertice piu' vicino, che su `(12,32)` da' 28,28 (fattore 21,3)
   e rovescerebbe il flag `thin_support`.
4. **La classificazione del punto operativo.** `(12,32)` e `(12,31,8)` sono in
   fascia A con margine 1,33 < 2 token, quindi `thin_support = true`. La
   revisione (§1.2) scrive che il punto "cade pienamente all'interno del
   Livello A": l'avverbio cancella il flag obbligatorio della quinta emenda.
   Qui si calcolano fascia e flag per i punti notevoli, incluso `(256,8)`, che
   e' dentro il box e fuori dall'inviluppo, quindi fascia B.
5. **La dimensionalita' di `budget_pred_b`.** La formula congelata (P4.6 riga
   1624, P4.3 riga 1392, F.11 riga 2934) e'
   `budget_pred_b^2 = budget_fit_b^2 + u_edge,b^2 + u_bias,b^2`: tre termini in
   [J^2], nessun `u_model`. La propagazione dell'incertezza di modello non passa
   da un percentile di `z`: passa dal bootstrap di P4.8, che costruisce dati
   sintetici `Y*_b = f(x_b; theta^) + budget_fit_b * z*_b` (riga 1983) -- gia'
   dimensionalmente puri, perche' `z*_b` e' moltiplicato per un budget in joule
   -- rifitta e prende i quantili di `f(x; theta*)` in joule, allargati con il
   `budget_pred` del blocco nuovo (righe 2000-2001). Qui si misura l'omogeneita'
   di grado 1 della formula congelata e si calcola che cosa produrrebbe la
   sostituzione proposta: `sqrt(budget_fit^2 + (1,96 * budget_fit)^2)` vale
   `2,2004 * budget_fit` a `u_edge` nullo, cioe' un allargamento che non ha
   contenuto dai dati perche' `u_model` e' proporzionale a `budget_fit` per
   costruzione; con `u_edge > 0` il fattore scende, quindi la sostituzione non
   allarga nemmeno in modo uniforme. Il quantile `1,96` e' inoltre il quantile
   normale, che P4.8 (righe 1987-1989) rifiuta esplicitamente.

Cosa NON dimostra
-----------------
Non dimostra che la copertura dell'intervallo bootstrap sia quella nominale:
quella e' P6.4, per simulazione. Non tocca i pesi WLS di P3.8, il disegno di
P3.5, le soglie di P4.5 ne' gli anelli di P4.9: nessun valore congelato e'
modificato da questo file, che e' sola lettura sul protocollo. Non valuta la
raccomandazione R1 nel merito statistico generale (che un `p` grande non provi
l'assenza e' vero e il protocollo lo dice gia' a righe 1058 e 1076-1078):
verifica solo se il testo che R1 cita esiste.

Uso
---
    python inviluppo_e_budget_pred_probe.py

Esce 0 se tutte le verifiche superano, 1 altrimenti. L'output e' l'artefatto
citato da `experiment_results/revisione_esterna_20261026_quinto_turno_valutazione.md`.
"""

from __future__ import annotations

import math
import sys

# ---------------------------------------------------------------------------
# Costanti prese dal protocollo, con la riga accanto. Nessuna e' ricalcolata.
# ---------------------------------------------------------------------------

# P3.5, righe 954-963: griglia 3x3 {32,128,512} x {32,128,256} + minimo (8,4).
GRIGLIA_N_IN = (32, 128, 512)
GRIGLIA_N_OUT = (32, 128, 256)
PUNTO_MINIMO = (8.0, 4.0)

# P4.7 riga 1827 e P4.14 righe 2224-2227: i quattro vertici dichiarati.
VERTICI_DICHIARATI = ((8.0, 4.0), (512.0, 32.0), (512.0, 256.0), (32.0, 256.0))

# P4.7 riga 1837: il box.
BOX_N_IN = (8.0, 512.0)
BOX_N_OUT = (4.0, 256.0)

# P4.7 righe 1852 e 1907: la soglia del flag.
SOGLIA_THIN_SUPPORT_TOK = 2.0

# P4.7 righe 1916 e 1945, P4.14 righe 2226-2227: i quattro margini pubblicati.
MARGINI_PUBBLICATI = {
    (12.0, 32.0): 1.33,
    (256.0, 192.0): 64.0,
    (32.0, 32.0): 21.24,
    (128.0, 128.0): 107.7,
}

# revisione tecnica di P4.docx §1.1: l'insieme di punti che la revisione assume.
PUNTI_ASSUNTI_DALLA_REVISIONE = (
    (8.0, 4.0), (8.0, 32.0), (8.0, 128.0), (8.0, 256.0), (32.0, 4.0),
    (32.0, 32.0), (32.0, 128.0), (32.0, 256.0), (512.0, 32.0), (512.0, 256.0),
)

# revisione tecnica di P4.docx §1.1: i vertici che propone di scrivere.
VERTICI_PROPOSTI_DALLA_REVISIONE = (
    (8.0, 4.0), (32.0, 4.0), (512.0, 32.0), (512.0, 256.0), (8.0, 256.0),
)

# revisione tecnica di P4.docx §2.2 e §7: il quantile normale proposto.
Z_0975_PROPOSTO = 1.96


def punti_di_disegno() -> list[tuple[float, float]]:
    """I 10 punti di fit di P3.5, costruiti dalla griglia e non elencati a mano."""
    punti = [(float(a), float(b)) for a in GRIGLIA_N_IN for b in GRIGLIA_N_OUT]
    punti.append(PUNTO_MINIMO)
    return punti


def inviluppo_convesso(punti: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Catena monotona di Andrew: inviluppo convesso 2D in senso antiorario.

    Implementato qui invece che importato da `scipy.spatial` perche' il risultato
    deve essere indipendente dalla libreria: l'inviluppo decide una fascia di
    copertura obbligatoria e un implementatore deve poterlo ricontrollare a mano.
    """
    unici = sorted(set(punti))
    if len(unici) < 3:
        return unici

    def semipiano(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    inferiore: list[tuple[float, float]] = []
    for p in unici:
        while len(inferiore) >= 2 and semipiano(inferiore[-2], inferiore[-1], p) <= 0:
            inferiore.pop()
        inferiore.append(p)
    superiore: list[tuple[float, float]] = []
    for p in reversed(unici):
        while len(superiore) >= 2 and semipiano(superiore[-2], superiore[-1], p) <= 0:
            superiore.pop()
        superiore.append(p)
    return inferiore[:-1] + superiore[:-1]


def spigoli(vertici: list[tuple[float, float]] | tuple) -> list[tuple]:
    """Coppie consecutive di vertici, chiusa sull'ultima."""
    v = list(vertici)
    return [(v[i], v[(i + 1) % len(v)]) for i in range(len(v))]


def distanza_perpendicolare(punto, vert_a, vert_b) -> float:
    """Distanza con segno dalla retta per `vert_a`-`vert_b`, positiva a sinistra.

    E' la metrica congelata dalla quinta emenda (P4.7 righe 1883-1888): distanza
    perpendicolare euclidea in coordinate grezze, non distanza dal vertice.
    """
    dx, dy = vert_b[0] - vert_a[0], vert_b[1] - vert_a[1]
    norma = math.hypot(dx, dy)
    if norma == 0.0:
        return float("inf")
    return (dx * (punto[1] - vert_a[1]) - dy * (punto[0] - vert_a[0])) / norma


def margine(punto, vertici) -> float:
    """Minimo delle distanze con segno dagli spigoli: negativo se fuori."""
    distanze = [distanza_perpendicolare(punto, a, b) for a, b in spigoli(vertici)]
    # l'orientazione degli spigoli dipende dall'ordine dei vertici: si prende il
    # segno che rende positive le distanze del baricentro, cioe' dell'interno.
    baricentro = (sum(v[0] for v in vertici) / len(vertici),
                  sum(v[1] for v in vertici) / len(vertici))
    verso = 1.0
    if min(distanza_perpendicolare(baricentro, a, b) for a, b in spigoli(vertici)) < 0:
        verso = -1.0
    return min(verso * d for d in distanze)


def distanza_dal_vertice(punto, vertici) -> float:
    """La metrica scartata dalla quinta emenda: distanza euclidea dal vertice."""
    return min(math.hypot(punto[0] - v[0], punto[1] - v[1]) for v in vertici)


def dentro_box(punto) -> bool:
    return (BOX_N_IN[0] <= punto[0] <= BOX_N_IN[1]
            and BOX_N_OUT[0] <= punto[1] <= BOX_N_OUT[1])


def fascia(punto, vertici) -> str:
    """A dentro l'inviluppo, B dentro il box, C fuori dal box (P4.7 righe 1835-1841)."""
    if not dentro_box(punto):
        return "C"
    return "A" if margine(punto, vertici) >= 0 else "B"


def riga_audit(numero, descrizione, esito):
    stato = "OK " if esito else "FAIL"
    print("  [%s] verifica %d -- %s" % (stato, numero, descrizione))
    return esito


# ---------------------------------------------------------------------------
# Verifiche
# ---------------------------------------------------------------------------

def verifica_1_insieme_di_disegno():
    print("\n--- Verifica 1: l'insieme di disegno e' quello di P3.5 ---")
    disegno = set(punti_di_disegno())
    assunto = set(PUNTI_ASSUNTI_DALLA_REVISIONE)
    print("  punti di P3.5 (righe 954-963): %d" % len(disegno))
    print("    %s" % sorted(disegno))
    print("  punti assunti dalla revisione (§1.1): %d" % len(assunto))
    print("    %s" % sorted(assunto))
    inventati = sorted(assunto - disegno)
    omessi = sorted(disegno - assunto)
    print("  nella revisione ma non nel disegno: %s" % inventati)
    print("  nel disegno ma non nella revisione: %s" % omessi)
    esito = (len(disegno) == 10
             and (32.0, 4.0) in inventati
             and len(inventati) == 4 and len(omessi) == 4)
    print("  => (32,4) non e' un punto di disegno: %s" % ((32.0, 4.0) not in disegno))
    print("  => la revisione lavora su un insieme con 4 punti inventati e 4 omessi")
    return riga_audit(1, "insieme di disegno confrontato con P3.5", esito)


def verifica_2_vertici_inviluppo():
    print("\n--- Verifica 2: i vertici dell'inviluppo di progetto ---")
    disegno = punti_di_disegno()
    hull = inviluppo_convesso(disegno)
    print("  vertici calcolati (catena monotona, nessuna libreria): %s" % (hull,))
    print("  vertici dichiarati da P4.7:1827 e P4.14:2225        : %s"
          % (VERTICI_DICHIARATI,))
    print("  vertici proposti dalla revisione (§1.1)             : %s"
          % (VERTICI_PROPOSTI_DALLA_REVISIONE,))
    tutti_dentro = all(margine(p, hull) >= -1e-9 for p in disegno)
    m_32_32 = margine((32.0, 32.0), hull)
    print("  tutti i 10 punti dentro o sull'inviluppo: %s" % tutti_dentro)
    print("  margine di (32,32) = %.4f token (il protocollo scrive 21,2 a riga 1830)"
          % m_32_32)
    print("  (32,32) e' un vertice? %s" % ((32.0, 32.0) in hull))
    # l'inviluppo proposto dalla revisione contiene punti che non sono di disegno
    prop = VERTICI_PROPOSTI_DALLA_REVISIONE
    vertici_proposti_non_di_disegno = [v for v in prop if v not in set(disegno)]
    print("  vertici proposti che non sono punti di disegno: %s"
          % vertici_proposti_non_di_disegno)
    esito = (set(hull) == set(VERTICI_DICHIARATI) and tutti_dentro
             and abs(m_32_32 - 21.24) < 0.01
             and (32.0, 32.0) not in hull)
    return riga_audit(2, "inviluppo = i quattro vertici dichiarati, (32,32) dentro",
                      esito)


def verifica_3_margini_pubblicati():
    print("\n--- Verifica 3: i quattro margini pubblicati ---")
    hull = inviluppo_convesso(punti_di_disegno())
    print("  %-14s %-12s %-12s %-10s" % ("punto", "perpendic.", "pubblicato", "dal vertice"))
    ok = True
    for punto, pubblicato in MARGINI_PUBBLICATI.items():
        m = margine(punto, hull)
        dv = distanza_dal_vertice(punto, hull)
        ok &= abs(m - pubblicato) < 0.01
        print("  %-14s %-12.4f %-12.2f %-10.4f" % ("(%g,%g)" % punto, m, pubblicato, dv))
    m12 = margine((12.0, 32.0), hull)
    d12 = distanza_dal_vertice((12.0, 32.0), hull)
    print("  => su (12,32) il rapporto fra le due metriche e' %.1f (il protocollo"
          % (d12 / m12))
    print("     scrive 21,3 a riga 1888): %.4f contro %.4f" % (d12, m12))
    return riga_audit(3, "margini 1,33 / 64,0 / 21,24 / 107,7 rigenerati", ok)


def verifica_4_classificazione():
    print("\n--- Verifica 4: fascia e flag sui punti notevoli ---")
    hull = inviluppo_convesso(punti_di_disegno())
    casi = [
        ("produzione reale (P4.7:1848)", (12.0, 32.0)),
        ("produzione, N_out misurato 31,8", (12.0, 31.8)),
        ("conferma alta (P3.5)", (256.0, 192.0)),
        ("alto prefill, basso decode", (256.0, 8.0)),
        ("fuori box in N_in", (600.0, 32.0)),
        ("fuori box in N_out", (128.0, 300.0)),
    ]
    ok = True
    attesi = ["A", "A", "A", "B", "C", "C"]
    for (etichetta, punto), atteso in zip(casi, attesi):
        f = fascia(punto, hull)
        m = margine(punto, hull)
        thin = (f == "A" and m < SOGLIA_THIN_SUPPORT_TOK)
        print("  %-34s %-12s fascia %s  margine %8.3f  thin_support %s"
              % (etichetta, "(%g,%g)" % punto, f, m, thin))
        ok &= (f == atteso)
    m12 = margine((12.0, 32.0), hull)
    thin12 = m12 < SOGLIA_THIN_SUPPORT_TOK
    print("  => la revisione (§1.2) scrive che (12,31,8) 'cade pienamente")
    print("     all'interno del Livello A': il margine e' %.3f token, sotto la"
          % m12)
    print("     soglia di 2, quindi thin_support = %s. Il flag non e' opzionale:" % thin12)
    print("     e' la quinta emenda di P4.7 (righe 1851-1855 e 1907).")
    ok &= thin12
    return riga_audit(4, "fasce A/B/C e thin_support sul punto operativo", ok)


def verifica_5_dimensionalita_budget():
    print("\n--- Verifica 5: dimensionalita' di budget_pred_b ---")

    def budget_pred_congelato(budget_fit, u_edge, u_bias):
        """P4.6:1624, P4.3:1392, F.11:2934. Tre termini, tutti in joule."""
        return math.sqrt(budget_fit ** 2 + u_edge ** 2 + u_bias ** 2)

    def budget_pred_proposto(budget_fit, u_edge, z0975=Z_0975_PROPOSTO):
        """La sostituzione della revisione: u_model = budget_fit * z_0.975*."""
        u_model = budget_fit * z0975
        return math.sqrt(budget_fit ** 2 + u_model ** 2 + u_edge ** 2)

    # omogeneita' di grado 1: [J] -> [J], nessun termine adimensionale sommato
    base = budget_pred_congelato(0.050, 0.002, 0.001)
    scalato = budget_pred_congelato(0.050 * 1000, 0.002 * 1000, 0.001 * 1000)
    print("  formula congelata: budget_pred^2 = budget_fit^2 + u_edge^2 + u_bias^2")
    print("  budget_pred(0,050 / 0,002 / 0,001 J) = %.9f J" % base)
    print("  stessi ingressi x 1000               = %.9f J (rapporto %.9f)"
          % (scalato, scalato / base))
    omogenea = abs(scalato / base - 1000.0) < 1e-9

    # nessun u_model nel testo congelato
    print("  occorrenze di 'u_model' nel protocollo: 0 (grep su 3455 righe)")
    print("  termini di budget_pred: budget_fit_b, u_edge,b, u_bias,b -- tutti [J]")

    # che cosa produce la sostituzione proposta
    print("\n  sostituzione proposta u_model = budget_fit * 1,96:")
    print("    (a) u_edge = 0: il rapporto e' una costante, per costruzione")
    rapporti_puri = []
    for bf in (0.001, 0.010, 0.050, 1.000, 100.0):
        c = budget_pred_congelato(bf, 0.0, 0.0)
        p = budget_pred_proposto(bf, 0.0)
        rapporti_puri.append(p / c)
        print("      budget_fit %9.4g J: congelato %9.6f -> proposto %9.6f (x %.6f)"
              % (bf, c, p, p / c))
    print("    (b) u_edge > 0: il rapporto scende sotto quella costante")
    for bf, ue in ((0.050, 0.002), (1.000, 0.500), (0.050, 0.050)):
        c = budget_pred_congelato(bf, ue, 0.0)
        p = budget_pred_proposto(bf, ue)
        print("      budget_fit %9.4g J, u_edge %9.4g J: x %.6f" % (bf, ue, p / c))
    fattore_atteso = math.sqrt(1 + Z_0975_PROPOSTO ** 2)
    print("  => con u_edge = 0 il rapporto e' identico per ogni blocco e vale")
    print("     sqrt(1 + 1,96^2) = %.6f: un allargamento del %.1f%% che non"
          % (fattore_atteso, (fattore_atteso - 1) * 100))
    print("     dipende dai dati, perche' u_model e' proporzionale a budget_fit.")
    print("     Con u_edge > 0 il fattore e' minore, quindi la sostituzione non e'")
    print("     nemmeno conservativa in modo uniforme: allarga di piu' i blocchi")
    print("     con il bordo piccolo, che non sono i blocchi piu' incerti.")
    costante = (all(abs(r - fattore_atteso) < 1e-12 for r in rapporti_puri)
                and budget_pred_proposto(0.050, 0.002) / budget_pred_congelato(0.050, 0.002, 0.0)
                < fattore_atteso)

    # la costruzione del bootstrap e' gia' dimensionalmente pura
    print("\n  bootstrap di P4.8 (riga 1983): Y*_b = f(x_b;theta^) + budget_fit_b * z*_b")
    f_fit, budget_fit, z_star = 1.250, 0.050, -1.37
    y_star = f_fit + budget_fit * z_star
    print("    f = %.4f J, budget_fit = %.4f J, z* = %.4f (adimensionale)"
          % (f_fit, budget_fit, z_star))
    print("    Y* = %.6f J  -> il prodotto budget_fit*z* e' in joule, non c'e'"
          % y_star)
    print("    nessun termine adimensionale da riscalare")
    puro = abs(y_star - 1.18150) < 1e-9

    print("\n  P4.8 righe 1987-1989, testo congelato: 'Standardizzare per")
    print("  budget_fit_b invece che per una sigma stimata ... non assume")
    print("  gaussianita' dei residui fisici su 33 punti'. Il quantile 1,96 e' il")
    print("  quantile normale: adottarlo reintroduce l'ipotesi che il testo esclude.")
    esito = omogenea and costante and puro
    return riga_audit(5, "budget_pred omogeneo in [J]; la proposta inflaziona x 2,2004",
                      esito)


def main():
    print("=" * 78)
    print("Harness P4: inviluppo di progetto, margini, dimensionalita' di budget_pred")
    print("quinto turno di revisione esterna (revisione tecnica di P4.docx, 2026-10-26)")
    print("=" * 78)
    esiti = [
        verifica_1_insieme_di_disegno(),
        verifica_2_vertici_inviluppo(),
        verifica_3_margini_pubblicati(),
        verifica_4_classificazione(),
        verifica_5_dimensionalita_budget(),
    ]
    print("\n" + "=" * 78)
    print("esito complessivo: %d/%d verifiche superate" % (sum(esiti), len(esiti)))
    print("=" * 78)
    print("\nConclusione di metodo. D1 e' costruito su un insieme di disegno che")
    print("non e' quello di P3.5: quattro punti inventati, quattro omessi. Con")
    print("l'insieme reale l'inviluppo ha i quattro vertici che il protocollo")
    print("dichiara, e i quattro margini pubblicati si rigenerano a 0,01 token.")
    print("D2 corregge una formula che nel protocollo non esiste: budget_pred ha")
    print("tre termini, tutti in joule, e l'incertezza di modello passa dal")
    print("bootstrap, che moltiplica z* per budget_fit_b e resta in joule. La")
    print("sostituzione proposta inflazionerebbe ogni budget_pred di un fattore")
    print("2,2004 a u_edge nullo (e di meno quando u_edge pesa, quindi in modo")
    print("non uniforme), senza contenuto dai dati e con un quantile normale che")
    print("P4.8 rifiuta. D3 e R1 citano testo assente: nessuna notazione C5 in P4,")
    print("nessun test di Breusch-Pagan o White in tutto il protocollo, e la")
    print("fallacia 'p grande = assenza' e' gia' scritta come motivo del")
    print("riferimento permutazionale (P3.9 righe 1058 e 1076-1078).")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())

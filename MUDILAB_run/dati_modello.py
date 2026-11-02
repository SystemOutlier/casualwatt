"""Adatta la tavola reale della relatrice agli usi del laboratorio.

Perche' esiste. Fino al 02-11 l'unica tabella disponibile era
`consegna/DATI.csv`: sei clienti, venti delle ventisette variabili del grafo,
celle vuote (`Accident = NaN`) e stati fuori vocabolario. Con sei righe una
frequenza empirica e' quantizzata in sesti e per molti stati vale zero, e il
motivo per cui `tools_corretto.py` FIX 11 ha preso la `Py` degli estremi
controfattuali dal grafo invece che dal file e' esattamente questo: il file non
era una distribuzione. La relatrice ha mandato `dataset.xls`: duemila righe
osservate, tutte e ventisette le variabili, nessuna cella vuota. E' il primo
dato *osservato* che entra nel laboratorio -- `DATI_sintetico_n2000_seed7.csv`
e' campionato dal grafo e quindi non puo' né validarlo né fornire una marginale
indipendente (lo dice il suo stesso docstring).

Cosa fa questo modulo. (1) Legge la tabella con i controlli che la consegna ha
imparato a volere: unita' di riga, nessuna cella vuota, nessun nome duplicato.
(2) Confronta colonne e stati con i domini dichiarati nel `.bif`, perche' uno
stato fuori dominio non e' un dato: e' l'errore che `pyAgrum` solleva come
`OutOfBounds` dentro `cau_inference`, e un test che parte da una tabella
incompatibile misura il validatore, non il modello. (3) Calcola le marginali
empiriche e le mette accanto a quelle del grafo, senza fonderle: la coincidenza
fra le due non e' di per se' una validazione, perche' non sappiamo se il grafo
sia stato imparato da queste stesse righe (4) Campiona righe complete come
evidenze, che e' l'uso nuovo: le query del `coherence` e del `controfattuale`
possono nascere da configurazioni realmente osservate invece che inventate.

Cosa NON fa. Non sostituisce `consegna/DATI.csv`, che resta il file della
consegna, e non cambia nessuna decisione di metodo presa: la `Py` usata dagli
estremi controfattuali viene dal grafo anche qui, finche' la scelta contraria
non e' misurata e registrata. Non rinomina `dataset.xls`: il file della
relatrice resta identico byte per byte (sha-256 nei test).

Nota sul formato. `dataset.xls` non e' un Excel: i suoi primi byte sono
`ILiCost,OtherCar,...`, cioe' CSV con a capo CRLF e senza BOM (verificato il
02-11-2026: i primi dodici byte sono l'intestazione e i `CRLF` sono 2001, una
per ogni riga, intestazione e duemila dati).
`pandas.read_excel` su quel file fallisce. La copia `dataset_car_2000.csv` e' la
stessa tabella con a capo LF, verificata riga per riga contro il sorgente
(`test_copia_ha_le_stesse_celle_del_sorgente`), perche' un nome di file che
mente e' un difetto che si tramanda agli script.

Uso:
    python dati_modello.py                 # rapporto completo
    python dati_modello.py --evidenze 12 --seme 7
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import pyagrum as gum

BASE_DIR = Path(__file__).resolve().parent
TABELLA_REALE = BASE_DIR / "dataset_car_2000.csv"
BIF = BASE_DIR / "consegna" / "insurance_grafo.bif"
N_ATTESO = 2000
N_VARIABILI = 27


def leggi_tabella(path=TABELLA_REALE):
    """Legge la tavola e la impone alla forma che il laboratorio richiede.

    Il file viene letto come CSV sempre, anche se l'estensione e' `.xls`: e'
    quello che contiene, non quello che si chiama.

    `keep_default_na=False` non e' un dettaglio. Due variabili del grafo,
    `ThisCarDam` e `Accident`, hanno fra gli stati ammessi una parola che si
    chiama `None`, e la lista NA di default di pandas contiene la stringa
    "None": letta con il default, questa tavola perde **2894 celle** (1459 su
    2000 righe perdono almeno un valore) che non sono mancanti, sono lo stato
    `None`, e le frequenze si calcolano su un sottoinsieme silenzioso. Con
    `keep_default_na=False` la cella vuota e' solo la stringa vuota, e il
    controllo qui sotto la vede.

    La stessa ragione spiega la `Accident = NaN` di `consegna/DATI.csv`: `NaN`
    non e' uno stato del dominio di `Accident` ({None, Mild, Moderate, Severe})
    e quelle celle sono state marcate come fuori vocabolario dalla verifica del
    31/10. Sono molto probabilmente lo stato `None` scritto da un giro di
    pandas, non dati mancanti: ipotesi con evidenza al momento, da registrare
    prima di correggerla da qualche parte.

    `dtype=str` non e' un vezzo stilistico. Sette variabili del grafo hanno
    dominio `{True, False}` e nel file sono scritte con le maiuscole esatte degli
    stati; lasciato a se', pandas le converte in colonne di booleani. Il valore
    non cambia, ma la chiave si: `value_counts` restituisce chiavi `bool`, il
    `.bif` dichiara chiavi `str`, e un `.get('True', 0.0)` su una chiave booleana
    restituisce zero. Misurato il 02-11: `Theft` usciva con scarto 0,9988 e
    "zero osservati: ['True', 'False']", cioe' la variabile sembrava non avere
    dati quando ne aveva 2000 su 2000. Con `dtype=str` ogni cella resta la
    stringa che si legge nel file, e le chiavi delle due marginali sono
    comparabili per costruzione.
    """
    path = Path(path)
    df = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False,
                     na_values=[], dtype=str)
    errori = []
    if len(df.columns) != N_VARIABILI:
        errori.append(f"{path.name}: {len(df.columns)} colonne, attese {N_VARIABILI}")
    if len(df) != N_ATTESO:
        errori.append(f"{path.name}: {len(df)} righe, attese {N_ATTESO}")
    duplicati = [c for c in df.columns[df.columns.duplicated()]]
    if duplicati:
        errori.append(f"colonne duplicate: {duplicati}")
    vuote = [c for c in df.columns if (df[c].astype(str).str.strip() == "").any()]
    if vuote:
        errori.append(f"celle vuote in: {vuote}")
    if errori:
        raise ValueError("tavola non ammissibile: " + " | ".join(errori))
    return df


def domini_rete(bif_path=BIF):
    """Gli stati ammessi per ogni variabile, letti dal grafo e non assunti."""
    grafo = gum.loadBN(str(bif_path))
    return {
        grafo.variable(v).name(): [str(l) for l in grafo.variable(v).labels()]
        for v in grafo.nodes()
    }


def difetti_vs_rete(df, domini=None):
    """Le ragioni per cui la tavola non puo' alimentare il grafo. Vuota = ok.

    Controlla le due cose che `cau_inference` non puo' perdonare: una variabile
    che non esiste nel grafo (KeyError dentro `_split_query`) e uno stato fuori
    dominio (`OutOfBounds`, che e' l'eccezione gia' osservata su `DATI.csv`).
    """
    if domini is None:
        domini = domini_rete()
    difetti = []
    fuori = sorted(set(df.columns) - set(domini))
    se_mancano = sorted(set(domini) - set(df.columns))
    if fuori:
        difetti.append(f"colonne non presenti nel grafo: {fuori}")
    if se_mancano:
        difetti.append(f"variabili del grafo assenti dalla tavola: {se_mancano}")
    for nome, stati in domini.items():
        if nome not in df.columns:
            continue
        ignoti = sorted(set(str(v) for v in df[nome]) - set(stati))
        if ignoti:
            difetti.append(f"{nome}: stati fuori dominio {ignoti}")
    return difetti


def marginali_empiriche(df):
    """Frequenze osservate: {variabile: {stato: proporzione sulle righe}}.

    `value_counts` conta, non proporziona: qui si divide per `n` e basta, perche'
    un conto scambiato per una proporzione e' lo scarto che vale 1230 invece di
    0,60 e non si vede se non lo si confronta con il grafo.
    """
    n = len(df)
    return {
        nome: {stato: round(float(c) / n, 6)
               for stato, c in df[nome].value_counts().sort_index().items()}
        for nome in df.columns
    }


def marginali_rete(domini=None, bif_path=BIF):
    """Marginali del modello, con lo stesso `LazyPropagation` del tool."""
    grafo = gum.loadBN(str(bif_path))
    ie = gum.LazyPropagation(grafo)
    ie.setEvidence({})
    ie.makeInference()
    out = {}
    for nome, stati in (domini or domini_rete(bif_path)).items():
        post = ie.posterior(nome)
        out[nome] = {stato: round(float(post[i]), 6)
                     for i, stato in enumerate(stati)}
    return out


def confronto(df=None, soglia=0.05, bif_path=BIF):
    """Accosta l'empirico al modello, riga per variabile, senza fondere i due.

    La colonna `scarto` e' la differenza assoluta massima fra le marginali, per
    variabile. Sotto `soglia` si scrive `concordante`; il termine NON dichiara
    una validazione del grafo: se il grafo e' stato imparato da queste righe la
    coincidenza e' attesa per costruzione, e questa informazione non c'e'.
    """
    df = TABELLA_REALE if df is None else df
    if isinstance(df, (str, Path)):
        df = leggi_tabella(df)
    domini = domini_rete(bif_path)
    emp = marginali_empiriche(df)
    rete = marginali_rete(domini, bif_path)
    righe = []
    for nome in domini:
        scarto = max(abs(emp[nome].get(s, 0.0) - rete[nome].get(s, 0.0))
                     for s in domini[nome])
        mai_emp = [s for s in domini[nome] if emp[nome].get(s, 0.0) == 0.0]
        mai_rete = [s for s in domini[nome] if rete[nome].get(s, 0.0) < 1e-9]
        righe.append({
            "variabile": nome,
            "stati": len(domini[nome]),
            "scarto_max": round(scarto, 4),
            "giudizio": "concordante" if scarto <= soglia else "discordante",
            "stati_osservati_zero": mai_emp,
            "stati_modello_quasi_zero": mai_rete,
        })
    return righe


def p_empirica(df, variabile, stato):
    """La `Py` frequentistica per `cobound`, dal dato osservato.

    Esiste perche' `funtions_corretto.cobound` accetta `py` esplicito: con la
    tavola da duemila righe la branca empirica torna utilizzabile, mentre con
    sei righe era la ragione del FIX 11. Chiamarla NON cambia il default della
    consegna, che resta la marginale del giunto.
    """
    df = leggi_tabella(df) if isinstance(df, (str, Path)) else df
    return round(float((df[variabile] == stato).mean()), 6)


def evidenze_da_righe(df=None, n=12, seed=7):
    """Righe complete prese a caso, in forma `{variabile: stato}`.

    Serve a generare query da configurazioni osservate invece che inventate. Il
    seme e' dichiarato: le stesse duemila righe con lo stesso seme danno lo
    stesso campione, quindi una query ricostruibile non dipende dall'umore del
    generatore.
    """
    df = TABELLA_REALE if df is None else df
    if isinstance(df, (str, Path)):
        df = leggi_tabella(df)
    n = int(n)
    if not 0 < n <= len(df):
        raise ValueError(f"n={n} fuori dall'intervallo 1..{len(df)}")
    campione = df.sample(n=n, random_state=int(seed))
    return [
        {"riga": int(i), "evidenza": {k: str(v) for k, v in row.items()}}
        for i, row in campione.iterrows()
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Adattamento della tavola reale")
    ap.add_argument("--tabella", default=str(TABELLA_REALE))
    ap.add_argument("--soglia", type=float, default=0.05,
                    help="scarto massimo tra marginali per 'concordante'")
    ap.add_argument("--evidenze", type=int, default=0,
                    help="stampa N evidenze campionate dalle righe osservate")
    ap.add_argument("--seme", type=int, default=7)
    a = ap.parse_args()

    df = leggi_tabella(a.tabella)
    vuote = int(sum(df[c].astype(str).str.strip().eq("").sum() for c in df.columns))
    print(f"tabella: {a.tabella}")
    print(f"dimensione: {len(df)} righe x {len(df.columns)} variabili, "
          f"celle vuote {vuote}")
    difetti = difetti_vs_rete(df)
    if difetti:
        print("TAVOLA INCOMPATIBILE COL GRAFO:")
        for d in difetti:
            print("  -", d)
        return 1
    domini = domini_rete()
    print(f"compatibilita' col grafo: {len(set(domini) & set(df.columns))}/"
          f"{len(domini)} variabili, nessun stato fuori dominio")

    righe = confronto(df, soglia=a.soglia)
    disc = [r for r in righe if r["giudizio"] == "discordante"]
    print(f"\nmarginali vs grafo (soglia {a.soglia}): "
          f"{len(righe) - len(disc)}/{len(righe)} concordanti")
    for r in sorted(righe, key=lambda x: -x["scarto_max"])[:8]:
        verso = "<" if r["giudizio"] == "concordante" else ">="
        extra = (f"  zero osservati: {r['stati_osservati_zero']}"
                 if r["stati_osservati_zero"] else "")
        print(f"  {r['variabile']:14s} scarto {r['scarto_max']:.4f} "
              f"{verso} {a.soglia}  {r['giudizio']}{extra}")
    print("  (la coincidenza non e' una validazione: non sappiamo se il grafo "
          "sia stato imparato da queste righe)")

    mai = [(r["variabile"], s) for r in righe for s in r["stati_osservati_zero"]]
    if mai:
        print(f"\nstati del grafo mai osservati su {len(df)} righe "
              f"({len(mai)}): {mai}")
        print("  su questi stati la branca empirica e' vuota per costruzione: "
              "una query che li chiede non ha riscontro nel dato, "
              "la Py frequente vale 0 e il giunto vale il suo numero.")

    if a.evidenze:
        print(f"\n{a.evidenze} evidenze campionate (seme {a.seme}):")
        for e in evidenze_da_righe(df, a.evidenze, a.seme):
            print("  riga", e["riga"], json.dumps(e["evidenza"], ensure_ascii=False)[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

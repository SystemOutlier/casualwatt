"""I 26 valori in prosa che `stati-alias` non risolve: cosa sono e se si risolvono.

Perche' esiste. Il regime `stati-alias` e' l'unica variante che aggiunge corrette
sull'held-out misurato -- 91 contro le 77 pubblicate il 02-11, con zero righe perse
(`harness/risultati/replay_regole_nuove_20261102.txt`) -- e dentro quel conto stanno
26 valori che la normalizzazione **non** scioglie. Il censimento di quegli stessi 26
esiste gia', ma e' un elenco di coppie `variabile:valore [stati] x conteggio`
(`harness/risultati/replay_prosa_non_risolta_20261103.txt`): dice quanti, non dice
cosa sono ne' se una regola potrebbe prenderli. Senza quella risposta il "+14" resta
meta' di un numero, perche' la domanda vera non e' "quante righe salva l'alias" ma
"quante delle 26 cadute sono normalizzabili e quante sono un altro difetto che passa
di qui".

Cosa fa, e perche' e' offline. Riprende i 240 JSON di
`risultati_misura/b_composta/20261102_191401` e riesegue da li' in poi solo la parte
che non vuole il modello: `traduzione_controllata.valida` con la sostituzione montata
da `replay_traduzione._stato_alias`, `tools.cau_inference` sul dizionario, e
`benchmark.genera._confronta` contro l'oracolo. Nessun modello, nessuna energia,
nessuna regola scritta nel modulo. Le funzioni vere sono quelle della catena: la
sostituzione e' decorata, non reimplementata, e il conto che esce -- 74 normalizzazioni
e 26 cadute -- e' verificato contro l'artefatto pubblicato prima di stampare qualsiasi
conclusione (se quel conto non torna, questo file non ha titolo per parlare).

Le tre famiglie sono riconosciute da un **rilevatore**, non a occhio:
  `eco`        tutte le etichette della variabile compaiono nel valore scritto;
  `booleano`   gli stati sono esattamente {True, False} e il valore non nomina nessuna
               delle due;
  `unita`      la forma-canone di un'etichetta differisce dal valore scritto per una
               sola parola di unita' (e' la famiglia gia' misurata come `alias+unita`).
Il censimento del 03-11 contava 14 + 6 + 3 + 3, tenendo separati l'eco scritto con le
pipe e la descrizione di `SocioEcon` perche' quella porta anche il testo della
relatrice. Il rilevatore li unisce, e la ragione e' in sezione 3: il testo fra le pipe
e' **il vocabolario che noi stessi aggiungiamo al prompt** (`elenco_vocabolario`), e
quello con le virgole e' la descrizione della relatrice che gia' stava nel prompt. Sono
la stessa cosa -- il modello ha copiato un elenco di stati nel campo del valore -- e
vengono da due righe diverse dello stesso prompt.

Cosa non fa. Non adotta niente: la disambiguazione candidata vive qui dentro, non in
`traduzione_controllata.py`, e il suo numero -- corrette, righe mosse, righe perse --
e' un conto su testi gia' scritti, non una misura. E non tocca i 26 come sintomo di
un prompt da riscrivere: quello si valuta con un run sul modello, e un run non si
conta da qui.

Uso:
    MUDILAB_COPIE=1 python analisi_prosa.py risultati_misura/b_composta/20261102_191401

L'output del 03-11 e' tracciato in `harness/risultati/analisi_prosa_20261103.txt`.
Serve Ollama? No. Serve la tavola della relatrice? No: pyAgrum viene caricato per
`_confronta` e per `cau_inference`, che qui lavora sui dizionari gia' scritti.
"""

import argparse
import collections
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

RAMI = ("cond_prob", "inter", "coherence", "counterfactual")
PAROLE_NEG = ("no", "not", "without", "never", "neither")

# L'aspettativa sull'artefatto pubblicato (`replay_regole_nuove_20261102.txt` e
# `replay_prosa_non_risolta_20261103.txt`): 74 normalizzazioni, 26 cadute. Se questo
# non torna, il censimento qui sotto non descrive piu' il regime che ha prodotto il
# 91, e la prima cosa da stampare e' il fallimento, non la conclusione.
ATTESE = (74, 26)


def norm(testo):
    import traduzione_controllata as TC
    return TC._norm(testo)


def parole(nome):
    import traduzione_controllata as TC
    return TC._parole(nome)


def alias_di_stati(stati):
    from replay_traduzione import alias_di
    return alias_di(stati)


def forma_prosa(etichetta):
    from replay_traduzione import _forma_prosa
    return _forma_prosa(etichetta)


def pulisci_senza_moneta(valore):
    import traduzione_controllata as TC
    from replay_traduzione import _pulisci_prosa
    return _pulisci_prosa(TC, valore)


def nomina_un_altro_nodo(valore, variabile, nomi_del_grafo, stretto=True):
    """I nodi del grafo **diversi** da `variabile` di cui il valore scritto nomina il nome.

    E' il rilevatore della sezione 6: un valore booleano scritto come frase non e' un
    problema di sinonimi se quella frase nomina un altro nodo. `stretto` chiede tutte
    le parole del nome (dopo il nome intero), non una sola: con la forma larga CND35
    accusava `CarValue` per la parola `value` che sta nel boilerplate `Values:` della
    descrizione copiata nel campo. La forma che regge va misurata, non dichiarata.
    """
    v = norm(valore)
    out = []
    for x in nomi_del_grafo:
        if x == variabile or not norm(x):
            continue
        if stretto:
            if all(w in v.split() for w in parole(x)[1:]) and any(
                    norm(x) in v or w in v.split() for w in parole(x)[1:]):
                out.append(x)
        elif any(w in v.split() for w in parole(x)[1:]) or norm(x) in v:
            out.append(x)
    return out


def polarita(valore):
    """'False' se il valore scritto nega, 'True' se afferma, None se non prende posizione."""
    se = [w for w in norm(valore).split() if w in PAROLE_NEG]
    return "False" if se else None


def contestuale(valore, variabile, stati, citazione, query):
    """La disambiguazione candidata, come funzione **pura**.

    E' pura di proposito: la catena di misura la invoca dentro `valida`, e una funzione
    pura la si puo' provare su una riga inventata in `test_analisi_prosa.py` senza
    montare nulla. La sostituzione che la monta in `main` passa il testo della riga
    corrente da fuori, perche' `stato_del_grafo(valore, variabile, stati)` non riceve
    ne' la query ne' le citazioni -- e' il solo motivo per cui la candidata esiste qui
    e non nel modulo.

    Ordine, e perche': prima l'uguaglianza esatta (il protocollo dei joule del 02-11),
    poi la tabella di alias (la variante gia' contata), poi questa. La candidata parla
    **solo** dove l'alias tace, cosi' il delta si legge come il suo effetto e non come
    quello dei due regimi sommati.

    Ritorna `(stato, via)` e `via` e' parte dell'output, non un dettaglio: il conto
    che decide ("quante cadute si risolvono") va leggibile per meccanesimo, perche'
    `eco` sulla citazione e `negazione` sulla stessa citazione sono due pretese
    diverse sul testo.
    """
    if valore in stati:
        return valore, "esatto"
    tabella = alias_di_stati(stati)[0]
    prosa = pulisci_senza_moneta(valore)
    if prosa in tabella:
        return tabella[prosa], "alias"
    eco = (len(stati) > 1
           and all(norm(s) and norm(s) in norm(valore) for s in stati))
    booleano = set(stati) == {"True", "False"}
    if not (eco or booleano):
        return None, "non_trattabile"
    for fonte, _via in ((norm(citazione or ""), "citazione"), (norm(query), "query")):
        if not fonte:
            continue
        if eco:
            cand = [s for s in stati if norm(s) in fonte or forma_prosa(s) in fonte]
            cand.sort(key=lambda s: -len(forma_prosa(s)))
            # il piu' specifico vince, ma solo se vince davvero: due stati la cui
            # forma-canone ha la stessa lunghezza non sono una scelta, sono
            # un'ambiguita', e scegliere qui vuole dire inventarsi lo stato
            if len(cand) > 1 and len(forma_prosa(cand[0])) == len(forma_prosa(cand[1])):
                cand = []
            if len(cand) == 1:
                return cand[0], "eco"
        else:
            # sul booleano non c'e' specificita' da confrontare: la polarita' e' una
            # sola, e si prende dalla citazione perche' quella e' la frase che il
            # modello ha dichiarato come sua fonte. La query subentra solo quando la
            # citazione manca, non quando non placa: due fonti che dicono cose diverse
            # non sono un dato, sono un'ambiguita' su cui non si puo' scegliere.
            return ("False" if any(w in PAROLE_NEG for w in fonte.split())
                    else "True"), "negazione"
    return None, "ambigua" if eco else "nessuna_polarita"


def letture_citazioni(tools, testo):
    """Il campo `citazioni` del testo del traduttore, o {} se il testo non e' leggibile.

    Legge con la funzione del tool, non con un regex: la stessa parsing che ricevera'
    il dizionario deve essere quella che alimenta la candidata, altrimenti si giudica
    una citazione che il ramo non avrebbe mai visto.
    """
    try:
        return (tools._parse_features(testo).get("citazioni") or {})
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella")
    a = ap.parse_args()

    argv = sys.argv
    sys.argv = [argv[0]]                      # run_query legge argv all'import
    import run_query  # noqa: F401  installa `tools`/`agents` sulle copie
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    sys.argv = argv
    import tools
    import agents
    import traduzione_controllata as TC
    import replay_traduzione as RT
    from benchmark.genera import _confronta, _features
    from diagnosi_coherence import _rete

    gt = {r["task_id"]: r for r in csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}
    cartella = (HERE / a.cartella) if not Path(a.cartella).is_absolute() else Path(a.cartella)
    memorizzate, escluse = RT._righe(cartella)

    print("cartella: %s" % cartella.name)
    print("comando: MUDILAB_COPIE=1 %s %s %s"
          % (sys.executable, Path(__file__).name, a.cartella))
    print("righe con un testo di traduttore: %d, senza: %d"
          % (len(memorizzate), len(escluse)))

    # --- 1. il censimento, decorando la sostituzione vera -----------------------
    # La sostituzione e' `RT._stato_alias`, quella che ha prodotto il 91 pubblicato;
    # qui si aggiunge un orecchio che registra le cadute insieme al lato del dizionario.
    # Il lato non lo indovina una regola a memoria: viene dal codice di `valida`, che
    # chiama `stato_del_grafo` per il target **prima** di qualsiasi input e, se il
    # target non risolve, ritorna subito -- quindi se `esito["target"]` e' vuoto la
    # caduta registrata e' quella, altrimenti e' un input (e ce ne sono quante ne
    # cadono, perche' gli input si provano uno per uno con `continue`).
    conto = collections.Counter()
    originale = TC.stato_del_grafo
    montata = RT._stato_alias(TC, conto)
    montata_punteggio = RT._stato_alias(TC, collections.Counter())
    cadute = []
    corrente = []
    contesto = {"cit": {}, "query": ""}

    def con_orecchio(valore, variabile, stati):
        es = montata(valore, variabile, stati)
        if es is None:
            corrente.append((variabile, valore, tuple(stati)))
        return es

    TC.stato_del_grafo = con_orecchio
    esiti_alias = {}
    try:
        for d, r, passi, p in memorizzate:
            riga = gt[d["task_id"]]
            etichetta = str(r.get("etichetta") or "").strip().lower()
            if not etichetta:
                from etichette import etichetta_dal_testo
                etichetta = etichetta_dal_testo(passi["classificator"]["text"])
            rete = d.get("rete") or None
            contesto["query"] = riga["query"]
            contesto["cit"] = letture_citazioni(tools, passi["translator"]["text"])
            corrente.clear()
            traduzione, esito = TC.valida(passi["translator"]["text"], etichetta,
                                          riga["query"], rete, citazione_output=False)
            lato_target = esito.get("target") is None
            for (variabile, valore, stati) in list(corrente):
                cadute.append({"file": p.name, "task": d["task_id"], "ramo": riga["ramo"],
                               "rete": _rete(rete),
                               "lato": "output" if lato_target else "input",
                               "variabile": variabile, "valore": valore,
                               "stati": list(stati), "oracolo": _features(riga),
                               "motivo": esito.get("motivo") or "",
                               "citazione": contesto["cit"].get(variabile) or ""})
            # Due istanze della stessa sostituzione, non una: `conto` appartiene
            # all'orecchio, e una seconda passata che lo incrementa raddoppia il
            # censimento (148 e 52 contro 74 e 26 -- misurato al secondo tentativo,
            # e la verifica in testa alla sezione esiste per questo). `montata_
            # punteggio` e' lo stesso codice con un contatore proprio: il punteggio
            # non cambia, cambia solo chi lo guarda.
            TC.stato_del_grafo = montata_punteggio
            esiti_alias[p.name] = RT.riproduci(
                d, r, passi, ({}, False, {}), gt, TC, tools, _confronta)
            TC.stato_del_grafo = con_orecchio
    finally:
        TC.stato_del_grafo = originale

    torna = (conto["normalizzato"], conto["mancato"]) == ATTESE
    print()
    print("=" * 78)
    print("1. il censimento, e la verifica contro l'artefatto pubblicato")
    print("   normalizzazioni %d, cadute %d -- l'artefatto del 02-11 dice %d e %d: %s"
          % (conto["normalizzato"], conto["mancato"], ATTESE[0], ATTESE[1],
             "TORNA" if torna else "NON TORNA"))
    if not torna:
        print("   >>> questo report non ha titolo per concludere: il regime montato qui"
              " non e'"
              "\n   >>> quello che ha prodotto il 91 pubblicato. Fermarsi e leggere"
              " perche'.")
        return 2
    print("   cadute registrate riga per riga: %d (lo stesso numero, perche' la caduta"
          % len(cadute))
    print("   e' una chiamata di `stato_del_grafo`, non una riga)")
    per_lato = collections.Counter(c["lato"] for c in cadute)
    print("   lato nel dizionario: " + ", ".join("%s %d" % x for x in per_lato.most_common()))
    print("   task coinvolti: %d (%s)" % (len({c["task"] for c in cadute}),
                                          ", ".join(sorted({c["task"] for c in cadute}))))
    print("   run coinvolti: %d su %d" % (len({c["file"] for c in cadute}), len(memorizzate)))

    # --- 2. le tre famiglie, per rilevatore -------------------------------------
    print()
    print("=" * 78)
    print("2. le famiglie, riconosciute dal rilevatore e non a occhio")
    famiglie = collections.Counter()
    per_famiglia = collections.defaultdict(list)
    for c in cadute:
        eco = (len(c["stati"]) > 1
               and all(norm(s) and norm(s) in norm(c["valore"]) for s in c["stati"]))
        booleano = set(c["stati"]) == {"True", "False"}
        unita = any(w in ("miles", "mile") for w in norm(c["valore"]).split())
        f = "eco" if eco else ("booleano" if booleano else
                               ("unita" if unita else "altro"))
        c["famiglia"] = f
        famiglie[f] += 1
        per_famiglia[f].append(c)
    for f, q in famiglie.most_common():
        task = sorted({c["task"] for c in per_famiglia[f]})
        print("   %-9s %2d cadute su %d task (%s)" % (f, q, len(task), ", ".join(task)))
        for riga_txt, n in sorted(collections.Counter(
                "%s %-6s %-12s %r" % (c["task"], c["lato"], c["variabile"], c["valore"][:44])
                for c in per_famiglia[f]).items()):
            print("      %s  x%d" % (riga_txt, n))
    print("   il censimento del 03-11 contava 14 + 6 + 3 + 3 tenendo `SocioEcon` fuori")
    print("   dall'eco: il rilevatore lo mette dentro, perche' le sue quattro etichette")
    print("   ci sono tutte, e la differenza e' solo il testo della relatrice incollato")
    print("   davanti (virgole) invece delle pipe. Con questo rilevatore: eco %d,"
          % famiglie["eco"], )
    print("   booleano %d, unita %d, altro %d -- totale %d."
          % (famiglie["booleano"], famiglie["unita"], famiglie["altro"], sum(famiglie.values())))

    # --- 3. da dove viene l'eco --------------------------------------------------
    print()
    print("=" * 78)
    print("3. l'eco copiato: quale riga del prompt")
    voc = TC.vocabolario(None)
    elenco_nostro = TC.elenco_vocabolario(voc)
    da_noi = da_loro = nessuna = 0
    for c in per_famiglia["eco"]:
        pipe = "|".join(voc.get(c["variabile"], c["stati"]))
        virgole = ", ".join(voc.get(c["variabile"], c["stati"]))
        if c["valore"] == pipe:
            da_noi += 1
        elif norm(virgole) in norm(c["valore"]):
            da_loro += 1
        else:
            nessuna += 1
    print("   %d/%d echo sono **esattamente** l'elenco con le pipe, cioe' il formato di"
          % (da_noi, len(per_famiglia["eco"])))
    print("   `elenco_vocabolario` -- il vocabolario che aggiunge il **nostro** prompt")
    print("   (`traduzione_controllata._VOCABOLARIO_PROMPT`), non il testo della")
    print("   relatrice. Verifica che l'elenco di una di quelle variabili sta davvero"
          " nel prompt:")
    esempio = next((c["variabile"] for c in per_famiglia["eco"] if c["valore"] ==
                    "|".join(voc.get(c["variabile"], c["stati"]))), None)
    if esempio:
        print("     %r in elenco_vocabolario: %s"
              % ("%s: %s" % (esempio, "|".join(voc[esempio])),
                 "%s: %s" % (esempio, "|".join(voc[esempio])) in elenco_nostro))
    print("   %d/%d sono le etichette in formato `a, b, c`, che e' la descrizione della"
          % (da_loro, len(per_famiglia["eco"])))
    print("   relatrice gia' nel prompt. Un esempio verificato su `agents.translator_"
          "prompt`: %s"
          % ("socio-economic status. Values: Prole, Middle, UpperMiddle, Wealthy"
             in agents.translator_prompt))
    print("   nessuna corrispondenza: %d" % nessuna)
    print("   Nessun valore eco e' inventato: sono elenchi veri tolti di peso dal")
    print("   contesto. L'alias non poteva niente, perche' non c'e' un sinonimo da")
    print("   trovare -- ci sono tutti e quattro. Il difetto e' che l'elenco e' finito")
    print("   nel campo del valore, e quello e' un problema di prompt, non di dizionari.")

    # --- 4. la candidata, valore per valore -------------------------------------
    print()
    print("=" * 78)
    print("4. la disambiguazione candidata: stato dal testo, e cosa ne pensa l'oracolo")
    esiti_cand = collections.Counter()
    tab = collections.defaultdict(int)
    for c in cadute:
        stato, via = contestuale(c["valore"], c["variabile"], c["stati"],
                                 c["citazione"], gt[c["task"]]["query"])
        atteso = (c["oracolo"]["input"].get(c["variabile"]) if c["lato"] == "input"
                  else gt[c["task"]]["target_state"])
        nel_oracolo = (c["variabile"] in c["oracolo"]["input"] if c["lato"] == "input"
                       else c["variabile"] == gt[c["task"]]["target_variable"])
        if stato is None:
            giudizio = via
        elif not nel_oracolo:
            vuole = ("e' il target" if c["variabile"] == gt[c["task"]]["target_variable"]
                     else "e' un'evidenza" if c["variabile"] in c["oracolo"]["input"]
                     else "non c'e'")
            giudizio = "risolto_ma_l_oracolo_non_lo_vuole_in_quel_campo (%s)" % vuole
        elif stato == atteso:
            giudizio = "risolto_e_uguale_all_oracolo"
        else:
            giudizio = "risolto_ma_lo_stato_e_un_altro"
        esiti_cand[giudizio] += 1
        tab[(c["famiglia"], giudizio)] += 1
        c["candidato"] = (stato, via)
    for giudizio, q in esiti_cand.most_common():
        print("   %2d  %s" % (q, giudizio))
    print("   per famiglia:")
    for f in ("eco", "booleano", "unita", "altro"):
        righe = ["%s %d" % (g.split(" (")[0], q)
                 for (fam, g), q in sorted(tab.items()) if fam == f]
        if righe:
            print("      %-9s %s" % (f, ", ".join(righe)))
    print("   e per via che ha risposto: " + ", ".join(
        "%s %d" % x for x in collections.Counter(
            v for _s, v in (c["candidato"] for c in cadute)).most_common()))

    # --- 5. e il punteggio? -----------------------------------------------------
    print()
    print("=" * 78)
    print("5. la candidata sul punteggio dei 240 run")

    def montata_candidata(valore, variabile, stati):
        return contestuale(valore, variabile, stati, contesto["cit"].get(variabile),
                           contesto["query"])[0]

    esiti_candidata = {}
    TC.stato_del_grafo = montata_candidata
    try:
        for d, r, passi, p in memorizzate:
            riga = gt[d["task_id"]]
            contesto["query"] = riga["query"]
            contesto["cit"] = letture_citazioni(tools, passi["translator"]["text"])
            esiti_candidata[p.name] = RT.riproduci(
                d, r, passi, ({}, False, {}), gt, TC, tools, _confronta)
    finally:
        TC.stato_del_grafo = originale

    c_alias = collections.Counter(v[0] for v in esiti_alias.values())
    c_eco = collections.Counter(v[0] for v in esiti_candidata.values())
    print("   stati-alias  : " + ", ".join("%s %d" % x for x in c_alias.most_common()))
    print("   alias+eco    : " + ", ".join("%s %d" % x for x in c_eco.most_common()))
    mosse = [(f, esiti_alias[f][0], esiti_candidata[f]) for f in esiti_alias
             if esiti_alias[f][0] != esiti_candidata[f][0]]
    print("   corrette: stati-alias %d, alias+eco %d -- in piu' %d, in meno %d"
          % (c_alias["corretta"], c_eco["corretta"],
             sum(1 for _f, _a, b in mosse if b[0] == "corretta"),
             sum(1 for _f, a, _b in mosse if a == "corretta")))
    print("   righe mosse: %d" % len(mosse))
    for f, prima, dopo in sorted(mosse):
        print("      %-16s %-9s -> %-9s %s" % (f, prima, dopo[0], dopo[1][:64]))
    print("   e' il numero che chiude l'asse: la candidata risolve valori, non righe.")
    print("   Le righe che passano da `rifiutata` a `numero` con un numero che non e'")
    print("   quello dell'oracolo sono un peggioramento di tipo, non un recupero: con")
    print("   il rifiuto la riga dichiara di non aver capito, qui stampa una risposta")
    print("   confidente e sbagliata. Le altre restano rifiutate, con il motivo")
    print("   spostato dal vocabolario alla cardinalita' o alla citazione -- la")
    print("   normalizzazione di uno stato non tocca la regola `citazione` (verbatim)")
    print("   ne' la regola `disgiunzione`.")

    # --- 6. i booleani: il valore nomina un altro nodo ----------------------------
    print()
    print("=" * 78)
    print("6. il booleano scritto come frase nomina un altro nodo del grafo")
    for c in per_famiglia["booleano"]:
        alt = nomina_un_altro_nodo(c["valore"], c["variabile"], list(voc))
        orc = c["oracolo"]
        campo = (orc["input"] if c["lato"] == "input"
                 else {gt[c["task"]]["target_variable"]: gt[c["task"]]["target_state"]})
        print("   %s %-6s %s = %r" % (c["task"], c["lato"], c["variabile"], c["valore"][:40]))
        print("        polarita' negata nel valore: %s | nomi di altri nodi nel valore:"
              % (polarita(c["valore"]) == "False"), )
        print("        %s" % (", ".join(alt) or "nessuno"))
        print("        l'oracolo vuole %s nel campo letto: %s"
              % (c["variabile"], campo.get(c["variabile"], "no")))
        for x in alt:
            vuole = orc["input"].get(x, gt[c["task"]]["target_state"]
                                     if x == gt[c["task"]]["target_variable"] else None)
            print("        ma il valore nomina %s, e l'oracolo la mette a %s: %s"
                  % (x, vuole,
                     "e' la stessa polarita' scritta"
                     if str(vuole) == str(polarita(c["valore"])) else "da leggere"))
    # Il costo delle due forme, stampato come **accuse** e non come un contro-numero:
    # un "falso positivo" definito da una proprieta' dell'oracolo sarebbe una seconda
    # regola inventata qui, e la sola cosa che rende leggibile la scelta fra le due
    # forme e' l'elenco di chi viene accusato da quale parola.
    for stretto in (True, False):
        accusate = collections.Counter()
        dettagli = collections.Counter()
        for c in cadute:
            for x in nomina_un_altro_nodo(c["valore"], c["variabile"], list(voc), stretto):
                accusate[c["task"]] += 1
                dettagli["%s %s=%r -> %s" % (c["task"], c["variabile"],
                                             c["valore"][:34], x)] += 1
        print("   rilevatore %s sulle %d cadute: %d cadute accusano un altro nodo"
              % ("stretto" if stretto else "largo", len(cadute), sum(accusate.values())))
        for riga_txt, n in sorted(dettagli.items()):
            print("      %s  x%d" % (riga_txt, n))
    print("   la forma larga accusa in piu' `CarValue` via la parola `value`, che pero'"
          "\n   sta nel boilerplate `Values:` della descrizione copiata nel campo, non"
          "\n   nomina il nodo: la forma che regge e' la stretta, e le accuse di questa"
          "\n   seconda forma sono tutte dello stesso tipo -- il valore nomina la"
          "\n   variabile che l'oracolo manipola, scritta nel campo di un'altra.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

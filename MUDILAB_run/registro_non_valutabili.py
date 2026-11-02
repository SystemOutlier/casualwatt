"""Registro dei casi non valutabili: causa, e quanti ne resta fuori dal denominatore.

Perche' esiste. Un punteggio detto come "32 su 81" nasconde tre famiglie di casi
diverse: le righe che il generatore non ha mai scritto perche' il valore non
discrimina, le righe che il codice deterministico (cobound, causalImpact) non sa
produrre, e le righe che esistono ma il protocollo ferma prima del tool. La terza
famiglia sta nel denominatore e conta come sbagliata; la prima e la seconda no, e
non comparire in nessun documento vuol dire spostare la soglia senza dirlo.

Cosa legge. `benchmark/manifest.json` per le prime due famiglie (le scrive
`benchmark/genera.py`, righe 875-885), e
`harness/riferimenti/tabella_prima_dopo_20261101.json` per la terza. Niente numeri
ricopiati a mano: se il manifest cambia, cambia anche questo registro.

Non chiama il modello. E' un assemblatore di artefatti gia' su disco.

Uso:  python registro_non_valutabili.py
"""
import io
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MANIFEST = HERE / "benchmark" / "manifest.json"
TABELLA = HERE / "harness" / "riferimenti" / "tabella_prima_dopo_20261101.json"
DIAG = HERE / "harness" / "riferimenti" / "coherence_prima_del_fix.json"
CONTROFATTUALE = HERE / "harness" / "riferimenti" / "fix_coherence_controfattuale.json"
OUT_MD = HERE / "harness" / "riferimenti" / "registro_non_valutabili.md"
OUT_JSON = HERE / "harness" / "riferimenti" / "registro_non_valutabili.json"

TITOLI = {
    "1_esclusi_alla_generazione_degeneri":
        "1. Esclusi alla generazione perche' il valore non discrimina",
    "2_esclusi_alla_generazione_non_supportati_dal_codice":
        "2. Esclusi alla generazione perche' il codice deterministico non risponde",
    "3_righe_presenti_ma_non_arrivano_al_tool":
        "3. Righe che esistono, ma il protocollo ferma prima del tool",
    "4_casi_che_il_tool_non_deve_numerare":
        "4. Forme che il tool non deve numerare, anche se il validatore le lasciasse passare",
    "5_le_quattro_quantita_per_regime":
        "5. Le quattro quantita' separate, per regime di citazione",
}


def _somma(nested):
    """(totale, per_ramo) su un dict {ramo: {chiave: int}} o {ramo: [liste]}."""
    totale, per_ramo = 0, {}
    for ramo, v in nested.items():
        if isinstance(v, dict):
            n = sum(x if isinstance(x, int) else sum(x.values()) for x in v.values())
        else:
            n = len(v)
        per_ramo[ramo] = n
        totale += n
    return totale, per_ramo


def construisci():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tab = json.loads(TABELLA.read_text(encoding="utf-8"))
    righe = tab["righe"]

    degeneri = {ramo: dict(conti) for ramo, conti in m["esclusi_degeneri"].items()}
    n_degeneri, degeneri_per_ramo = _somma(degeneri)
    scartati = m["scartati_layer_deterministico"]
    n_scartati, scartati_per_ramo = _somma(scartati)

    esiti = Counter(x["dopo"] for x in righe)
    rifiutate = [x for x in righe if x["dopo"] == "rifiutata"]

    # Il dettaglio del ramo coherence: la riga c'e', il numero esce, e il metro
    # non la puo' comunque promuovere perche' la mappatura e' sbagliata. Questo
    # distingue "non valutabile dal metro" da "valutata e sbagliata".
    diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def _categoria_mappatura(r):
        if r.get("esito_tool") == "non arrivato al tool":
            return "non arrivato al tool"
        m = r.get("mappatura") or {}
        if m.get("target_invertito"):
            return "target invertito"
        if not m.get("input_mancanti") and not m.get("input_in_piu") \
                and m.get("output_avuto") == m.get("output_atteso"):
            return "mappatura esatta"
        return "altro errore di mappatura"

    mappatura = Counter(_categoria_mappatura(r) for r in diag["righe"])
    per_motivo = Counter()
    for x in rifiutate:
        # il motivo arriva gia' tagliato a 70 caratteri dal tabella_prima_dopo; qui
        # si raggruppa per famiglia, non per stringa intera
        testo = x["motivo_dopo"]
        if "servono almeno" in testo:
            per_motivo["evidenze richieste non presenti nella traduzione"] += 1
        elif "disgiunzione" in testo:
            per_motivo["la variabile e' gia' il target della domanda"] += 1
        elif "citazione" in testo:
            per_motivo["citazione mancante o non valida"] += 1
        else:
            per_motivo[testo[:40]] += 1

    controfattuale = json.loads(CONTROFATTUALE.read_text(encoding="utf-8"))
    contraddittori = [{"caso": e["caso"],
                       "traduzione": e["traduzione"],
                       "A_fissato": e["A fissato"],
                       "B_senza_FIX_20": e["B senza_FIX_20"],
                       "C_prima_dei_fix": e["C prima_dei_fix"]}
                      for e in controfattuale
                      if e["caso"].startswith("sintetico")]

    return {
        "fonte_manifest": str(MANIFEST),
        "generato": m.get("generato"),
        "seed": m.get("seed"),
        "righe_benchmark": m["conteggi"]["ramo"],
        "1_esclusi_alla_generazione_degeneri": {
            "per_ramo": degeneri_per_ramo, "dettaglio": degeneri, "totale": n_degeneri,
            "impatto_denominatore": (
                "non entrano nei 161: il denominatore non cresce. Sono esclusi perche' "
                "il valore atteso si stampa 0.0000/1.0000, o sta a ridosso della soglia "
                "0.60, o l'intervallo controfattuale e' nullo: una variante che risponde "
                "un numero a caso prende lo stesso punto, quindi la riga non discrimina."),
        },
        "2_esclusi_alla_generazione_non_supportati_dal_codice": {
            "per_ramo": scartati_per_ramo, "dettaglio": scartati, "totale": n_scartati,
            "impatto_denominatore": (
                "non entrano nei 161: il denominatore non cresce. E' il codice della "
                "consegna che non sa rispondere (cobound non calcola il giunto su ogni "
                "coppia, causalImpact si ferma sugli effetti deterministici), non il "
                "modello: una riga del genere renderebbe uguale il fallimento di tutte "
                "le varianti."),
        },
        "3_righe_presenti_ma_non_arrivano_al_tool": {
            "denominatore": len(righe),
            "esito_per_categoria": dict(esiti),
            "rifiutate_dal_validatore": len(rifiutate),
            "per_famiglia_di_motivo": dict(per_motivo),
            "righe": [{"task_id": x["task_id"], "ramo": x["ramo"],
                       "motivo": x["motivo_dopo"]} for x in rifiutate],
            "coherence_mappatura": dict(mappatura),
            "coherence_mappatura_come_si_legge": (
                "le righe contate come 'mappatura esatta' sono quelle che il metro puo' "
                "promuovere; le altre escono dal tool con un numero giusto o sbagliato "
                "che non corrisponde comunque alla domanda dell'oracolo. Il collo di "
                "bottiglia del ramo non e' l'inferenza, e non e' l'etichetta: e' la "
                "scelta di quali chiavi vanno in `input` e quale in `output`."),
            "impatto_denominatore": (
                f"restano NEL denominatore: {len(rifiutate)} su {len(righe)} contano "
                "come non corrette. E' una scelta di protocollo, non un incidente: se "
                "uscissero dal conteggio il punteggio salirebbe a "
                f"{sum(1 for x in righe if x['dopo'] == 'corretta')}/"
                f"{len(righe) - len(rifiutate)} senza che il modello abbia fatto nulla "
                "in piu'."),
        },
        "4_casi_che_il_tool_non_deve_numerare": {
            "nota": ("Forme che il ramo `coherence` riceveva e numerava: target dentro "
                     "le evidenze, e evidenza con stato fuori dominio quando la guardia "
                     "_valida_stati non c'e'. Misurate a tre bracci in "
                     "`fix_coherence_controfattuale.json`."),
            "presenti_nel_dev_81": sum(1 for x in righe
                                       if x["ramo"] == "coherence"
                                       and x["dopo"] != "rifiutata"
                                       and _target_in_input(x.get("traduzione"))),
            "prova_a_tre_bracci": contraddittori,
            "impatto_denominatore": (
                "zero righe spostate sul dev con la regola primaria: il validatore le "
                "ferma prima. Il fix esiste per non far dipendere il verdetto dal "
                "validatore, che e' un altro modulo e un altro protocollo."),
        },
        "5_le_quattro_quantita_per_regime": {
            "solo_validatore_nessun_tool": le_quattro_quantita(),
            "impatto_denominatore": (
                "i tre regimi hanno lo stesso denominatore (81) e numeri diversi: non "
                "e' lo stesso metro tre volte. Sull'unico regime primario congelato "
                "(gate sulla frase, citazione del target libera) il quarto numero e' "
                "una misura, perche' il gate protegge le evidenze ma non il target; "
                "il regime con la citazione del target obbligatoria riporta zero per "
                "costruzione e va letto come proprieta' del filtro, non come assenza "
                "di citazioni inventate. La coppia 32/40 e il prezzo della riga INT26, "
                "che solo il regime esplorativo manda al tool dove muore di "
                "`bad allocation`, stanno rieseguiti e registrati in "
                "`replay_regimi_b_composta_20261101.md`."),
        },
    }


def _target_in_input(traduzione):
    if not isinstance(traduzione, dict):
        return False
    inn = set((traduzione.get("input") or {}).keys())
    out = set((traduzione.get("output") or {}).keys())
    return bool(inn & out)


def _markdown(reg):
    L = ["# Registro dei casi non valutabili",
         "",
         f"Generato da: `{Path(reg['fonte_manifest']).name}` (manifest del "
         f"{reg['generato']}, seed {reg['seed']}) e "
         "`tabella_prima_dopo_20261101.json`. Nessun numero ricopiato a mano.",
         f"Benchmark: {reg['righe_benchmark']} per ramo.",
         ""]
    for tit in ("1_esclusi_alla_generazione_degeneri",
                "2_esclusi_alla_generazione_non_supportati_dal_codice",
                "3_righe_presenti_ma_non_arrivano_al_tool",
                "4_casi_che_il_tool_non_deve_numerare",
                "5_le_quattro_quantita_per_regime"):
        blocco = reg[tit]
        L += ["## " + TITOLI[tit], ""]
        for chiave in ("per_ramo", "esito_per_categoria", "denominatore",
                       "rifiutate_dal_validatore", "per_famiglia_di_motivo",
                       "coherence_mappatura",
                       "presenti_nel_dev_81", "totale"):
            if chiave in blocco:
                L.append(f"- **{chiave}**: {blocco[chiave]}")
        if "coherence_mappatura_come_si_legge" in blocco:
            L += ["", f"*Come si legge*: {blocco['coherence_mappatura_come_si_legge']}"]
        if "prova_a_tre_bracci" in blocco:
            L += ["", "Le stesse traduzioni, tre versioni del ramo "
                  "(`fix_coherence_controfattuale.json`):", "",
                  "| caso | A fissato | B senza FIX 20 | C prima dei fix |",
                  "|---|---|---|---|"]
            for e in blocco["prova_a_tre_bracci"]:
                L.append(f"| {e['caso']} | {e['A_fissato']['tipo']}: "
                         f"`{e['A_fissato']['testo'][:70]}` | {e['B_senza_FIX_20']['tipo']}: "
                         f"`{e['B_senza_FIX_20']['testo'][:70]}` | "
                         f"{e['C_prima_dei_fix']['tipo']}: "
                         f"`{e['C_prima_dei_fix']['testo'][:70]}` |")
        L += ["", f"*Impatto sul denominatore*: {blocco['impatto_denominatore']}", ""]
        if tit == "3_righe_presenti_ma_non_arrivano_al_tool":
            L += ["| task | ramo | motivo (troncato a 70 caratteri dal replay) |",
                  "|---|---|---|"]
            for r in blocco["righe"]:
                L.append(f"| {r['task_id']} | {r['ramo']} | {r['motivo']} |")
            L.append("")
        if "solo_validatore_nessun_tool" in blocco:
            L += ["", "Le quattro quantita' separate, sullo stesso denominatore di 81 "
                  "righe dev e sugli stessi testi registrati. `target` e' la variabile "
                  "della domanda; `evidenza` una delle sue condizioni.", "",
                  "| regime | accettate | rifiutate | copertura | target citato "
                  "verbatim | target citato ma non supportato | target senza citazione "
                  "| un'evidenza non supportata |",
                  "|---|---|---|---|---|---|---|---|"]
            for nome, v in blocco["solo_validatore_nessun_tool"].items():
                L.append(f"| {nome} | {v['accettate']} | {v['rifiutate']} | "
                         f"{v['copertura']} | "
                         f"{v['accettate_target_con_citazione_verbatim']} | "
                         f"{v['accettate_target_con_citazione_non_supportata']} | "
                         f"{v['accettate_target_senza_citazione']} | "
                         f"{v['accettate_con_un_evidenza_non_supportata']} |")
            L.append("")
            for nome, v in blocco["solo_validatore_nessun_tool"].items():
                statuto = ("una misura" if v["quarto_numero_e_una_misura"]
                           else "zero per costruzione: e' il filtro, non un risultato")
                L.append(f"- `{nome}`: il quarto numero e' {statuto}; "
                         f"`avviso_output` scritto dal validatore = "
                         f"{v['avviso_output_del_validatore']}, che coincide con il "
                         f"conteggio: {v['coerenza_con_avviso_output_del_validatore']}")
                if not v["coerenza_con_avviso_output_del_validatore"]:
                    L.append(f"  La divergenza e' attesa e non e' un difetto del "
                             f"conteggio: in questo regime il validatore applica al "
                             f"target la stessa regola rilassata, quindi dichiara "
                             f"avviso solo sulle citazioni che non reggono nemmeno a "
                             f"quella ({v['avviso_output_del_validatore']} righe), "
                             f"mentre la regola stretta qui non copre "
                             f"{v['accettate_target_con_citazione_non_supportata'] + v['accettate_target_senza_citazione']} "
                             f"righe. La differenza e' la popolazione delle parafrasi "
                             f"tollerate dal regime esplorativo.")
            L.append("")
            for nome, v in blocco["solo_validatore_nessun_tool"].items():
                if v["righe_target_non_supportato"]:
                    L.append(f"- righe accettate il cui target ha una citazione che "
                             f"la regola stretta non regge, {nome}: "
                             f"{' '.join(v['righe_target_non_supportato'])}")
            L.append("")
        if "dettaglio" in blocco:
            if tit.startswith("2_"):
                famiglie = Counter()
                coppie = Counter()
                for ramo, v in blocco["dettaglio"].items():
                    for chiave, conto in v.items():
                        n = sum(conto.values()) if isinstance(conto, dict) else conto
                        tipo = chiave.split("eccezione")[-1].strip() or chiave
                        famiglie[f"{ramo}: {tipo}"] += n
                        coppie[tipo] += n
                L += ["Famiglie di causa (somma dei tentativi scartati su quella "
                      "coppia di variabili):", "",
                      "| ramo | causa | tentativi |", "|---|---|---|"]
                for k, n in sorted(famiglie.items(), key=lambda t: -t[1]):
                    ramo, causa = k.split(": ", 1)
                    L.append(f"| {ramo} | {causa} | {n} |")
                L += ["", "Per sola causa, sommati sui rami: "
                      + ", ".join(f"{c}={n}" for c, n in coppie.most_common()), ""]
            else:
                L += ["Dettaglio (dal manifest):", "",
                      "```json",
                      json.dumps(blocco["dettaglio"], ensure_ascii=False, indent=1),
                      "```", ""]
    return "\n".join(L)


def le_quattro_quantita():
    """Le quattro misure che la decisione 1 vuole separate, per regime.

    Un punteggio unico schiaccia cose diverse: una traduzione rifiutata, una
    accettata con la citazione verbatim, una accettata con la citazione che
    verbatim non e'. Le quattro righe della tabella restano numeri diversi anche
    dove il punteggio di correttezza coincide, e il confronto per "quante righe
    corrette" perderebbe l'unica informazione che distingue i regimi.

    Due posti dove la regola non e' simmetrica, e vanno letti prima dei numeri:
    la citazione di ogni evidenza la paga sempre, perche' `valida` scarta la voce
    che non regge (`traduzione_controllata.py:309-312`); la citazione del target
    la paga solo se il regime la pretende, altrimenti il validatore la dichiara
    in `avviso_output` e la riga prosegue (`:273-283`). Il quarto numero della
    primaria congelata misura esattamente quella popolazione, e non e' quindi zero
    per costruzione. Zero per costruzione e' solo il regime con la citazione del
    target obbligatoria, dove la regola rifiuta prima che il contatore veda.

    Il conteggio e' incrociato con `avviso_output` dello stesso `esito`. Sui due
    regimi dove il validatore applica la regola stretta al target le due cifre
    devono coincidere, e divergere li farebbe valere zero come prova. Sul regime
    rilassato divergono per costruzione, perche' li' anche il target e' giudicato
    dalla regola rilassata: la colonna lo dice e il `perche'` sta in fondo.

    Solo il validatore, qui: nessuna chiamata al tool e nessun run del modello.
    """
    argv = sys.argv
    sys.argv = [argv[0]]
    import run_query  # noqa: F401
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    import traduzione_controllata as TC
    import replay_traduzione as R
    import tools
    import csv as _csv

    gt = {r["task_id"]: r for r in _csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}
    cart = HERE / "harness" / "risultati" / "b_composta" / "20261101_183106"
    elaborabili, _escluse = R._righe(cart)
    originale = TC._citazione_valida
    rilassata = R._regola_senza_verbatim(TC)

    out = {}
    # `misura` dice se il quarto numero di quel regime e' una misura o una
    # tautologia. Con la citazione del target obbligatoria (`traduzione_controllata
    # .py:273-279`) la regola rifiuta direttamente le righe che il contatore dovrebbe
    # segnalare, quindi lo zero e' una proprieta' del regime, non un risultato.
    # Negli altri due il conteggio e' indipendente dal gate: la primaria non
    # pretende la citazione del target e la dichiarerebbe soltanto.
    per_regime = (("primaria congelata (gate sulla frase)", None, False, True),
                  ("primaria, citazione del target obbligatoria", None, True, False),
                  ("esplorativa senza gate (NON protocollo)", rilassata, False, True))
    for nome, regola, cit_out, misura in per_regime:
        accettate, rifiutate = [], []
        verb, non_verb, senza_cit = [], [], []
        evidenze_peggiori, dichiarate = [], []
        for d, r, passi, _p in elaborabili:
            riga_gt = gt[d["task_id"]]
            if riga_gt["split"] != "dev":
                continue
            if regola is not None:
                TC._citazione_valida = regola
            try:
                traduzione, esito = TC.valida(passi["translator"]["text"],
                                              riga_gt["etichetta_attesa"],
                                              riga_gt["query"], d.get("rete"),
                                              citazione_output=cit_out)
            finally:
                TC._citazione_valida = originale
            if traduzione is None:
                rifiutate.append(d["task_id"])
                continue
            accettate.append(d["task_id"])
            # Accuratezza, perche' la primaria guarda la sola frase intera e una
            # parafrasi puo' reggere o inventare a seconda di dove sta. `valida`
            # rende solo {input, output} (`traduzione_controllata.py:335`), quindi
            # le citazioni si riprendono dal testo grezzo dello stesso passo, e si
            # ricontrollano contro la regola stretta `originale`, che qui e' il
            # referente e non la regola in vigore.
            grezzo = tools._parse_features(passi["translator"]["text"])
            citta = grezzo.get("citazioni") or {}
            qn = TC._norm(riga_gt["query"])
            (t, stato_t), = (traduzione.get("output") or {}).items()
            cit_t = str(citta.get(t) or "").strip()
            if not cit_t:
                senza_cit.append(d["task_id"])
            elif originale(cit_t, t, str(stato_t), qn):
                non_verb.append(d["task_id"])
            else:
                verb.append(d["task_id"])
            if [var for var, s in (traduzione.get("input") or {}).items()
                    if str(citta.get(var) or "").strip()
                    and originale(str(citta[var]), var, str(s), qn)]:
                evidenze_peggiori.append(d["task_id"])
            # Il validatore scrive gia' da se' la citazione del target che non
            # regge, quando la regola non la pretende: `avviso_output`
            # (`traduzione_controllata.py:280-283`). Se il mio conteggio e' giusto
            # deve coincidere con quella dichiarazione, riga per riga.
            if esito.get("avviso_output"):
                dichiarate.append(d["task_id"])
        out[nome] = {
            "accettate": len(accettate), "rifiutate": len(rifiutate),
            "copertura": round(len(accettate) / max(1, len(accettate) + len(rifiutate)), 3),
            "accettate_target_con_citazione_verbatim": len(verb),
            "accettate_target_con_citazione_non_supportata": len(non_verb),
            "accettate_target_senza_citazione": len(senza_cit),
            "accettate_con_un_evidenza_non_supportata": len(evidenze_peggiori),
            "quarto_numero_e_una_misura": bool(misura),
            "righe_target_non_supportato": sorted(set(non_verb) | set(senza_cit)),
            "coerenza_con_avviso_output_del_validatore":
                set(dichiarate) == set(non_verb) | set(senza_cit),
            "avviso_output_del_validatore": len(dichiarate),
        }
    return out


if __name__ == "__main__":
    reg = construisci()
    OUT_JSON.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_MD.write_text(_markdown(reg), encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in
                          ("totale", "denominatore", "rifiutate_dal_validatore",
                           "esito_per_categoria", "per_ramo", "presenti_nel_dev_81")}
                      for k, v in reg.items() if k[0].isdigit()},
                     ensure_ascii=False, indent=1))
    print(f"\nscritto: {OUT_MD}\nscritto: {OUT_JSON}")

"""Rigenera la banda di `bias_w` dichiarata e la sua propagazione in `budget_pred`.

Perche' esiste questo file
--------------------------
Il gate load-versus-control di P4.4 e' stato eseguito due volte e ha fallito
entrambe le volte con il criterio congelato F.12:

    2026-11-07  bias_w = 0,479571 W  >  mediana_c(budget_base_w,c) = 0,262324 W
                (4 controlli utilizzabili su 6, quorum 4; macchina rumorosa)
    2026-11-08  bias_w = 0,125171 W  >  mediana_c(budget_base_w,c) = 0,117995 W
                (6 controlli utilizzabili su 6, quorum 4; ambiente quieto
                verificato, 3 letture consecutive con `background_load=False`)

P4.4 requisito 1 e il ramo "se non passa" di P4.5 (`protocollo_v4_20261024.md`
:1666-1670 e :1797-1801) prescrivono gia' il percorso: la campagna principale
parte comunque, con `bias_declared` e con `u_bias,b = |bias_w| · Δt̄_W,b` in
quadratura dentro `budget_pred_b` (P4.6, F.11). Cio' che il testo congelato
NON dice, perche' non poteva dirlo prima dei dati, e' **quale** `bias_w` entra
nel conto quando il gate e' stato eseguito due volte con esiti diversi, e
**quale** `Δt̄_W,b` usare finche' la campagna principale -- i cui blocchi
definiscono quella durata media -- non esiste. Questo file e' l'harness che
fissa quei due numeri per esecuzione, a partire dai soli artefatti congelati:
per AGENTS.md un'analisi non tracciata e' un numero che nessuno puo'
rigenerare, quindi non e' evidenza.

Cosa NON fa, dichiarato
-----------------------
* Non esegue il gate e non sceglie una terza campagna: il disegno a 12 coppie
  resta pianificato e non eseguito (`experiment_results/p44_gate_20261109/`
  contiene solo `plan.json`), ed e' una decisione separata da questo punto.
* Non stima una deviazione standard del bias: due esecuzioni del gate non
  sono una stima di varianza (P1.7), quindi la banda fra i due valori misurati
  e' un **intervallo dichiarato**, non un intervallo di confidenza.
* Non corregge i dati: `u_bias,b` e' un contributo di incertezza in quadratura,
  non una correzione sistematica (protocollo :1928-1931). Il segno del bias si
  riporta, non si applica.

Cosa verifica, in relazioni matematiche
---------------------------------------
1. **I due artefatti sono dello stesso disegno** (stesso `order_seed`,
   geometria, modello, `dt_nominal_s`) e il loro esito e' un fallimento del
   criterio, non una non-eseguibilita': quorum raggiunto in entrambi. La
   differenza fra le due esecuzioni e' l'ambiente (precondizione di quiete
   presente solo l'08-11; 2 controlli scartati dal filtro assoluto solo
   l'07-11), non il protocollo.
2. **`bias_w` si rigenera dai controlli utilizzabili** come
   `Σ_c E_net,control,c / Σ_c Δt_W,c` e riproduce il valore riportato: e' la
   definizione congelata (F.12), non una nuova.
3. **La soglia si rigenera** come mediana dei `budget_base_w,c` dei soli
   controlli utilizzabili (`statistics.median`, con n pari la media dei due
   centrali) e riproduce `bias_threshold_w`.
4. **La banda dichiarata**: i due valori misurati, il loro rapporto, il segno
   concorde, e la traduzione in unita' di metrica `|bias_w|·6 / |bias_w|·11`
   riprodotta e confrontata con la coppia riportata negli artefatti.
5. **`Δt̄_W,b`**: la durata nominale congelata `dt_nominal_s = 2,930748 s`
   (pilota P2.9) contro la media misurata delle finestre dei controlli
   utilizzabili di ciascun run: la stima pre-campagna e' ancorata a un numero
   congelato, e la concordanza e' verificata entro una tolleranza dichiarata.
6. **La propagazione**: `u_bias,b = |bias_w| · Δt̄_W,b` ai due estremi della
   banda con la durata nominale; il valore dichiarato per il budget della
   campagna e' l'estremo conservativo; la forma della componente
   (`value`/`tipo`/`inclusa`/`motivo`) e' validata dal validatore di
   produzione `tools/gate_uncertainty.py` e combinata in quadratura, cosi' la
   convenzione e' eseguibile e non e' una frase.

Uso: `python u_bias_budget_pred_probe.py`. Non tocca hardware, non legge il
contatore EMI, non dipende da Ollama: legge JSON congelati e fa aritmetica,
quindi e' eseguibile ovunque e il suo output è riproducibile bit per bit.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

GATE_07 = os.path.join(HERE, "experiment_results", "p44_gate_20261107",
                       "analysis.json")
GATE_08 = os.path.join(HERE, "experiment_results", "p44_gate_20261108",
                       "analysis.json")
DT_NOMINALE = os.path.join(HERE, "experiment_results", "p29_pilot_20261107",
                           "dt_nominal_frozen.json")
GATE_UNCERTAINTY = os.path.join(HERE, "cwEnergyModular", "tools",
                                "gate_uncertainty.py")

# Scala ancorata della traduzione in unita' di metrica (P4.5, protocollo
# :1808-1819): 1 W di bias sposta J/token del 6-11% alla geometria operativa.
# È una grandezza riportata, non una soglia.
JTOK_LO, JTOK_HI = 6.0, 11.0

# Tolleranza sulla concordanza fra `dt_nominal_s` congelata e la media misurata
# delle finestre dei controlli utilizzabili. La finestra di controllo attende
# la durata nominale, quindi le due grandezze devono coincidere a meno della
# cadenza del contatore e degli sconfinamenti del cooldown: 5e-3 in relativo
# copre il caso peggiore osservato (run 07-11, controllo con
# `block_cooldown_timeout = true`) e boccia uno scostamento strutturale.
TOLL_DT_RELATIVA = 5e-3


def carica_json(percorso: str) -> dict:
    with open(percorso, "r", encoding="utf-8") as fh:
        return json.load(fh)


def carica_gate_uncertainty():
    """Il validatore di produzione, non una reimplementazione locale."""
    specifica = importlib.util.spec_from_file_location(
        "gate_uncertainty", GATE_UNCERTAINTY)
    modulo = importlib.util.module_from_spec(specifica)
    sys.modules["gate_uncertainty"] = modulo
    specifica.loader.exec_module(modulo)
    return modulo


def controlli_utilizzabili(analysis: dict) -> list:
    """I soli controlli ammessi al criterio dal filtro assoluto di P4.5."""
    return [c for c in analysis["controls"] if c.get("usable") is True]


def bias_da_controlli(analysis: dict) -> float:
    """`bias_w = Σ_c E_net,control,c / Σ_c Δt_W,c` sui soli utilizzabili."""
    utili = controlli_utilizzabili(analysis)
    return sum(c["e_net_j"] for c in utili) / sum(c["dt_w_s"] for c in utili)


def soglia_da_controlli(analysis: dict) -> float:
    """Mediana dei `budget_base_w,c` sui soli controlli utilizzabili."""
    return statistics.median(
        c["budget_base_w"] for c in controlli_utilizzabili(analysis))


def dt_medio_misurato(analysis: dict) -> float:
    """Media delle durate delle finestre dei controlli utilizzabili."""
    utili = controlli_utilizzabili(analysis)
    return sum(c["dt_w_s"] for c in utili) / len(utili)


def verifica_1_artefatti(a7: dict, a8: dict, dt_nom: dict) -> bool:
    """Stesso disegno, due ambienti, due fallimenti del criterio (non N/A)."""
    print("1. I due artefatti congelati")
    stesso = (a7["order_seed"] == a8["order_seed"]
              and a7["geometry"] == a8["geometry"]
              and a7["model"] == a8["model"]
              and a7["dt_nominal_s"] == a8["dt_nominal_s"]
              == dt_nom["dt_nominal_s"])
    print("   order_seed   : %s (identico)" % a7["order_seed"])
    print("   geometria    : %s | modello %s" % (a7["geometry"], a7["model"]))
    print("   dt_nominal_s : %.6f s (congelata dal pilota P2.9)"
          % a7["dt_nominal_s"])
    for etichetta, a in (("07-11", a7), ("08-11", a8)):
        ambiente = ("quieto (precondizione verificata)"
                    if "quiet_precondition" in a else
                    "rumoroso (2 controlli scartati da |dP| > 1 W)")
        print("   %s: status=%s executable=%s  utilizzabili %d/%d, quorum %d"
              % (etichetta, a["status"], a["executable"],
                 a["controls_usable_n"], a["n_pairs"], a["quorum"]))
        print("          bias_w=%.6f W  soglia=%.6f W  ambiente: %s"
              % (a["bias_w"], a["bias_threshold_w"], ambiente))
    ok = (stesso
          and a7["status"] == "fail" and a8["status"] == "fail"
          and a7["executable"] and a8["executable"]
          and a7["controls_usable_n"] >= a7["quorum"]
          and a8["controls_usable_n"] >= a8["quorum"])
    print("   esito: %s — stesso disegno, due esecuzioni, entrambe fail del"
          % ("PASSA" if ok else "FALLISCE"))
    print("          criterio (quorum raggiunto: non e' una non-eseguibilita';")
    print("          la differenza e' l'ambiente, non il protocollo)")
    return ok


def verifica_2_bias(a7: dict, a8: dict) -> bool:
    """`bias_w` rigenerato dai controlli utilizzabili riproduce il riportato."""
    print("\n2. Rigenerazione di bias_w = Σ E_net,c / Σ Δt_W,c (solo utilizzabili)")
    ok = True
    for etichetta, a in (("07-11", a7), ("08-11", a8)):
        rig = bias_da_controlli(a)
        rip = a["bias_w"]
        scarto = abs(rig - rip)
        ok = ok and scarto <= 1e-12 * max(1.0, abs(rip))
        print("   %s: rigenerato %.15f W  riportato %.15f W  scarto %.1e"
              % (etichetta, rig, rip, scarto))
    print("   esito: %s — la definizione congelata riproduce il valore"
          % ("PASSA" if ok else "FALLISCE"))
    print("          riportato in entrambi gli artefatti")
    return ok


def verifica_3_soglia(a7: dict, a8: dict) -> bool:
    """La soglia e' la mediana dei budget dei soli controlli utilizzabili."""
    print("\n3. Rigenerazione della soglia = mediana_c(budget_base_w,c)")
    ok = True
    for etichetta, a in (("07-11", a7), ("08-11", a8)):
        rig = soglia_da_controlli(a)
        rip = a["bias_threshold_w"]
        scarto = abs(rig - rip)
        ok = ok and scarto <= 1e-12 * max(1.0, abs(rip))
        print("   %s: rigenerata %.15f W  riportata %.15f W  scarto %.1e"
              % (etichetta, rig, rip, scarto))
    print("   esito: %s — `statistics.median` sui soli utilizzabili"
          % ("PASSA" if ok else "FALLISCE"))
    print("          riproduce la soglia (con n pari e' la media dei due")
    print("          centrali: 0,222563 e 0,302084 l'07-11; 0,033178 e")
    print("          0,202812 l'08-11)")
    return ok


def verifica_4_banda(a7: dict, a8: dict) -> tuple:
    """La banda dichiarata: due valori, segno concorde, traduzione in metrica."""
    print("\n4. La banda dichiarata fra le due esecuzioni")
    b7, b8 = a7["bias_w"], a8["bias_w"]
    lo, hi = min(b7, b8), max(b7, b8)
    print("   banda di bias_w: [%.6f ; %.6f] W   rapporto %.2f volte"
          % (lo, hi, hi / lo))
    print("   segno: entrambi positivi — il residuo netto dei controlli e'")
    print("         positivo in entrambe le esecuzioni, quindi la baseline")
    print("         sottostima la potenza durante la finestra e l'energia")
    print("         pubblicata risulta sovrastimata, in entrambi gli ambienti")
    ok_segno = b7 > 0.0 and b8 > 0.0
    print("   estremo conservativo (quello che entra nel budget): %.6f W" % hi)
    ok_jtok = True
    for etichetta, a in (("07-11", a7), ("08-11", a8)):
        rip = a["bias_jtok_pct"]
        rig = [abs(a["bias_w"]) * JTOK_LO, abs(a["bias_w"]) * JTOK_HI]
        scarto = max(abs(rig[0] - rip[0]), abs(rig[1] - rip[1]))
        ok_jtok = ok_jtok and scarto <= 1e-9
        print("   traduzione %s: |bias|·6/·11 = [%.6f ; %.6f] %% di J/token"
              " (riportata [%.6f ; %.6f], scarto %.1e)"
              % (etichetta, rig[0], rig[1], rip[0], rip[1], scarto))
    ok = ok_segno and ok_jtok
    print("   esito: %s — segno concorde e traduzione in unita' di metrica"
          % ("PASSA" if ok else "FALLISCE"))
    print("          riprodotta; grandezza riportata, non soglia")
    return ok, lo, hi


def verifica_5_dt(a7: dict, a8: dict, dt_nom: dict) -> bool:
    """`dt_nominal_s` congelata contro la media misurata delle finestre."""
    print("\n5. Δt̄_W,b: durata nominale congelata vs media misurata")
    nominale = dt_nom["dt_nominal_s"]
    regola = dt_nom.get("rule", "")
    print("   dt_nominal_s = %.6f s (regola: %s)"
          % (nominale, regola.split(":")[0] if regola else "P4.4 requisito 5"))
    ok = True
    for etichetta, a in (("07-11", a7), ("08-11", a8)):
        misurata = dt_medio_misurato(a)
        rel = abs(misurata - nominale) / nominale
        ok = ok and rel <= TOLL_DT_RELATIVA
        print("   %s: media misurata %.6f s su %d controlli utilizzabili,"
              " scarto relativo %.2e (tolleranza %.0e)"
              % (etichetta, misurata, a["controls_usable_n"], rel,
                 TOLL_DT_RELATIVA))
    print("   esito: %s — la stima pre-campagna e' ancorata a un numero"
          % ("PASSA" if ok else "FALLISCE"))
    print("          congelato e la media misurata degli utilizzabili la")
    print("          conferma: la finestra di controllo attende il nominale.")
    print("          Lo scostamento del 07-11 viene dal controllo con")
    print("          cooldown fuori tempo (Δt_W = 2,960884 s), dichiarato")
    print("          nell'artefatto (`block_cooldown_timeout = true`).")
    return ok


def verifica_6_propagazione(a7: dict, a8: dict, dt_nom: dict,
                            lo: float, hi: float, gu) -> bool:
    """u_bias,b ai due estremi, componente validata dal validatore di produzione."""
    print("\n6. Propagazione u_bias,b = |bias_w| · Δt̄_W,b in budget_pred_b")
    nominale = dt_nom["dt_nominal_s"]
    u_lo = lo * nominale
    u_hi = hi * nominale
    print("   stima pre-campagna (Δt̄ = dt_nominal_s = %.6f s):" % nominale)
    print("     estremo 08-11 : %.6f W × %.6f s = %.6f J"
          % (lo, nominale, u_lo))
    print("     estremo 07-11 : %.6f W × %.6f s = %.6f J"
          % (hi, nominale, u_hi))
    print("   con la media misurata delle finestre di ciascun run:")
    for etichetta, a in (("07-11", a7), ("08-11", a8)):
        misurata = dt_medio_misurato(a)
        print("     %s: %.6f W × %.6f s = %.6f J"
              % (etichetta, a["bias_w"], misurata, a["bias_w"] * misurata))
    print("   quando i blocchi della campagna esisteranno, Δt̄_W,b sara' la")
    print("   media per blocco di `duration_s`, la stessa grandezza di")
    print("   u_base,b (protocollo :1890-1905): il numero qui sopra e' una")
    print("   STIMA dichiarata, non una misura.")

    motivo = ("bias dichiarato dei due gate P4.4 eseguiti (07-11 e 08-11), "
              "estremo conservativo; contributo di incertezza comune a tutti "
              "i blocchi della campagna, non correzione sistematica")
    componente = {"value": u_hi, "tipo": "B", "inclusa": True,
                  "motivo": motivo}
    errori = gu.valida_componente("u_bias", componente)
    print("   componente dichiarata per `combina_incluse`:")
    print("     {\"value\": %.6f, \"tipo\": \"B\", \"inclusa\": true,"
          % componente["value"])
    print("      \"motivo\": \"...\"}  — tipo B: l'informazione viene dai")
    print("     gate, non da ripetizioni del blocco b (GUM, JCGM 100:2008)")
    esempio = {
        "u_bias": componente,
        "u_edge": {"value": 0.9, "tipo": "B", "inclusa": True,
                   "motivo": "esempio: termine di bordo, valore segnaposto"},
    }
    rss = gu.combina_incluse(esempio)
    atteso = math.hypot(u_hi, 0.9)
    ok = (not errori and rss is not None
          and abs(rss - atteso) <= 1e-12
          and u_hi > u_lo)
    print("   validatore di produzione: %d errori di forma" % len(errori))
    print("   combinazione in quadratura con un u_edge segnaposto: %.6f J ="
          " hypot(%.6f, 0,9) = %.6f J" % (rss, u_hi, atteso))
    print("   esito: %s — la forma e' accettata dal validatore di produzione"
          % ("PASSA" if ok else "FALLISCE"))
    print("          e il termine entra in quadratura, non in somma")
    return ok


def main() -> int:
    print("=" * 74)
    print("Banda di bias_w dei due gate P4.4 e propagazione in budget_pred_b")
    print("=" * 74)
    a7 = carica_json(GATE_07)
    a8 = carica_json(GATE_08)
    dt_nom = carica_json(DT_NOMINALE)
    gu = carica_gate_uncertainty()

    esiti = [
        verifica_1_artefatti(a7, a8, dt_nom),
        verifica_2_bias(a7, a8),
        verifica_3_soglia(a7, a8),
    ]
    ok_banda, lo, hi = verifica_4_banda(a7, a8)
    esiti.append(ok_banda)
    esiti.append(verifica_5_dt(a7, a8, dt_nom))
    esiti.append(verifica_6_propagazione(a7, a8, dt_nom, lo, hi, gu))

    print("\n" + "=" * 74)
    print("esito complessivo: %d/%d verifiche superate"
          % (sum(bool(e) for e in esiti), len(esiti)))
    print("=" * 74)
    print("\nDichiarazione per la campagna principale (percorso (b) di P4.5):")
    print("* entrambi i fail sono conservati, con la provenienza di ciascuno")
    print("  (git_head e runner_sha256 nei due `analysis.json`);")
    print("* il bias entra in `budget_pred_b` come `u_bias,b = |bias_w| ·")
    print("  Δt̄_W,b` con l'estremo conservativo della banda, dichiarato come")
    print("  STIMA di tipo B finche' i blocchi della campagna non definiscono")
    print("  il proprio Δt̄_W,b;")
    print("* la validazione di F.12 NON e' superata: l'anello 4 di P4.9 cede,")
    print("  `chain_status` resta `bias_declared` e nessuna riga e' `validated`.")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())

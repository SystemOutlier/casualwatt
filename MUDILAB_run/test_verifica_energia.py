"""Test delle funzioni di `verifica_energia.py`, su righe sintetiche.

Perche' esistono. `verifica_energia.py` calcola sei definizioni di "joule di un
run" sopra gli stessi artefatti e ne stampa i totali: se una delle sue funzioni
summa male, il numero che ne esce (901,683 contro il pubblicato 964,929) e' solo
un numero piu' grande sbagliato in un altro modo. Qui non si misura nulla sulla
marca: si fissa il **comportamento** delle primitive (`_finestra`, `_somma`,
`_delta_passi`, `_aggrega`, e dalla chiusura del 03-11 `baseline_da_note`,
`passi_appaiati`, `riposo`, `marginali`, `_variante`, `_valutazione_da_artefatto`)
su righe costruite a mano, perche' le proprieta' che rendono leggibile il confronto
sono tutte proprieta' generali, non osservazioni sui 240 run:

1. la correzione tocca **solo** il terzo ramo della cascata: una righe che ha una
   finestra totale valida da `pubblicata` e da `passi_attiva` esce con lo stesso
   numero (se cosi' non fosse, il delta non sarebbe attribuibile alle righe
   fermate dal gate e il discorso sul "limite inferiore" cadrebbe);
2. un `attiva_valida` spento **non si somma come zero**: la riga si dichiara
   scoperta, perche' sommare 0 vorrebbe dire contare un joule che non c'e' e
   tenere la riga nel denominatore (e' la stessa norma del protocollo: nessuna
   baseline calibrata -> si dichiara, non si inventa lo zero);
3. il denominatore di `j_per_corretta` sono le risposte corrette, non le righe con
   un numero: una riga senza energia resta fuori dal numeratore e **dentro** il
   conteggio delle corrette se e' corretta;
4. se la baseline e' zero (attiva == package riga per riga) le due definizioni
   coincidono: e' la verifica aritmetica che il delta che si stampa e' esattamente
   la quota di riposo, non un effetto di seconda mano;
5. (dalla chiusura) la quota di riposo si chiama **riposo** solo se i tre numeri
   che la definiscono stanno nello stesso oggetto: baseline letta dalla nota della
   riga, `(package - attiva)` per passo, e i `seconds` per passo. `riposo` deve
   dare gli stessi joule dalla somma degli scarti e dal prodotto, e deve tornare
   None se uno dei tre manca -- un'identita' costruita con la baseline di un'altra
   riga o con un tempo dedotto sarebbe vera per costruzione;
6. le mediane di branca (`marginali`) che stimano il costo del tratto tagliato dal
   gate **non** devono essere prese sulle righe che quel tratto non ce l'hanno: se
   una riga fermata entrasse nel campione, la stima di "quanto costa il tratto in
   piu'" la si starebbe facendo su chi non lo ha percorso.

Cosa **non** fissano: il valore dei numeri sulla marca, che e' lavoro dello script
e il cui output va in `harness/risultati/verifica_energia_<data>.txt`.

Uso:  MUDILAB_COPIE=1 python -m pytest MUDILAB_run/test_verifica_energia.py -v

`python` qui e' l'interprete che ha pytest: su questo host e' il 3.14 di sistema
(`pytest 9.1.1`, verificato il 03-11), **non** il venv di misura
(`MUDILabV/mudilab_env/Scripts/python.exe`), che non installa pytest. Lo stesso
modulo si importa in entrambi: pyAgrum serve a `benchmark/valuta._confronta`, e
nessuna copia della relatrice ne' nessun modello viene toccato; la variabile
d'ambiente serve per tenere la stessa invocazione degli altri test di questa
cartella.
"""

import json

import pytest

import verifica_energia as VE


# due forme prese dai JSON registrati: la riga che arriva alla finestra totale e
# quella che il gate ferma prima del calcolo (`totale: null`, due passi misurati).
CON_FINESTRA = {
    "totale": {"energia_attiva_j": 100.0, "energia_pkg_j": 130.0, "attiva_valida": True},
    "steps": [{"misura": {"energia_attiva_j": 60.0, "energia_pkg_j": 78.0,
                          "attiva_valida": True}},
              {"misura": {"energia_attiva_j": 30.0, "energia_pkg_j": 39.0,
                          "attiva_valida": True}}],
    "fuori_dai_passi_j": 10.0,
}
SENZA_FINESTRA = {
    "totale": None,
    "steps": [{"misura": {"energia_attiva_j": 60.0, "energia_pkg_j": 78.0,
                          "attiva_valida": True}},
              {"misura": {"energia_attiva_j": 30.0, "energia_pkg_j": 39.0,
                          "attiva_valida": True}}],
    "fuori_dai_passi_j": None,
}


def test_il_terzo_ramo_pubblicato_somma_il_package_dei_passi():
    """Il ramo sotto accusa, fissato: una riga fermata dal gate vale 117, non 90.

    E' la ragione per cui lo script esiste. Con `totale` assente la cascata di
    `valuta.py` ricade sui passi e prende `energia_pkg_j`: 78 + 39 = 117, mentre
    l'energia attiva degli stessi due passi e' 60 + 30 = 90. Se questo numero
    cambia senza una decisione, cambia la metrica pubblicata.
    """
    joule, dove = VE._valore(SENZA_FINESTRA, "pubblicata")
    assert joule == pytest.approx(117.0)
    assert dove == "somma_passi"


def test_passi_attiva_cambia_solo_le_righe_senza_finestra():
    """La correzione minima e' minima per davvero: 100 dove c'e' la finestra, 90 dove non c'e'.

    Senza questa proprieta' il delta stampato non sarebbe attribuibile alle 102
    righe fermate dal gate, e "964,9 include la quota di riposo di quelle righe"
    sarebbe una frase su un numero che si muove anche altrove. La riga con la
    finestra prende l'attiva di finestra (100) da entrambe le definizioni: il
    package di quella riga (130) non entra mai nel conto, nemmeno pubblicato.
    """
    assert VE._valore(CON_FINESTRA, "pubblicata") == (pytest.approx(100.0),
                                                     "totale_attiva")
    assert VE._valore(CON_FINESTRA, "passi_attiva")[0] == pytest.approx(100.0)
    assert VE._valore(SENZA_FINESTRA, "passi_attiva") == (pytest.approx(90.0),
                                                          "somma_passi_attiva")


def test_attiva_non_valida_si_dichiara_scoperta_non_si_somma_come_zero():
    """Un passo con `attiva_valida` spento esce dalla somma e viene contato.

    E' la norma del protocollo sulle baseline: senza calibrazione il numero non
    si inventa a zero. Se `_somma` trattasse il caso come 0.0, una riga con un
    solo passo valido entrerebbe nel totale con meta' energia e il delta
    sarebbe una mediazione fra denominatori diversi.
    """
    meta_valida = {"steps": [{"misura": {"energia_attiva_j": 60.0,
                                         "energia_pkg_j": 78.0,
                                         "attiva_valida": True}},
                             {"misura": {"energia_attiva_j": 30.0,
                                         "energia_pkg_j": 39.0,
                                         "attiva_valida": False}}]}
    assert VE._somma(meta_valida, "energia_attiva_j") == (60.0, 1, 1)
    assert VE._somma(meta_valida, "energia_pkg_j") == (117.0, 2, 0)


def test_nessun_passo_coperto_lascia_la_riga_fuori_dal_conto():
    """`_somma` torna None, non 0.0: la riga cala dalla copertura, non dal totale.

    E' l'analogo a livello di passo del "limite inferiore" di `valuta.py`: un run
    senza numero energetico non deve aggiungere nulla ne' spostare il
    denominatore.
    """
    vuoto = {"steps": [{"misura": {"energia_pkg_j": None}}, {"misura": {}}]}
    assert VE._somma(vuoto, "energia_pkg_j") == (None, 0, 2)
    assert VE._valore(vuoto, "passi_attiva") == (None, "assente")


def test_la_finestra_non_prende_attiva_se_non_e_valida():
    """Il gate di `_finestra` e' `attiva_valida`, non la presenza del numero.

    Il campo esiste anche quando la baseline non e' calibrata (vale l'attiva di
    default, che e' la package): prenderlo per buono presenterebbe come "meno il
    riposo" un numero che il riposo non l'ha tolto.
    """
    non_calibrata = {"totale": {"energia_attiva_j": 130.0, "energia_pkg_j": 130.0,
                               "attiva_valida": False}}
    assert VE._finestra(non_calibrata, "energia_attiva_j") == (None, "attiva_non_valida")
    assert VE._finestra(non_calibrata, "energia_pkg_j") == (130.0, "finestra")
    assert VE._finestra({"totale": None}, "energia_attiva_j") == (None, "nessuna_finestra")


def test_delta_passi_esige_entrambe_le_grandezze():
    """La coppia (package, attiva) per passo si fa solo se tutte e due esistono.

    Serve alla sezione 2 dello script, che imputa lo scarto alla quota di riposo:
    un delta costruito su un sottoinsieme di passi sarebbe attribuito a un'altra
    cosa.
    """
    monco = {"steps": [{"misura": {"energia_attiva_j": 60.0, "energia_pkg_j": 78.0,
                                   "attiva_valida": True}},
                       {"misura": {"energia_pkg_j": 39.0}}]}
    assert VE._delta_passi(monco) is None
    assert VE._delta_passi(SENZA_FINESTRA) == (pytest.approx(117.0),
                                               pytest.approx(90.0))


def test_aggrega_divide_per_le_corrette_non_per_le_righe_coperte():
    """`j_per_corretta` = energia / risposte corrette, e la copertura si dichiara.

    E' la definizione di `valuta.py:308`, quella da cui viene il 964,929: quattro
    righe, due corrette, una senza energia -> (100 + 90 + 90) / 2, non / 3 e non
    / 4. Se il denominatore fosse quello delle righe coperte il numero salirebbe
    perche' un run fallito e' uscito dal conto invece che dall'energia.
    """
    senza = {"totale": None, "steps": [{"misura": {}}]}
    risultati = [("a", CON_FINESTRA), ("b", SENZA_FINESTRA),
                 ("c", SENZA_FINESTRA), ("d", senza)]
    totale, coperte, per_corretta = VE._aggrega(risultati, 2, "passi_attiva")
    assert coperte == 3
    assert totale == pytest.approx(100.0 + 90.0 + 90.0)
    assert per_corretta == pytest.approx(totale / 2)


def test_con_baseline_a_zero_le_due_definizioni_tornano_lo_stesso_numero():
    """Se non c'e' riposo da sottrarre, la correzione non sposta niente.

    E' la verifica che il delta e' **esattamente** la quota di riposo e non un
    effetto della cascata: stessa riga, stessa finestra, attiva == package ->
    `pubblicata` e `passi_attiva` coincidono al centesimo.
    """
    identica = {"totale": None,
                "steps": [{"misura": {"energia_attiva_j": 78.0, "energia_pkg_j": 78.0,
                                      "attiva_valida": True}},
                          {"misura": {"energia_attiva_j": 39.0, "energia_pkg_j": 39.0,
                                      "attiva_valida": True}}]}
    risultati = [("x", identica)]
    assert VE._aggrega(risultati, 1, "pubblicata")[:1] == \
        VE._aggrega(risultati, 1, "passi_attiva")[:1]


def test_un_nome_di_definizione_sconosciuto_solleva():
    """Un refuso nel nome di una definizione non deve stampare un altro numero.

    Con sei definizioni in tabella, una scritta male darebbe la riga della
    definizione che si credeva di stare leggendo: meglio un errore secco.
    """
    with pytest.raises(ValueError):
        VE._valore(CON_FINESTRA, "passi_ativa")


# ------------------------------------------------------- le primitive della chiusura

NOTA = {"misura": {"note": ["canale emi-counter", "baseline calibrata: 6.480 W"]}}


def _passo(nome, pkg, att, sec, valida=True):
    return {"step": nome, "seconds": sec,
            "misura": {"energia_pkg_j": pkg, "energia_attiva_j": att,
                       "attiva_valida": valida}}


def test_la_baseline_si_legge_dalla_nota_della_riga_e_non_si_deduce():
    """I watt di baseline sono **quelli dichiarati dalla riga**, o None.

    La chiusura del 03-11 dice che lo scarto delle 102 righe e' riposo perche'
    eguaglia `baseline x secondi`. Se la baseline fosse presa dalla marca (o, peggio,
    stimata da chi legge), l'identita' sarebbe vera per costruzione e direbbe zero.
    Qui si fissa che `baseline_da_note` legge il numero scritto nelle note dello
    stesso run e torna None quando la nota non c'e' -- e None, nelle funzioni sopra,
    significa "questa riga esce dal confronto", non "baseline zero".
    """
    assert VE.baseline_da_note(NOTA) == pytest.approx(6.48)
    assert VE.baseline_da_note({"misura": {"note": ["canale emi-counter"]}}) is None
    assert VE.baseline_da_note({"misura": {}}) is None
    assert VE.baseline_da_note({}) is None


def test_passi_appaiati_esclude_il_passo_monco_e_mantiene_il_nome():
    """Un passo entra nell'identita' solo con package, attiva e **secondi**, e il
    nome viaggia con la tupla.

    Sono due bisogni distinti della sezione 9. Il primo: un'identita'
    `(package - attiva) = baseline x secondi` calzata su un sottoinsieme di passi e'
    un'identita' falsa, quindi `classificator` senza `seconds` e il passo con
    `attiva_valida` spento devono **sparire**, non entrare come zero. Il secondo: il
    tratto che il gate taglia si distingue da quello che resta solo per nome dei passi
    (`translator`+`classificator` contro `cau_inference`+`causal_A`), e la distinzione
    per posizione o per conteggio si rompere' al primo ramo con un passo in piu'.
    """
    riga = {"steps": [_passo("translator", 78.0, 60.0, 3.0),
                      {"step": "classificator",
                       "misura": {"energia_pkg_j": 39.0, "energia_attiva_j": 30.0,
                                  "attiva_valida": True}},
                      _passo("cau_inference", 20.0, 10.0, 1.5, valida=False),
                      _passo("causal_A", 40.0, 25.0, 3.0)]}
    assert VE.passi_appaiati(riga) == [("translator", 78.0, 60.0, 3.0),
                                       ("causal_A", 40.0, 25.0, 3.0)]
    assert VE.passi_appaiati({}) == []


def test_riposo_da_gli_stessi_joule_dalla_somma_e_dal_prodotto():
    """Sul caso costruito a mano le due strade danno lo stesso numero, e la riga
    senza nota non entra.

    E' il cuore della chiusura: `riposo` restituisce **entrambi** i numeri -- la
    somma degli scarti per passo e il prodotto baseline x secondi -- per poter
    stampare il residuo, non l'uguaglianza. Qui la riga e' disegnata perche' il
    residuo sia 0: due passi a 6,48 W di riposo ciascuno (6,1 s e 3,9 s) fanno
    64.8 J da entrambe le parti. Il secondo assert fissa il caso opposto: senza
    baseline dichiarata torna None, quindi la riga non entra nell'identita' e il
    conteggio delle righe confrontabili scende -- che e' cio' che la sezione 6
    stampa, invece di riempire il buco.
    """
    riga = dict(NOTA)
    riga["steps"] = [_passo("translator", 60.0 + 6.48 * 6.1, 60.0, 6.1),
                     _passo("classificator", 30.0 + 6.48 * 3.9, 30.0, 3.9)]
    scarto, previsto = VE.riposo(riga)
    assert scarto == pytest.approx(64.8)
    assert previsto == pytest.approx(64.8)
    assert VE.riposo({"steps": riga["steps"]}) is None
    assert VE.riposo({"misura": NOTA["misura"], "steps": []}) is None


def test_marginali_non_usano_le_righe_che_il_gate_ha_fermato():
    """Le mediane del tratto extra si fanno sui run che **quel tratto l'hanno fatto**.

    Serve alla sezione 9, che stima quanto costerebbe a una riga fermata arrivare al
    tool. Se una riga con due soli passi entrasse nel campione, la media del tratto
    `cau_inference`+`causal_A` verrebbe abbassata da chi non lo ha percorso, e la
    stima sarebbe un artefatto del mix. Qui ci sono due righe da quattro passi e una
    da due: `n` deve valere 2 e le mediane devono essere le mediane delle due
    valide (extra 35 e 50 -> 42,5; riposo di testa 27 e 50 -> 38,5; rapporto
    finestra/passi 1,0 e 2,0 -> 1,5).
    """
    def riga_completa(a1, a2, e1, e2, f, o1, o2):
        return {"totale": {"energia_attiva_j": f * (a1 + a2 + e1 + e2),
                           "energia_pkg_j": 0.0, "attiva_valida": True},
                "steps": [_passo("translator", a1 + o1, a1, 3.0),
                          _passo("classificator", a2 + o2, a2, 2.0),
                          _passo("cau_inference", e1 + 3.0, e1, 1.0),
                          _passo("causal_A", e2 + 5.0, e2, 3.0)]}
    valida = [riga_completa(60.0, 30.0, 10.0, 25.0, 1.0, 18.0, 9.0),
              riga_completa(70.0, 40.0, 15.0, 35.0, 2.0, 30.0, 20.0)]
    fermata = {"totale": None,
               "steps": [_passo("translator", 78.0, 60.0, 3.0),
                         _passo("classificator", 39.0, 30.0, 2.0)]}
    out = VE.marginali({"inter": valida + [fermata]})
    assert out["inter"]["n"] == 2
    assert out["inter"]["attiva_extra"] == pytest.approx(42.5)
    assert out["inter"]["riposo_testa"] == pytest.approx(38.5)
    assert out["inter"]["finestra_su_passi"] == pytest.approx(1.5)


def test_la_variante_si_legge_dal_riepilogo_della_marca(tmp_path):
    """Il nome della variante viene da `riepilogo.json`, non dal nome della cartella.

    L'artefatto di valutazione indicizza per variante: se il cartello della marca
    cambiasse (una copia, un suffisso), la ricerca per nome di cartella darebbe None
    e la sezione 7 stamperebbe "riconciliazione non fatta" per un motivo che non e'
    quello vero. Qui si fissa la precedenza: con il riepilogo presente si usa quello
    che dichiara, senza si ricade sul cartello.
    """
    marca = tmp_path / "risultati_misura" / "b_composta" / "20260101_000000"
    marca.mkdir(parents=True)
    (marca / "riepilogo.json").write_text('{"variante": "b_composta"}', encoding="utf-8")
    assert VE._variante(marca) == "b_composta"
    orfana = tmp_path / "risultati_misura" / "z_pilot" / "20260101_000000"
    orfana.mkdir(parents=True)
    assert VE._variante(orfana) == "z_pilot"


def test_l_artefatto_di_valutazione_si_trova_sopra_la_marca_e_manca_se_manca(tmp_path):
    """`_valutazione_da_artefatto` prende le righe della variante **giusta**, e non
    ne inventa.

    La riconciliazione della sezione 7 ha senso solo se legge l'artefatto che la
    marca ha prodotto: il percorso e' un livello sopra la marca (con il nome proprio
    del pilota, che e' una valutazione separata). Il secondo caso e' quello che
    protegge il conto: se la variante non e' nell'artefatto -- o l'artefatto non
    esiste -- deve tornare (None, None) e la sezione deve dirlo, invece di
    confrontare il ricalcolo con le righe di un'altra variante.
    """
    marca = tmp_path / "risultati_misura" / "b_composta" / "20260101_000000"
    marca.mkdir(parents=True)
    artef = marca.parent.parent / "valutazione.json"
    artef.write_text(json.dumps({"varianti": {"b_composta": {"righe": [{"task_id": "A"}]}}}),
                     encoding="utf-8")
    p, righe = VE._valutazione_da_artefatto(marca, "b_composta")
    assert p == artef and righe == [{"task_id": "A"}]
    assert VE._valutazione_da_artefatto(marca, "b_solo_numero") == (None, None)
    pilota = tmp_path / "risultati_misura_pilota" / "b_composta" / "20260101_000000"
    pilota.mkdir(parents=True)
    (pilota.parent.parent / "valutazione_pilota_dev.json").write_text(
        json.dumps({"varianti": {"b_composta": {"righe": [{"task_id": "P"}]}}}),
        encoding="utf-8")
    p2, r2 = VE._valutazione_da_artefatto(pilota, "b_composta")
    assert p2.name == "valutazione_pilota_dev.json" and r2 == [{"task_id": "P"}]

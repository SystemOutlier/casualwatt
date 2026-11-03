"""Test delle funzioni di `verifica_energia.py`, su righe sintetiche.

Perche' esistono. `verifica_energia.py` calcola sei definizioni di "joule di un
run" sopra gli stessi artefatti e ne stampa i totali: se una delle sue funzioni
summa male, il numero che ne esce (901,683 contro il pubblicato 964,929) e' solo
un numero piu' grande sbagliato in un altro modo. Qui non si misura nulla sulla
marca: si fissa il **comportamento** delle quattro primitive (`_finestra`,
`_somma`, `_delta_passi`, `_aggrega`) su righe costruite a mano, perche' le tre
proprieta' che rendono leggibile il confronto sono tutte proprieta' generali, non
osservazioni sui 240 run:

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
   la quota di riposo, non un effetto di seconda mano.

Cosa **non** fissano: il valore dei numeri sulla marca, che e' lavoro dello script
e il cui output va in `harness/risultati/verifica_energia_<data>.txt`.

Uso:  MUDILAB_COPIE=1 python -m pytest MUDILAB_run/test_verifica_energia.py -v

`python` e' l'interprete del venv di misura
(`MUDILabV/mudilab_env/Scripts/python.exe`). Il modulo importa
`benchmark/valuta.py`, che importa pyAgrum per `_confronta`: nessuna copia della
relatrice e nessun modello vengono toccati, ma la variabile d'ambiente serve per
tenere la stessa invocazione degli altri test di questa cartella.
"""

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

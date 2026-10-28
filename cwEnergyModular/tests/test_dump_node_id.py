# -*- coding: utf-8 -*-
"""
tests/test_dump_node_id.py — Il verbale dell'Appendice D non deve perdere
docstring per colpa del parsing del node id.

Esecuzione (dalla cartella cwEnergyModular/):
    python -m pytest tests/test_dump_node_id.py -v
    python tests/test_dump_node_id.py

Perche' esiste. ``tools/dump_tests_latex.py`` costruisce l'Appendice D della
tesi e dichiara nel suo header quante righe della tabella hanno una docstring.
Il 24/10 l'header usciva con ``100 righe documentate su 101``: una riga
risultava ``nessuna docstring``, ma il test in causa
(``tests/test_metodo_ammissibile.py::test_stato_non_di_misura_produce_none``)
la docstring ce l'ha davvero. La variante con parametro VUOTO --
``@pytest.mark.parametrize("metodo", [..., ""])`` -- produce il node id
``test_stato_non_di_misura_produce_none[]``, e la regex del parser esigeva un
parametro non vuoto (``.+``): niente match, il nome tornava con le parentesi,
la chiave ``(classe, nome)`` non trovava nulla. Un difetto di misura del
generatore, non del test -- e il numero sbagliato finisce in una pagina di tesi.

Che cosa verifica: la forma del node id (con/senza parametro, vuoto o no, in
classe o no) e il fatto che, per il case reale, la chiave di indice trovi la
docstring nell'AST. Verifica anche che un'etichetta parametrizzata lunga e
col trattino (``librehardwaremonitor-energy``) riceva un punto di capo: senza,
la cella non si spezza e il file generato va in overfull nel PDF. Dal 26/10
verifica pure il parametro con SPAZIO, che il 24/10 era ancora invisibile perche'
nessun test era parametrizzato con stringhe contenenti spazi: ``raccogli``
spezzava l'id al primo spazio e ``esegui`` non lo matchava.

Che cosa NON verifica: che la tabella LaTeX generata sia impaginata bene --
il test qui sotto prova che i punti di capo \\emph{esistono}, non che la colonna
li usi e che nessuna riga sfori il margine; quella resta una verifica sul
``main.log`` dopo la compilazione (un ``\\endfirsthead`` mancante, ad esempio,
non produce overfull box).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tools import dump_tests_latex as gen  # noqa: E402


# ------------------------------------------------------------------ forma
@pytest.mark.parametrize("node_id,atteso", [
    ("tests/test_x.py::test_semplice", ("tests/test_x.py", "", "test_semplice", "")),
    ("tests/test_x.py::test_param[emi-counter]",
     ("tests/test_x.py", "", "test_param", "emi-counter")),
    # il caso che il 24/10 perdeva la docstring: parametro stringa vuota
    ("tests/test_x.py::test_param[]", ("tests/test_x.py", "", "test_param", "")),
    ("tests/test_x.py::TestClasse::test_in_classe[0.5]",
     ("tests/test_x.py", "TestClasse", "test_in_classe", "0.5")),
    ("tests/test_x.py::TestClasse::test_in_classe",
     ("tests/test_x.py", "TestClasse", "test_in_classe", "")),
])
def test_il_parser_spetta_il_node_id(node_id, atteso):
    """File, classe, nome e parametro separati correttamente, parametro vuoto incluso."""
    assert gen.nome_e_parametri(node_id) == atteso


def test_parametro_vuoto_non_deforma_il_nome():
    """Il nome restituito per 'test_x[]' e' 'test_x': con le parentesi non esiste in nessun AST."""
    _f, _c, nome, param = gen.nome_e_parametri("tests/test_x.py::test_senza_doc[]")
    assert nome == "test_senza_doc"
    assert param == ""
    assert "[" not in nome


# ----------------------------------------------------- parametro che contiene '::'
def test_il_parametro_puo_contenere_un_node_id():
    """Test parametrizzato con node id come input: il '::' dentro le parentesi NON e' una classe."""
    nid = "tests/y.py::test_parser[tests/x.py::test_semplice-atteso0]"
    assert gen.nome_e_parametri(nid) == (
        "tests/y.py", "", "test_parser", "tests/x.py::test_semplice-atteso0")


def test_classe_riconosciuta_anche_con_parametro_composito():
    """'TestClasse::test_x[a::b]': classe estratta, parametro intero conservato."""
    nid = "tests/y.py::TestClasse::test_x[a::b]"
    assert gen.nome_e_parametri(nid) == ("tests/y.py", "TestClasse", "test_x", "a::b")


# ------------------------------------------------------- parametro con SPAZIO
# 26/10, lo stesso difetto di forma visto il 24/10 col parametro vuoto, ma
# dall'altra parte del pipeline. `@pytest.mark.parametrize` usa la stringa del
# parametro come id tale e quale (gli unici caratteri sostituiti sono quelli non
# stampabili): un id come 'righe0-3-2 durate su 3' arriva reale nella raccolta e
# nella riga di `pytest -v`. Il generatore lo suppose privo di spazi in due
# punti -- `ln.split(" ")[0]` in `raccogli` e `^(\S+::\S+)\s+(PASSED...)` in
# `esegui` -- e in entrambi il node id si troncava al primo spazio. Non e' un
# errore rumoroso: nel primo caso la riga perdeva la docstring e finiva nel
# verbale come 'nessuna docstring' (copertura dichiarata piu' bassa di quella
# vera); nel secondo perdeva l'esito e si stampava '\textbf{n/eseguito}' per un
# test passato. Preso dal guard sull'AST al primo run dei test di baseline del
# 26/10, non da una lettura del file generato.
# I due parametric test qui sotto usano id ESPliciti e corti, non quelli di
# pytest. Un parametro stringa lungo finisce node-id per intero (e' il difetto
# che questo file esiste per intercettare): con le riga-di-output come id la
# prima colonna dell'Appendice D prende un frammento inseguibile da 72 caratteri
# e il guard `test_il_frammento_piu_lunguo_del_verbale_sta_in_un_segmento` cade,
# come e' caduto il 26/10 alla prima esecuzione di questi test.
@pytest.mark.parametrize("riga,atteso", [
    # righe catturate verbatim da `pytest -v` il 26/10
    pytest.param(
        "tests/test_baseline_ordine_v4.py::"
        "test_block_mean_lascia_vuoto_quando_non_e_calcolabile"
        "[righe0-3-2 durate su 3] PASSED [ 15%]",
        ("tests/test_baseline_ordine_v4.py::"
         "test_block_mean_lascia_vuoto_quando_non_e_calcolabile"
         "[righe0-3-2 durate su 3]", "PASSED"),
        id="spazio-nel-parametro"),
    pytest.param(
        "tests/test_judge_edge_capture.py::"
        "test_i_rifiuti_del_bordo_hanno_ciascuno_la_loro_ragione"
        "[call2-nessun \\u0394t] PASSED [ 64%]",
        ("tests/test_judge_edge_capture.py::"
         "test_i_rifiuti_del_bordo_hanno_ciascuno_la_loro_ragione"
         "[call2-nessun \\u0394t]", "PASSED"),
        id="unicode-escapato"),
    # lo stesso formato senza spazio deve continuare a matchare
    pytest.param(
        "tests/test_x.py::test_param[emi-counter] SKIPPED [ 22%]",
        ("tests/test_x.py::test_param[emi-counter]", "SKIPPED"),
        id="senza-spazio"),
])
def test_la_riga_di_esecuzione_con_spazio_porta_l_esito_al_node_id_intero(riga, atteso):
    """Il pattern a quantificatore pigro regge gli spazi nel parametro: id intero ed esito giusto."""
    m = gen._RIGA_ESITO.match(riga)
    assert m is not None, riga
    assert (m.group(1), m.group(2)) == atteso


def test_la_riga_riassuntiva_dei_salti_non_diventa_un_esito():
    """'SKIPPED [3] tests\\test_rapl.py:43: motivo' non ha '::': non puo' generare una riga di tabella."""
    assert gen._RIGA_ESITO.match(
        "SKIPPED [3] tests\\test_rapl.py:43: RAPL non disponibile su questo host"
    ) is None


@pytest.mark.parametrize("riga,vero", [
    pytest.param("tests/test_x.py::test_med[righe0-3-2 durate su 3]", True,
                 id="id-con-spazio"),
    pytest.param("tests/test_x.py::test_med[call0-contatore assente]", True,
                 id="altre-due-parole"),
    pytest.param("tests/test_x.py::test_semplice", True, id="senza-parametro"),
    pytest.param("282 tests collected in 0.38s", False, id="coda-del-conto"),
    pytest.param("= short test summary info =" * 3, False, id="testata-di-sezione"),
    pytest.param("", False, id="riga-vuota"),
])
def test_la_selezione_della_raccolta_prende_le_righe_con_spazio(riga, vero):
    """Un node id con spazi e' una riga di tabella; la coda del conto e le intestazioni no."""
    assert gen._riga_di_raccolta(riga) is vero


def test_il_parametro_con_spazio_arriva_intero_al_parser():
    """Nome e parametro separati anche quando il parametro contiene spazi: il nome non deve portarsi le quadre."""
    nid = "tests/test_x.py::test_med[righe0-3-2 durate su 3]"
    percorso, classe, fname, param = gen.nome_e_parametri(nid)
    assert percorso == "tests/test_x.py"
    assert classe == ""
    assert fname == "test_med"
    assert param == "righe0-3-2 durate su 3"


def test_spazio_nel_parametro_non_e_troncato_dalla_raccolta_reale():
    """Sulla raccolta vera: nessun node id perde la quadra di chiusura."""
    for nid in gen.raccogli(["--collect-only", "-q"]):
        assert "[" not in nid or nid.endswith("]"), nid


@pytest.mark.parametrize("testo,n_parti", [
    ("test_a", 1),
    ("TestC::test_a", 2),
    ("test_a[x::y]", 1),          # il '::' e' dentro il parametro
    ("TestC::test_a[x::y]", 2),
    ("test_a[[]]", 1),            # parentesi bilanciate dentro il parametro
])
def test_lo_spezzatore_ignora_i_separatori_dentro_le_parentesi(testo, n_parti):
    """_spezza_node_id taglia solo fuori dalle quadre: e' li' che sta il confine fra classe e parametro."""
    assert len(gen._spezza_node_id(testo)) == n_parti


# ------------------------------------------------------------------ caso reale
def test_il_case_reale_del_24_10_trova_la_docstring():
    """'test_stato_non_di_misura_produce_none[]' deve risolvere la sua docstring via (classe, nome)."""
    abs_path = os.path.join(gen.MODULE_DIR, "tests/test_metodo_ammissibile.py")
    mod_doc, per_test = gen.docstring_da_ast(abs_path)
    assert os.path.exists(abs_path), abs_path

    nid = "tests/test_metodo_ammissibile.py::test_stato_non_di_misura_produce_none[]"
    percorso, classe, fname, param = gen.nome_e_parametri(nid)
    assert percorso == "tests/test_metodo_ammissibile.py"
    doc = per_test.get((classe, fname), "")
    assert doc, (
        "chiave (classe, nome) = %r non trovata: lo stesso bug che stampava "
        "'100 righe documentate su 101' nell'header dell'Appendice D"
        % ((classe, fname),))
    assert "N/A" in doc or "nessuno zero" in doc or "None" in doc


def test_tutti_i_node_id_raccolti_hanno_un_nome_trovabile_nell_ast():
    """Nessun node id della raccolta produce un nome che l'AST del suo file non conosce."""
    raccolti = gen.raccogli(["--collect-only", "-q"])
    assert raccolti, "raccolta vuota: il verbale sarebbe una tabella senza righe"
    cache = {}
    orfani = []
    for nid in raccolti:
        percorso, classe, fname, _param = gen.nome_e_parametri(nid)
        if percorso not in cache:
            abs_path = os.path.join(gen.MODULE_DIR, percorso)
            cache[percorso] = (gen.docstring_da_ast(abs_path)[1]
                               if os.path.exists(abs_path) else {})
        if fname not in {k[1] for k in cache[percorso]}:
            orfani.append((nid, fname))
    assert not orfani, f"nomi non risolvibili nell'AST: {orfani[:5]}"


# ------------------------------------------------------------ punti di capo
# Il 24/10 il PDF dell'Appendice D usciva con sei overfull box, uno da 66 pt.
# Nessuna delle righe segnalate era un test senza docstring: erano le righe
# parametrizzate sulle etichette di canale. Il generatore spezzava gli
# identificatori solo dopo l'underscore -- ma 'emi-counter' e
# 'librehardwaremonitor-energy' di underscore non ne hanno, e in \texttt il
# trattino NON e' un punto di capo. Il risultato e' che la cella
#   test\_\allowbreak{}...|numero\,(\texttt{librehardwaremonitor-energy})
# non aveva alcun punto dove andare a capo, e sfondava la colonna da
# 0,30\textwidth. Un difetto di impaginazione generato dal generatore: il
# numero dei test era giusto, la pagina no.
@pytest.mark.parametrize("etichetta,segmenti", [
    ("emi-counter", ["emi-", "counter"]),
    ("power-integration", ["power-", "integration"]),
    ("librehardwaremonitor-energy", ["librehardwaremonitor-", "energy"]),
    ("librehardwaremonitor", ["librehardwaremonitor"]),
    ("energy_calculation_method", ["energy_", "calculation_", "method"]),
])
def test_le_etichette_di_canale_hanno_un_punto_di_capo(etichetta, segmenti):
    """Ogni trattino e ogni underscore e' seguito da \\allowbreak: il separatore resta nel frammento prima del capo."""
    tex = gen._spezza_identificatore(gen.tex_escape(etichetta))
    if len(segmenti) > 1:
        assert tex.count("\\allowbreak{}") == len(segmenti) - 1, tex
    assert gen.frammenti_inseguibili(tex) == segmenti


def test_il_frammento_piu_lunguo_del_verbale_sta_in_un_segmento():
    """Sulle 116 righe reali: nessuna cella della prima colonna ha un frammento inseguibile oltre 26 caratteri."""
    peggio = ("", 0)
    for nid in gen.raccogli(["--collect-only", "-q"]):
        _percorso, classe, fname, param = gen.nome_e_parametri(nid)
        for frammento in gen.frammenti_inseguibili(gen.cella_test(fname, classe, param)):
            if len(frammento) > peggio[1]:
                peggio = (frammento, len(frammento))
    # 26 perche' 'librehardwaremonitor-' (20) e' il segmento che il 24/10
    # sfondava la colonna da 0,30\textwidth in \footnotesize \texttt: con i punti
    # di capo la riga si spezza li', senza non si spezza da nessuna parte.
    assert peggio[1] <= 26, (
        "frammento inseguibile di %d caratteri (%r): la prima colonna "
        "dell'Appendice D non lo contiene e il PDF va in overfull box"
        % (peggio[1], peggio[0]))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

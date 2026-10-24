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
docstring nell'AST.

Che cosa NON verifica: che la tabella LaTeX generata sia impaginata bene; quella
e' una verifica visiva sul PDF (e un ``\\endfirsthead`` mancante non produce
overfull box).
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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

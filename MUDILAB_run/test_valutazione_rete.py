"""Test della regola di integrita' rete in `benchmark/valuta.py`.

Perche' esiste. Il pilota misurato del 02-11 su dev (`risultati_misura_pilota/`)
chiude 81 righe con energia al 100% e stampa
`ATTENZIONE: 41 run su una rete diversa da quella dell'oracolo`. Se fosse vero,
meta' del dev -- e meta' dell'held-out, che si usa una volta sola -- non sarebbe
confrontabile. La causa e' misurata, non ipotizzata: su questo host
`core.autocrlf` = true e il filtro di checkout riscrive il .bif. Confronto fra
`git cat-file blob HEAD:MUDILAB_run/consegna/insurance_grafo.bif` e il file su
disco, misurato il 02-11:

    blob git   22719 B, 548 LF nudi, 0 CR+LF, sha 39f9e706..  <- cio' che lessero
                                                               `genera.py` e il
                                                               manifest
    disco      23267 B,   0 LF nudi, 548 CR+LF, sha 94c01027..  <- cio' che legge
                                                               l'harness

23267 - 22719 = 548 = il numero di righe del file, e il testo riga per riga e'
identico. Normalizzando CR+LF -> LF il file di disco ridà `39f9e706..`, il digest
del manifest: le due reti sono lo stesso grafo, fra l'hash del run e quello del
manifest c'e' solo il fine riga.

La regola che questi test fissano: il confronto accetta il digest del manifest
(`esatto`) e, solo se normalizzare i fine riga del file attuale restituisce
proprio quel digest, accetta anche il digest com'e' sul disco (`a-capo`). Un
contenuto diverso non puo' essere ammesso, perche' la normalizzazione non fa
tornare un hash che non torna.

Cosa **non** fanno: nessun confronto fra le due reti caricate con pyAgrum --
sarebbe piu' debole del risultato sui byte, due file identici salvo i fine riga
danno lo stesso grafo per costruzione -- e niente energia: qui non si chiama il
modello.

Uso, con il python di sistema che ha pytest (il venv `MUDILabV` della misura NON
deve contenerlo, vedi `test_coherence_e_oracolo.py`):

    python -m pytest MUDILAB_run/test_valutazione_rete.py -v
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))

# `benchmark/genera.py` importa pyAgrum e pandas, e `valuta.py` importa genera per
# `_confronta`: nessun assert qui sotto usa quelle librerie, ma l'import deve
# riuscire -- se l'ambiente non ha pyAgrum il modulo di test fallisce in modo
# visibile, non silenzioso.
import benchmark.valuta as V  # noqa: E402

MANIFEST = json.loads((HERE / "benchmark" / "manifest.json").read_text(encoding="utf-8"))
RETE_CONSEGNA = HERE / "consegna" / "insurance_grafo.bif"
SHA_MANIFEST = MANIFEST["reti"]["base"]["sha256"]


def _sha(byte: bytes) -> str:
    return hashlib.sha256(byte).hexdigest()


def _norma(byte: bytes) -> bytes:
    return byte.replace(b"\r\n", b"\n")


# -- 1. l'evento reale, ancorato ai byte -------------------------------------------------

def test_rete_di_consegna_e_il_digest_del_manifest():
    """Il disco, normalizzato, DEVE ridare il digest registrato al manifest.

    E' l'ancoraggio del claim: se qualcuno tocca una CPT del file di consegna,
    questo test si spezza e le righe sul grafo base non sono davvero
    confrontabili.
    """
    assert _sha(_norma(RETE_CONSEGNA.read_bytes())) == SHA_MANIFEST


def test_digest_disk_diverso_solo_per_il_fine_riga():
    byte = RETE_CONSEGNA.read_bytes()
    assert _sha(byte) != SHA_MANIFEST
    assert len(byte) - len(_norma(byte)) == byte.count(b"\r\n")
    # se il checkout ha portato CRLF, non ci devono essere LF nudi: sarebbe un
    # file misto, e la normalizzazione non sarebbe piu' invertibile
    if byte.count(b"\r\n"):
        assert byte.count(b"\n") == byte.count(b"\r\n")
    else:  # checkout senza filtro (Linux, o autocrlf=false): identico al manifest
        assert _sha(byte) == SHA_MANIFEST


def test_digest_accettati_del_file_di_consegna():
    accettati = V._digest_accettati(RETE_CONSEGNA, SHA_MANIFEST)
    assert accettati[SHA_MANIFEST] == "esatto"
    assert accettati[_sha(RETE_CONSEGNA.read_bytes())] == "a-capo"


# -- 2. la regola non si allarga ---------------------------------------------------------

def test_contenuto_diverso_non_diventa_a_capo(tmp_path):
    """Una cifra cambiata in una CPT non passa, con o senza normalizzazione."""
    byte = RETE_CONSEGNA.read_bytes()
    assert byte.count(b"0.15") >= 1, "il pattern dell'esperimento non c'e' piu'"
    truccato = byte.replace(b"0.15", b"0.16", 1)
    assert truccato != byte
    falso = tmp_path / "rete.bif"
    falso.write_bytes(truccato)
    accettati = V._digest_accettati(falso, SHA_MANIFEST)
    assert list(accettati.values()) == ["esatto"], accettati
    assert _sha(truccato) not in accettati
    assert _sha(_norma(truccato)) not in accettati


def test_file_assente_da_solo_esatto(tmp_path):
    """Nessun file da normalizzare: la regola non inventa un secondo digest."""
    assert V._digest_accettati(tmp_path / "non_c_e.bif", "abcd") == {"abcd": "esatto"}


# -- 3. l'etichetta che finisce nei JSON -------------------------------------------------

HASH_RETI = V._hash_reti()


def test_hash_reti_etichetta_tutte_e_due_le_reti():
    assert set(HASH_RETI) == {V._chiave_rete(V.ROOT / v["percorso"])
                             for v in MANIFEST["reti"].values()}
    for accettati in HASH_RETI.values():
        assert set(accettati.values()) <= {"esatto", "a-capo"}
        assert "esatto" in accettati.values()


@pytest.mark.parametrize("hash_di_riga,coerente,modo", [
    (lambda: SHA_MANIFEST, True, "esatto"),
    (lambda: _sha(RETE_CONSEGNA.read_bytes()), True, "a-capo"),
    (lambda: "0" * 64, False, "incoerente"),
])
def test_confronto_rete_etichetta_il_confronto(hash_di_riga, coerente, modo):
    riga = {"rete": str(RETE_CONSEGNA), "rete_hash": hash_di_riga()}
    assert V._confronto_rete(riga, HASH_RETI) == (coerente, modo)


def test_percorso_assoluto_quello_che_l_harness_registra():
    """La riga JSON porta il percorso assoluto risolto: deve agganciare la chiave.

    E' il caso reale (`esegui_variante._hash_rete` firma il file passato al tool).
    Se la normalizzazione del percorso non torna, ogni riga risulta incoerente e
    il controllo non serve a niente.
    """
    assert V._chiave_rete(RETE_CONSEGNA) in HASH_RETI
    riga = {"rete": str(RETE_CONSEGNA), "rete_hash": _sha(RETE_CONSEGNA.read_bytes())}
    assert V._confronto_rete(riga, HASH_RETI) == (True, "a-capo")


def test_rete_non_dichiarata_non_e_un_fallimento():
    assert V._confronto_rete({"rete": None, "rete_hash": None}, HASH_RETI) == \
        (None, "non dichiarata")

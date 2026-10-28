# -*- coding: utf-8 -*-
"""``CW_ENERGY_FILE`` e' un override di selezione, non un anello della catena.

``_try_power_counter`` viene chiamato PRIMA del ramo di piattaforma
(``energy/energy_session.py:139``), quindi su Windows un file valido deve
fermare la selezione: se EMI o PawnIO venissero comunque tentati, la riga
mescolerebbe un contatore simulato con un contatore reale e il token
``energy-file`` non descriverebbe piu' la sorgente del numero. Questi test
fissano i tre esiti possibili:

  * file presente e leggibile -> metodo ``energy-file``, catena terminata;
  * file assente -> ``False`` e la catena Windows prosegue (EMI);
  * file con valore non numerico -> ``False`` e la catena prosegue.

La terza condizione esiste perche' un file corrotto non deve diventare un
metodo dichiarato: ``_read_energy_file`` restituisce ``None`` e il chiamante
tratta il caso come "questo anello non risponde", non come uno zero.
"""
from pathlib import Path

from energy import energy_session as es


def _scrivi_file_energia(tmp_path: Path, valore: str = "123.45") -> Path:
    path = tmp_path / "energy.joule"
    path.write_text(valore, encoding="utf-8")
    return path


def _sessione_senza_init():
    """Istanza senza ``__init__``: qui interessa solo ``_try_power_counter``."""
    sessione = es._CPUJouleSource.__new__(es._CPUJouleSource)
    sessione._notes = []
    sessione.method = None
    return sessione


def test_cw_energy_file_ha_priorita_anche_su_windows(tmp_path, monkeypatch):
    """Con il file valido la selezione si ferma: EMI e PawnIO non si tentano.

    Il test non guarda solo il valore di ritorno: costruisce la sorgente
    intera con ``platform_system()`` Windows simulato e i due backend
    sostituiti da funzioni che falliscono. Se la precedenza non fosse reale,
    il costruttore solleverebbe ``AssertionError`` invece di restare su
    ``energy-file``.
    """
    path = _scrivi_file_energia(tmp_path)
    monkeypatch.setenv("CW_ENERGY_FILE", str(path))
    monkeypatch.setattr(es, "platform_system", lambda: "Windows")

    def _non_deve_essere_tentato(self):  # pragma: no cover - solo se fallisce
        raise AssertionError(
            "con una sorgente da file valida la catena deve fermarsi"
        )

    monkeypatch.setattr(es._CPUJouleSource, "_try_emi", _non_deve_essere_tentato)
    monkeypatch.setattr(es._CPUJouleSource, "_try_pawnio", _non_deve_essere_tentato)

    src = es._CPUJouleSource()

    assert src.method == "energy-file"
    assert src._power_path == str(path)
    assert any("[DEV/TEST/Windows]" in nota for nota in src._notes)


def test_cw_energy_file_assente_lascia_passare_la_catena(tmp_path, monkeypatch):
    """File assente: ``False``, nessun metodo fissato, catena Windows su EMI.

    Un percorso inesistente non e' un errore della sessione: e' un override
    che non si applica. Il metodo non deve dichiarare ``unavailable`` ne'
    scrivere ``energy-file``, altrimenti la variabile d'ambiente toglierebbe
    la misura reale per il solo fatto di essere impostata.
    """
    monkeypatch.setenv("CW_ENERGY_FILE", str(tmp_path / "missing.joule"))
    monkeypatch.setattr(es, "platform_system", lambda: "Windows")

    sessione = _sessione_senza_init()

    assert sessione._try_power_counter() is False
    assert sessione.method is None

    def _emi_finta(self):
        self.method = "emi-counter"
        return True

    monkeypatch.setattr(es._CPUJouleSource, "_try_emi", _emi_finta)

    src = es._CPUJouleSource()

    assert src.method == "emi-counter"


def test_cw_energy_file_valore_non_numerico_lascia_passare_la_catena(
        tmp_path, monkeypatch):
    """File illeggibile come numero: ``False`` e la catena prosegue.

    ``_read_energy_file`` restituisce ``None`` su ``ValueError``. Il caso va
    distinto da uno zero legittimo (contatore fermo): un file corrotto non
    produce un numero, quindi non puo' produrre un metodo.
    """
    path = _scrivi_file_energia(tmp_path, valore="not-a-number")
    monkeypatch.setenv("CW_ENERGY_FILE", str(path))
    monkeypatch.setattr(es, "platform_system", lambda: "Windows")

    sessione = _sessione_senza_init()

    assert sessione._try_power_counter() is False
    assert sessione.method is None

    def _emi_finta(self):
        self.method = "emi-counter"
        return True

    monkeypatch.setattr(es._CPUJouleSource, "_try_emi", _emi_finta)

    src = es._CPUJouleSource()

    assert src.method == "emi-counter"

# -*- coding: utf-8 -*-
"""Rete: una volta sola, con il segno giusto, e senza 0.0 al posto di N/A.

Tre correzioni del 2026-10-26, una per gruppo di test, ognuna con la ragione
fisica o aritmetica che la rende obbligatoria.

1. **Lo stesso pacchetto non si conta due volte.** Il tracker somma i byte di
   tutte le interfacce: sotto VPN lo stesso pacchetto compare sull'adattatore
   tunnel (in chiaro) e su quello fisico (cifrato). Sommarli raddoppia il
   termine di rete, e l'errore dipende dalla configurazione della macchina, non
   dal carico. La regola e' contare le interfacce fisiche; l'eccezione e'
   dichiarata, non silenziosa: se le fisiche non vedono byte mentre le virtuali
   si' -- host Hyper-V, dove il traffico passa dallo switch virtuale -- si
   contano tutte le non-loopback e il confine lo scrive. Il test congela
   entrambi i rami, perche' una regola che si applica solo quando conviene non
   e' una regola. La natura dell'interfaccia non si legge dall'alias -- su
   questo host "Ethernet 2" e' un VirtualBox Host-Only -- quindi si usa la
   descrizione del driver quando c'e' e il nome come seconda via; le due letture
   degradate (contatori per interfaccia illeggibili, oppure un bordo per
   interfaccia e l'altro aggregato) sono dichiarate e non producono uno zero:
   l'aggregato include il loopback e lo dice, il delta fra perimetri diversi
   vale `None`.
2. **Un delta negativo non e' un traffico nullo.** Un contatore che si azzera o
   un'interfaccia ricreata nella finestra producono un delta firmato negativo.
   Il valore applicato resta 0 -- i byte negativi non esistono -- ma il grezzo
   va conservato e il fatto dichiarato: e' la stessa regola di
   `negative_increment` nella v4 (`benchmark_v4.py:1685`), e nasce dallo stesso
   errore: un troncamento silenzioso trasforma un guasto in un numero.
3. **N/A non e' 0.0.** Se i contatori non sono leggibili l'energia di rete e'
   `None`, e il log della riga non deve formattarla con `.5f`: su `None` quel
   formato solleva `TypeError`, il `except` a valle trasforma una richiesta
   riuscita in una riga d'errore, e la riga finisce con rete e locale a `0.0`
   (`benchmark_unified.py:1179-1190`). La correzione e' `_j_log`, che esiste per
   questo e ha la docstring che lo dice (`:1269-1275`).

I test non toccano la rete dell'host: le letture sono sintetiche, iniettate con
`monkeypatch` su `NetworkEnergyTracker._read`. L'ultimo test legge il sorgente
del runner, perche' il difetto 3 vive dentro una f-string e non e' raggiungibile
senza una chiamata cloud reale.

4. **La fonte si cita solo per il suo valore.** Il confine della riga dice da
   dove viene il coefficiente: con 2,7 uJ/bit cita Baliga et al. 2011 con
   equazione e pagina, con un `CW_NET_J_PER_BIT` diverso dichiara il parametro e
   tace la citazione. Attribuire l'articolo a un numero che non e' il suo e' una
   citazione inventata sopra un dato. Qui stanno anche i due casi di zero
   legittimo contro zero inventato: la riga locale, dove lo zero e' il confine
   (regola 12.1), e la rete illeggibile in cloud, dove il valore e' `N/A` e lo
   resta fino a `end_to_end_energy_j`.

Esecuzione:  python -m pytest tests/test_rete_nic_confine.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from energy.network_energy import (  # noqa: E402
    NetworkEnergyTracker,
    _NicSample,
    _choose,
    _sum_delta,
    _is_loopback,
    _is_virtual,
)


def _sample(per_nic, source="pernic"):
    """Lettura sintetica: nome interfaccia -> (byte inviati, byte ricevuti)."""
    return _NicSample(per_nic=dict(per_nic), source=source)


@pytest.fixture(autouse=True)
def _senza_registro(monkeypatch):
    """Descrizioni dei driver vuote: i test non dipendono dal registro host.

    La classificazione reale legge il registro di Windows; qui la mappa e'
    iniettata, cosi' l'esito e' lo stesso su qualunque macchina. I due test
    sulla descrizione la sostituiscono con una mappa nota.
    """
    monkeypatch.setattr("energy.network_energy._nic_descriptions", lambda: {})


def _measured(monkeypatch, before, after, fn=None):
    """Esegue una `measure` con le due letture iniettate, senza rete reale."""
    letture = iter([before, after])
    monkeypatch.setattr(
        NetworkEnergyTracker, "_read", staticmethod(lambda: next(letture)))
    return NetworkEnergyTracker().measure(fn or (lambda: "ok"))[1]


# --- 1. selezione delle interfacce -----------------------------------------

def test_sotto_vpn_il_pacchetto_si_conta_una_volta_sola():
    """Fisica + tunnel con gli stessi byte: si contano i byte della fisica.

    Sotto VPN il tunnel trasporta in chiaro cio' che la NIC fisica trasporta
    cifrato: sono lo stesso traffico. Contarli entrambi darebbe 2x, e il fattore
    dipenderebbe dalla configurazione dell'host invece che dal carico.
    """
    before = _sample({"Ethernet": (0, 0), "WireGuard Tunnel": (0, 0)})
    after = _sample({"Ethernet": (1_000_000, 4_000_000),
                     "WireGuard Tunnel": (1_000_000, 4_000_000)})
    names, scope = _choose(before, after)
    assert names == ["Ethernet"]
    assert scope.startswith("physical")
    assert "name only" in scope
    assert _sum_delta(before, after, names) == (1_000_000, 4_000_000)


def test_l_alias_senza_marcatori_si_classifica_con_la_descrizione_del_driver(monkeypatch):
    """Su Windows "Ethernet 2" puo' essere un VirtualBox Host-Only.

    L'alias non lo dice e nessun marcatore del nome lo prende: la descrizione
    del driver si'. Se la si ignora, un adattatore host-only entra nella somma
    come se fosse la scheda che porta il traffico verso il provider.
    """
    monkeypatch.setattr(
        "energy.network_energy._nic_descriptions",
        lambda: {"Ethernet 2": "VirtualBox Host-Only Ethernet Adapter"},
    )
    before = _sample({"Ethernet": (0, 0), "Ethernet 2": (0, 0)})
    after = _sample({"Ethernet": (1000, 2000), "Ethernet 2": (5000, 5000)})
    names, scope = _choose(before, after)
    assert names == ["Ethernet"]
    assert "driver description" in scope
    assert _is_virtual("Ethernet 2", "VirtualBox Host-Only Ethernet Adapter")
    assert not _is_virtual("Ethernet 2")


def test_l_energia_di_rete_con_vpn_non_raddoppia(monkeypatch):
    """1 MB reali su una fisica e sul tunnel -> 8e6 bit, cioe' 21,6 J.

    1,0 MB decimale = 8e6 bit; con 2,7e-6 J/bit sono 21,6 J. Se il tunnel
    venisse sommato sarebbero 43,2 J, con un errore del +100% sul termine di
    rete che nessuna colonna dichiarerebbe.
    """
    before = _sample({"Ethernet": (0, 0), "TAP-Windows Adapter V9": (0, 0)})
    after = _sample({"Ethernet": (100_000, 900_000),
                     "TAP-Windows Adapter V9": (100_000, 900_000)})
    res = _measured(monkeypatch, before, after)
    assert res.total_bytes == 1_000_000
    assert res.energy_j == pytest.approx(21.6, abs=1e-9)


def test_se_le_fisiche_non_vedono_byte_si_ricade_sulle_virtuali_dichiarandolo():
    """Host Hyper-V: il traffico e' sullo switch virtuale, la NIC fisica e' ferma.

    Qui la regola "solo fisiche" darebbe zero byte su una richiesta che c'e'
    stata. Si ricade su tutte le non-loopback -- anche la fisica ferma, che
    contribuisce zero e resta nel confine -- e la ragione finisce nel confine:
    un fallback dichiarato, mai un fallback silenzioso.
    """
    before = _sample({"Ethernet": (0, 0), "vEthernet (Default Switch)": (0, 0)})
    after = _sample({"Ethernet": (0, 0), "vEthernet (Default Switch)": (0, 5_000_000)})
    names, scope = _choose(before, after)
    assert names == ["Ethernet", "vEthernet (Default Switch)"]
    assert "physical counters saw 0 B" in scope
    # La fisica entra nell'elenco ma non nei byte: il totale e' quello del tunnel.
    assert _sum_delta(before, after, names) == (0, 5_000_000)


def test_il_loopback_non_entra_mai_nella_somma():
    """Il loopback non e' rete: i suoi byte non hanno percorso ne' coefficiente."""
    before = _sample({"Ethernet": (0, 0), "Loopback Pseudo-Interface 1": (0, 0)})
    after = _sample({"Ethernet": (10, 10), "Loopback Pseudo-Interface 1": (10**9, 10**9)})
    names, _ = _choose(before, after)
    assert names == ["Ethernet"]
    assert all(n not in names for n in ("Loopback Pseudo-Interface 1",))
    assert _is_loopback("Loopback Pseudo-Interface 1")
    assert not _is_virtual("Ethernet")


def test_il_confine_dichiara_le_interfacce_sommate(monkeypatch):
    """Senza i nomi, due righe con lo stesso numero non sono confrontabili."""
    before = _sample({"Ethernet": (0, 0), "VMware Network Adapter VMnet8": (0, 0)})
    after = _sample({"Ethernet": (512, 1024),
                     "VMware Network Adapter VMnet8": (0, 4096)})
    res = _measured(monkeypatch, before, after)
    assert res.interfaces == "Ethernet"
    assert "interfaces [Ethernet] (physical (name only))" in res.measurement_boundary
    assert _is_virtual("VMware Network Adapter VMnet8")


def test_letture_di_natura_diversa_danno_na_non_zero(monkeypatch):
    """Un bordo per interfaccia e l'altro aggregato: il delta non esiste.

    Sommare interfacce note a un totale che ne contiene di ignote darebbe un
    numero con un perimetro diverso ai due estremi della finestra. La regola e'
    N/A, non 0.0: un perimetro che cambia non e' un traffico nullo.
    """
    before = _sample({"Ethernet": (0, 0)})
    after = _sample({"<aggregato>": (10, 10)}, source="aggregate")
    res = _measured(monkeypatch, before, after)
    assert res.energy_j is None
    assert "source mismatch" in res.measurement_boundary
    assert any("natura diversa" in n for n in res.notes)


def test_la_lettura_aggregata_dichiara_che_il_loopback_non_e_separabile():
    """Ultima risorsa: psutil somma tutte le interfacce, loopback compreso.

    Non e' un perimetro equivalente a quello per interfaccia; il confine lo
    scrive, cosi' la riga non si legge come se il loopback fosse escluso.
    """
    before = _sample({"<aggregato>": (0, 0)}, source="aggregate")
    after = _sample({"<aggregato>": (1000, 2000)}, source="aggregate")
    names, scope = _choose(before, after)
    assert names == ["<aggregato>"]
    assert "loopback not separable" in scope


# --- 2. delta negativo ------------------------------------------------------

def test_delta_negativo_applicato_zero_ma_conservato_e_dichiarato(monkeypatch):
    """Contatore azzerato: il grezzo resta negativo, l'applicato e' 0.

    Un delta negativo e' fisicamente impossibile come traffico: significa che il
    contatore e' stato azzerato o l'interfaccia ricreata nella finestra. Lo zero
    applicato e' un troncamento dichiarato, non una misura; per questo il valore
    grezzo resta in `*_bytes_raw` e la nota lo scrive.
    """
    before = _sample({"Ethernet": (5_000_000, 50_000_000)})
    after = _sample({"Ethernet": (0, 0)})
    res = _measured(monkeypatch, before, after)
    assert res.negative_increment is True
    assert res.upload_bytes_raw == -5_000_000
    assert res.download_bytes_raw == -50_000_000
    assert res.upload_bytes == 0 and res.download_bytes == 0
    assert res.total_bytes == 0
    assert res.energy_j == 0.0
    assert any("negativo" in n for n in res.notes)


def test_delta_positivo_non_alza_il_flag(monkeypatch):
    """La guardia sul flag non deve scattare sul caso normale."""
    before = _sample({"Ethernet": (0, 0)})
    after = _sample({"Ethernet": (1000, 2000)})
    res = _measured(monkeypatch, before, after)
    assert res.negative_increment is False
    assert res.energy_j == pytest.approx(3000 * 8 * 2.7e-6, abs=1e-12)


# --- 3. N/A invece di 0.0 ---------------------------------------------------

def test_contatori_illeggibili_danno_na_non_zero(monkeypatch):
    """La rete non leggibile e' un'assenza dichiarata, non un costo nullo."""
    monkeypatch.setattr(NetworkEnergyTracker, "_read", staticmethod(lambda: None))
    res = NetworkEnergyTracker().measure(lambda: "ok")[1]
    assert res.energy_j is None
    assert res.measurement_boundary == "client-NIC counters unavailable"
    assert any("N/A" in n for n in res.notes)


def test_il_log_della_riga_non_formatta_none_con_punto_fisso():
    """Il difetto era una f-string: su `None`, `.5f` solleva TypeError.

    Il `except` a valle trasforma una richiesta riuscita in riga d'errore con
    locale e rete a 0.0. Il test legge il sorgente perche' quel ramo non e'
    raggiungibile senza una chiamata cloud reale; verifica la sola cosa che
    conta: il formato N-A-aware e' usato per la rete.
    """
    src = (Path(__file__).resolve().parent.parent / "benchmark_unified.py").read_text(
        encoding="utf-8")
    assert "net_res.energy_j:.5f" not in src
    assert "_j_log(net_res.energy_j)" in src


# --- 4. provenienza del coefficiente, zero di confine -----------------------

def test_il_confine_cita_baliga_solo_col_valore_della_fonte(monkeypatch):
    """2,7 uJ/bit -> la riga cita l'articolo; un override -> non lo cita.

    Il confine e' l'unico posto in cui la riga dichiara che cosa contiene il
    joule di rete. Se citasse Baliga anche dopo un `CW_NET_J_PER_BIT` diverso,
    attribuirebbe a una fonte un numero che non e' il suo, e due righe con
    coefficienti diversi sembrerebbero confrontabili.
    """
    from energy.network_energy import (
        NETWORK_ENERGY_COEFFICIENT_DEFAULT_J_PER_BIT as dflt,
        network_coefficient_provenance,
    )

    same = network_coefficient_provenance(dflt)
    assert "Baliga et al. 2011" in same
    assert "DOI 10.1109/JPROC.2010.2060451" in same
    assert "model estimate, not a measurement" in same

    over = network_coefficient_provenance(1.0e-5)
    # L'articolo puo' comparire solo per negarlo: nessun DOI ne' equazione,
    # cioe' nessun ancoraggio bibliografico che lo leghi a questo valore.
    assert "NOT Baliga et al. 2011" in over
    assert "DOI" not in over and "eq. 2" not in over
    assert "CW_NET_J_PER_BIT" in over

    # e il confine della riga vera porta lo stesso testo: non e' una funzione
    # parallela a quella usata in misura.
    before = _sample({"Ethernet": (0, 0)})
    after = _sample({"Ethernet": (1000, 1000)})
    res = _measured(monkeypatch, before, after)
    assert same in res.measurement_boundary


def test_in_cloud_una_rete_non_letta_resta_na_fino_all_end_to_end(monkeypatch):
    """Contatori NIC illeggibili: rete N/A e end-to-end N/A, mai 0,0 J.

    Uno zero al posto di N/A abbasserebbe la somma end-to-end e i J/token della
    riga, e nessuna colonna direbbe che la rete non e' stata misurata: la riga
    sembrerebbe una richiesta senza costo di rete invece di una stima mancante.
    """
    import types

    import benchmark_unified as bu

    monkeypatch.setattr(NetworkEnergyTracker, "_read", staticmethod(lambda: None))
    net_res = NetworkEnergyTracker().measure(lambda: "ok")[1]
    assert net_res.energy_j is None

    ev = types.SimpleNamespace(
        n_correct_links=None, acc_comp=None, is_correct=None, acc_links_basis="",
        acc_links=None, judge_score=None, cosine_sim=None)
    rec = {"output_tokens": 10, "notes": "",
           "local_carbon_intensity_gco2eq_kwh": 0}
    bu._finalize_energy_fields(rec, 5.0, net_res.energy_j, 20.0, ev)
    assert rec["network_energy_j"] == "N/A"
    assert rec["end_to_end_energy_j"] == "N/A"
    assert "network_energy_j" in rec["notes"]


def test_la_riga_locale_dichiara_rete_zero_per_confine(monkeypatch):
    """In locale non esiste un percorso di rete: 0,0 J e il confine lo dice.

    Lo zero qui e' la definizione del perimetro (regola 12.1), non una lettura:
    senza l'etichetta sarebbe indistinguibile da un contatore che ha osservato
    zero byte in una richiesta cloud.
    """
    import types

    import benchmark_unified as bu

    monkeypatch.setattr(
        bu, "get_carbon_intensity",
        lambda zone=None: types.SimpleNamespace(
            gco2eq_per_kwh=267.0, zone="IT", source="test-table", timestamp=0.0))
    rec = bu._basic_record(
        "R1", "S1", "llama", "llama", "ollama", "local", None,
        {"id": "p1", "text": "p", "source": "manual", "ground_truth": "21"},
        bu.evalres_placeholder())
    assert rec["network_energy_j"] == 0.0
    assert rec["network_measurement_boundary"] == "not-applicable (local mode)"

# -*- coding: utf-8 -*-
"""Selezione semantica del device EMI e del canale PKG (F11/F13, decisione D17).

Il backend EMI, fino al 26/10/2026, apriva il PRIMO device apribile e leggeva
il PRIMO canale del record: due assunzioni, non due misure (difetti F11 e F13
della specifica ``metodi_per_dominio_20261025_spec.md``). Il 27/10 il percorso
legge ``IOCTL_EMI_GET_VERSION`` -> ``GET_METADATA_SIZE`` -> ``GET_METADATA`` e
decide sui nomi: un device e' un device CPU solo se espone un canale di dominio
``pkg``, e ogni valore appartiene al canale il cui nome contiene il token del
dominio.

Qui si provano le decisioni, non l'hardware: i metadati sono blob costruiti con
il layout documentato (``EMI_METADATA_V2``: OEM 32 B, modello 32 B, revisione e
ChannelCount u16 a 64 e 66, poi ``EMI_CHANNEL_V2`` = unita' u32 + dimensione
u16 + nome UTF-16), quindi i test girano anche su Linux e su Windows senza
driver. Il metadato reale di questa macchina -- EMI v2, 492 byte, OEM
"Microsoft", modello "PPM", quattro canali ``RAPL_Package0_PKG/_DRAM/_PP0/_PP1``
-- e' il caso del primo test, letto il 27/10/2026.

Le prove che il device selezionato produca lo stesso numero di prima sono
altrove: ``test_emi_backend.py`` (catena e finestre) e i protocolli A-B-A sul
device vero. La selezione per nome non e' una validazione della scala.
"""
import struct

import pytest

from energy import emi_backend as eb

PWH = eb.PWH_TO_J

#: I canali del metadato del host di prova, nell'ordine del record.
REAL_NAMES = ("RAPL_Package0_PKG", "RAPL_Package0_DRAM",
              "RAPL_Package0_PP0", "RAPL_Package0_PP1")


def _blob(channels=(), oem="Microsoft", model="PPM", revision=1, unit=0,
          name_size=None):
    """Metadato V2 con il layout documentato, costruito canale per canale.

    ``name_size`` riproduce il dimensionamento del driver: sul host di prova
    ``ChannelNameSize`` vale 100 byte per ogni canale (nome + riempimento NUL),
    non la lunghezza naturale della stringa.
    """
    head = (oem.encode("utf-16-le").ljust(32, b"\x00")[:32]
            + model.encode("utf-16-le").ljust(32, b"\x00")[:32]
            + struct.pack("<HH", revision, len(channels)))
    body = b""
    for name in channels:
        raw = name.encode("utf-16-le") + b"\x00\x00"
        if name_size is not None:
            assert len(raw) <= name_size
            raw = raw.ljust(name_size, b"\x00")
        body += struct.pack("<IH", unit, len(raw)) + raw
    return head + body


def _meta(names, **kw):
    return eb.parse_metadata(_blob(names, **kw), eb.EMI_VERSION_V2)


# ------------------------------------------------------------------ metadato
def test_metadato_v2_di_questa_macchina_si_interpreta():
    """Il metadato reale (4 canali, 492 byte) da' i nomi, il dominio per nome e l'unita' pWh."""
    blob = _blob(REAL_NAMES, name_size=100)
    assert len(blob) == 492, "il layout deve riprodurre la dimensione osservata"
    meta = eb.parse_metadata(blob, eb.EMI_VERSION_V2)
    assert (meta.hardware_oem, meta.hardware_model, meta.hardware_revision) == (
        "Microsoft", "PPM", 1)
    assert [c.name for c in meta.channels] == list(REAL_NAMES)
    assert [c.domain for c in meta.channels] == ["pkg", "dram", "pp0", "pp1"]
    assert [c.index for c in meta.channels] == [0, 1, 2, 3]
    assert all(c.unit == eb.UNIT_PWH for c in meta.channels)


def test_metadato_troncato_non_diventa_un_canale_in_meno():
    """Un blob tagliato e' un errore dichiarato: leggere meno canali in silenzio sposterebbe i domini."""
    good = _blob(REAL_NAMES)
    with pytest.raises(ValueError, match="troncato"):
        eb.parse_metadata(good[:40], eb.EMI_VERSION_V2)
    # ChannelNameSize che sborda dal metadato: non si legge oltre il buffer
    broken = bytearray(good)
    struct.pack_into("<H", broken, 68 + 4, 60000)
    with pytest.raises(ValueError, match="non plausibile"):
        eb.parse_metadata(bytes(broken), eb.EMI_VERSION_V2)


def test_nome_senza_un_solo_token_non_diventa_un_dominio():
    """Un nome ambiguo o generico non produce un dominio: mancante e' dichiarabile, indovinato no."""
    assert eb.domain_from_channel_name("ENERGY0") is None
    assert eb.domain_from_channel_name("TOTAL") is None
    # due domini nello stesso nome: non si sceglie il primo che capita
    assert eb.domain_from_channel_name("RAPL_Package0_PKG_DRAM") is None
    assert eb.domain_from_channel_name("rapl_package0_pkg") == "pkg"


# ------------------------------------------------------------------ selezione
def test_con_tre_device_si_seleziona_solo_il_cpu():
    """Batteria, GPU e CPU sulla stessa interfaccia: si sceglie il device CPU e gli altri si scartano con motivo."""
    cpu = ("cpu-emi", _meta(REAL_NAMES))
    battery = ("battery-emi", _meta(("BATTERY0_ENERGY", "BATTERY0_POWER")))
    gpu = ("gpu-emi", _meta(("GPU0_ENERGY", "GPU0_POWER")))
    chosen, rejected = eb.select_cpu_device([battery, cpu, gpu])
    assert [c.path for c in chosen] == ["cpu-emi"]
    assert chosen[0].channel.name == "RAPL_Package0_PKG"
    assert {p for p, _ in rejected} == {"battery-emi", "gpu-emi"}
    assert all("nessun canale PKG" in why for _, why in rejected)


def test_senza_device_cpu_la_catena_e_unavailable():
    """Se nessun device espone un canale PKG il canale non si inventa: unavailable, con i nomi letti."""
    chosen, rejected = eb.select_cpu_device([
        ("sensorhub", _meta(("SENSORHUB0_ENERGY",))),
        ("gpu", _meta(("GPU0_ENERGY",))),
    ])
    assert chosen == []
    assert len(rejected) == 2
    assert all("SENSORHUB0_ENERGY" in why or "GPU0_ENERGY" in why
               for _, why in rejected)
    choice, why = eb.choose_single(chosen)
    assert choice is None
    assert "nessun device CPU" in why


def test_batteria_e_gpu_non_hanno_un_dominio_noto():
    """I canali di batteria e GPU non contengono token PKG/DRAM/PP0/PP1: nessun dominio, nessuna lettura."""
    meta = _meta(("BATTERY0_ENERGY", "GPU0_ENERGY", "SENSORHUB0_ENERGY"))
    assert [c.domain for c in meta.channels] == [None, None, None]


def test_piu_canali_pkg_distinti_sono_ambigui():
    """Due package sullo stesso device: leggere il primo e chiamarlo "il package" e' l'errore F11."""
    chosen, rejected = eb.select_cpu_device([
        ("dual-socket", _meta(("RAPL_Package0_PKG", "RAPL_Package1_PKG"))),
    ])
    assert chosen == []
    assert len(rejected) == 1
    assert rejected[0][1].startswith("ambiguous_domain")


def test_canale_pkg_specchiato_letto_una_volta():
    """Canali omonimi sono lo stesso contatore specchiato: si legge il primo indice e lo si dichiara."""
    chosen, rejected = eb.select_cpu_device([
        ("mirrored", _meta(("RAPL_Package0_PKG", "RAPL_Package0_PKG"))),
    ])
    assert rejected == []
    assert len(chosen) == 1
    assert chosen[0].channel.index == 0
    assert any("specchiato" in n for n in chosen[0].notes)


def test_canale_pkg_non_in_pwh_viene_scartato():
    """L'unita' si verifica nel metadato: un PKG con unita' diversa da pWh non si converte con 3,6e-9."""
    chosen, rejected = eb.select_cpu_device([
        ("odd-unit", _meta(("RAPL_Package0_PKG",), unit=3)),
    ])
    assert chosen == []
    assert "non pWh" in rejected[0][1]


def test_piu_device_cpu_non_si_risolvono_da_soli():
    """Package multipli su device distinti: nessuna scelta automatica, la scelta esplicita resta CW_EMI_DEVICE."""
    meta = _meta(REAL_NAMES)
    one = eb.DeviceChoice("socket-0", meta, meta.channels[0], ())
    two = eb.DeviceChoice("socket-1", meta, meta.channels[0], ())
    choice, why = eb.choose_single([one, two])
    assert choice is None
    assert "ambiguous_domain" in why and "CW_EMI_DEVICE" in why


# ------------------------------------------------------------------ lettura
def test_la_lettura_segue_il_nome_non_la_posizione():
    """Ordine del record diverso da pkg,dram,pp0,pp1: il PKG e' il canale 1, cioe' il secondo, non il primo."""
    b = eb.EMICounterBackend(auto_open=False)
    b.available = True
    b.channels = eb.channels_from_names(
        ("RAPL_Package0_DRAM", "RAPL_Package0_PKG", "RAPL_Package0_PP0"))
    b.read_raw = lambda: (111, 900, 7_000_000, 901, 222, 902)
    d = b.read_domains()
    assert d["pkg"][0] == pytest.approx(7_000_000 * PWH)
    assert d["pkg"][1] == 901, "il timestamp e' quello del canale PKG, non del primo"
    assert d["dram"][0] == pytest.approx(111 * PWH)
    assert b.read_cumulative_energy_j() == pytest.approx(7_000_000 * PWH)
    assert b.read_fields_j()["ts_100ns"] == 901


def test_senza_metadato_non_si_legge_il_primo_canale():
    """Nessun canale dichiarato significa nessuna lettura, non "il canale 0 e' il package"."""
    b = eb.EMICounterBackend(auto_open=False)
    b.available = True
    b.read_raw = lambda: (1_000_000, 1, 2, 2, 3, 3, 4, 4)
    assert b.pkg_channel is None
    assert b.read_cumulative_energy_j() is None
    assert b.read_domains() is None


def test_la_lettura_usa_la_dimensione_del_metadato():
    """Il buffer di misura e' 16 byte per canale, dettato dal metadato, e una risposta corta e' None."""
    b = eb.EMICounterBackend(auto_open=False)
    b.available = True
    b.channels = eb.channels_from_names(("RAPL_Package0_PKG", "RAPL_Package0_DRAM"))
    b._handle = 1
    seen = {}

    def fake(handle, code, out_size, min_out):
        seen["size"] = out_size
        return b"\x00" * out_size, ""

    b._ioctl = fake
    v = b._ioctl_raw()
    assert seen["size"] == 32 and len(v) == 4

    b.channels = eb.channels_from_names(REAL_NAMES)
    b._ioctl_raw()
    assert seen["size"] == 64

    b._ioctl = lambda handle, code, out_size, min_out: (None, "got=48")
    assert b._ioctl_raw() is None
    assert "got=48" in b.last_error


# ------------------------------------------------------------------ versioni
def test_v1_e_dichiarato_non_scambiato_per_un_guasto():
    """Un device V1 si scarta con la ragione "V1": non e' un IOCTL fallito e non si legge a 4 domini."""
    b = eb.EMICounterBackend(auto_open=False)
    b._ioctl = lambda handle, code, out_size, min_out: (
        struct.pack("<H", eb.EMI_VERSION_V1), "")
    meta, why = b._read_metadata(1)
    assert meta is None and "V1" in why


def test_versione_non_riconosciuta_e_dichiarata():
    """Una versione EMI diversa da 1 e 2 non si interpreta con il parser V2: si scarta dicendolo."""
    b = eb.EMICounterBackend(auto_open=False)
    b._ioctl = lambda handle, code, out_size, min_out: (
        struct.pack("<H", 7), "")
    meta, why = b._read_metadata(1)
    assert meta is None and "non riconosciuta" in why


def test_metadato_illeggibile_non_lascia_canali_a_meta():
    """Se GET_METADATA fallisce il device si scarta con la ragione, non con zero canali letti in silenzio."""
    b = eb.EMICounterBackend(auto_open=False)
    calls = []

    def fake(handle, code, out_size, min_out):
        calls.append(code)
        if code == eb.IOCTL_GET_VERSION:
            return struct.pack("<H", eb.EMI_VERSION_V2), ""
        if code == eb.IOCTL_GET_METADATA_SIZE:
            return struct.pack("<I", 492), ""
        return None, "err=31"

    b._ioctl = fake
    meta, why = b._read_metadata(1)
    assert meta is None
    assert "GET_METADATA fallita" in why
    assert calls == [eb.IOCTL_GET_VERSION, eb.IOCTL_GET_METADATA_SIZE,
                     eb.IOCTL_GET_METADATA]

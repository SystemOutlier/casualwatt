# -*- coding: utf-8 -*-
"""PawnIO MSR: registri per produttore, unita' letta, riporto contro reset,
e i criteri di HVCI e firma che decidono se il driver entra nella catena.

Fatti verificati alla fonte il 28-10-2026 e fissati qui:

  * Intel e AMD hanno indirizzi **diversi** (``msr-index.h``:
    ``MSR_RAPL_POWER_UNIT`` 0x606 e ``MSR_PKG_ENERGY_STATUS`` 0x611 contro
    ``MSR_AMD_RAPL_POWER_UNIT`` 0xC0010299 e ``MSR_AMD_PKG_ENERGY_STATUS``
    0xC001029B): su AMD non si legge 0x611, nemmeno per analogia;
  * il campo dell'unita' e' ``(unit >> 8) & 0x1F`` con quantum ``1 / 2^EU`` per
    entrambi i produttori (``rapl.c:609-620``, modello AMD a ``:837``) e si
    **legge**: un valore nullo o implausibile non diventa un quantum assunto;
  * il contatore e' a 32 bit (``rapl.c:108``, maschera a ``:573``): un calo
    alto->basso e' un riporto e si somma con il modulo ``2^32``; un calo
    qualunque altro e' un reset e il segmento non produce energia, senza mai
    essere clampato a zero;
  * con HVCI attivo (o non determinabile) il driver deve avere firma valida e
    firmatario Microsoft; un ``unknown`` di PowerShell non e' una firma valida.

``PawnIOLib`` e' finta in ogni test: nessun driver, nessun MSR reale.
"""
import hashlib

import pytest

from energy import pawnio_backend as pb


UNIT_INTEL = 0xA0E03          # campo EU = 14 -> quantum 1/2^14 J (host reale)
QUANTUM_EU14 = 1.0 / (1 << 14)
MOD = 1 << 32

MICROSOFT = (
    "CN=Microsoft Windows Hardware Compatibility Publisher, O=Microsoft "
    "Corporation, L=Redmond, S=Washington, C=US"
)


class FakeLib:
    """Sostituto di ``_PawnIOLib``: registri statici + contatore a lista."""

    def __init__(self, *, unit_msr, energy_msr, unit_raw, energy_values,
                 lib_version="2.0.0", fail_on=(), fail_open=None):
        self.unit_msr = unit_msr
        self.energy_msr = energy_msr
        self.unit_raw = unit_raw
        self.energy_values = list(energy_values)
        self.lib_version = lib_version
        self.fail_on = set(fail_on)
        self.fail_open = fail_open
        self.read_log = []
        self.opened = False
        self.loaded = False
        self.blob_len = 0
        self.closed = False

    def version(self):
        return self.lib_version

    def open(self):
        self.opened = True
        if self.fail_open is not None:
            raise pb.PawnIOLibError("pawnio_open", self.fail_open)

    def load(self, blob):
        self.loaded = True
        self.blob_len = len(blob)

    def read_msr(self, msr):
        self.read_log.append(msr)
        if msr in self.fail_on:
            raise OSError("ioctl rifiutata")
        if msr == self.unit_msr:
            return self.unit_raw
        if msr == self.energy_msr:
            if not self.energy_values:
                raise OSError("contatore esaurito")
            return self.energy_values.pop(0)
        raise OSError(f"MSR 0x{msr:X} non leggibile")

    def close(self):
        self.closed = True


def _module(tmp_path, name="IntelMSR.bin", blob=b"blob-verificato"):
    d = tmp_path / "modules"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(blob)
    return d, p, {name: hashlib.sha256(blob).hexdigest()}


def _build(vendor="intel", *, unit_raw=UNIT_INTEL, energy_values=(1000, 1100),
           hvci="enabled", sig_status="Valid", sig_subject=MICROSOFT,
           service="running", mod_dir=None, hashes=None, lib=None,
           lib_calls=None, sig_calls=None):
    spec = pb.VENDORS.get(vendor, pb.VENDORS["intel"])
    fake = lib if lib is not None else FakeLib(
        unit_msr=spec["unit_msr"], energy_msr=spec["energy_msr"],
        unit_raw=unit_raw, energy_values=energy_values)

    def factory(path):
        if lib_calls is not None:
            lib_calls.append(path)
        return fake

    def signature_reader(path):
        if sig_calls is not None:
            sig_calls.append(path)
        return {"status": sig_status, "subject": sig_subject,
                "thumbprint": "00"}

    backend = pb.PawnIOMSRBackend(
        vendor=vendor,
        modules_dir=mod_dir,
        dll_path="C:/finto/PawnIOLib.dll",
        expected_hashes=hashes,
        hvci_reader=lambda: hvci,
        signature_reader=signature_reader,
        service_reader=lambda: service,
        driver_path_reader=lambda: "C:/Windows/System32/drivers/PawnIO.sys",
        lib_factory=factory,
    )
    return backend, fake


# -- registri e unita' -------------------------------------------------------
def test_intel_legge_0x606_e_0x611_e_deriva_il_quantum(tmp_path):
    """Il percorso Intel legge l'unita' da 0x606 e il contatore da 0x611, e il
    quantum esce dal campo EU, non da una costante (rapl.c:609-620)."""
    mod_dir, _, hashes = _module(tmp_path)
    backend, fake = _build(mod_dir=mod_dir, hashes=hashes,
                           energy_values=(1000, 1100))

    assert backend.available, backend.reason
    assert backend.unit_msr == 0x606
    assert backend.energy_msr == 0x611
    assert backend.unit_raw == UNIT_INTEL
    assert backend.quantum_j == pytest.approx(QUANTUM_EU14)
    assert backend.lib_version == "2.0.0"
    assert fake.opened and fake.loaded and fake.blob_len == len(
        b"blob-verificato")
    # letture: unita', ancora dell'energia, poi il contatore dal test
    assert fake.read_log[0] == 0x606
    assert fake.read_log[1] == 0x611
    assert backend.read_cumulative_energy_j() == pytest.approx(100 * QUANTUM_EU14)


def test_amd_non_legge_0611(tmp_path):
    """Su AMD il registro e' 0xC001029B: 0x611 non esiste e non si legge per
    analogia. Se comparisse nel log, il test fallisce."""
    mod_dir, _, hashes = _module(tmp_path, "AMDFamily17.bin", b"blob-amd")
    backend, fake = _build(vendor="amd", mod_dir=mod_dir, hashes=hashes,
                           energy_values=(4000, 4000 + (1 << 20)))

    assert backend.available, backend.reason
    assert backend.unit_msr == 0xC0010299
    assert backend.energy_msr == 0xC001029B
    assert 0x611 not in fake.read_log
    assert 0x606 not in fake.read_log
    assert backend.read_cumulative_energy_j() == pytest.approx(
        (1 << 20) * QUANTUM_EU14)


@pytest.mark.parametrize("unit_raw", [0, 0xFFFFFFFF])
def test_unita_implausibile_non_diventa_un_quantum(tmp_path, unit_raw):
    """Un registro unita' nullo o tutto uno non ha un campo EU utilizzabile: il
    backend si dichiara non disponibile invece di assumere 1 J o 0 J."""
    mod_dir, _, hashes = _module(tmp_path)
    backend, fake = _build(mod_dir=mod_dir, hashes=hashes, unit_raw=unit_raw)

    assert not backend.available
    assert backend.reason == "unit_unreadable"
    assert backend.quantum_j is None
    assert fake.closed           # la libreria si chiude, non resta aperta


def test_lettura_energia_fallita_e_dichiarata(tmp_path):
    """L'unita' si' che il contatore no: due ragioni diverse, non una.

    Qui 0x606 risponde e il quantum viene derivato, poi la prima lettura di
    0x611 solleva. La relazione che il test fissa e' che il backend non puo'
    restare ``available`` con un ``quantum_j`` valido e nessun ``_last_raw``:
    il delta successivo sarebbe sottratto a un valore mai letto, cioe' inventato.
    ``energy_unreadable`` (:525) e' dunque una ragione distinta da
    ``unit_unreadable`` (:506), e la libreria si chiude (:528) invece di
    restare aperta su un canale che non produce numero.
    """
    mod_dir, _, hashes = _module(tmp_path)
    spec = pb.VENDORS["intel"]
    lib = FakeLib(unit_msr=spec["unit_msr"], energy_msr=spec["energy_msr"],
                  unit_raw=UNIT_INTEL, energy_values=(), fail_on={0x611})
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes, lib=lib)

    assert not backend.available
    assert backend.reason == "energy_unreadable"


# -- riporto contro reset ----------------------------------------------------
def test_riporto_del_contatore_a_32_bit(tmp_path):
    """Vecchio valore nella parte alta e nuovo nella parte bassa: e' un riporto,
    il delta e' ``2^32 - old + new`` e non energia negativa."""
    mod_dir, _, hashes = _module(tmp_path)
    old, new = 0xFFFFFF00, 0x00000100
    delta = MOD - old + new
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes,
                        energy_values=(old, new))

    total = backend.read_cumulative_energy_j()
    assert total == pytest.approx(delta * QUANTUM_EU14)
    assert backend.wraps == 1
    assert backend.resets == 0


def test_calo_senza_riporto_e_reset_e_non_produce_energia(tmp_path):
    """Un calo che non e' un riporto e' un reset: il segmento non produce
    energia, il totale non scende e non viene clampato a zero."""
    mod_dir, _, hashes = _module(tmp_path)
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes,
                        energy_values=(1_000_000, 900_000, 900_100))

    assert backend.read_cumulative_energy_j() == pytest.approx(0.0)
    assert backend.resets == 1
    assert backend.wraps == 0
    # dopo il reset si riparte dal nuovo valore, senza recuperare il buco
    assert backend.read_cumulative_energy_j() == pytest.approx(
        100 * QUANTUM_EU14)
    assert backend.resets == 1
    assert any("reset" in n for n in backend.notes)


# -- criteri HVCI e firma ----------------------------------------------------
@pytest.mark.parametrize(
    "hvci,sig_subject,ok",
    [
        ("enabled", MICROSOFT, True),
        ("unknown", MICROSOFT, True),      # HVCI non determinabile: chiuso
        ("enabled", "CN=Altro Firmatario, O=Example", False),
        ("unknown", "CN=Altro Firmatario, O=Example", False),
        # con HVCI spento la firma di terzi e' ammessa: nessun requisito
        # WHCP, ma la firma deve comunque essere valida
        ("disabled", "CN=Altro Firmatario, O=Example", True),
    ],
    # id espliciti: il soggetto Microsoft e' lungo 110 caratteri e finirebbe
    # nei node id, cioe' nella prima colonna dell'Appendice D
    ids=["ms-hvci-on", "ms-hvci-unknown", "terzi-hvci-on", "terzi-hvci-unknown",
         "terzi-hvci-off"],
)
def test_hvci_decide_quale_firmatario_e_ammesso(tmp_path, hvci, sig_subject,
                                                ok):
    """La regola di ammissione e' una congiunzione, non una disgiunzione.

    Il predicato testato, caso per caso su tutte le combinazioni, e'
    ``ammesso = firma_valida AND (HVCI spento OR firmatario Microsoft)``
    (`_signature_rejection` :540-554). Le due righe con ``hvci == "unknown"``
    fissano il ``fail closed`` di AGENTS.md: un HVCI non determinabile tratta
    il sistema come attivo, mai come spento. La riga
    ``("disabled", terzi, True)`` fissa il lato opposto, perche' un test che
    ammettesse solo Microsoft non distinguerebbe la regola dal suo caso
    particolare. La ragione e la nota sono quelle dichiarate, non un generico
    ``pawnio_unavailable``.
    """
    mod_dir, _, hashes = _module(tmp_path)
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes, hvci=hvci,
                        sig_subject=sig_subject)
    assert backend.available is ok
    if not ok:
        assert backend.reason == "driver_signer_not_microsoft"
        assert "non Microsoft" in " ".join(backend.notes)


@pytest.mark.parametrize("status", ["NotSigned", "HashMismatch", "UnknownError",
                                    "unknown"])
def test_firma_non_valida_fallisce_chiuso(tmp_path, status):
    """Qualunque stato diverso da ``Valid`` — incluso ``unknown`` quando
    PowerShell non risponde — rifiuta il driver."""
    mod_dir, _, hashes = _module(tmp_path)
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes, sig_status=status)
    assert not backend.available
    assert backend.reason == "driver_signature_invalid"


def test_servizio_fermo_non_si_arriva_alla_firma(tmp_path):
    """La cascata dei criteri ha un ordine, e l'ordine e' parte del contratto.

    Con il servizio PawnIO fermo il costruttore si ferma a
    ``service_not_running`` (:433-437) prima di leggere percorso del driver e
    firma. L'asserzione forte qui non e' la ragione, e' ``calls == []``: la
    sonda di firma non deve essere invocata. Se lo fosse, su un host reale
    si sparerebbe un PowerShell per ogni run con il servizio spento, e il
    verdetto pubblicherebbe lo stato di un driver che non e' in grado di
    rispondere, invece del motivo per cui non risponde.
    """
    mod_dir, _, hashes = _module(tmp_path)
    calls = []
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes, service="stopped",
                        sig_calls=calls)
    assert not backend.available
    assert backend.reason == "service_not_running"
    assert calls == []


# -- moduli ------------------------------------------------------------------
def test_modulo_assente(tmp_path):
    """Nessun blob, nessun ``pawnio_open``: l'assenza si ferma prima.

    La directory esiste ma dentro non c'e' ``IntelMSR.bin``: la ragione e'
    ``module_missing`` (:459-463, il ramo del file assente, non quello della
    directory mancante a :453). L'asserzione che conta e' ``not fake.opened``:
    la libreria PawnIO non deve essere aperta per nulla. Aprire un handle di
    kernel mode senza poi avere il modulo da passare a ``pawnio_load``
    significherebbe tenere aperto un canale per una catena che non producera'
    numero, e la riga dovrebbe dichiarare un tentativo mai finito.
    """
    d = tmp_path / "vuota"
    d.mkdir()
    backend, fake = _build(mod_dir=d, hashes={})
    assert not backend.available
    assert backend.reason == "module_missing"
    assert not fake.opened


def test_hash_del_modulo_diverso_non_si_carica(tmp_path):
    """Un blob diverso da quello verificato non entra: la release pinnata e'
    l'unica ammessa, e il rifiuto avviene prima di aprire la libreria."""
    mod_dir, _, _ = _module(tmp_path, blob=b"blob-alterato")
    calls = []
    backend, _ = _build(mod_dir=mod_dir, hashes={"IntelMSR.bin": "0" * 64},
                        lib_calls=calls)
    assert not backend.available
    assert backend.reason == "module_hash_mismatch"
    assert calls == []


def test_produttore_sconosciuto(tmp_path):
    """Produttore non in tabella: nessun registro per analogia, e gli indirizzi
    restano ``None`` (:422-428). L'alternativa a questo comportamento sarebbe
    ereditare 0x606/0x611 dal default Intel, cioe' leggere un MSR che per quel
    silicio non e' il contatore del package: darebbe un numero verosimile e
    sbagliato, il peggio che un canale di misura possa fare.
    """
    mod_dir, _, hashes = _module(tmp_path)
    backend, _ = _build(vendor="zzz", mod_dir=mod_dir, hashes=hashes)
    assert not backend.available
    assert backend.reason == "vendor_unknown"
    assert backend.unit_msr is None


# -- sonda e utilita' --------------------------------------------------------
def test_probe_riporta_i_criteri_applicati(tmp_path):
    """La sonda deve mostrare il perche' del verdetto, non solo il verdetto.

    ``probe()`` (:611-635) e' cio' che finisce nel verbale:
    ``tools/pawnio_probe.py:102`` e ``:250`` incollano ``msr.probe()``
    nell'output. Se riportasse solo ``pass``, un lettore non
    potrebbe distinguere "HVCI attivo e firma Microsoft" da "HVCI spento e
    firma di terzi", che sono due stati di sicurezza diversi con lo stesso
    numero. Il test fissa la forma dell'oggetto: ``unit_msr``/``energy_msr``
    come stringhe esadecimali leggibili (:627-630) e non come interi crudi,
    ``quantum_j`` come float derivato (1/2^14) e
    non come costante copiata, ``module_sha256`` che deve coincidere con
    l'hash del blob realmente presente, e il ``module_version`` della release
    pinnata. Un campo che cambia nome qui rompe il consumatore, quindi la
    chiave e' parte del contratto.
    """
    mod_dir, path, hashes = _module(tmp_path)
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes)
    info = backend.probe()
    assert info["pass"] is True
    assert info["vendor"] == "intel"
    assert info["hvci"] == "enabled"
    assert info["driver_signature"] == "Valid"
    assert info["module_version"] == pb.MODULES_VERSION
    assert info["module_sha256"] == hashes["IntelMSR.bin"]
    assert info["unit_msr"] == "0x606"
    assert info["energy_msr"] == "0x611"
    assert info["quantum_j"] == pytest.approx(QUANTUM_EU14)
    assert backend.module_path == str(path)


def test_chiusura_rende_il_backend_non_disponibile(tmp_path):
    """Dopo ``close()`` (:637-639) il canale deve mancare, non zero.

    L'invariante e' che un canale chiuso dia lettura nulla, non un numero:
    ``read_raw`` :565-567 rifiuta quando ``available`` e' falso o la libreria
    non c'e', e ``read_cumulative_energy_j`` :581-582 restituisce ``None`` per
    quella strada. Se la chiusura restituisse il totale acumulatorio invece di
    ``None``, una finestra che si chiude a meta' pubblicherebbe un'energia
    parziale come se fosse la misura completa; se restituisse 0, la cascata
    EMI -> PawnIO vedrebbe un numero e non un canale assente.
    ``fake.closed`` fissa anche il lato opposto: l'handle di kernel mode viene
    rilasciato davvero.
    """
    mod_dir, _, hashes = _module(tmp_path)
    backend, fake = _build(mod_dir=mod_dir, hashes=hashes)
    backend.close()
    assert backend.available is False
    assert fake.closed is True
    assert backend.read_cumulative_energy_j() is None


def test_accesso_negato_dichiara_il_privilegio(tmp_path):
    """Da token ristretto pawnio_open risponde 0x80070005 (misurato il
    28-10-2026): il canale manca per privilegio, e la ragione lo dice invece
    di confonderlo con un driver rotto."""
    mod_dir, _, hashes = _module(tmp_path)
    spec = pb.VENDORS["intel"]
    lib = FakeLib(unit_msr=spec["unit_msr"], energy_msr=spec["energy_msr"],
                  unit_raw=UNIT_INTEL, energy_values=(), fail_open=0x80070005)
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes, lib=lib)

    assert backend.available is False
    assert backend.reason == "access_denied"
    assert any("elevato" in n for n in backend.notes)
    assert backend.probe()["reason"] == "access_denied"


def test_altro_errore_di_apertura_resta_pawnio_unavailable(tmp_path):
    """Solo E_ACCESSDENIED ha una ragione propria: un HRESULT diverso non
    diventa 'access_denied' per assonanza."""
    mod_dir, _, hashes = _module(tmp_path)
    spec = pb.VENDORS["intel"]
    lib = FakeLib(unit_msr=spec["unit_msr"], energy_msr=spec["energy_msr"],
                  unit_raw=UNIT_INTEL, energy_values=(), fail_open=0x80004005)
    backend, _ = _build(mod_dir=mod_dir, hashes=hashes, lib=lib)

    assert backend.available is False
    assert backend.reason == "pawnio_unavailable"


def test_find_modules_dir_rispetta_la_variabile(tmp_path, monkeypatch):
    """La directory dei moduli si dichiara, non si indovina (:272-285).

    ``CW_PAWNIO_MODULES`` e' il primo candidato e qui vince su
    ``ProgramFiles\\PawnIO\\modules`` e sulla cache di
    ``fetch_pawnio_modules.py``; la seconda asserzione fissa il caso opposto:
    con una variabile che punta a una directory inesistente, e nessun `.bin`
    negli altri candidati, l'esito e' ``None``. Non esiste una terza strada in
    cui il codice si inventa un percorso o apre un modulo che non era stato
    dichiarato. Il test copre la precedenza della variabile e l'assenza
    dichiarata, non il caso in cui install e cache contengono entrambe un
    blob: li distinguerebbe un fixture con due directory piene, e non c'e'.
    """
    # La cache reale va esclusa: su un host dove i moduli sono installati
    # `find_modules_dir` li trova anche quando la variabile e' sbagliata, e il
    # test misurerebbe la macchina invece della precedenza.
    monkeypatch.setattr(pb, "default_modules_dir", lambda: tmp_path / "cache-vuota")
    d = tmp_path / "mod"
    d.mkdir()
    (d / "IntelMSR.bin").write_bytes(b"x")
    env = {"ProgramFiles": str(tmp_path / "pf")}
    assert pb.find_modules_dir({**env, "CW_PAWNIO_MODULES": str(d)}) == d
    assert pb.find_modules_dir({**env, "CW_PAWNIO_MODULES": str(tmp_path / "no")}
                               ) is None

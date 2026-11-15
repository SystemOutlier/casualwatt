# -*- coding: utf-8 -*-
"""
tests/test_warmup_stabilizzazione_p44.py — la modalità
``background_controlled`` del warm-up post-carico, provata pezzo per pezzo.

Perche' esiste. La politica ``background_controlled`` della P4.4 Background
Emenda dichiara il fondo ATTIVO: su questa macchina la cpu sta sopra il 2 %
per costruzione (Qoder, PyCharm, i servi di Windows) e la quiete assoluta
non e' uno stato raggiungibile, quindi il criterio del warm-up non puo'
essere il rientro assoluto. In questa modalità il criterio diventa la
STABILIZZAZIONE — potenza non sopra la media mobile degli ultimi campioni
per ``sustain_s`` continui — e la cpu, registrata, non decide. Qui si
verifica proprio quella sostituzione di criterio e, con essa, che il tool
NON dica in propria difesa condizioni che non ha verificato: un log che
stampasse «cpu sotto 18 %» dopo aver misurato solo la potenza sarebbe una
prova fabbricata, non una registrazione.

Che cosa verifica questo file:
  1. il criterio di stabilizzazione si compie con cpu SOGLIA dichiarata ma
     non giudicata, purche' la potenza non salga sopra la media mobile;
  2. il log di successo dichiara esattamente la condizione misurata — la
     media mobile — e non aggiunge la cpu, che in questa modalità non e'
     stata valutata;
  3. un rialzo persistente sopra la media mobile azzera il tratto, mentre
     un picco singolo non lo fa (il fondo è attivo: un picco è rumore, una
     tendenza è transitorio);
  4. il target è la baseline del blocco di carico e le soglie arrivano dal
     piano, non da costanti rilette a horoscopo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import run_gate_p44 as rg  # noqa: E402


class _Orologio:
    """Orologio finto che avanza a passo dichiarato e registra i sonni."""

    def __init__(self, passo=1.0):
        self.t = 0.0
        self.passo = passo
        self.dormito: list = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.dormito.append(s)
        self.t += s


def _sequenza(valori, nome):
    """Lettore che consuma una lettura per chiamata e grida se ne chiede una
    piu' di quante il test ne abbia dichiarate."""
    seq = list(valori)

    def read():
        if not seq:
            raise AssertionError(
                f"il warm-up ha letto piu' campioni di {nome} del dichiarato")
        return seq.pop(0)

    return read


def _stabilizza(target, potenze, cpu_finestre, *, mode="stabilization",
                tolerance_w=0.5, cpu_max_pct=18.0, sustain_s=3.0, cap_s=60.0,
                passo=1.0, temperatura=(27.85, "fake:MSAcpi_ThermalZoneTemperature"),
                registri=None, orologio=None, log=None) -> dict:
    """Esegue il criterio in modalità ``stabilization`` con TUTTE le sorgenti
    iniettate: potenza, cpu, orologio, sonno, registro termico e canale di
    log. Nessun test di questo file tocca la macchina reale, e il log viene
    raccolto perche' e' esso stesso un risultato da verificare — dice quale
    condizione il tool dichiara di aver misurato."""
    orologio = orologio if orologio is not None else _Orologio(passo=passo)
    righe = log if log is not None else []

    def leggi_temperatura():
        return temperatura

    finestre_cpu = [[] if c is None else [c] for c in cpu_finestre]
    esito = rg._stabilizza_post_carico(
        target, tolerance_w=tolerance_w, cpu_max_pct=cpu_max_pct,
        sustain_s=sustain_s, cap_s=cap_s, step_s=passo, window_s=2.0,
        mode=mode,
        campiona_potenza=_sequenza(potenze, "potenza"),
        campiona_cpu=_sequenza(finestre_cpu, "cpu_percent"),
        legge_temperatura=leggi_temperatura,
        registra=(registri.append if registri is not None else None),
        clock=orologio.now, sleep=orologio.sleep, on_log=righe.append)
    orologio_copia = orologio
    esito["_orologio"] = orologio_copia
    esito["_log"] = righe
    return esito


def test_stabilizzazione_avanza_con_cpu_sopra_soglia_e_il_log_non_la_dice():
    """In ``background_controlled`` la cpu e' sopra soglia per costruzione:
    qui sta al 22,6 % (il MASSIMO della caratterizzazione del 14-11) e la
    soglia e' 18 % — un criterio che la giudicasse non chiuderebbe mai. Il
    criterio si compie lo stesso, perche' misura la potenza; e il log di
    successo dichiara esattamente quella, non una condizione cpu che non ha
    guardato. Un messaggio che stampasse «cpu sotto 18 %» sarebbe la prova
    di un controllo non avvenuto, non una registrazione."""
    esito = _stabilizza(
        6.7, [6.7, 6.7, 6.7, 6.7], [22.6, 22.6, 22.6, 22.6],
        cpu_max_pct=18.0)
    assert esito["warmup_completed"] is True
    assert esito["warmup_motivo"] == "criterio_soddisfatto"
    assert esito["warmup_valori_cpu_pct"] == [22.6] * 4

    messaggi = [m for m in esito["_log"]
                if "stabilizzazione raggiunta" in m]
    assert len(messaggi) == 1
    messaggio = messaggi[0]
    assert "media mobile" in messaggio
    assert "cpu sotto" not in messaggio
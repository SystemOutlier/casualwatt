# -*- coding: utf-8 -*-
"""background_monitor.py — orchestratore del monitoraggio del background.

Perché esiste. Il runner v4 (`benchmark_v4.py`) misura l'energia di blocchi
di inferenza, ma non verificava se il background del sistema era stabile
tra un blocco e l'altro. `machine_state.py` fornisce già gli strumenti di
acquisizione (`background_signature`, `signatures_match_with_intensity`,
`total_cpu_samples`), ma nessuno li coordinava nel percorso di misura.

Questo modulo è un **orchestratore**, non un acquisitore: coordina i campioni
pre e post blocco, conserva il riferimento iniziale, e valuta l'esito usando
`signatures_match_with_intensity()`. Non misura energia, non scrive righe CSV,
non decide soglie universali.

Quattro dimensioni della validità:
1. **Identità**: sono cambiati i processi presenti?
2. **Intensità**: è aumentato il carico dei processi indipendenti dal workload?
3. **Continuità**: il monitoraggio è rimasto attivo durante tutta la misura?
4. **Attendibilità**: il monitoraggio stesso ha introdotto un overhead significativo?

Un verdetto `unstable` è un **warning**, non un'invalidazione: la misura resta,
ma è dichiarata non conforme al criterio di stabilità. Un verdetto
`insufficient_data` significa che il dato manca, non che il controllo è passato.

Lo schema CSV P5 è congelato a 174 nomi: l'esito del monitoraggio entra nel
campo `notes` della riga e del riepilogo di blocco, non in una colonna nuova.
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Tuple

import machine_state as ms


class BackgroundMonitor:
    """Orchestra il monitoraggio del background prima e dopo ogni blocco.

    Il monitor raccoglie un campione prima del primo blocco (riferimento)
    e un campione dopo ogni blocco successivo. Fornisce due valutazioni:
    - **Locale**: confronto pre vs post dello stesso blocco.
    - **Globale**: confronto ultimo campione vs riferimento iniziale.

    Se il riferimento non è stato impostato, il primo campione pre diventa
    il riferimento.

    Vocabolario chiuso dell'esito:
    - ``stable``: identità e intensità stabili entro tolleranza.
    - ``unstable``: identità cambiata o intensità variabile oltre tolleranza.
    - ``insufficient_data``: dati mancanti o monitoraggio non attivo.

    Il costo del monitoraggio è dichiarato: ogni campione richiede
    ~3 secondi per il campionamento CPU totale (3 campioni a 1 s).
    """

    def __init__(self, char_sha256: Optional[str] = None) -> None:
        """Inizializza il monitor con l'hash della caratterizzazione.

        Args:
            char_sha256: hash SHA-256 della caratterizzazione idle di riferimento.
                Se fornito, viene incluso in ogni firma del background.
        """
        self.char_sha256 = char_sha256
        self.reference_signature: Optional[Dict] = None
        self.samples: List[Dict] = []
        self.block_verdicts: List[Dict] = []
        self.errors: List[str] = []

    def sample_pre(self) -> Dict:
        """Campione prima del blocco: firma + CPU totale.

        Raccoglie 3 campioni di CPU totale su 3 secondi e la firma del
        background con PID, nome, CPU%, piano energetico e batteria.
        Se è il primo campione, diventa anche il riferimento.

        Restituisce la firma con ``kind="pre"`` aggiunto.

        Raises:
            Exception: se il campionamento fallisce, il chiamante deve
                catturare l'eccezione e trattarla come insufficient_data.
        """
        cpu_samples = ms.total_cpu_samples()
        sig = ms.background_signature(
            char_sha256=self.char_sha256,
            cpu_samples=cpu_samples,
        )
        sig["kind"] = "pre"
        self.samples.append(sig)
        if self.reference_signature is None:
            self.reference_signature = sig
        return sig

    def sample_post(self) -> Dict:
        """Campione dopo il blocco: firma + CPU totale.

        Stessa procedura di ``sample_pre()``, ma con ``kind="post"``.
        Il riferimento non viene aggiornato: resta il primo campione pre.

        Restituisce la firma con ``kind="post"`` aggiunto.

        Raises:
            Exception: se il campionamento fallisce, il chiamante deve
                catturare l'eccezione e trattarla come insufficient_data.
        """
        cpu_samples = ms.total_cpu_samples()
        sig = ms.background_signature(
            char_sha256=self.char_sha256,
            cpu_samples=cpu_samples,
        )
        sig["kind"] = "post"
        self.samples.append(sig)
        return sig

    @staticmethod
    def _map_verdict(
        verdetto: str, diff: List[str]
    ) -> Tuple[str, List[str]]:
        """Mappa i 4 token di signatures_match_with_intensity ai 3 del monitor."""
        if verdetto == "identity_changed":
            return ("unstable", diff)
        if verdetto == "intensity_unstable":
            return ("unstable", diff)
        if verdetto == "insufficient_data":
            return ("insufficient_data", diff)
        return ("stable", diff)

    def evaluate_local(
        self,
        pre_sig: Dict,
        post_sig: Dict,
        cpu_tolerance_pct: float = 5.0,
        power_tolerance_w: Optional[float] = None,
    ) -> Tuple[str, List[str]]:
        """Confronto locale: pre vs post dello stesso blocco.

        Verifica se il background è rimasto stabile durante il singolo blocco,
        indipendentemente dal riferimento iniziale della campagna.

        Args:
            pre_sig: firma raccolta prima del blocco.
            post_sig: firma raccolta dopo il blocco.
            cpu_tolerance_pct: tolleranza sulla CPU totale media in percentuale.
            power_tolerance_w: tolleranza sulla potenza media in Watt (opzionale).

        Restituisce:
            (verdetto, differenze) dove verdetto è uno dei tre token chiusi.
        """
        if pre_sig is None or post_sig is None:
            return ("insufficient_data", ["campione pre o post mancante"])
        verdetto, diff = ms.signatures_match_with_intensity(
            pre_sig,
            post_sig,
            cpu_tolerance_pct=cpu_tolerance_pct,
            power_tolerance_w=power_tolerance_w,
        )
        return self._map_verdict(verdetto, diff)

    def evaluate_global(
        self,
        cpu_tolerance_pct: float = 5.0,
        power_tolerance_w: Optional[float] = None,
    ) -> Tuple[str, List[str]]:
        """Confronto globale: ultimo campione vs riferimento iniziale.

        Verifica se il background è derivato rispetto alla condizione iniziale
        della campagna, anche se il singolo blocco era stabile localmente.

        Args:
            cpu_tolerance_pct: tolleranza sulla CPU totale media in percentuale.
            power_tolerance_w: tolleranza sulla potenza media in Watt (opzionale).

        Restituisce:
            (verdetto, differenze) dove verdetto è uno dei tre token chiusi.
        """
        if self.reference_signature is None:
            return ("insufficient_data", ["nessun campione di riferimento"])
        if not self.samples:
            return ("insufficient_data", ["nessun campione raccolto"])

        last = self.samples[-1]
        verdetto, diff = ms.signatures_match_with_intensity(
            self.reference_signature,
            last,
            cpu_tolerance_pct=cpu_tolerance_pct,
            power_tolerance_w=power_tolerance_w,
        )
        return self._map_verdict(verdetto, diff)

    def evaluate_background(
        self,
        cpu_tolerance_pct: float = 5.0,
        power_tolerance_w: Optional[float] = None,
    ) -> Tuple[str, List[str]]:
        """Alias di evaluate_global() per retrocompatibilità.

        .. deprecated:: Usa evaluate_global() per chiarezza.
        """
        return self.evaluate_global(cpu_tolerance_pct, power_tolerance_w)

    def record_block_verdict(
        self,
        block_id: str,
        local_verdict: str,
        local_diff: List[str],
        global_verdict: str,
        global_diff: List[str],
        overhead_s: float = 0.0,
    ) -> None:
        """Registra i verdetti di un blocco per la serializzazione JSON.

        Args:
            block_id: identificatore univoco del blocco.
            local_verdict: esito del confronto pre/post dello stesso blocco.
            local_diff: differenze rilevate nel confronto locale.
            global_verdict: esito del confronto con il riferimento iniziale.
            global_diff: differenze rilevate nel confronto globale.
            overhead_s: tempo di campionamento del monitor in secondi.
        """
        verdict = {
            "block_id": block_id,
            "local_verdict": local_verdict,
            "local_diff": local_diff,
            "global_verdict": global_verdict,
            "global_diff": global_diff,
            "overhead_s": overhead_s,
            "timestamp": time.monotonic(),
        }
        self.block_verdicts.append(verdict)

    def to_json(self) -> Dict:
        """Restituisce lo stato completo come dizionario JSON-serializzabile.

        Include verdetti per blocco, differenze, campioni raccolti,
        riferimento iniziale, errori e stato di completezza. Per il campo
        notes del CSV usare invece to_notes_string().
        """
        ref_info = None
        if self.reference_signature is not None:
            ref_info = {
                "pid": self.reference_signature.get("processes", [{}])[0].get("pid")
                if self.reference_signature.get("processes") else None,
                "name": self.reference_signature.get("processes", [{}])[0].get("name")
                if self.reference_signature.get("processes") else None,
                "cpu_total_mean_pct": self.reference_signature.get("cpu_total_mean_pct"),
            }
        state = {
            "background_monitor": {
                "samples_collected": len(self.samples),
                "reference_available": self.reference_signature is not None,
                "reference_info": ref_info,
                "block_verdicts": self.block_verdicts,
                "errors": self.errors,
                "coverage_status": (
                    "insufficient" if len(self.samples) < 2 else "pre_post_only"
                ),
            }
        }
        return state

    def to_notes_string(self) -> str:
        """Serializza un riepilogo breve per il campo notes del CSV P5.

        Il formato usa una chiave strutturata ``background_monitor:{...}``
        per permettere l'estrazione dal campo notes senza confondere con
        altre note testuali.

        Restituisce una stringa pronta da appendere al campo notes.
        """
        state = {
            "background_monitor": {
                "samples_collected": len(self.samples),
                "reference_available": self.reference_signature is not None,
            }
        }
        return f"background_monitor:{json.dumps(state, ensure_ascii=False)}"

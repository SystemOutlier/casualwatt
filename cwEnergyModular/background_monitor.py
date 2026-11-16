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
    e un campione dopo ogni blocco successivo, confrontando sempre con il
    riferimento iniziale. Se il riferimento non è stato impostato, il primo
    campione pre diventa il riferimento.

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

    def evaluate_background(
        self,
        cpu_tolerance_pct: float = 5.0,
        power_tolerance_w: Optional[float] = None,
    ) -> Tuple[str, List[str]]:
        """Valuta il background confrontando l'ultimo campione con il riferimento.

        Usa ``signatures_match_with_intensity()`` per confrontare identità
        e intensità, poi mappa i 4 token della funzione ai 3 token del monitor:
        - ``stable`` → ``stable``
        - ``intensity_unstable`` → ``unstable``
        - ``identity_changed`` → ``unstable``
        - ``insufficient_data`` → ``insufficient_data``

        Args:
            cpu_tolerance_pct: tolleranza sulla CPU totale media in percentuale.
                Se la differenza tra le medie CPU supera questo valore,
                l'intensità è instabile. La tolleranza viene dal piano,
                non è una costante universale.
            power_tolerance_w: tolleranza sulla potenza media in Watt (opzionale).
                Se fornita, anche la potenza deve stare entro questa banda.

        Restituisce:
            (verdetto, differenze) dove verdetto è uno dei tre token chiusi
            e differenze elenca le ragioni del verdetto.
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
        # Mappa i 4 token di signatures_match_with_intensity ai 3 token del monitor
        if verdetto == "identity_changed":
            return ("unstable", diff)
        if verdetto == "intensity_unstable":
            return ("unstable", diff)
        if verdetto == "insufficient_data":
            return ("insufficient_data", diff)
        return ("stable", diff)

    def to_json(self) -> str:
        """Serializza lo stato del monitor in JSON per il campo notes.

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

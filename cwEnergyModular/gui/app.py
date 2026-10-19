# -*- coding: utf-8 -*-
"""
gui/app.py — Finestra principale CasualWatt (tre pannelli, sez. 4).

Layout verticale: Selezione modelli -> Esecuzione benchmark -> Risultati.
All'apertura carica in background i modelli Ollama e cloud; alla chiusura
arresta la sessione di campionamento.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.benchmark_panel import BenchmarkPanel
from gui.model_selection import ModelSelectionPanel
from gui.results_panel import ResultsPanel

import sys


def _is_windows() -> bool:
    return sys.platform.startswith("win")


class CasualWattApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CasualWatt Energy Benchmark v1.0")
        self.geometry("1280x860")
        self.minsize(980, 700)

        # controllo privilegi all'avvio: LHM (sensori Energy-CPU) richiede un
        # token elevato su Windows; l'utente puo' ri-elevarsi con un click
        # dal pulsante nel pannello di esecuzione.
        try:
            from elevation import elevate_available, is_admin

            if _is_windows() and not is_admin() and elevate_available():
                self.title("CasualWatt Energy Benchmark v1.0 — [privilegi standard]")
        except Exception:
            pass

        try:
            style = ttk.Style(self)
            if "vista" in style.theme_names():
                style.theme_use("vista")
            elif "clam" in style.theme_names():
                style.theme_use("clam")
        except Exception:
            pass

        # STRUTTURA: header fisso + tk.PanedWindow verticale CLASSICO con i
        # 3 pannelli (Selezione / Esecuzione+Log / Risultati) come figli
        # diretti. Sash trascinabili col mouse, minsize reali in add().
        # Il divisorio interno Controlli <-> Log sta in benchmark_panel.py.
        header = ttk.Label(
            self,
            text="CasualWatt — benchmark energetico causale per LLM locali (Ollama) e cloud",
            font=("Segoe UI", 11, "bold"),
        )
        header.pack(side="top", fill="x", padx=10, pady=(8, 2))

        # Contenitore ridimensionabile col mouse: tk.PanedWindow CLASSICO
        # (NON ttk.Panedwindow!). I pannelli sono FIGLI diretti del
        # PanedWindow: niente pack/grid su di essi, solo paned.add().
        #
        # Perche' tk.PanedWindow e non ttk:
        #  - "paneconfigure" NON esiste su Tk 8.6 (TclError all'avvio);
        #  - ttk::panedwindow non espone -minsize in modo affidabile e i
        #     suoi figli gestiti con "place" spariscono se ri-parentati;
        #  - tk.PanedWindow accetta minsize direttamente in add() su
        #     QUALSIASI Tcl/Tk (verificato 8.6 e 8.7+) e il sash e'
        #     trascinabile nativamente col mouse.
        self.paned = tk.PanedWindow(self, orient="vertical", sashwidth=7,
                                    sashrelief="raised", opaqueresize=True)
        self.paned.pack(fill="both", expand=True, padx=10, pady=(4, 8))

        self.selection = ModelSelectionPanel(self.paned, log=self._log_to_benchmark)
        self.benchmark = BenchmarkPanel(self.paned, get_selections=self._get_selections)
        self.results = ResultsPanel(self.paned)
        # FIX finestre nascoste: con i vecchi minsize (200+200+180=580) il
        # pannello centrale (Esecuzione+Log) veniva compresso sotto la sua
        # impronta minima e il LOG spariva. Ora benchmark ha un minsize che
        # garantisce la visibilita' di log_text; gli altri due sono comprimibili.
        self.paned.add(self.selection, minsize=120, stretch="always")
        self.paned.add(self.benchmark, minsize=170, stretch="always")
        self.paned.add(self.results, minsize=120, stretch="always")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # auto-carica liste
        self.after(300, self.selection.reload_local)
        self.after(500, self.selection.reload_cloud)
        self.after(800, self.results.refresh)
        # diagnostica energetica non bloccante all'avvio (console + log GUI):
        # segnala subito se clr/pythonnet/DLL/UAC impediscono LHM di leggere
        # i Joule, prima che l'utente prema "Calibra idle".
        self.after(1200, self._run_startup_diagnostics)

    # ------------------------------------------------------------------ glue
    def _run_startup_diagnostics(self):
        import threading

        def _worker():
            try:
                import diagnostics

                summary = diagnostics.run_diagnostics(log_callback=self.log_from_thread)
                if summary.get("errors"):
                    self.log_from_thread(
                        "[CasualWatt] Diagnostica avviamento: problemi rilevati "
                        f"({', '.join(summary['errors'])}). Metodo energia atteso: "
                        f"{summary.get('method_expected', 'n/d')}"
                    )
                else:
                    self.log_from_thread(
                        "[CasualWatt] Diagnostica avviamento completata: "
                        f"metodo energia atteso = {summary.get('method_expected', 'n/d')}"
                    )
            except Exception as exc:  # la diagnostica non deve mai crashare l'app
                self.log_from_thread(f"[CasualWatt] Diagnostica avviamento fallita: {exc}")

        threading.Thread(target=_worker, daemon=True).start()

    def log_from_thread(self, msg: str):
        """Log thread-safe nel pannello di esecuzione (Tk e' single-thread)."""
        try:
            self.after(0, lambda: self.benchmark.log(str(msg)))
        except Exception:
            pass

    def _get_selections(self):
        return self.selection.get_selected_local(), self.selection.get_selected_cloud()

    def _log_to_benchmark(self, msg: str):
        self.benchmark.log(msg)

    def _on_close(self):
        try:
            self.benchmark.stop()
            from energy.energy_session import SESSION

            # stop() NON chiude LHM/NVML (spec §6); close() li chiude una
            # sola volta alla fine della sessione applicativa.
            SESSION.stop()
            SESSION.close()
        except Exception:
            pass
        self.destroy()


def main():
    app = CasualWattApp()
    app.mainloop()


if __name__ == "__main__":
    main()

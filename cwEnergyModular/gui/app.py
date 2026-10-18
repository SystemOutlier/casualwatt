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

        header = ttk.Label(
            self,
            text="CasualWatt — benchmark energetico causale per LLM locali (Ollama) e cloud",
            font=("Segoe UI", 11, "bold"),
        )
        header.pack(fill="x", padx=10, pady=(8, 2))

        # pannello 1 — selezione (non viene mai "schiacciato": sta sopra il
        # PanedWindow ed e' a dimensione fissa)
        self.selection = ModelSelectionPanel(self, log=self._log_to_benchmark)
        self.selection.pack(fill="both", expand=False, padx=10, pady=4)

        # Pannelli 2+3 dentro un PanedWindow VERTICALE: l'utente puo'
        # trascinare i divisori (sash) per aumentare/diminuire l'altezza di
        # Esecuzione/Log e dei Risultati. minsize impedisce che una sezione
        # scompaia del tutto o comprima quella superiore oltre l'usabilita'.
        main_pane = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # pannello 2 — esecuzione + log (al suo interno un ulteriore sash
        # separa i controlli dal Log: vedi BenchmarkPanel.pane_log)
        self.benchmark = BenchmarkPanel(main_pane, get_selections=self._get_selections)
        main_pane.add(self.benchmark, weight=1)

        # pannello 3 — risultati
        self.results = ResultsPanel(main_pane)
        main_pane.add(self.results, weight=1)

        # vincoli minimi: nessuna sezione puo' essere trascinata fino a
        # sparire o a schiacciare la sezione superiore sopra l'usabilita'
        main_pane.paneconfigure(self.benchmark, minsize=260)
        main_pane.paneconfigure(self.results, minsize=220)

        # altezze iniziali ragionevoli appena il widget ha una geometria
        def _set_initial_sashes():
            try:
                total = main_pane.winfo_height()
                if total > 480:
                    main_pane.sashpos(0, int(total * 0.55))
            except Exception:
                pass

        self.after(250, _set_initial_sashes)

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

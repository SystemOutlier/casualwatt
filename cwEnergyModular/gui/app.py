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

        # STRUTTURA A 3 ZONE (pack side=top): header fisso, SELEZIONE
        # scrollabile (canvas+scrollbar: le liste Treeview possono chiedere
        # piu' altezza della finestra; senza scrollregion Tk comprimeva
        # l'area espandibile fino a far "sparire" Log e Risultati — bug
        # osservato su Windows 11), poi il body ESPANDIBILE che riceve tutto
        # lo spazio residuo. I sash custom dentro il body regolano
        # Esecuzione/Log <-> Risultati con clamp reale ai minimi MIN_*; il
        # divisorio interno Controlli <-> Log sta in benchmark_panel.py.
        header = ttk.Label(
            self,
            text="CasualWatt — benchmark energetico causale per LLM locali (Ollama) e cloud",
            font=("Segoe UI", 11, "bold"),
        )
        header.pack(side="top", fill="x", padx=10, pady=(8, 2))

        SEL_H = 240   # altezza zona selezione (le liste scrollano al suo interno)
        sel_holder = tk.Frame(self, height=SEL_H)
        sel_holder.pack(side="top", fill="x", padx=10, pady=(0, 4))
        # propagate disattivata DOPO la creazione del canvas-figlio: cosi'
        # l'altezza resta SEL_H (i figli non possono schiacciare Log/Risultati)
        # ma la LARGHEZZA continua a seguire il contenuto (liste piene).
        sel_canvas = tk.Canvas(sel_holder, highlightthickness=0, bd=0,
                               width=900, height=SEL_H - 8)
        sel_canvas.pack(side="left", fill="both", expand=True)
        sel_holder.pack_propagate(False)
        sel_vsb = ttk.Scrollbar(sel_holder, orient="vertical",
                                command=sel_canvas.yview)
        sel_vsb.pack(side="right", fill="y")
        sel_canvas.configure(yscrollcommand=sel_vsb.set)

        shell = tk.Frame(sel_canvas)
        _shell_win = sel_canvas.create_window((0, 0), window=shell, anchor="nw")

        def _sync_sel_region(*_a):
            try:
                sel_canvas.configure(scrollregion=sel_canvas.bbox("all"))
                w = sel_canvas.winfo_width()
                if w > 1:
                    sel_canvas.itemconfigure(_shell_win, width=w)
            except Exception:
                pass
        shell.bind("<Configure>", lambda e: _sync_sel_region())
        def _sel_wheel(e):
            try:
                if getattr(e, "delta", 0):
                    sel_canvas.yview_scroll(-int(e.delta / 120) or (-1 if e.delta else 0), "units")
                elif e.num == 4:
                    sel_canvas.yview_scroll(-1, "units")
                elif e.num == 5:
                    sel_canvas.yview_scroll(1, "units")
            except Exception:
                pass
        sel_canvas.bind("<MouseWheel>", _sel_wheel)
        sel_canvas.bind("<Button-4>", _sel_wheel)
        sel_canvas.bind("<Button-5>", _sel_wheel)

        self.selection = ModelSelectionPanel(shell, log=self._log_to_benchmark)
        self.selection.pack(fill="x", expand=False)

        # Pannelli 2+3 in un layout GRID a righe pesate con divisori
        # custom trascinabili (mouse) tra Esecuzione/Log e Risultati.
        #
        # CRONACA DEI TENTATIVI (Windows 11 / Python 3.14 / Tcl-Tk 8.6.x):
        #  1) "paneconfigure"/"panconfigure": comandi INESISTENTI su Tk 8.6
        #     -> TclError all'avvio ("bad command paneconfigure").
        #  2) ttk.PanedWindow + wrapper grid/sentinella per simulare il
        #     -minsize: i pannelli Log/Risultati sono SPARITI dalla vista
        #     (ttk::panedwindow gestisce i figli col gestore nativo "place";
        #     rimetterli in un wrapper con grid() ne azzera il rendering).
        #  3) SOLUZIONE ADO TTATA: guscio pack (header + selezione fissa in
        #     alto) + area "body" che espande, al suo interno grid a righe
        #     pesate con sash custom trascinabili. Il min-height E' REALE:
        #     durante il drag la posizione viene clampata ai valori MIN_*,
        #     quindi nessuna sezione puo' sparire o schiacciare l'altra.
        #     Nessun comando ttk::panedwindow "pane" invocato: layout
        #     identico su qualunque Tcl/Tk (8.6 e 8.7+).
        MIN_BENCH_H, MIN_RESULTS_H = 260, 220

        body = tk.Frame(self, height=MIN_BENCH_H + MIN_RESULTS_H + 16)
        body.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 8))
        body.columnconfigure(0, weight=1)
        for _r, _w in ((0, 5), (1, 0), (2, 4)):
            body.rowconfigure(_r, weight=_w)

        # pannello 2 — esecuzione + log (riga 0; contiene gia' il suo
        # divisorio interno controlli/log, vedi benchmark_panel.py)
        self.benchmark = BenchmarkPanel(body, get_selections=self._get_selections)
        self.benchmark.grid(row=0, column=0, sticky="nsew")

        # divisore custom Esecuzione <-> Risultati (riga 1)
        sash_br = tk.Frame(body, height=6, bd=1, relief="raised",
                           background="#d8d8d8")
        try:  # cursore doppio-arco verticale (valido su Windows/Tk 8.6)
            sash_br.configure(cursor="sb_vdouble_arrow")
        except Exception:
            pass
        sash_br.grid(row=1, column=0, sticky="ew")

        # pannello 3 — risultati (riga 2)
        self.results = ResultsPanel(body)
        self.results.grid(row=2, column=0, sticky="nsew")

        def _bind_sash(sash, min_above, min_below, widget_above, widget_below,
                       row_above, row_below):
            """Trascina il sash regolando i PESI ASSOLUTI (px) delle righe
            grid soprastante/sottostante. Il container ha pack_propagate
            disattivato: le righe pesate si dividono l'altezza disponibile
            in proporzione ai pesi, che qui sono esattamente gli height in
            pixel voluti. Clamp reale: nessun pannello puo' scendere sotto
            il proprio minimo -> nessuna sezione sparisce o schiaccia
            l'altra."""
            def _apply(pos_y):
                try:
                    h_a = widget_above.winfo_height()
                    h_b = widget_below.winfo_height()
                    span = max(h_a + h_b, min_above + min_below, 1)
                    new_above = max(min_above, min(span - min_below, pos_y))
                    new_below = span - new_above
                    body.rowconfigure(row_above, weight=max(int(new_above), 1))
                    body.rowconfigure(row_below, weight=max(int(new_below), 1))
                except Exception:
                    pass
            state = {"y0": None}
            def _press(event):
                state["y0"] = event.y_root
            def _drag(event):
                if state["y0"] is None:
                    return
                h_a = widget_above.winfo_height()
                _apply(h_a + (event.y_root - state["y0"]))
            def _release(_e):
                state["y0"] = None
            sash.bind("<ButtonPress-1>", _press)
            sash.bind("<B1-Motion>", _drag)
            sash.bind("<ButtonRelease-1>", _release)

        _bind_sash(sash_br, MIN_BENCH_H, MIN_RESULTS_H,
                   self.benchmark, self.results, 0, 2)

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

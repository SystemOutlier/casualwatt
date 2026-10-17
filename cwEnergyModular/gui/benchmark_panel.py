# -*- coding: utf-8 -*-
"""
gui/benchmark_panel.py — Pannello 2: esecuzione benchmark (sez. 4.2).

Contiene: Avvia/Ferma, barra di avanzamento, area log testuale, campi
numero prompt / temperatura / timeout, pulsante "Calibra idle" e campo di
lettura della potenza idle calibrata. Il lavoro pesante gira in un thread;
la comunicazione con Tk avviene solo via ``after()``.

Sorgente dei Test (Modalita' di Input Universale): radiobutton con due
opzioni dinamiche — A) Dataset Esterno CSV (pulsante "Sfoglia..." per file
generati da tool esterni tipo MUDILab, colonna prompt + eventuale
ground_truth/expected_result) oppure B) Prompt Manuale: blocchi dinamici
numerati ("Test 1", "Test 2", ...) in un'area scrollabile, ognuno con due
campi espliciti Domanda + Risposta Attesa (opzionale), "+ Aggiungi Prompt"
e "✕" per rimuovere. I test NON sono mai hardcodati nel framework.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Tuple


class BenchmarkPanel(ttk.LabelFrame):
    def __init__(self, master, get_selections=None, **kw):
        super().__init__(master, text="Esecuzione benchmark", **kw)
        self.get_selections = get_selections or (lambda: ([], []))
        self._stop_event = threading.Event()
        self._worker = None
        self._q: queue.Queue = queue.Queue()
        self._running = False

        # ------------------------- parametri ---------------------------------
        params = ttk.Frame(self)
        params.pack(fill="x", padx=6, pady=4)

        ttk.Label(params, text="Numero prompt:").grid(row=0, column=0, sticky="w")
        self.var_num_prompts = tk.IntVar(value=self._default("DEFAULT_NUM_PROMPTS", 3))
        ttk.Spinbox(params, from_=1, to=50, width=6, textvariable=self.var_num_prompts).grid(row=0, column=1, padx=(2, 14))

        ttk.Label(params, text="Temperatura:").grid(row=0, column=2, sticky="w")
        self.var_temperature = tk.DoubleVar(value=self._default("DEFAULT_TEMPERATURE", 0.2))
        ttk.Spinbox(params, from_=0.0, to=2.0, increment=0.1, width=6, textvariable=self.var_temperature).grid(row=0, column=3, padx=(2, 14))

        ttk.Label(params, text="Timeout (s):").grid(row=0, column=4, sticky="w")
        self.var_timeout = tk.DoubleVar(value=self._default("DEFAULT_TIMEOUT_S", 60))
        ttk.Spinbox(params, from_=5, to=600, increment=5, width=6, textvariable=self.var_timeout).grid(row=0, column=5, padx=(2, 14))

        # etichetta su colonna propria (no overlap coi campi della row 0) e
        # box di lettura largo quanto basta per "non calibrata" e per il
        # valore "xx.xx W" post-calibrazione
        ttk.Label(params, text="Potenza idle calibrata (W):").grid(row=1, column=0, sticky="w")
        self.var_idle = tk.StringVar(value="non calibrata")
        self.idle_label = ttk.Entry(params, textvariable=self.var_idle, width=18, state="readonly")
        self.idle_label.grid(row=1, column=1, columnspan=2, padx=(2, 14), sticky="w")

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=6, pady=2)
        self.btn_start = ttk.Button(btns, text="Avvia benchmark", command=self.start)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ttk.Button(btns, text="Ferma benchmark", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=2)
        ttk.Button(btns, text="Calibra idle", command=self.calibrate_idle).pack(side="left", padx=8)

        # ----------------------- stato privilegi UAC ------------------------
        # LibreHardwareMonitor legge i sensori Energy-CPU solo con token
        # elevato: mostro lo stato e offro il riavvio elevato con un click.
        try:
            from elevation import elevate_available, is_admin

            self._elevate_possible = elevate_available()
            _admin = is_admin()
        except Exception:  # pragma: no cover - degradazione protetta
            self._elevate_possible = False
            _admin = False
        if _admin:
            self.lbl_uac = ttk.Label(
                btns, text="\u2714 Amministratore", foreground="#1a7f37")
        elif self._elevate_possible:
            self.lbl_uac = ttk.Button(
                btns, text="\u26a0 Riavvia come Amministratore",
                command=self.relaunch_as_admin)
        else:
            self.lbl_uac = ttk.Label(
                btns, text="privilegi standard (LHM richiede admin)",
                foreground="gray")
        self.lbl_uac.pack(side="right", padx=6)

        # ---------------- sorgente dei test (universale) ---------------------
        src = ttk.LabelFrame(self, text="Sorgente dei Test")
        src.pack(fill="x", padx=6, pady=(4, 2))

        self.var_test_mode = tk.StringVar(value="csv")
        rb_csv = ttk.Radiobutton(
            src, text="Dataset Esterno (File CSV)", value="csv",
            variable=self.var_test_mode, command=self._on_test_mode_change,
        )
        rb_manual = ttk.Radiobutton(
            src, text="Prompt Manuale", value="manual",
            variable=self.var_test_mode, command=self._on_test_mode_change,
        )
        rb_csv.grid(row=0, column=0, sticky="w", padx=6, pady=(2, 0))
        rb_manual.grid(row=0, column=1, sticky="w", padx=12, pady=(2, 0))

        # --- A) fila CSV: entry percorso + Sfoglia + info parsing ------------
        self.csv_frame = ttk.Frame(src)
        self.csv_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=2)
        self.var_csv_path = tk.StringVar(value="")
        self.csv_entry = ttk.Entry(self.csv_frame, textvariable=self.var_csv_path)
        self.csv_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(self.csv_frame, text="Sfoglia...", width=10,
                   command=self.browse_csv).pack(side="left")
        self.csv_info = ttk.Label(src, text="Nessun CSV caricato. Colonne attese: "
                                            "prompt (o text/question/input/query); opzionale "
                                            "ground_truth (o expected_result).",
                                  foreground="gray")
        self.csv_info.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 2))

        # --- B) fila manuale: blocchi dinamici Domanda + Risposta Attesa ------
        # UI esplicita a campi separati: niente parsing del separatore " / ",
        # rischio di errori azzerato anche con prompt lunghi. La lista interna
        # e' persistente tra i cambi di modalita' (grid_forget non distrugge).
        self.manual_frame = ttk.Frame(src)
        self._manual_rows: List[dict] = []

        man_head = ttk.Frame(self.manual_frame)
        man_head.pack(fill="x", padx=6, pady=(4, 2))
        ttk.Button(man_head, text="+ Aggiungi Prompt", width=16,
                   command=self._manual_add_row).pack(side="left")
        ttk.Label(
            man_head,
            text="Inserisci la domanda nel campo \"Domanda\"; la risposta attesa "
                 "in \"Risposta Attesa\" (opzionale: se vuota -> accuratezza N/A, "
                 "salvate solo metriche energetiche/latenza/token).",
            foreground="gray", wraplength=560, justify="left",
        ).pack(side="left", padx=12)

        # contenitore scrollabile (canvas + inner frame + scrollbar verticale)
        man_body = ttk.Frame(self.manual_frame)
        man_body.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._man_canvas = tk.Canvas(man_body, height=132, highlightthickness=0)
        man_vsbar = ttk.Scrollbar(man_body, orient="vertical",
                                  command=self._man_canvas.yview)
        self._man_inner = ttk.Frame(self._man_canvas)
        self._man_inner.bind(
            "<Configure>",
            lambda e: self._man_canvas.configure(scrollregion=self._man_canvas.bbox("all")),
        )
        self._man_win = self._man_canvas.create_window((0, 0), window=self._man_inner, anchor="nw")
        self._man_canvas.bind(
            "<Configure>", lambda e: self._man_canvas.itemconfigure(self._man_win, width=e.width)
        )
        self._man_canvas.configure(yscrollcommand=man_vsbar.set)
        self._man_canvas.pack(side="left", fill="both", expand=True)
        man_vsbar.pack(side="right", fill="y")
        # rotellina del mouse dentro il canvas (Windows/Tk standard)
        self._man_canvas.bind_all("<MouseWheel>", self._man_on_wheel)
        self._man_canvas.bind_all("<Button-4>", self._man_on_wheel)   # X11 fallback
        self._man_canvas.bind_all("<Button-5>", self._man_on_wheel)   # X11 fallback

        self._manual_add_row()  # primo blocco "Test 1" gia' pronto

        src.columnconfigure(0, weight=1)
        src.columnconfigure(1, weight=1)
        self._on_test_mode_change()  # stato iniziale widget dinamici

        # ------------------------- progress + log ----------------------------
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=6, pady=(4, 2))

        self.log_text = tk.Text(self, height=9, wrap="word", state="disabled",
                                font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        self._poller = None

    @staticmethod
    def _default(name, fallback):
        try:
            import config

            return getattr(config, name, fallback)
        except Exception:
            return fallback

    # ------------------------------------------------- sorgente dei test -----
    def _on_test_mode_change(self):
        """Mostra SOLO i widget della modalita' selezionata (pulito/dinamico)."""
        mode = self.var_test_mode.get()
        for frame in (self.csv_frame, self.manual_frame):
            frame.grid_forget()
        if mode == "manual":
            self.manual_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
            self.csv_info.grid_remove()
        else:
            self.csv_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=2)
            self.csv_info.grid()

    def browse_csv(self):
        """Apre il file dialog e precarica/valida il dataset esterno."""
        try:
            from tkinter import filedialog

            path = filedialog.askopenfilename(
                title="Seleziona dataset CSV (output tool esterni, es. MUDILab)",
                filetypes=[("CSV", "*.csv"), ("Tutti i file", "*.*")],
            )
            if not path:
                return
            self.var_csv_path.set(path)
            self._preview_csv(path)
        except Exception as exc:
            self.log(f"Errore apertura file dialog: {exc}")

    def _preview_csv(self, path: str):
        """Validazione immediata del CSV: mostra n. prompt e presenza GT."""
        try:
            from test_source import load_prompts_from_csv

            items, err = load_prompts_from_csv(path)
        except Exception as exc:
            items, err = [], f"{type(exc).__name__}: {exc}"
        if items:
            n_gt = sum(1 for it in items if it.get("ground_truth"))
            txt = (f"CSV OK: {len(items)} prompt caricati; ground_truth presente "
                   f"per {n_gt}" + (" (accuratezza valutata dove disponibile)"
                                    if n_gt else " (accuratezza -> N/A: solo metriche energetiche)"))
            self.csv_info.config(text=txt, foreground="#1a7f37")
            self.log(txt + f" — file: {path}")
        else:
            self.csv_info.config(text=f"CSV non valido: {err}", foreground="#b35900")
            self.log(f"CSV non valido: {err}")

    def get_test_source_kwargs(self) -> dict:
        """Estrapola la selezione corrente per il runner (usato anche da CLI).

        Modalita' manuale: costruisce un testo compatibile con il parser di
        test_source ('prompt / ground_truth' per riga) dai campi espliciti.
        Gli a capo dentro i singoli campi vengono appiattiti con uno spazio
        per non corrompere il formato one-per-line; il separatore ' / ' e'
        generato SOLO noi blocchi con risposta attesa compilata, quindi il
        parsing downstream e' deterministico (niente ambiguita' utente).
        NB: questo metodo viene invocato dal thread del benchmark -> legge i
        widget Tk in modo thread-safe via invoke sul thread principale.
        """
        mode = self.var_test_mode.get()
        if mode == "manual":
            return {"test_mode": "manual", "manual_text": self._collect_manual_text()}
        return {"test_mode": "csv", "csv_path": self.var_csv_path.get().strip()}

    # ----------------------------------------------------- righe manuali -----
    def _man_on_wheel(self, event):
        """Scrolla la lista dei blocchi con la rotellina (Windows delta 120)."""
        try:
            if getattr(event, "num", None) == 4:      # X11 scroll giu'
                self._man_canvas.yview_scroll(1, "units")
            elif getattr(event, "num", None) == 5:    # X11 scroll su'
                self._man_canvas.yview_scroll(-1, "units")
            else:
                step = -1 if getattr(event, "delta", 0) > 0 else 1
                self._man_canvas.yview_scroll(step, "units")
        except Exception:
            pass

    def _manual_add_row(self):
        """Aggiunge un blocco numerato 'Test N' con Domanda + Risposta Attesa."""
        idx = len(self._manual_rows) + 1
        row_frame = ttk.Frame(self._man_inner, padding=(2, 2))
        row_frame.pack(fill="x", padx=2, pady=1)

        lbl_num = ttk.Label(row_frame, text=f"Test {idx}:", width=8)
        lbl_num.grid(row=0, column=0, sticky="w")

        var_q = tk.StringVar()
        var_gt = tk.StringVar()
        ent_q = ttk.Entry(row_frame, textvariable=var_q)
        ent_q.grid(row=0, column=1, sticky="ew", padx=(2, 6))
        ttk.Label(row_frame, text="Risposta Attesa (opz.):").grid(
            row=0, column=2, sticky="e", padx=(0, 2))
        ent_gt = ttk.Entry(row_frame, textvariable=var_gt, width=22)
        ent_gt.grid(row=0, column=3, sticky="ew", padx=(0, 6))
        row_frame.columnconfigure(1, weight=3)
        row_frame.columnconfigure(3, weight=1)

        entry = {"frame": row_frame, "label": lbl_num, "var_q": var_q,
                 "var_gt": var_gt, "ent_q": ent_q, "ent_gt": ent_gt}
        btn_rm = ttk.Button(row_frame, text="✕", width=3,
                            command=lambda e=entry: self._manual_remove_row(e))
        btn_rm.grid(row=0, column=4, sticky="e")
        entry["btn_rm"] = btn_rm
        self._manual_rows.append(entry)
        ent_q.focus_set()
        self._man_canvas.update_idletasks()
        try:  # porta la vista sull'ultima riga aggiunta
            self._man_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _manual_remove_row(self, entry):
        """Rimuove un blocco e rinumeria i restanti (Test 1..N)."""
        try:
            self._manual_rows.remove(entry)
        except ValueError:
            return
        entry["frame"].destroy()
        for i, row in enumerate(self._manual_rows, start=1):
            row["label"].config(text=f"Test {i}:")

    def _read_manual_entries(self) -> List[Tuple[str, Optional[str]]]:
        """Legge le coppie (domanda, risposta_attesa) dai campi Tk.

        Chiamato solo dal thread principale (start() prima di avviare il
        worker); lettura diretta degli StringVar, niente cross-thread.
        """
        out: List[Tuple[str, Optional[str]]] = []
        for row in self._manual_rows:
            q = row["var_q"].get().replace("\n", " ").replace("\r", " ").strip()
            gt = row["var_gt"].get().replace("\n", " ").replace("\r", " ").strip()
            out.append((q, gt or None))
        return out

    def _collect_manual_text(self) -> str:
        """Serializza i blocchi nel formato parseato da test_source."""
        lines = []
        for q, gt in self._read_manual_entries():
            if not q:
                continue
            lines.append(f"{q} / {gt}" if gt else q)
        return "\n".join(lines)

    def count_manual_prompts(self) -> int:
        """Numero di blocchi con domanda compilata (per log/validazione GUI)."""
        return sum(1 for q, _ in self._read_manual_entries() if q)

    # ------------------------------------------------------------------- log
    def log(self, msg: str):
        self._q.put(("log", msg))

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "log":
                    stamp = time.strftime("%H:%M:%S")
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", f"[{stamp}] {payload}\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                elif kind == "progress":
                    done, total = payload
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = done
                elif kind == "idle":
                    self.var_idle.set(f"{payload:.2f} W")
                elif kind == "done":
                    self._set_running(False)
                    summary = payload
                    self.log(
                        f"Benchmark terminato: {summary.get('records', 0)} record, "
                        f"{summary.get('errors', 0)} errori"
                        + (" (ANNULLATO)" if summary.get("cancelled") else "")
                    )
        except queue.Empty:
            pass
        finally:
            if self._running or not self._q.empty():
                self.after(120, self._drain_queue)
            else:
                self._poller = None

    def _ensure_poller(self):
        if self._poller is None:
            self._poller = True
            self.after(50, self._drain_queue)

    def _set_running(self, running: bool):
        self._running = running
        self.btn_start.config(state="normal" if not running else "disabled")
        self.btn_stop.config(state="normal" if running else "disabled")

    # --------------------------------------------------------------- actions
    def start(self):
        if self._running:
            return
        local_models, cloud_sel = self.get_selections()
        if not local_models and not cloud_sel:
            self.log("Seleziona almeno un modello locale o cloud prima di avviare.")
            return

        # convalida sorgente dei test PRIMA di avviare il thread (GUI: niente
        # fallback silenzioso, errore esplicito a video)
        src_kwargs = self.get_test_source_kwargs()
        try:
            from test_source import load_test_source

            items, err = load_test_source(
                mode=src_kwargs["test_mode"],
                csv_path=src_kwargs.get("csv_path"),
                manual_text=src_kwargs.get("manual_text"),
                fallback_config=False,
            )
        except Exception as exc:
            items, err = [], f"{type(exc).__name__}: {exc}"
        if not items:
            self.log(f"Impossibile avviare: sorgente test non valida — {err}")
            return
        n_gt = sum(1 for it in items if it.get("ground_truth"))
        self.log(
            f"Sorgente test selezionata: {len(items)} prompt "
            f"({src_kwargs['test_mode']}); ground truth per {n_gt} "
            + ("-> accuratezza valutata tramite confronto"
               if n_gt else "-> accuratezza N/A: verranno salvate solo le metriche energetiche/di latenza")
        )

        self._stop_event.clear()
        self.progress["value"] = 0
        self._set_running(True)
        self._ensure_poller()
        self.log(
            f"Avvio benchmark — locali: {local_models or '-'} | "
            f"cloud: {[c['model'] for c in cloud_sel] or '-'} | "
            f"sorgente: {src_kwargs['test_mode']} | "
            f"prompt: {self.var_num_prompts.get()} T={self.var_temperature.get()} "
            f"timeout={self.var_timeout.get()}s"
        )
        kwargs = dict(
            local_models=local_models,
            cloud_selection=cloud_sel,
            num_prompts=int(self.var_num_prompts.get()),
            temperature=float(self.var_temperature.get()),
            timeout_s=float(self.var_timeout.get()),
            on_log=lambda m: self._q.put(("log", m)),
            on_progress=lambda i, n: self._q.put(("progress", (i, n))),
            stop_event=self._stop_event,
            skip_idle_calibration=SESSION_has_idle(),
            **src_kwargs,
        )
        self._worker = threading.Thread(
            target=self._run_worker, kwargs=kwargs, daemon=True, name="cw-benchmark"
        )
        self._worker.start()

    def _run_worker(self, **kwargs):
        try:
            from benchmark_unified import run_unified_benchmark

            summary = run_unified_benchmark(**kwargs)
            self._q.put(("done", summary))
        except Exception as exc:  # doppia rete difensiva
            self._q.put(("log", f"ERRORE FATALE benchmark: {type(exc).__name__}: {exc}"))
            self._q.put(("done", {"records": 0, "errors": 1, "cancelled": True}))

    def stop(self):
        if not self._running:
            return
        self._stop_event.set()
        self.log("Interrupt richiesto: atteso completamento della richiesta corrente…")

    # ------------------------------------------------------------ calibrazione
    def calibrate_idle(self):
        from energy.energy_session import SESSION

        def worker():
            was_running = SESSION.running
            try:
                if not was_running:
                    SESSION.start()
                    time.sleep(SESSION.interval_s * 2)
                self._q.put(("log", "Calibrazione idle EMPIRICA: NON generare carico sul PC…"))
                pw = SESSION.calibrate_idle()
                self._q.put(("idle", pw))
                self._q.put((
                    "log",
                    f"P_idle = {pw:.2f} W misurata a riposo "
                    f"(delta Joule / durata; contatore: {SESSION.source_method})",
                ))
            except Exception as exc:
                self._q.put(("log", f"Calibrazione fallita: {exc}"))
                # niente fallimento silenzioso: se il contatore non legge i
                # Joule, la causa piu' probabile e' UAC o pythonnet/clr:
                # esegui la diagnostica completa (console + log GUI).
                try:
                    import diagnostics

                    self._q.put(("log", "--- Diagnostica LHM/clr in corso (console + qui) ---"))
                    summary = diagnostics.run_diagnostics(
                        log_callback=lambda m: self._q.put(("log", m))
                    )
                    method = summary.get("method_expected", "n/d")
                    self._q.put(("log", f"--- Fine diagnostica: metodo atteso = {method} ---"))
                except Exception as d_exc:
                    self._q.put(("log", f"Diagnostica non disponibile: {d_exc}"))
            finally:
                if not was_running:
                    SESSION.stop()

        t = threading.Thread(target=worker, daemon=True, name="cw-idle-calib")
        t.start()
        self._ensure_poller()

    # ------------------------------------------------------------ elevazione
    def relaunch_as_admin(self):
        """Riavvia CasualWatt con privilegi amministrativi (prompt UAC).

        Necessario per far leggere a LibreHardwareMonitor i sensori fisici
        Energy-CPU. Se un benchmark e' in corso viene prima fermato in modo
        pulito; al successo dell'avvio elevato l'istanza corrente si chiude.
        """
        import tkinter as _tk
        from tkinter import messagebox

        from elevation import relaunch_as_admin as _relaunch

        if self._running:
            if not messagebox.askyesno(
                "Riavvio come Amministratore",
                "Benchmark in corso: verra' fermato prima del riavvio.\n"
                "Continuare?",
            ):
                return
            self.stop()

        handle = _relaunch()
        if handle > 0:
            self.log("Riavvio elevato richiesto (prompt UAC): nuova istanza in avvio…")
            try:
                if messagebox.askyesno(
                    "Riavvio come Amministratore",
                    "Elevazione richiesta: la nuova finestra di CasualWatt "
                    "(amministratore) sta partendo.\n\n"
                    "Chiudere questa istanza non elevata?",
                ):
                    toplevel = self.winfo_toplevel()
                    if hasattr(toplevel, "_on_close"):
                        toplevel._on_close()
                    else:
                        toplevel.destroy()
            except _tk.TclError:
                pass
        else:
            self.log(
                "Elevazione non riuscita (prompt UAC annullato o negato). "
                "Riprova oppure avvia manualmente: 'py main.py' da PowerShell admin."
            )


def SESSION_has_idle() -> bool:
    try:
        from energy.energy_session import SESSION

        return SESSION.idle_power_w is not None
    except Exception:
        return False

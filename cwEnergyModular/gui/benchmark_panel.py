# -*- coding: utf-8 -*-
"""
gui/benchmark_panel.py — Pannello 2: esecuzione benchmark (sez. 4.2).

Contiene: Avvia/Ferma, barra di avanzamento, area log testuale, campi
numero prompt / temperatura / timeout, pulsante "Calibra idle" e campo di
lettura della potenza idle calibrata. Il lavoro pesante gira in un thread;
la comunicazione con Tk avviene solo via ``after()``.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk


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

        ttk.Label(params, text="Potenza idle calibrata (W):").grid(row=1, column=0, columnspan=3, sticky="w")
        self.var_idle = tk.StringVar(value="non calibrata")
        self.idle_label = ttk.Entry(params, textvariable=self.var_idle, width=10, state="readonly")
        self.idle_label.grid(row=1, column=3, padx=2, sticky="w")

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=6, pady=2)
        self.btn_start = ttk.Button(btns, text="Avvia benchmark", command=self.start)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ttk.Button(btns, text="Ferma benchmark", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=2)
        ttk.Button(btns, text="Calibra idle", command=self.calibrate_idle).pack(side="left", padx=8)

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
        self._stop_event.clear()
        self.progress["value"] = 0
        self._set_running(True)
        self._ensure_poller()
        self.log(
            f"Avvio benchmark — locali: {local_models or '-'} | "
            f"cloud: {[c['model'] for c in cloud_sel] or '-'} | "
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
            try:
                was_running = SESSION.running
                if not was_running:
                    SESSION.start()
                    time.sleep(SESSION.interval_s * 2)
                self._q.put(("log", "Calibrazione idle: NON generare carico sul PC…"))
                pw = SESSION.calibrate_idle()
                self._q.put(("idle", pw))
                self._q.put(("log", f"P_idle = {pw:.2f} W (fonte: {SESSION.source_method})"))
                if not was_running:
                    SESSION.stop()
            except Exception as exc:
                self._q.put(("log", f"Calibrazione fallita: {exc}"))

        t = threading.Thread(target=worker, daemon=True, name="cw-idle-calib")
        t.start()
        self._ensure_poller()


def SESSION_has_idle() -> bool:
    try:
        from energy.energy_session import SESSION

        return SESSION.idle_power_w is not None
    except Exception:
        return False

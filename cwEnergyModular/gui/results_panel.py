# -*- coding: utf-8 -*-
"""
gui/results_panel.py — Pannello 3: risultati (sez. 4.3).

Tabella Treeview dei record dal CSV, pulsanti Apri CSV / Esporta CSV /
Aggiorna e due grafici Canvas opzionali: energia vs accuratezza e
energia vs ECE (acc_comp per joule), disegnati senza matplotlib.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List

CSV_VIEW_COLUMNS = [
    ("model_label", "Modello", 170),
    ("mode", "Mode", 60),
    ("prompt_id", "Prompt", 90),
    ("test_source", "Sorgente", 72),
    ("duration_s", "Latenza (s)", 80),
    ("input_tokens", "Token in", 72),
    ("output_tokens", "Token out", 78),
    ("total_tokens", "Token tot", 78),
    ("local_energy_j", "Locale J", 80),
    ("network_energy_j", "Rete J", 70),
    ("cloud_energy_j", "Cloud J", 75),
    ("end_to_end_energy_j", "E2E J", 85),
    ("energy_per_output_token_j", "J/token", 75),
    ("causal_accuracy", "Acc", 50),
    ("ece_per_joule", "ECE/J", 80),
    ("epcl_j_per_link", "EPCL", 75),
]

# colonne con valori energetici/numerici: formattazione a decimali FISSI
# (2 per i Joule) invece di notazione compatta ".4g" che mostrava interi
# grandi o troncava la precisione; token e durata hanno regole proprie.
_COL_FORMAT = {
    "duration_s": "durata",          # 3 decimali (latenza sub-secondo utile)
    "input_tokens": "int",
    "output_tokens": "int",
    "total_tokens": "int",
    "local_energy_j": "joule",
    "network_energy_j": "joule",
    "cloud_energy_j": "joule",
    "end_to_end_energy_j": "joule",
    "energy_per_output_token_j": "joule",
    "causal_accuracy": "ratio",      # 2 decimali
    "ece_per_joule": "sci",          # valori piccolissimi -> 4 decimali
    "epcl_j_per_link": "joule",
}


def _fmt_cell(cid: str, raw) -> str:
    """Formattazione pulita per la tabella dei risultati."""
    rule = _COL_FORMAT.get(cid)
    if rule is None:
        return "N/A" if raw == "N/A" else ("" if raw is None else str(raw))
    if raw == "N/A":  # valutazione saltata: mostrato esplicitamente
        return "N/A"
    try:
        fv = float(raw)
    except (TypeError, ValueError):
        return str(raw) if raw not in (None, "") else ""
    if fv != fv:  # NaN
        return ""
    if rule == "int":
        return f"{int(round(fv))}"
    if rule == "durata":
        return f"{fv:.3f}"
    if rule == "joule":
        return f"{fv:.2f}"
    if rule == "ratio":
        return f"{fv:.2f}"
    if rule == "sci":
        return f"{fv:.4f}"
    return str(raw)


def _read_rows() -> List[dict]:
    try:
        import csv as _csv

        import config

        path = config.CSV_RESULTS_PATH
        if not path.exists():
            return []
        with open(path, "r", newline="", encoding="utf-8-sig") as fh:
            rows = list(_csv.DictReader(fh))
        return rows
    except Exception:
        return []


class ResultsPanel(ttk.LabelFrame):
    def __init__(self, master, **kw):
        super().__init__(master, text="Risultati", **kw)

        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Button(top, text="Aggiorna", command=self.refresh).pack(side="left", padx=2)
        ttk.Button(top, text="Apri CSV", command=self.open_csv).pack(side="left", padx=2)
        ttk.Button(top, text="Esporta CSV", command=self.export_csv).pack(side="left", padx=2)
        self.status = ttk.Label(top, text="—", foreground="gray")
        self.status.pack(side="right")

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        table_wrap = ttk.Frame(mid)
        table_wrap.pack(side="left", fill="both", expand=True)
        cols = [c for c, _, _ in CSV_VIEW_COLUMNS]
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings", height=9)
        for cid, label, w in CSV_VIEW_COLUMNS:
            self.tree.heading(cid, text=label)
            self.tree.column(cid, width=w, anchor="e" if cid not in ("model_label", "prompt_id") else "w")
        scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        hscroll = ttk.Scrollbar(table_wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        table_wrap.rowconfigure(0, weight=1)
        table_wrap.columnconfigure(0, weight=1)

        # ------------------------------ grafici ------------------------------
        charts = ttk.Frame(mid)
        charts.pack(side="left", fill="y", padx=(8, 0))
        self.canvas_acc = tk.Canvas(charts, width=250, height=150, bg="#fbfbfb",
                                    highlightbackground="#cccccc")
        self.canvas_acc.pack(fill="x", pady=(0, 6))
        self.canvas_ece = tk.Canvas(charts, width=250, height=150, bg="#fbfbfb",
                                    highlightbackground="#cccccc")
        self.canvas_ece.pack(fill="x")

        self._rows_cache: List[dict] = []

    # ---------------------------------------------------------------- actions
    def refresh(self):
        rows = _read_rows()
        self._rows_cache = rows
        self.tree.delete(*self.tree.get_children())
        for r in rows[-500:][::-1]:  # piu' recenti in alto
            vals = [_fmt_cell(cid, r.get(cid, "")) for cid, _, _ in CSV_VIEW_COLUMNS]
            self.tree.insert("", "end", values=vals)
        self.status.config(text=f"{len(rows)} righe nel CSV")
        self._draw_scatter(self.canvas_acc, rows, x="end_to_end_energy_j", y="causal_accuracy",
                           title="Energia E2E [J] vs Accuratezza causale")
        self._draw_scatter(self.canvas_ece, rows, x="end_to_end_energy_j", y="ece_per_joule",
                           title="Energia E2E [J] vs ECE/J", logx=True)

    @staticmethod
    def _num(v):
        try:
            f = float(v)
            return f if f == f else None
        except (TypeError, ValueError):
            return None

    def _draw_scatter(self, canvas, rows, x, y, title, logx=False):
        canvas.delete("all")
        pts = []
        for r in rows:
            xv, yv = self._num(r.get(x)), self._num(r.get(y))
            if xv is not None and yv is not None and xv > 0:
                pts.append((xv, yv, str(r.get("model_label", ""))[:18]))
        W, H = int(canvas["width"]), int(canvas["height"])
        m = 26
        canvas.create_text(W // 2, 8, text=title, font=("Segoe UI", 8, "bold"))
        if len(pts) < 1:
            canvas.create_text(W // 2, H // 2, text="nessun dato", fill="gray")
            return
        import math

        xs = [math.log10(p[0]) if logx else p[0] for p in pts]
        ys = [p[1] for p in pts]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmax - xmin < 1e-9:
            xmax = xmin + 1
        if ymax - ymin < 1e-9:
            ymax = ymin + 1
        canvas.create_line(m, H - m, W - 6, H - m)
        canvas.create_line(m, 16, m, H - m)
        colors = {"local": "#1f77b4", "cloud": "#d62728"}
        for (xv, yv, lab), lx, ly in zip(pts, xs, ys):
            px = m + (lx - xmin) / (xmax - xmin) * (W - m - 10)
            py = (H - m) - (ly - ymin) / (ymax - ymin) * (H - m - 22)
            mode = "local" if lab.startswith(("llama", "qwen", "phi", "mistral", "gemma")) else None
            canvas.create_oval(px - 3, py - 3, px + 3, py + 3, fill=colors.get(mode or "", "#2ca02c"), outline="")
        fmt = (lambda v: f"{10**v:.3g}") if logx else (lambda v: f"{v:.3g}")
        canvas.create_text(m, H - 10, text=fmt(xmin), anchor="w", font=("Segoe UI", 7))
        canvas.create_text(W - 8, H - 10, text=fmt(xmax), anchor="e", font=("Segoe UI", 7))
        canvas.create_text(m - 4, 18, text=f"{ymax:.3g}", anchor="e", font=("Segoe UI", 7))
        canvas.create_text(m - 4, H - m, text=f"{ymin:.3g}", anchor="e", font=("Segoe UI", 7))

    def open_csv(self):
        try:
            import config

            path = str(config.CSV_RESULTS_PATH)
            if not os.path.exists(path):
                messagebox.showinfo("CasualWatt", "Il CSV non esiste ancora: esegui un benchmark.")
                return
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("CasualWatt", f"Impossibile aprire il CSV: {exc}")

    def export_csv(self):
        try:
            import config

            default = str(config.CSV_RESULTS_PATH)
        except Exception:
            default = "casualwatt_results.csv"
        dst = filedialog.asksaveasfilename(
            title="Esporta CSV", defaultextension=".csv",
            initialfile=os.path.basename(default),
            filetypes=[("CSV", "*.csv")],
        )
        if not dst:
            return
        try:
            import shutil

            src = default
            if os.path.exists(src):
                shutil.copyfile(src, dst)
                messagebox.showinfo("CasualWatt", f"Esportato in:\n{dst}")
            else:
                messagebox.showinfo("CasualWatt", "Nessun CSV da esportare: esegui prima un benchmark.")
        except Exception as exc:
            messagebox.showerror("CasualWatt", f"Esportazione fallita: {exc}")

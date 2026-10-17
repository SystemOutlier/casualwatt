# -*- coding: utf-8 -*-
"""
gui/model_selection.py — Pannello 1: selezione modelli locali e cloud (sez. 4.1).

Due sezioni affiancate con Treeview a selezione multipla:
* Modelli locali Ollama  -> GET /api/tags (nome, dimensione, data modifica);
* Modelli cloud          -> provider configurati (provider | modello);
pulsanti Seleziona/Deseleziona tutti e Ricarica per ciascuna lista.
Le selezioni correnti si leggono con ``get_selected_local()`` /
``get_selected_cloud()``.
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Dict, List


def _human_size(nbytes: int) -> str:
    try:
        x = float(nbytes)
    except Exception:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024 or unit == "TB":
            return f"{x:.1f} {unit}"
        x /= 1024
    return ""


class ModelSelectionPanel(ttk.Frame):
    def __init__(self, master, log=None, **kw):
        super().__init__(master, **kw)
        self.log = log or (lambda m: None)

        # ------------------------- LOCALI -----------------------------------
        left = ttk.LabelFrame(self, text="Modelli locali Ollama")
        left.pack(side="left", fill="both", expand=True, padx=6, pady=4)

        cols = ("name", "size", "modified")
        self.local_tree = ttk.Treeview(left, columns=cols, selectmode="extended", show="headings")
        self.local_tree.heading("name", text="Modello")
        self.local_tree.heading("size", text="Dimensione")
        self.local_tree.heading("modified", text="Ultima modifica")
        self.local_tree.column("name", width=230)
        self.local_tree.column("size", width=90, anchor="e")
        self.local_tree.column("modified", width=150)
        lscroll = ttk.Scrollbar(left, orient="vertical", command=self.local_tree.yview)
        self.local_tree.configure(yscrollcommand=lscroll.set)
        self.local_tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        lscroll.pack(side="right", fill="y")

        lbtns = ttk.Frame(left)
        lbtns.pack(fill="x", pady=3)
        ttk.Button(lbtns, text="Ricarica", command=self.reload_local).pack(side="left", padx=2)
        ttk.Button(lbtns, text="Seleziona tutti", command=lambda: self._select_all(self.local_tree)).pack(side="left", padx=2)
        ttk.Button(lbtns, text="Deseleziona tutti", command=lambda: self._deselect_all(self.local_tree)).pack(side="left", padx=2)
        self.local_status = ttk.Label(left, text="— non caricato —", foreground="gray")
        self.local_status.pack(fill="x", padx=4, pady=(0, 3))

        # ------------------------- CLOUD -------------------------------------
        right = ttk.LabelFrame(self, text="Modelli cloud")
        right.pack(side="left", fill="both", expand=True, padx=6, pady=4)

        ccols = ("provider", "model")
        self.cloud_tree = ttk.Treeview(right, columns=ccols, selectmode="extended", show="headings")
        self.cloud_tree.heading("provider", text="Provider")
        self.cloud_tree.heading("model", text="Modello")
        self.cloud_tree.column("provider", width=110)
        self.cloud_tree.column("model", width=260)
        cscroll = ttk.Scrollbar(right, orient="vertical", command=self.cloud_tree.yview)
        self.cloud_tree.configure(yscrollcommand=cscroll.set)
        self.cloud_tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        cscroll.pack(side="right", fill="y")

        cbtns = ttk.Frame(right)
        cbtns.pack(fill="x", pady=3)
        ttk.Button(cbtns, text="Ricarica", command=self.reload_cloud).pack(side="left", padx=2)
        ttk.Button(cbtns, text="Seleziona tutti", command=lambda: self._select_all(self.cloud_tree)).pack(side="left", padx=2)
        ttk.Button(cbtns, text="Deseleziona tutti", command=lambda: self._deselect_all(self.cloud_tree)).pack(side="left", padx=2)
        self.cloud_status = ttk.Label(right, text="— non caricato —", foreground="gray")
        self.cloud_status.pack(fill="x", padx=4, pady=(0, 3))

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _select_all(tree):
        tree.selection_set(tree.get_children())

    @staticmethod
    def _deselect_all(tree):
        tree.selection_remove(tree.get_children())

    # ---------------------------------------------------------------- reloads
    def reload_local(self):
        self.local_status.config(text="caricamento…", foreground="orange")
        threading.Thread(target=self._fetch_local_worker, daemon=True).start()

    def _fetch_local_worker(self):
        try:
            from benchmark_unified import get_ollama_models

            models = get_ollama_models()
            self.after(0, lambda: self._populate_local(models))
        except Exception as exc:
            self.after(0, lambda e=exc: self.local_status.config(
                text=f"errore: {e}", foreground="red"))

    def _populate_local(self, models: List[Dict]):
        self.local_tree.delete(*self.local_tree.get_children())
        for m in models:
            self.local_tree.insert(
                "",
                "end",
                values=(
                    m.get("name", ""),
                    _human_size(m.get("size", 0)),
                    (m.get("modified_at", "") or "").replace("T", " ")[:19],
                ),
            )
        if models:
            self.local_status.config(
                text=f"{len(models)} modelli trovati ({self._endpoint_hint()})",
                foreground="green",
            )
        else:
            self.local_status.config(
                text=f"nessun modello — Ollama offline su {self._endpoint_hint()}",
                foreground="red",
            )

    @staticmethod
    def _endpoint_hint():
        try:
            import config

            return config.OLLAMA_API_URL
        except Exception:
            return "http://localhost:11434"

    def reload_cloud(self):
        self.cloud_status.config(text="caricamento…", foreground="orange")
        threading.Thread(target=self._fetch_cloud_worker, daemon=True).start()

    def _fetch_cloud_worker(self):
        try:
            from cloud_estimator import get_cloud_models

            models = get_cloud_models()
            self.after(0, lambda: self._populate_cloud(models))
        except Exception as exc:
            self.after(0, lambda e=exc: self.cloud_status.config(
                text=f"errore: {e}", foreground="red"))

    def _populate_cloud(self, models: List[Dict]):
        self.cloud_tree.delete(*self.cloud_tree.get_children())
        for m in models:
            self.cloud_tree.insert("", "end", values=(m.get("provider", ""), m.get("model", "")))
        if models:
            self.cloud_status.config(
                text=f"{len(models)} modelli disponibili", foreground="green")
        else:
            self.cloud_status.config(
                text="nessun modello: imposta GROQ_API_KEY / OPENROUTER_API_KEY / GOOGLE_API_KEY (.env)",
                foreground="red",
            )

    # ------------------------------------------------------------- selections
    def get_selected_local(self) -> List[str]:
        return [self.local_tree.item(iid)["values"][0] for iid in self.local_tree.selection()]

    def get_selected_cloud(self) -> List[Dict]:
        out = []
        for iid in self.cloud_tree.selection():
            v = self.cloud_tree.item(iid)["values"]
            out.append({"provider": str(v[0]), "model": str(v[1])})
        return out

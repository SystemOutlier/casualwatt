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

        # ---- Impostazioni / Chiavi API (sopra il box dei modelli cloud) -----
        # I campi sono oscurati (show="*"): le chiavi restano private.
        # "Salva Chiavi" aggiorna os.environ della sessione + persiste nel file
        # nascosto .casualwatt_keys.json; all'avvio i campi sono auto-populati
        # dallo stesso file (config.load_saved_api_keys).
        keys_frame = ttk.LabelFrame(right, text="Impostazioni / Chiavi API")
        keys_frame.pack(fill="x", padx=4, pady=(4, 2))
        self._key_vars: Dict[str, tk.StringVar] = {}
        _key_fields = (
            ("GROQ_API_KEY", "Groq"),
            ("OPENROUTER_API_KEY", "OpenRouter"),
            ("GOOGLE_API_KEY", "Google"),
            ("ELECTRICITY_MAPS_API_TOKEN", "Electricity Maps"),
        )
        for row, (var, label) in enumerate(_key_fields):
            ttk.Label(keys_frame, text=f"{label}:").grid(
                row=row, column=0, sticky="e", padx=(6, 4), pady=1)
            sv = tk.StringVar()
            ent = ttk.Entry(keys_frame, textvariable=sv, show="*", width=38)
            ent.grid(row=row, column=1, sticky="we", pady=1)
            self._key_vars[var] = sv
        keys_frame.columnconfigure(1, weight=1)

        btn_row = ttk.Frame(keys_frame)
        btn_row.grid(row=len(_key_fields), column=0, columnspan=2, sticky="we", pady=3)
        ttk.Button(btn_row, text="Salva Chiavi", command=self.save_keys).pack(side="left", padx=6)
        self.show_keys_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_row, text="Mostra", variable=self.show_keys_var,
                        command=self._toggle_keys_visibility).pack(side="left", padx=2)
        self.keys_status = ttk.Label(btn_row, text="", foreground="gray")
        self.keys_status.pack(side="left", padx=8)
        self._load_keys_into_fields()

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

    # ------------------------------------------------------------- chiavi API
    def _load_keys_into_fields(self):
        """Auto-popola i campi all'avvio: prima env di sessione, poi file salvato."""
        import os

        try:
            import config

            saved = config.load_saved_api_keys()
        except Exception:
            saved = {}
        for var, sv in self._key_vars.items():
            val = os.getenv(var, "") or saved.get(var, "")
            sv.set(val)
        n = sum(1 for v in self._key_vars.values() if v.get().strip())
        self.keys_status.config(
            text=f"{n} chiave/i caricata/e" if n else "nessuna chiave salvata",
            foreground="gray")

    def _toggle_keys_visibility(self):
        """Checkbutton 'Mostra': rivela/nasconde i caratteri dei campi chiave."""
        show = "" if self.show_keys_var.get() else "*"

        def _walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Entry):
                    child.configure(show=show)
                _walk(child)

        _walk(self)

    def save_keys(self):
        """Pulsante 'Salva Chiavi': aggiorna env + provider + file nascosto."""
        try:
            import config

            keys = {var: sv.get().strip() for var, sv in self._key_vars.items()}
            ok = config.apply_api_keys(keys, persist=True)
            enabled = [
                name for name, cfg in config.CLOUD_PROVIDERS.items()
                if cfg.get("enabled")
            ]
            if ok:
                self.keys_status.config(
                    text="salvate. Provider attivi: " + (", ".join(enabled) or "nessuno"),
                    foreground="green")
                self.log(f"Chiavi API aggiornate (provider abilitati: {enabled or 'nessuno'})")
            else:
                self.keys_status.config(
                    text="applicate alla sessione, salvataggio su file fallito",
                    foreground="orange")
                self.log("Chiavi applicate ma non persistite su file (permessi?)")
        except Exception as exc:
            self.keys_status.config(text=f"errore: {exc}", foreground="red")
            # riga vuota nel campo = rimozione della chiave dall'ambiente
        # ricarica automatica della lista cloud con le nuove chiavi
        self.reload_cloud()

    # ---------------------------------------------------------------- reloads
    def reload_local(self):
        self.local_status.config(text="caricamento…", foreground="orange")
        threading.Thread(target=self._fetch_local_worker, daemon=True).start()

    def _fetch_local_worker(self):
        try:
            from benchmark_unified import get_ollama_models

            models, err = get_ollama_models()
            self.after(0, lambda: self._populate_local(models, err))
        except Exception as exc:
            # errore imprevisto (es. import) -> mostra causa
            self.after(0, lambda e=exc: self.local_status.config(
                text=f"errore: {e}", foreground="red"))

    def _populate_local(self, models: List[Dict], err: str = ""):
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
        elif err:
            # endpoint irraggiungibile / errore di rete: mostra la causa reale
            self.local_status.config(text=f"Ollama offline — {err}", foreground="red")
        else:
            self.local_status.config(
                text=f"nessun modello installato — Ollama online su {self._endpoint_hint()} "
                     f"(usa 'ollama pull ...')",
                foreground="orange",
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

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


class _Tooltip:
    """Tooltip leggero per widget Tkinter (mostra testo al passaggio del mouse)."""

    def __init__(self, widget, text: str, delay_ms: int = 500):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._tipwindow: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event=None):
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self):
        if self._tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify="left", background="#ffffe0",
            relief="solid", borderwidth=1, font=("tahoma", "8", "normal"),
            wraplength=320,
        )
        label.pack(ipadx=4, ipady=2)

    def _hide(self, _event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tipwindow:
            self._tipwindow.destroy()
            self._tipwindow = None

    def update_text(self, text: str):
        self.text = text


class ModelSelectionPanel(ttk.Frame):
    def __init__(self, master, log=None, **kw):
        super().__init__(master, **kw)
        self.log = log or (lambda m: None)

        # ------------------------- LOCALI -----------------------------------
        left = ttk.LabelFrame(self, text="Modelli locali Ollama")
        left.pack(side="left", fill="both", expand=True, padx=6, pady=4)

        cols = ("name", "size", "modified")
        self.local_tree = ttk.Treeview(left, columns=cols, selectmode="extended", show="headings", height=4)
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

        # ---- Provider disponibili nei menu a tendina ------------------------
        # Elenco selezionabile del Combobox (specifica richiesta):
        #   Groq, OpenRouter, Google, OpenAI, Anthropic, Hugging Face,
        #   Electricity Maps.
        # All'avvio le 4 righe preimpostate mostrano Groq, OpenRouter, Google,
        # Electricity Maps (retrocompat con .casualwatt_keys.json); aprendo una
        # tendina l'utente vede l'elenco COMPLETO e puo' cambiare provider.
        _env_by_label = {
            "Groq": "GROQ_API_KEY",
            "OpenRouter": "OPENROUTER_API_KEY",
            "Google": "GOOGLE_API_KEY",
            "OpenAI": "OPENAI_API_KEY",
            "Anthropic": "ANTHROPIC_API_KEY",
            "Hugging Face": "HF_TOKEN",
            "Electricity Maps": "ELECTRICITY_MAPS_API_TOKEN",
        }
        self._provider_names: List[str] = [
            "Groq", "OpenRouter", "Google", "OpenAI", "Anthropic",
            "Hugging Face",
            "Electricity Maps",
        ]
        self._provider_by_label: Dict[str, str] = dict(_env_by_label)
        _default_rows = tuple(
            (lbl, _env_by_label[lbl])
            for lbl in ("Groq", "OpenRouter", "Google", "Electricity Maps")
        )
        _alias = {"Google Gemini": "Google"}          # etichetta storica
        try:
            import config

            for pid, pcfg in config.CLOUD_PROVIDERS.items():
                lbl = _alias.get(pcfg.get("label", pid), pcfg.get("label", pid))
                if lbl not in self._provider_by_label:
                    # provider esteso in config -> aggiungibile dalla tendina
                    self._provider_names.append(lbl)
                # map: label -> variabile d'ambiente del provider
                self._provider_by_label[lbl] = pcfg.get(
                    "api_key_env", _env_by_label.get(lbl, lbl))
        except Exception:
            pass

        # ---- Righe dinamiche: Combobox provider + Entry chiave oscurato -----
        self._key_rows: List[Dict] = []   # {prov_var, key_var, entry, frame}
        self._key_vars: Dict[str, tk.StringVar] = {}  # env -> StringVar (API storica)

        def _make_row(prov_label: str, env_name: str = "", value: str = ""):
            rowf = ttk.Frame(keys_frame)
            idx = len(self._key_rows)
            pv = tk.StringVar(value=prov_label)
            kv = tk.StringVar(value=value)
            # values preso dalla LISTA VIVA: '+ Aggiungi Provider' / estensioni
            # di config.CLOUD_PROVIDERS aggiornano il combobox al volo
            combo = ttk.Combobox(rowf, textvariable=pv,
                                 values=self._provider_names,
                                 state="readonly", width=17)
            combo.pack(side="left", padx=(6, 4))
            ent = ttk.Entry(rowf, textvariable=kv, show="*", width=34)
            ent.pack(side="left", fill="x", expand=True, pady=1)
            delb = ttk.Button(rowf, text="✕", width=3,
                              command=lambda r=rowf: self._remove_key_row(r))
            delb.pack(side="left", padx=4)
            rowf.grid(row=idx, column=0, columnspan=2, sticky="we", pady=1)
            rec = {"prov": pv, "key": kv, "entry": ent, "frame": rowf}
            self._key_rows.append(rec)
            if env_name:
                self._key_vars[env_name] = kv
            return rec

        # exposed as method so '+ Aggiungi Provider' can create dynamic rows
        self._make_key_row = lambda prov_label, env_name="", value="": _make_row(
            prov_label, env_name, value)

        for lbl, env in _default_rows:
            _make_row(lbl, env)
        keys_frame.columnconfigure(0, weight=1)

        add_row = ttk.Frame(keys_frame)
        add_row.grid(row=len(self._key_rows), column=0, columnspan=2, sticky="we", pady=1)
        ttk.Button(add_row, text="+ Aggiungi Provider",
                   command=self._add_key_row).pack(side="left", padx=6)
        ttk.Label(add_row, foreground="gray",
                  text="(righe preimpostate: Groq, OpenRouter, Google, Electricity Maps — "
                       "aggiungi/rimuovi righe per estendere i provider)").pack(side="left", padx=4)

        btn_row = ttk.Frame(keys_frame)
        btn_row.grid(row=len(self._key_rows) + 1, column=0, columnspan=2, sticky="we", pady=3)
        self._keys_frame = keys_frame
        self._keys_addrow = add_row
        self._keys_btnrow = btn_row
        ttk.Button(btn_row, text="Salva Chiavi", command=self.save_keys).pack(side="left", padx=6)
        self.show_keys_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_row, text="Mostra", variable=self.show_keys_var,
                        command=self._toggle_keys_visibility).pack(side="left", padx=2)
        self.keys_status = ttk.Label(btn_row, text="", foreground="gray")
        self.keys_status.pack(side="left", padx=8)
        self._load_keys_into_fields()

        ccols = ("provider", "model")
        self.cloud_tree = ttk.Treeview(right, columns=ccols, selectmode="extended", show="headings", height=4)
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
        # 'Modelli Gratuiti': riordina la lista gia' caricata portando in
        # testa i modelli gratuiti (toggle: una seconda clic riporta l'ordine
        # originale provider/modello senza ricaricare dalle API)
        self._cloud_models_cache: List[Dict] = []
        self._cloud_free_first = False
        self.btn_free_first = ttk.Button(
            cbtns, text="Modelli Gratuiti", command=self.toggle_free_first)
        self.btn_free_first.pack(side="left", padx=2)
        ttk.Button(cbtns, text="Seleziona tutti", command=lambda: self._select_all(self.cloud_tree)).pack(side="left", padx=2)
        ttk.Button(cbtns, text="Deseleziona tutti", command=lambda: self._deselect_all(self.cloud_tree)).pack(side="left", padx=2)
        self.cloud_status = ttk.Label(right, text="— non caricato —", foreground="gray")
        self.cloud_status.pack(fill="x", padx=4, pady=(0, 3))

        # Checkbox filtro EcoLogits (solo modelli con stima energetica nativa)
        filter_frame = ttk.Frame(right)
        filter_frame.pack(fill="x", padx=4, pady=(2, 0))
        self._cloud_ecologits_only = tk.BooleanVar(value=False)
        self.chk_ecologits_only = ttk.Checkbutton(
            filter_frame,
            text="Mostra solo modelli con stima energetica nativa",
            variable=self._cloud_ecologits_only,
            command=self._toggle_ecologits_filter,
        )
        self.chk_ecologits_only.pack(side="left", padx=2)
        _Tooltip(
            self.chk_ecologits_only,
            "CasualWatt utilizza EcoLogits per calcolare l'impronta energetica "
            "reale basata sull'architettura hardware del modello. Se la spunta "
            "è disattivata, per i modelli non supportati verrà usata una stima "
            "analitica di fallback basata sul conteggio dei token di input e output.",
        )

    # ------------------------------------------------------- righe dinamiche
    def _add_key_row(self):
        """'+ Aggiungi Provider': nuova riga Combobox + Entry vuota."""
        try:
            import config

            config._reconfigure_grid  # noqa (solo check modulo presente)
        except Exception:
            pass
        first_free = next(
            (lbl for lbl in self._provider_names
             if all(r["prov"].get() != lbl for r in self._key_rows)),
            self._provider_names[0] if self._provider_names else "Groq")
        _make = getattr(self, "_make_key_row", None)
        if _make is not None:
            _make(first_free)
        self._relayout_keys_frame()

    def _remove_key_row(self, rowf):
        for rec in list(self._key_rows):
            if rec["frame"] is rowf:
                self._key_rows.remove(rec)
                break
        rowf.destroy()
        self._relayout_keys_frame()

    def _relayout_keys_frame(self):
        """Rigridda le righe dopo add/remove (indici contigui)."""
        try:
            keys_frame = self._keys_frame
            for i, rec in enumerate(self._key_rows):
                rec["frame"].grid_configure(row=i)
            self._keys_addrow.grid_configure(row=len(self._key_rows))
            self._keys_btnrow.grid_configure(row=len(self._key_rows) + 1)
        except Exception:
            pass

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _select_all(tree):
        tree.selection_set(tree.get_children())

    @staticmethod
    def _deselect_all(tree):
        tree.selection_remove(tree.get_children())

    # ------------------------------------------------------------- chiavi API
    def _collect_keys(self) -> Dict[str, str]:
        """Raccoglie {env_name: chiave} da TUTTE le righe correnti.

        Le quattro righe preimpostate mappano sulle variabili storiche
        (retrocompat con .casualwatt_keys.json); le righe aggiunte dinamicamente
        risolvono il provider dal Combobox tramite _provider_by_label.
        Chiavi vuote = rimozione; duplicati provider -> prima non vuota.
        """
        keys: Dict[str, str] = {}
        for rec in self._key_rows:
            lbl = rec["prov"].get().strip()
            env = self._provider_by_label.get(lbl, "")
            if not env:
                continue
            val = rec["key"].get().strip()
            if val or env not in keys:
                keys[env] = val
        return keys

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
        """Pulsante 'Salva Chiavi': aggiorna env + provider + file nascosto.

        Le chiavi sono raccolte da tutte le righe (preimpostate e dinamiche);
        il formato del file .casualwatt_keys.json resta quello storico
        {ENV_NAME: chiave} -> piena retrocompatibilita' con i salvataggi
        esistenti, che vengono anche fusi per non perdere eventuali chiavi di
        provider rimossi temporaneamente dal pannello.
        """
        try:
            import config

            keys = self._collect_keys()
            try:
                saved = config.load_saved_api_keys() or {}
                for k, v in saved.items():
                    if k not in keys and v:
                        keys[k] = v  # conserva chiavi di provider non esposti
            except Exception:
                pass
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
        # cache per il riordino 'Modelli Gratuiti' senza ricaricare le API
        self._cloud_models_cache = list(models)
        self._render_cloud_tree(self._cloud_sorted())
        if models:
            n_free = sum(1 for m in models if m.get("free"))
            self.cloud_status.config(
                text=f"{len(models)} modelli disponibili"
                     + (f" ({n_free} gratuiti)" if n_free else ""),
                foreground="green")
        else:
            self.cloud_status.config(
                text="nessun modello: imposta GROQ_API_KEY / OPENROUTER_API_KEY / GOOGLE_API_KEY (.env)",
                foreground="red",
            )

    def _cloud_sorted(self) -> List[Dict]:
        """Lista cloud nell'ordine corrente (free-first se toggle attivo, filtro EcoLogits se attivo)."""
        models = list(self._cloud_models_cache)
        # filtro EcoLogits: solo modelli con stima energetica nativa
        if self._cloud_ecologits_only.get():
            models = [m for m in models if m.get("has_ecologits")]
        if self._cloud_free_first:
            # gratuiti prima, poi il resto; stabile entro i due gruppi
            models.sort(key=lambda m: 0 if m.get("free") else 1)
        return models

    def _render_cloud_tree(self, models: List[Dict]):
        sel_before = {tuple(self.cloud_tree.item(i)["values"])
                      for i in self.cloud_tree.selection()}
        self.cloud_tree.delete(*self.cloud_tree.get_children())
        new_ids = []
        for m in models:
            # colonna 'model': solo nome + tag visivo (il provider ha la sua
            # colonna; il prefisso 'provider |' della label e' scartato per
            # non sporcare l'ID che viene riletto in get_selected_cloud)
            name = str(m.get("model", ""))
            if m.get("free") and "[Gratuito]" not in name:
                name += " [Gratuito]"
            # badge EcoLogits: stima nativa vs analitica
            if m.get("has_ecologits"):
                name += " [EcoLogits ✅]"
            else:
                name += " [Stima Analitica ⚠️]"
            iid = self.cloud_tree.insert(
                "", "end", values=(m.get("provider", ""), name))
            if (m.get("provider", ""), name) in sel_before:
                new_ids.append(iid)
        # conserva la selezione dell'utente attraverso il riordino
        if new_ids:
            self.cloud_tree.selection_set(new_ids)

    def toggle_free_first(self):
        """Pulsante 'Modelli Gratuiti': porta i gratuiti in cima alla lista."""
        if not self._cloud_models_cache:
            self.cloud_status.config(
                text="carica prima i modelli con 'Ricarica'", foreground="orange")
            return
        self._cloud_free_first = not self._cloud_free_first
        try:
            self.btn_free_first.config(
                text="Ordine originale" if self._cloud_free_first
                else "Modelli Gratuiti")
        except Exception:
            pass
        self._render_cloud_tree(self._cloud_sorted())

    def _toggle_ecologits_filter(self):
        """Checkbox 'Mostra solo modelli con stima energetica nativa': filtra la lista."""
        self._render_cloud_tree(self._cloud_sorted())

    # ------------------------------------------------------------- selections
    def get_selected_local(self) -> List[str]:
        return [self.local_tree.item(iid)["values"][0] for iid in self.local_tree.selection()]

    def get_selected_cloud(self) -> List[Dict]:
        """Ritorna i modelli selezionati con ID pulito (senza tag visivi).

        Il tag e' solo visivo nella colonna label; l'ID inviato al provider
        deve essere quello nudo restituito dal fetch (altrimenti 404).
        """
        out = []
        for iid in self.cloud_tree.selection():
            v = self.cloud_tree.item(iid)["values"]
            model = str(v[1])
            # rimuovi tutti i tag visivi
            for tag in ("[Gratuito]", "[EcoLogits ✅]", "[Stima Analitica ⚠️]"):
                model = model.replace(tag, "")
            model = model.strip()
            out.append({"provider": str(v[0]), "model": model})
        return out

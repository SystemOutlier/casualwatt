"""Sonda della deriva dei fattori EcoLogits fra release (26-10-2026).

Perche' esiste
--------------
La specifica `experiment_results/metodi_per_dominio_20261025_spec.md` (D12, §6)
afferma che due righe cloud prodotte da versioni diverse del motore EcoLogits
**non sono la stessa misura**, ma fino a oggi rifiutava di scrivere un numero:
nessuno aveva controllato *cosa* si muove fra due release. Questo probe chiude
quella verifica obbliga e lo fa in un modo solo: tiene fissa la formula e muove
solamente i dati del registro.

Che cosa verifica, alla fonte
-----------------------------
1. che il **codice** di stima sia identico fra le due release (hash SHA-256 di
   `ecologits/impacts/llm.py` e `ecologits/tracers/utils.py` dell'installazione
   contro la stessa entry all'interno del wheel della release target). Se il
   codice differsse, il confronto dei numeri non isolerebbe i fattori;
2. che i **dati** del registro differiscano: numero di modelli registrati,
   modelli presenti in una sola release, modelli comuni con contenuto diverso;
3. quale **campo** si muove (su `openai/gpt-4o-mini` e' `deployment`, da cui
   deriva la soglia del clamp `gpu_latency = n_out/tps + ttft`, impacts/llm.py:97-99);
4. l'effetto numerico sul **plateau**: la stessa chiamata, con gli stessi input e
   gli stessi fattori di mix/ambiente, calcolata con i `tps`/`ttft` delle due
   release. Il rapporto fra i due numeri e' la deriva del fattore, non una
   percentuale di accuratezza.

Uso
---
    python probe_ecologits_release_drift_20261026.py [wheel.odl.tar.gz]

Senza argomento cerca il wheel della release target nella cache temporanea e, se
manca, lo scarica con `pip download --no-deps` (serve rete; nessuna credenziale,
nessuna chiamata ai provider). Con argomento usa il wheel indicato.

Il probe NON tocca il codice di produzione, non apre i contatori EMI, non scrive
fuori dalla directory di lavoro se non il proprio output quando rediretto.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile

TARGET_VERSION = os.environ.get("CW_ECO_TARGET", "0.11.3")
# Il modello su cui la sonda del clamp ha gia' lavorato (probe_ecologits_clamp).
PROBE_MODEL = ("openai", "gpt-4o-mini")
OUTPUT_TOKENS = 32
REQUEST_LATENCY_S = 8.0  # sopra la soglia di entrambe le release: clamp vincolato


def _installed_pkg_dir() -> str:
    import ecologits

    return os.path.dirname(ecologits.__file__)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wheel_path() -> str:
    """Wheel della release target: da argv, dalla cache nota, o via pip download."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    cache = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
                         "Temp", "eco3113")
    os.makedirs(cache, exist_ok=True)
    hits = [f for f in os.listdir(cache) if f.startswith(f"ecologits-{TARGET_VERSION}")]
    if hits:
        return os.path.join(cache, hits[0])
    subprocess.run([sys.executable, "-m", "pip", "download",
                    f"ecologits=={TARGET_VERSION}", "--no-deps", "-q", "-d", cache],
                   check=True)
    hits = [f for f in os.listdir(cache) if f.startswith(f"ecologits-{TARGET_VERSION}")]
    if not hits:
        raise SystemExit(f"wheel {TARGET_VERSION} non trovato dopo il download")
    return os.path.join(cache, hits[0])


def _num(x):
    """ValueOrRange -> valore mediano, come fa il motore quando non vuole range."""
    if isinstance(x, dict) and "min" in x and "max" in x:
        return (x["min"] + x["max"]) / 2.0
    return x


def _find(models_json: dict, provider: str, name: str):
    for m in models_json.get("models", []):
        if m.get("provider") == provider and m.get("name") == name:
            return m
    return None


def main() -> int:
    import ecologits
    from ecologits.impacts.llm import compute_llm_impacts

    pkg = _installed_pkg_dir()
    whl = _wheel_path()
    zf = zipfile.ZipFile(whl)

    print("=== 1. il codice di stima e' lo stesso? ===")
    print(f"installazione: ecologits {ecologits.__version__}  |  target: {TARGET_VERSION}")
    print(f"wheel: {whl}")
    stessi = True
    for rel in ("impacts/llm.py", "tracers/utils.py", "model_repository.py",
                "_ecologits.py", "data/electricity_mixes.json"):
        a = open(os.path.join(pkg, rel.replace("/", os.sep)), "rb").read()
        b = zf.read(f"ecologits/{rel}")
        ok = a == b
        stessi &= ok
        print(f"  {rel:32s} {'IDENTICO' if ok else 'DIVERSO'}"
              f"  {len(a)} -> {len(b)} byte")

    print("\n=== 2. che cosa muove il registro dei modelli ===")
    cur = json.load(open(os.path.join(pkg, "data", "models.json"), encoding="utf-8"))
    new = json.load(zf.open("ecologits/data/models.json"))

    def index(d):
        out = {}
        for m in d.get("models", []):
            out[(m.get("provider"), m.get("name"))] = m
        return out

    ic, in_ = index(cur), index(new)
    print(f"  modelli installati ({ecologits.__version__}): {len(ic)}")
    print(f"  modelli release {TARGET_VERSION}: {len(in_)}")
    print(f"  presenti solo nell'installazione: {len(set(ic) - set(in_))}")
    print(f"  presenti solo nella release target: {len(set(in_) - set(ic))}")
    diversi = [k for k in set(ic) & set(in_) if ic[k] != in_[k]]
    print(f"  modelli comuni con contenuto DIVERSO: {len(diversi)}"
          f"  (su {len(set(ic) & set(in_))} comuni)")

    print("\n=== 3. il campo che si muove, sul modello della sonda ===")
    mc, mn = _find(cur, *PROBE_MODEL), _find(new, *PROBE_MODEL)
    if mc is None or mn is None:
        print("  modello non registrato in una delle due release: niente confronto")
        return 1
    for tag, m in ((ecologits.__version__, mc), (TARGET_VERSION, mn)):
        dep = m.get("deployment") or {}
        thr = (OUTPUT_TOKENS / dep["tps"] + dep["ttft"]) if dep.get("tps") else None
        print(f"  {tag}: deployment={dep}  soglia n_out/tps+ttft={thr:.4f}s"
              if thr else f"  {tag}: deployment={dep}  soglia=None")

    print("\n=== 4. la stessa chiamata con i due registri (formula fissa) ===")
    if not stessi:
        print("  AVVERTENZA: il codice differisce, il rapporto non e' solo deriva dei fattori")
    res = {}
    for tag, m in ((ecologits.__version__, mc), (TARGET_VERSION, mn)):
        arch = m.get("architecture") or {}
        par = arch.get("parameters") or {}
        dep = m.get("deployment") or {}
        r = compute_llm_impacts(
            model_active_parameter_count=_num(par.get("active", par)),
            model_total_parameter_count=_num(par.get("total", par)),
            output_token_count=OUTPUT_TOKENS,
            request_latency=REQUEST_LATENCY_S,
            if_electricity_mix_adpe=1.0, if_electricity_mix_pe=1.0,
            if_electricity_mix_gwp=1.0, if_electricity_mix_wue=1.0,
            datacenter_pue=1.0, datacenter_wue=1.0,
            tps=dep.get("tps"), ttft=dep.get("ttft"))
        e = r.energy
        val = float(getattr(e, "value", None)) if getattr(e, "value", None) is not None \
            else (_num({"min": e.min, "max": e.max}) if hasattr(e, "min") else None)
        res[tag] = val
        print(f"  {tag}: energy = {val:.12e} kWh"
              f"  (request_latency={REQUEST_LATENCY_S}s > soglia: plateau)")
    (k0, v0), (k1, v1) = list(res.items())
    print(f"  rapporto {k1}/{k0} = {v1 / v0:.6f}"
          f"  -> variazione {100.0 * (v1 / v0 - 1.0):+.2f}%")
    print("\nLettura: con la formula identica e il miscelamento elettrico fissato a 1")
    print("(quindi fuori dal confronto), la differenza e' solo nei dati del registro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

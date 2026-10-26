# -*- coding: utf-8 -*-
"""CasualWatt - sonda multi-piattaforma dei metodi di misura dell'energia.
Solo lettura, nessun amministratore richiesto (dove serve, lo segnala).
Uso:  python cw_probe.py        ->  stampa il riepilogo e salva cw_probe_<sistema>.json
Non invia nulla in rete (tranne la richiesta locale a Ollama, se presente)."""
import glob, json, os, platform, subprocess, sys, time, urllib.request

R = {"python": sys.version.split()[0], "os": platform.system(), "release": platform.release(),
     "machine": platform.machine(), "colab": ("google.colab" in sys.modules) or bool(os.environ.get("COLAB_RELEASE_TAG")) or os.path.isdir("/content")}


def sh(cmd, timeout=8):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=isinstance(cmd, str))
        return (p.stdout or "").strip()
    except Exception as e:
        return ""


def rd(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except PermissionError:
        return "PERMISSION_DENIED"
    except Exception:
        return None


# ---------------- CPU e virtualizzazione ----------------
def probe_cpu_and_virt():
    o = {}
    if R["os"] == "Linux":
        info = rd("/proc/cpuinfo") or ""
        o["cpu"] = next((l.split(":", 1)[1].strip() for l in info.splitlines() if l.startswith("model name")), None)
        o["hypervisor_flag"] = any("hypervisor" in l for l in info.splitlines() if l.startswith("flags"))
        o["systemd_detect_virt"] = sh("systemd-detect-virt") or None
        o["dmi_product"] = rd("/sys/class/dmi/id/product_name")
        o["wsl"] = "microsoft" in (platform.release() or "").lower()
    elif R["os"] == "Windows":
        o["cpu"] = platform.processor()
        out = sh(["powershell", "-NoProfile", "-Command",
                  "Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,HypervisorPresent | ConvertTo-Json"], 15)
        try:
            d = json.loads(out); o.update({"manufacturer": d.get("Manufacturer"), "model": d.get("Model"),
                                           "hypervisor_present": d.get("HypervisorPresent")})
        except Exception:
            o["model"] = None
        m = (o.get("model") or "").lower() + " " + (o.get("manufacturer") or "").lower()
        o["vm_by_model_string"] = any(k in m for k in ("virtual", "vmware", "kvm", "qemu", "vbox", "xen"))
        o["note"] = "hypervisor_present e' True anche su PC fisici con Hyper-V/WSL2: non indica una VM da solo"
    elif R["os"] == "Darwin":
        o["cpu"] = sh("sysctl -n machdep.cpu.brand_string") or platform.processor()
        o["sw_vers"] = sh("sw_vers -productVersion")
    return o


# ---------------- Windows: EMI ----------------
def probe_emi():
    o = {"applicable": R["os"] == "Windows"}
    if not o["applicable"]:
        return o
    try:
        from codecarbon.core import windows_emi as w
    except Exception as e:
        o["available"] = None
        o["error"] = f"codecarbon >= 3.3 non installato o senza windows_emi ({type(e).__name__})"
        return o
    try:
        o["available"] = bool(w.is_emi_available())
        paths = w.list_emi_device_paths()
        o["devices"] = len(paths)
        if not paths:
            return o
        p = paths[0]
        names = w._read_device_channels(p)
        o["channels"] = names
        a = w._read_device_measurements(p, len(names)); t0 = time.perf_counter(); time.sleep(2.0)
        b = w._read_device_measurements(p, len(names)); wall = time.perf_counter() - t0
        o["power_w_by_channel"] = {}
        for n, (e0, ts0), (e1, ts1) in zip(names, a, b):
            dt = (ts1 - ts0) * 1e-7
            o["power_w_by_channel"][n] = round((e1 - e0) * 3.6e-9 / dt, 3) if dt > 0 else None
        o["monotonic"] = all(e1 >= e0 for (e0, _), (e1, _) in zip(a, b))
    except Exception as e:
        o["available"] = False
        o["error"] = f"{type(e).__name__}: {e}"
    return o


# ---------------- Linux: powercap / RAPL ----------------
def probe_rapl():
    o = {"applicable": R["os"] == "Linux"}
    if not o["applicable"]:
        return o
    base = "/sys/class/powercap"
    o["powercap_dir"] = os.path.isdir(base)
    zones = []
    for z in sorted(glob.glob(base + "/*rapl*")):
        e = rd(z + "/energy_uj")
        if e is None:
            continue
        zones.append({"zone": os.path.basename(z), "name": rd(z + "/name"),
                      "readable": e != "PERMISSION_DENIED", "max_range_uj": rd(z + "/max_energy_range_uj"),
                      "_e0": e})
    o["zones"] = zones
    if zones and any(z["readable"] for z in zones):
        time.sleep(1.0)
        for z in zones:
            if z["readable"]:
                e1 = rd(f"{base}/{z['zone']}/energy_uj")
                try:
                    d = int(e1) - int(z["_e0"])
                    if d < 0 and z["max_range_uj"]:
                        d += int(z["max_range_uj"])
                    z["power_w_1s"] = round(d / 1e6, 3)
                except Exception:
                    z["power_w_1s"] = None
    for z in zones:
        z.pop("_e0", None)
    o["hint"] = ("Se 'readable' e' False: lettura limitata a root nei kernel recenti; "
                 "serve sudo o un permesso esplicito, non e' un errore del programma." )
    return o


# ---------------- GPU: NVML e AMD SMI ----------------
def probe_nvml():
    o = {}
    try:
        import pynvml
    except Exception:
        o["available"] = None
        o["error"] = "pynvml/nvidia-ml-py non installato"
        return o
    try:
        pynvml.nvmlInit()
        o["available"] = True
        o["driver"] = str(pynvml.nvmlSystemGetDriverVersion())
        n = pynvml.nvmlDeviceGetCount(); o["devices"] = []
        for i in range(n):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            d = {"index": i, "name": str(pynvml.nvmlDeviceGetName(h))}
            try:
                e0 = pynvml.nvmlDeviceGetTotalEnergyConsumption(h); time.sleep(2.0)
                e1 = pynvml.nvmlDeviceGetTotalEnergyConsumption(h)
                d["energy_counter"] = True; d["power_w_from_counter"] = round((e1 - e0) / 1000.0 / 2.0, 2)
            except Exception as e:
                d["energy_counter"] = False; d["energy_counter_error"] = type(e).__name__
            try:
                d["power_usage_w"] = pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0
            except Exception:
                d["power_usage_w"] = None
            try:
                pynvml.nvmlDeviceGetProcessUtilization(h, 0); d["per_process_util"] = True
            except Exception as e:
                d["per_process_util"] = False; d["per_process_util_error"] = type(e).__name__
            o["devices"].append(d)
    except Exception as e:
        o["available"] = False
        o["error"] = f"{type(e).__name__}: {e}"
    return o


def probe_amd_gpu():
    try:
        import amdsmi  # noqa
        return {"available": True, "note": "amdsmi importabile: verificare amdsmi_get_energy_count (ROCm >= 6.1, Linux bare metal)"}
    except Exception:
        return {"available": None, "note": "amdsmi non installato (normale se non c'e' GPU AMD)"}


# ---------------- macOS ----------------
def probe_mac():
    if R["os"] != "Darwin":
        return {"applicable": False}
    return {"applicable": True, "powermetrics_present": bool(sh("which powermetrics")),
            "root": os.geteuid() == 0, "note": "powermetrics richiede root"}


# ---------------- Ollama ----------------
def probe_ollama():
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
    url = host if host.startswith("http") else "http://" + host
    local = any(h in url for h in ("127.0.0.1", "localhost", "[::1]", "0.0.0.0"))
    o = {"host": url, "is_local": local}
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/version", timeout=2) as r:
            o["version"] = json.loads(r.read().decode()).get("version")
    except Exception as e:
        o["version"] = None; o["reachable"] = False
    if not local:
        o["warning"] = "endpoint Ollama NON locale: l'energia misurata qui non e' quella dell'inferenza"
    return o


def main():
    R["cpu_virt"] = probe_cpu_and_virt()
    R["emi"] = probe_emi()
    R["rapl"] = probe_rapl()
    R["nvml"] = probe_nvml()
    R["amd_gpu"] = probe_amd_gpu()
    R["mac"] = probe_mac()
    R["ollama"] = probe_ollama()

    print("=== CasualWatt: sonda dei metodi di misura ===")
    print(f"Sistema: {R['os']} {R['release']} ({R['machine']}), Python {R['python']}, Colab: {R['colab']}")
    cv = R["cpu_virt"]
    print(f"CPU: {cv.get('cpu')} | VM? flag={cv.get('hypervisor_flag')} virt={cv.get('systemd_detect_virt')} "
          f"modello={cv.get('model') or cv.get('dmi_product')} wsl={cv.get('wsl')}")
    e = R["emi"]
    if e.get("applicable"):
        print(f"EMI (Windows): disponibile={e.get('available')} canali={e.get('channels')} potenza W={e.get('power_w_by_channel')} {e.get('error','')}")
    rp = R["rapl"]
    if rp.get("applicable"):
        print(f"RAPL (Linux): powercap={rp.get('powercap_dir')} zone={[ (z['zone'], z['name'], z['readable'], z.get('power_w_1s')) for z in rp.get('zones', [])]}")
    nv = R["nvml"]
    print(f"NVML: disponibile={nv.get('available')} {nv.get('error','')}")
    for d in nv.get("devices", []):
        print(f"   GPU{d['index']} {d['name']}: contatore energia={d.get('energy_counter')} "
              f"potenza dal contatore={d.get('power_w_from_counter')} W; per-processo={d.get('per_process_util')}")
    print(f"AMD SMI: {R['amd_gpu']['note']}")
    if R["mac"].get("applicable"):
        print(f"macOS: {R['mac']}")
    print(f"Ollama: {R['ollama']}")
    name = f"cw_probe_{R['os'].lower()}{'_colab' if R['colab'] else ''}.json"
    with open(name, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(f"\nSalvato: {name} (contiene solo i dati sopra, nessun nome host).")


if __name__ == "__main__":
    main()

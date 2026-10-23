#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_handoff.py — pacchetto i sorgenti di cpuepower2 + il brief per il coder.

Include i file sorgente (.py, README.md, pyproject.toml, requirements.txt) e le
DLL LHM necessarie al task T3 (niente .git, niente __pycache__). Serve per dare
al coder IL codice reale su cui stiamo lavorando (copia unica:
CWProject/cpuepower2), perche' i path che ha citato lui (backends/lhm_backend.py
ecc.) non esistono nel repo.
"""
from __future__ import annotations

import datetime
import zipfile
from pathlib import Path

SRC = Path(r"C:\Users\Massimo\Documents\CasualWatt\CWProject\cpuepower2")
OUT = Path(r"C:\Users\Massimo\Documents\CasualWatt\CWProject\handoff")
INCLUDE_DIRS = ["cpuepower", "tests", "examples"]
INCLUDE_FILES = ["README.md", "pyproject.toml", "requirements.txt"]
#: T3 (backend LHM) non e' riproducibile senza l'assembly + le sue dipendenze.
INCLUDE_BINARIES = [
    "LibreHardwareMonitorLib.dll",
    "HidSharp.dll",
    "Microsoft.Win32.TaskScheduler.dll",
]
BRIEF = SRC.parent / "handoff" / "BRIEF_CODER.md"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    zpath = OUT / f"cpuepower2_handoff_{ts}.zip"
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in INCLUDE_FILES:
            p = SRC / f
            if p.exists():
                z.write(p, f"cpuepower2/{f}")
                n += 1
        for d in INCLUDE_DIRS:
            for p in sorted((SRC / d).rglob("*.py")):
                if "__pycache__" in p.parts:
                    continue
                z.write(p, "cpuepower2/" + str(p.relative_to(SRC)).replace("\\", "/"))
                n += 1
        for f in INCLUDE_BINARIES:
            p = SRC / f
            if p.exists():
                z.write(p, f"cpuepower2/dll/{f}")
                n += 1
        if BRIEF.exists():
            z.write(BRIEF, "BRIEF_CODER.md")
            n += 1
    print(f"[OK] {zpath}  ({n} file, {zpath.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

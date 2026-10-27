# -*- coding: utf-8 -*-
"""Scarica, verifica ed estrae i moduli PawnIO ammessi (release pinnata).

Il backend ``energy/pawnio_backend.py`` carica solo i moduli della release
``0.2.11`` con SHA-256 pinnato: un blob diverso non e' stato verificato da
nessuno e non si usa. Questo strumento e' l'unico modo previsto per procurarsi
quei blob, e li verifica DUE volte — lo zip alla fonte e ogni modulo dopo
l'estrazione — perche' una verifica sola sull'archivio non dice cosa e' finito
sul disco.

Il binario non sta nel repository: la destinazione predefinita e' la cache
dichiarata ``%LOCALAPPDATA%\\CasualWatt\\pawnio-modules\\0.2.11``, fuori da git.
Con ``--install`` i moduli vengono copiati anche nella cartella di installazione
di PawnIO (richiede privilegi di amministratore).

Uso:
    python cwEnergyModular/tools/fetch_pawnio_modules.py            # cache
    python cwEnergyModular/tools/fetch_pawnio_modules.py --install  # + install
    python cwEnergyModular/tools/fetch_pawnio_modules.py --check DIR

Licenza dei moduli: LGPL-2.1-or-later (``COPYING`` nella release, estratto
accanto ai ``.bin``).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy.pawnio_backend import (  # noqa: E402
    MODULE_SHA256, MODULES_VERSION, MODULES_ZIP_SHA256, default_modules_dir,
)

URL = (
    "https://github.com/namazso/PawnIO.Modules/releases/download/"
    f"{MODULES_VERSION}/release_{MODULES_VERSION.replace('.', '_')}.zip"
)
WANTED = tuple(MODULE_SHA256) + ("COPYING",)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str = URL, timeout: float = 60.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def extract(blob: bytes, dest: Path) -> None:
    """Estrae SOLO i moduli del backend e la licenza, dopo il controllo degli hash."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
        missing = [n for n in WANTED if n not in names]
        if missing:
            raise SystemExit(f"archivio incompleto: mancano {missing}")
        for name in WANTED:
            data = zf.read(name)
            if name in MODULE_SHA256:
                got = sha256_bytes(data)
                if got != MODULE_SHA256[name]:
                    raise SystemExit(
                        f"{name}: SHA-256 {got} diverso dal blob verificato "
                        f"{MODULE_SHA256[name]}: non si estrae")
            (dest / name).write_bytes(data)


def check(directory: Path) -> list:
    """Esito della verifica dei moduli presenti in ``directory``."""
    out = []
    for name, want in MODULE_SHA256.items():
        path = directory / name
        if not path.is_file():
            out.append((name, "assente", want))
            continue
        got = sha256_bytes(path.read_bytes())
        out.append((name, "ok" if got == want else f"diverso ({got})", want))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", type=Path, default=None,
                    help="cartella di destinazione (default: cache dichiarata)")
    ap.add_argument("--install", action="store_true",
                    help="copia anche in %%ProgramFiles%%\\PawnIO\\modules")
    ap.add_argument("--check", type=Path, default=None,
                    help="verifica una cartella senza scaricare nulla")
    ap.add_argument("--url", default=URL)
    args = ap.parse_args(argv)

    if args.check is not None:
        bad = 0
        for name, status, want in check(args.check):
            print(f"{name}: {status}\n  atteso {want}")
            bad += 0 if status == "ok" else 1
        return 0 if not bad else 1

    dest = args.dest or default_modules_dir()
    print(f"release {MODULES_VERSION}: {args.url}")
    blob = download(args.url)
    got = sha256_bytes(blob)
    print(f"zip SHA-256 {got}")
    if got != MODULES_ZIP_SHA256:
        print(f"ATTESO {MODULES_ZIP_SHA256}: archivio non ammesso, non estraggo")
        return 2
    extract(blob, dest)
    print(f"estratto in {dest}")
    for name, status, _want in check(dest):
        print(f"  {name}: {status}")
        if status != "ok":
            return 3

    if args.install:
        target = (Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                  / "PawnIO" / "modules")
        target.mkdir(parents=True, exist_ok=True)
        for name in WANTED:
            shutil.copy2(dest / name, target / name)
        print(f"copiato in {target}")
        for name, status, _want in check(target):
            print(f"  {name}: {status}")
            if status != "ok":
                return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

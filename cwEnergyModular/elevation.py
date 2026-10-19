# -*- coding: utf-8 -*-
"""
elevation.py — Supporto UAC (Windows) per i privilegi di amministratore.

LibreHardwareMonitor richiede un token con privilegi elevati per aprire i
driver dei sensori hardware (Energy-CPU, etc.). Questo modulo offre:

  * is_admin()            -> True se il processo corrente e' gia' elevato;
  * elevate_available()   -> True se la ri-elevazione e' possibile su SO;
  * relaunch_as_admin()   -> riavvia l'applicazione tramite ShellExecuteW
                             con verbo "runas" (prompt UAC).

Su piattaforme non-Windows tutte le funzioni degradano silenziosamente
(is_admin -> False/True a seconda dei privilegi unix, elevate_available
-> False), in coerenza con la filosofia agnostica del framework.
"""
from __future__ import annotations

import ctypes
import os
import sys
from typing import List, Optional


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def is_admin() -> bool:
    """True se il processo corrente ha privilegi amministrativi."""
    if not _is_windows():
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            return False
    try:
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        # E_OK==1 => elevato; qualunque errore => non elevato
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_available() -> bool:
    """La richiesta di elevazione UAC e' supportata su questo SO?"""
    return _is_windows()


def build_command(argv: Optional[List[str]] = None) -> Optional[List[str]]:
    """Costruisce ['executable', 'arg1', ...] per rilanciare l'app.

    - script (.py in esecuzione): usa lo stesso interpretatore Python;
    - eseguibile congelato (PyInstaller ecc.): usa sys.executable as-is.
    Gli argomenti della riga corrente vengono preservati.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    exe = sys.executable
    if not exe:
        return None
    frozen = getattr(sys, "frozen", False)
    if frozen:
        return [exe] + args
    script = sys.argv[0] if sys.argv else ""
    if not script:
        return None
    if not os.path.isabs(script):
        script = os.path.abspath(script)
    return [exe, f'"{script}"'] + args


def relaunch_as_admin(argv: Optional[List[str]] = None) -> int:
    """Riavvia il processo corrente come amministratore (prompt UAC).

    Ritorna l'handle (>0) del nuovo processo in caso di successo;
    ritorna -1 se l'operazione non e' supportata o e' fallita
    (es. utente annulla il prompt UAC: ShellExecuteW restituisce <=3).
    NON termina il processo chiamante: decide la GUI se chiudere.
    """
    if not _is_windows():
        return -1
    cmd = build_command(argv)
    if not cmd:
        return -1
    try:
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        # ShellExecuteW(hwnd, verb, file, parameters, directory, show)
        hinstance = shell32.ShellExecuteW(
            None,           # hwnd owner
            "runas",        # verbo: richiedi elevazione UAC
            cmd[0],         # eseguibile (python.exe / exe congelato)
            " ".join(cmd[1:]),  # parametri (script + argv)
            os.path.dirname(os.path.abspath(sys.argv[0])) or None,  # cwd progetto
            1,              # SW_SHOWNORMAL
        )
        # ShellExecuteW restituisce un handle >32 in caso di successo;
        # valori <=32 sono codici di errore DDE/SE_* (SE_ERR_ABORTED=1 se
        # l'utente annulla il prompt UAC).
        return int(hinstance) if int(hinstance) > 32 else -1
    except Exception:
        return -1

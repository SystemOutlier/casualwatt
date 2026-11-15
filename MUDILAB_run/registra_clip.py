"""Registra lo schermo con ffmpeg (gdigrab) mentre gira un comando, e chiude il file.

Nato per la clip delle query controfattuali: `--cmd demo_controfattuali.py` riprende
il terminale dal primo all'ultimo passo e scrive un mp4 accanto al log della demo.

Perche' un script e non `Win+G`: la chiusura di Game Bar non e' pilotabile da riga di
comando e una clip interrotta a meta' non e' utilizzabile. Qui ffmpeg riceve `q` su
stdin alla fine del comando (o a Ctrl+C), che e' il modo documentato di fermare
gdigrab Finalizzando il contenitore: un mp4 scritto con SIGKILL resta corrotto.

Cattura l'intero desktop, senza microfono. La durata massima di default (20 minuti) e'
una guardia: se il comando si blocca, la registrazione finisce comunque. Con il blocco 0
della demo lo schermo non resta sul terminale: `demo_controfattuali.py` apre Jupyter Lab
sul notebook della relatrice e il browser prende il foreground da solo, quindi il filmato
passa dal terminale alla sua pagina e ritorno senza che nessuno prema Registra.

Uso:
    python registra_clip.py --cmd demo_controfattuali.py
    python registra_clip.py --cmd "demo_controfattuali.py --blocco 1" --fps 10
    python registra_clip.py --cmd "demo_controfattuali.py --pausa 8" --lead 6
    python registra_clip.py --senza-video --cmd demo_controfattuali.py   # prova a secco
"""

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "harness" / "risultati"


def ffprobe_durata(file: Path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration", "-of", "csv=p=0", str(file)],
                             capture_output=True, text=True)
        return float(out.stdout.strip())
    except Exception:
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cmd", required=True,
                   help="comando da eseguire e riprendere (python o .py, argv o stringa)")
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--max", type=int, default=1200, help="durata massima in secondi")
    p.add_argument("--lead", type=float, default=2.0,
                   help="secondi di anticipo prima di lanciare il comando (cambio finestra)")
    p.add_argument("--region", default=None,
                   help="ritaglio x,y,w,h (default: tutto il desktop)")
    p.add_argument("--ffmpeg", default=None, help="percorso di ffmpeg se non e' sul PATH")
    p.add_argument("--out", default=None, help="nome del mp4 (default: clip_<stamp>.mp4)")
    p.add_argument("--senza-video", action="store_true",
                   help="esegue il comando senza registrare: prova a secco")
    args = p.parse_args()

    interprete = str(HERE / ".." / "MUDILABV" / "mudilab_env" / "Scripts" / "python.exe")
    if not Path(interprete).exists():
        interprete = sys.executable

    # --cmd e' un comando python relativo a questa cartella: lo si lancia
    # dell'interprete che ha pyagrum, non da PATH
    argv = [interprete] + args.cmd.split()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video = Path(args.out) if args.out else OUT / f"clip_{stamp}.mp4"
    OUT.mkdir(parents=True, exist_ok=True)

    if args.senza_video:
        print("[prova a secco] ", " ".join(argv), flush=True)
        return subprocess.call(argv, cwd=str(HERE))

    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg non trovato sul PATH: passalo con --ffmpeg "
                         "(su questa macchina e' in AppData/Local/Microsoft/WinGet/Links)")

    comando = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "gdigrab",
               "-framerate", str(args.fps), "-draw_mouse", "1", "-t", str(args.max)]
    if args.region:
        x, y, w, h = args.region.split(",")
        comando += ["-offset_x", x, "-offset_y", y, "-video_size", f"{w}x{h}"]
    comando += ["-i", "desktop", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "23", "-pix_fmt", "yuv420p", "-y", str(video)]

    print("[>] avvio registrazione:", " ".join(comando), flush=True)
    registrazione = subprocess.Popen(comando, stdin=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True,
                                     encoding="utf-8", errors="replace")
    time.sleep(args.lead)    # lascia che il terminale venga portato in primo piano
    if registrazione.poll() is not None:
        err = (registrazione.stderr.read() or "")[:600]
        raise SystemExit(f"ffmpeg e' morto subito, nulla da riprendere:\n{err}")

    inizio = time.time()
    try:
        esito = subprocess.call(argv, cwd=str(HERE))
    except KeyboardInterrupt:
        esito = 130
        print("[!] interrotto dall'utente, chiudo il video", flush=True)
    finally:
        try:
            registrazione.stdin.write("q")
            registrazione.stdin.flush()
        except Exception:
            registrazione.kill()
        try:
            registrazione.wait(timeout=30)
        except subprocess.TimeoutExpired:
            registrazione.kill()

    durato = time.time() - inizio
    if not video.exists():
        print("[X] nessun file scritto. stderr ffmpeg:",
              (registrazione.stderr.read() or "")[:800], flush=True)
        return 1
    dentro = ffprobe_durata(video)
    # ASCII: il terminale e' cp1252 e un spunta la fa morire a registrazione chiusa
    # (misurato sullo smoke test del 02-11: mp4 valido, print con UnicodeEncodeError)
    print(f"[OK] {video}  {video.stat().st_size/1e6:.1f} MB", flush=True)
    print(f"     ripresa {durato:.1f} s, contenitore {dentro if dentro else '?'} s", flush=True)
    print(f"     comando chiuso con uscita {esito}; log della demo in {OUT}", flush=True)
    return esito


if __name__ == "__main__":
    sys.exit(main())

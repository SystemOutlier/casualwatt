@echo off
rem Lancia la clip dei tre blocchi in una finestra col titolo MUDILABCLIP.
rem Il titolo serve al blocco 0: finita la pagina della professoressa, il demo
rem richiama AppActivate("MUDILABCLIP") per riportare il terminale in primo piano
rem davanti al browser che Jupyter ha aperto da solo. Senza titolo, i blocchi 1 e 2
rem restano ripresi dietro una scheda che non interessa a nessuno.
rem Durate misurate: apertura Lab ~8 s, blocco 1 10,6 s, blocco 2 4,2 s.
title MUDILABCLIP
cd /d %~dp0
set PY=..\MUDILABV\mudilab_env\Scripts\python.exe
%PY% registra_clip.py --lead 6 --cmd "demo_controfattuali.py --durata-nota 75 --pausa 8 --riporta MUDILABCLIP"
echo.
echo Fine. La finestra resta aperta: chiudila quando hai visto il log.

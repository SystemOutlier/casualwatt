@echo off
rem Apre run_clip.cmd in una finestra nuova col titolo MUDILABCLIP.
rem Il `start` di cmd vuole il titolo fra virgolette quando il primo argomento non
rem e' un programma: da Git Bash le virgolette si perdono e start prova a eseguire
rem "MUDILABCLIP" come comando (misurato: "Impossibile trovare il file \MUDILABCLIP\").
rem Da un file .cmd le virgolette arrivano a cmd intatte.
start "MUDILABCLIP" cmd /k "%~dp0run_clip.cmd"

@echo off
REM =====================================================================
REM  CasualWatt Energy Benchmark - Avvio automatico con privilegi Admin
REM  Doppio clic su questo file -> prompt UAC -> app gia' elevata,
REM  pronta per leggere i sensori reali di LibreHardwareMonitor.
REM =====================================================================
setlocal EnableExtensions

REM --- Cartella dello script (funziona anche da "Esegui come amministratore")
cd /d "%~dp0"

REM --- Verifica se gia' amministratore
net session >nul 2>&1
if %errorlevel%==0 goto :run_app

REM --- Non elevato: richiedo l'elevazione via PowerShell (UAC)
echo [CasualWatt] Richiesta elevazione privilegi (UAC)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -FilePath '%~f0' -Verb RunAs"
if errorlevel 1 (
    echo [CasualWatt] Elevazione annullata o fallita. Avvio con privilegi standard.
    goto :run_app
)
exit /b 0

:run_app
REM --- Scelta interprete Python: py launcher (consigliato su Windows), poi python
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE where python >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
    echo [ERRORE] Python non trovato nel PATH.
    echo Installa Python 3.10+ da https://python.org e riprova.
    pause
    exit /b 1
)

REM --- Stato elevazione nel log della console
net session >nul 2>&1
if %errorlevel%==0 (
    echo [CasualWatt] Processo ELEVATO: i sensori LHM saranno leggibili.
) else (
    echo [CasualWatt] ATTENZIONE: privilegi standard, LHM potrebbe non leggere l'hardware.
)

REM --- Lancio dell'applicazione dalla radice del progetto (import relativi OK)
echo [CasualWatt] Avvio: %PYEXE% main.py
%PYEXE% main.py
if errorlevel 1 (
    echo.
    echo [CasualWatt] Il programma e' terminato con un errore. Messaggio sopra.
    pause
)
endlocal

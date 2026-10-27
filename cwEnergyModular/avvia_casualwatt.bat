@echo off
REM =====================================================================
REM  CasualWatt Energy Benchmark - Avvio
REM
REM  Nessuna elevazione: il contatore EMI (energy/emi_backend.py, IOCTL via
REM  ctypes) legge a privilegi standard, e su Linux i contatori RAPL
REM  richiedono root solo per il gruppo 'power'. LibreHardwareMonitor, che
REM  richiedeva UAC, e' fuori dall'implementazione dal 27/10/2026 (D18).
REM  Per una diagnostica del contatore:  py diagnostics.py
REM =====================================================================
setlocal EnableExtensions

REM --- Cartella dello script (funziona anche da "Esegui come amministratore")
cd /d "%~dp0"

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

REM --- Lancio dell'applicazione dalla radice del progetto (import relativi OK)
echo [CasualWatt] Avvio: %PYEXE% main.py
%PYEXE% main.py
if errorlevel 1 (
    echo.
    echo [CasualWatt] Il programma e' terminato con un errore. Messaggio sopra.
    pause
)
endlocal

@echo off
rem Misura la variante scelta sullo split held-out del benchmark.
rem
rem Perche' uno script e non un comando a mano. I flag di misura sono una
rem decisione, non una digitazione: se cambiano fra un run e l'altro, due
rem numeri con la stessa etichetta vengono da due protocolli. Qui stanno in un
rem posto solo e finiscono in `opzioni_harness` dentro riepilogo.json.
rem
rem Cosa fissa:
rem   --split held-out        lo sviluppo ha scelto la variante, l'held-out la
rem                           verifica una volta sola
rem   --ripetizioni 3         tre passate sulle stesse 80 righe: a n = 3 si
rem                           riportano i tre valori e la terna min/mediana/max,
rem                           non una deviazione standard
rem   --calibra-idle          tre finestre da 30 s a riposo (~90 s) per la
rem                           baseline; senza, l'energia e' solo del package
rem   --riscalda-modelli      carica i modelli fuori dalla finestra
rem   --scarta-primo-run      il primo run paga la cache dei prompt fredda
rem                           (39 s contro 1,3 s) e non entra nei numeri
rem
rem Prima del run: nessun altro processo python, macchina altrimenti ferma.
rem L'energia e' del package CPU: un secondo processo la sporca.
rem
rem Uso:  run_misura.cmd b_vincolata
rem
setlocal
cd /d "%~dp0"

if "%~1"=="" echo uso: %~nx0 ^<variante^> & exit /b 2

rem La CWD e' harness/: quindi ..\..\ per uscire da MUDILAB_run, ..\ per starci dentro.
set PY=..\..\MUDILabV\mudilab_env\Scripts\python.exe
set OUT=..\risultati_misura
set MUDILAB_COPIE=1
set MUDILAB_MODEL=llama3.2:3b-instruct-q4_K_M

"%PY%" preflight_misura.py --secondi 2
if errorlevel 1 echo PREFLIGHT FALLITO: nessun run misurato & exit /b 1

rem L'exit code di esegui_variante.py e' 1 quando *qualche riga* fallisce, e una
rem riga fallita e' un dato (il modello ha sbagliato etichetta o mappatura), non
rem un guasto del run: il riepilogo la conta e valuta.py la classifica. Percio' non
rem si esce qui. Un run davvero perso si riconosce da riepilogo.json assente o da
rem n_falliti = n_run, non dal codice di uscita.
"%PY%" esegui_variante.py --variante %~1 --benchmark ..\benchmark\benchmark.csv --split held-out --ripetizioni 3 --calibra-idle --riscalda-modelli --scarta-primo-run --out "%OUT%"
dir /b /s "%OUT%\%~1\riepilogo.json" >nul 2>&1
if errorlevel 1 echo NESSUN RIEPILOGO: il run non ha prodotto risultati & exit /b 1

"%PY%" ..\benchmark\valuta.py "%OUT%" --out "%OUT%\valutazione.json"

@echo off
setlocal
rem Uso:  run.cmd "la domanda" [modello]
rem
rem Cosa esegue:
rem   MUDILAB_COPIE=1  -> le tre copie corrette, che stanno accanto a questo file
rem   (non impostata)  -> i file originali; la loro cartella si indica con
rem                       MUDILAB_ORIG, oppure con --orig lanciando run_query.py
rem Il modello: secondo argomento, oppure la variabile MUDILAB_MODEL.
rem L'interprete: il python del PATH (ambiente attivo), oppure MUDILAB_PYTHON.
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
if not "%~2"=="" set "MUDILAB_MODEL=%~2"
set "PY=%MUDILAB_PYTHON%"
if not defined PY set "PY=python"
"%PY%" "%~dp0run_query.py" "%~1"
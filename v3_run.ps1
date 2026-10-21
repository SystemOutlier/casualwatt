# v3_run.ps1 — launcher elevato per experiment_validate_lhm.py (v3)
# Avviato da Start-Process -Verb RunAs; log completo su experiment_results\v3_console_log.txt
Set-Location "C:\Users\Massimo\Documents\CasualWatt\CWProject"
New-Item -ItemType Directory -Force -Path "experiment_results" | Out-Null
"=== avvio: $(Get-Date -Format 's') ===" | Out-File -FilePath "experiment_results\v3_console_log.txt" -Encoding utf8
& "C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe" "experiment_validate_lhm.py" *>&1 |
    Tee-Object -FilePath "experiment_results\v3_console_log.txt" -Append
"`n=== fine: $(Get-Date -Format 's')  exit=$LASTEXITCODE ===" |
    Out-File -FilePath "experiment_results\v3_console_log.txt" -Append -Encoding utf8
Write-Host "`nRUN v3 COMPLETATA - premi un tasto per chiudere questa finestra"
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

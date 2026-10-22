# four_way_run.ps1 — launcher ELEVATO per four_way_test.py
# Va eseguito dalla shell normale con:  .\four_way_run.ps1   (compare il prompt UAC)
# LHM/CasualWatt richiede amministratore; EMI e CodeCarbon no.
Set-Location "C:\Users\Massimo\Documents\CasualWatt\CWProject"
New-Item -ItemType Directory -Force -Path "experiment_results" | Out-Null
$log = "C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\four_way_console_log.txt"
"=== avvio: $(Get-Date -Format 's') ===" | Out-File -FilePath $log -Encoding utf8
& "C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe" "four_way_test.py" *>&1 |
    Tee-Object -FilePath $log -Append
"`n=== fine: $(Get-Date -Format 's')  exit=$LASTEXITCODE ===" |
    Out-File -FilePath $log -Append -Encoding utf8
Write-Host "`nFOUR-WAY COMPLETATA - premi un tasto per chiudere questa finestra"
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# probe_alternative_sources.ps1 — risultato NEGATIVO documentato: le "alternative
# senza installare nulla" citate da un altro LLM non arbitrano la misura su MINI_IT13.
# richied AMMINISTRATORE per powercfg /srumutil (senza elevazione dace'
# ERROR 0x1f + "SruUpdateStats failed, status 5").
# Output: esperiment_results\alternative_sources_probe_<ts>.txt
$ErrorActionPreference = "Continue"
$root = "C:\Users\Massimo\Documents\CasualWatt\CWProject"
Set-Location $root
New-Item -ItemType Directory -Force -Path "$root\experiment_results" | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$csv = "$root\experiment_results\srum_dump_$ts.csv"
$out = "$root\experiment_results\alternative_sources_probe_$ts.txt"

function Section($t) { "`n=== $t ===" }

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("PROBE ALTERNATIVE FONTI DI ENERGIA CPU - MINI_IT13 - $(Get-Date -Format 's')")
$adm = (New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
$lines.Add("processo elevato: $adm")

# 1) powercfg /srumutil (SRUM = stime EPI di Windows, non MSR; granularita' ~60 s)
$lines.Add((Section "1. powercfg /srumutil (alternativa 'nativa')" | Out-String).TrimEnd())
$r = (& powercfg /srumutil /output $csv 2>&1 | Out-String)
$lines.Add("output: " + $r.Trim())
if (Test-Path $csv) {
    $n = (Get-Content $csv | Measure-Object -Line).Lines
    $lines.Add("CSV SCRITTO: $csv ($n righe)")
    $lines.Add("intestazione: " + ((Get-Content $csv -TotalCount 1) -join ""))
    # colonne con campo energia, se esistono
    $head = ((Get-Content $csv -TotalCount 1) -join "")
    if ($head -match "(?i)energy|joule|power") { $lines.Add("campi energia: PRESENTI") }
    else { $lines.Add("campi energia: NESSUN campo energy/joule/power nel dump") }
} else {
    $lines.Add("CSV NON scritto (comando fallito) -> SRUM non disponibile come misura")
}

# 2) namespace WMI: esistono i provider di OpenHardwareMonitor / LibreHardwareMonitor?
$lines.Add((Section "2. namespace WMI di terze parti" | Out-String).TrimEnd())
$ns = (Get-CimInstance -Namespace root -ClassName __Namespace -ErrorAction SilentlyContinue |
       ForEach-Object { $_.Name }) -join ", "
$lines.Add("root\ : $ns")
foreach ($p in @("root\OpenHardwareMonitor", "root\LibreHardwareMonitor", "root\LHM")) {
    try {
        $c = Get-CimInstance -Namespace $p -ClassName Sensor -ErrorAction Stop
        $lines.Add("$p -> Sensor: $($c.Count) istanze")
    } catch {
        $lines.Add("$p -> ASSENTE/ERR: " + $_.Exception.Message.Split("`n")[0])
    }
}

# 3) classi power/energy in root\wmi (il tentativo di CimProcessorPowerMetricsBackend)
$lines.Add((Section "3. root\wmi: classi con nome power/energy" | Out-String).TrimEnd())
$cls = Get-CimClass -Namespace root\wmi -ErrorAction SilentlyContinue |
       Where-Object { $_.CimClassName -match "(?i)power|energy|meter" } |
       ForEach-Object { $_.CimClassName }
if ($cls) { $lines.Add(($cls -join "`n")) } else { $lines.Add("nessuna classe power/energy/meter") }
foreach ($cand in @("ProcessorPowerMetrics", "MSAPRProcessorPowerMetrics")) {
    try {
        $i = @(Get-CimInstance -Namespace root\wmi -ClassName $cand -ErrorAction Stop)
        $lines.Add("$cand -> $($i.Count) istanze")
    } catch {
        $lines.Add("$cand -> ERRORE: " + $_.Exception.Message.Split("`n")[0])
    }
}

# 4) controprova: il nostro canale nativo funziona SENZA driver e SENZA admin
$lines.Add((Section "4. controprova: EMI nativo (canale usato dal four-way)" | Out-String).TrimEnd())
try {
    $code = @'
import ctypes, struct
D = (r'\\?\acpi#genuineintel_-_intel64_family_6_model_186_-_13th_gen_'
     r'intel(r)_core(tm)_i9-13900hk#0#{45bd8344-7ed6-49cf-a440-c276c933b053}')
k = ctypes.windll.kernel32
k.CreateFileW.restype = ctypes.c_void_p
h = k.CreateFileW(D, 0x80000000, 3, None, 3, 0x80, None)
out = ctypes.create_string_buffer(64); got = ctypes.c_uint(0)
ok = k.DeviceIoControl(h, 0x0022400C, None, 0, out, 64, ctypes.byref(got), None)
v = struct.unpack("<8Q", out.raw[:64])
print(f"EMI open={h is not None} ioctl={ok} PKG_energy_pWh={v[0]} PKG_time_100ns={v[1]}")
'@
    $tmp = "$env:TEMP\emi_probe_$ts.py"
    Set-Content -Path $tmp -Value $code -Encoding utf8
    $lines.Add((& "C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe" $tmp 2>&1 | Out-String).Trim())
} catch { $lines.Add("EMI probe fallita: " + $_.Exception.Message) }

# 5) presenza software citati
$lines.Add((Section "5. software citati come alternative: presenti?" | Out-String).TrimEnd())
foreach ($p in @("C:\Program Files\Intel\Power Gadget 3.5",
                 "C:\Program Files (x86)\Intel\Intel(R) Power Gadget",
                 "C:\Program Files\Open Hardware Monitor",
                 "C:\HWiNFO64 Pro")) {
    $lines.Add("$p -> " + (Test-Path $p))
}
$hw = Get-Process HWiNFO64 -ErrorAction SilentlyContinue
$lines.Add("processo HWiNFO64 in esecuzione: " + $(if ($hw) { "SI pid $($hw.Id)" } else { "NO" }))
$oll = Get-Process ollama* -ErrorAction SilentlyContinue | ForEach-Object { $_.ProcessName }
$lines.Add("processi ollama: " + $(if ($oll) { ($oll | Sort-Object -Unique) -join ", " } else { "nessuno" }))

$lines | Out-File -FilePath $out -Encoding utf8
Write-Host $out
$lines | ForEach-Object { Write-Host $_ }

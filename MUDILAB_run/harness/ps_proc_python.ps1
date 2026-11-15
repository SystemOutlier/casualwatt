Get-CimInstance Win32_Process -Filter "name='python.exe'" | ForEach-Object {
  $c = $_.CommandLine
  if ($c.Length -gt 150) { $c = $c.Substring(0,150) }
  "{0} p={1} :: {2}" -f $_.ProcessId, $_.ParentProcessId, $c
}

param([string]$Python = 'py', [switch]$Installer)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if ($Python -eq 'py') { & $Python -3.12 -m venv .venv }
    else { & $Python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 requis. Utiliser -Python avec le chemin de python.exe.' }
    $Installer = $true
}
if ($Installer) {
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances échouée.' }
}
Write-Host 'Supervision : http://localhost:8000'
Write-Host 'Dans un second terminal : .\.venv\Scripts\python.exe -m pdm.simulator --protocol http --count 200 --interval 0.5'
& '.\.venv\Scripts\python.exe' -m uvicorn pdm.api:app --host 127.0.0.1 --port 8000

param(
    [int]$Days = 90
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONIOENCODING = "utf-8"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\..\.."))
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$dbInspector = Join-Path $repoRoot "inspect_runtime_db.py"
$snapshotValidator = Join-Path $repoRoot "validate_daily_snapshot.py"
$tradingLog = Join-Path $repoRoot "logs\trading.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment Python not found: $python"
}

Write-Host "=== CherryPulse performance summary ==="
& $python -B $dbInspector summary --days $Days

Write-Host "`n=== Daily snapshot validation ==="
& $python -B $snapshotValidator
$snapshotExitCode = $LASTEXITCODE

Write-Host "`n=== Latest trading log ==="
if (Test-Path -LiteralPath $tradingLog) {
    Get-Content -LiteralPath $tradingLog -Encoding UTF8 -Tail 40
} else {
    Write-Host "trading.log not found."
}

if ($snapshotExitCode -ne 0) {
    Write-Warning "Snapshot validation failed. Do not bypass it to start main_live.py."
}

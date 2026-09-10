param(
  [ValidateSet("pre", "post")]
  [string]$Mode = "pre"
)

$ErrorActionPreference = "Stop"

function Invoke-Git([string[]]$Arguments) {
  $output = & git @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "git command failed: git $($Arguments -join ' ')"
  }
  return $output
}

$branch = (Invoke-Git @("branch", "--show-current")).Trim()
if ([string]::IsNullOrWhiteSpace($branch)) {
  throw "Detached HEAD is not allowed for automated work."
}
if ($branch -in @("main", "master")) {
  throw "Refusing to run automation on protected branch '$branch'."
}

$changed = @(Invoke-Git @("diff", "--name-only", "main...HEAD"))
$working = @(Invoke-Git @("status", "--porcelain"))
$allChanged = @($changed + ($working | ForEach-Object {
  if ($_ -match "^..\s+(.+)$") { $Matches[1] }
}))

$forbidden = @(
  $allChanged | Where-Object {
    $_ -match "(^|/)\.env($|\.)" -or
    $_ -eq "broker/kiwoom_broker.py" -or
    $_ -eq "broker/kiwoom.py"
  }
)
if ($forbidden.Count -gt 0) {
  throw "Forbidden files detected: $($forbidden -join ', ')"
}

$liveDiff = @(Invoke-Git @("diff", "main...HEAD", "--", "*.py", "*.json", "*.yaml", "*.yml") |
  Select-String -Pattern 'RUN_MODE\s*=\s*.*live|LIVE_TRADING\s*=\s*True')
if ($liveDiff.Count -gt 0) {
  throw "Live-trading enablement detected in the automation diff."
}

if ($Mode -eq "post") {
  Invoke-Git @("diff", "--check", "main...HEAD") | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Whitespace errors detected by git diff --check."
  }
}

Write-Output "SAFETY_OK mode=$Mode branch=$branch changed=$($allChanged.Count)"

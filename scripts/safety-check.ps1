param(
  [ValidateSet("pre", "post")][string]$Mode = "pre",
  [string]$BaselinePath,
  [string]$ScopePath
)
$ErrorActionPreference = "Stop"
function Invoke-Git([string[]]$Arguments) { $output = & git @Arguments; if ($LASTEXITCODE -ne 0) { throw "git command failed: git $($Arguments -join ' ')" }; return @($output) }
function Canonical([string]$Path) { return (($Path -replace '\\', '/') -replace '^\./', '').Trim() }
function File-Hash([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '<missing>' }
  return (& git hash-object -- $Path).Trim()
}
function Status-Paths {
  $paths = @(); foreach ($line in (Invoke-Git @("status", "--porcelain=v1", "--untracked-files=all"))) {
    if ($line.Length -lt 4) { continue }; $path = $line.Substring(3)
    if ($path -match '^(.*) -> (.*)$') { $paths += Canonical $Matches[1]; $paths += Canonical $Matches[2] } else { $paths += Canonical $path }
  }
  return @($paths | Where-Object { $_ } | Sort-Object -Unique)
}
function Load-Baseline([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) { throw "Baseline metadata is required." }
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Baseline metadata not found: $Path" }
  try { $data = Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json } catch { throw "Invalid baseline metadata: $Path" }
  if ($data.baselineHead -notmatch '^[0-9a-f]{40}$' -or $null -eq $data.baselinePaths -or $null -eq $data.baselineStatus -or $null -eq $data.baselineHashes -or [string]::IsNullOrWhiteSpace($data.taskId) -or [string]::IsNullOrWhiteSpace($data.branch) -or [string]::IsNullOrWhiteSpace($data.recordedAt)) { throw "Incomplete baseline metadata: $Path" }
  return $data
}
function Load-Scope([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) { throw "Scope manifest is required." }
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Scope manifest not found: $Path" }
  $text = Get-Content -LiteralPath $Path -Raw -Encoding utf8
  $taskMatch = [regex]::Match($text, '(?m)^- task_id:\s*(.+?)\s*$')
  $headMatch = [regex]::Match($text, '(?m)^- base_head:\s*(.+?)\s*$')
  if (-not $taskMatch.Success -or -not $headMatch.Success) { throw "Invalid scope manifest: $Path" }
  function Read-Section([string]$Name) {
    $match = [regex]::Match($text, "(?ms)^## $Name\r?\n(.*?)(?=^## |\z)")
    if (-not $match.Success) { throw "Scope manifest is missing section '$Name': $Path" }
    return @([regex]::Matches($match.Groups[1].Value, '(?m)^-\s+(.+?)\s*$') | ForEach-Object { $_.Groups[1].Value })
  }
  return [pscustomobject]@{
    taskId = $taskMatch.Groups[1].Value.Trim()
    baselineHead = $headMatch.Groups[1].Value.Trim()
    reviewPaths = @(Read-Section 'reviewPaths')
    excludedPaths = @(Read-Section 'Baseline paths excluded from this task')
    untrackedTests = @(Read-Section 'untrackedTests')
  }
}
function Changed-Paths($baseline) {
  $paths = @(Status-Paths)
  if ($null -eq $baseline) {
    $paths += @(Invoke-Git @("diff", "--name-only", "main...HEAD") | ForEach-Object { Canonical $_ })
  } else {
    $paths += @(Invoke-Git @("diff", "--name-only", $baseline.baselineHead) | ForEach-Object { Canonical $_ })
  }
  return @($paths | Sort-Object -Unique)
}
function Is-WorkingTreeOnlyAddition([string]$Path) {
  foreach ($line in (& git status --porcelain=v1 --untracked-files=all -- $Path)) {
    if ($line.Length -ge 4 -and $line.Substring(0, 2) -in @('??', ' A')) { return $true }
  }
  return $false
}
function Is-AllowedReviewPath([string]$Path, [string]$TaskId) {
  $canonical = Canonical $Path
  $taskIdPattern = [regex]::Escape($TaskId)
  if ($canonical -in @(
      '.opencode/agents/reviewer.md',
      'docs/agent-handoff/README.md',
      'scripts/run-task.ps1',
      'scripts/safety-check.ps1'
    )) { return $true }
  if ($canonical -match "^docs/agent-handoff/$taskIdPattern-(SPEC|SCOPE-MANIFEST|IMPLEMENTATION|TEST)\.md$") { return $true }
  return $canonical -match '^tests?/.*\.(py|ps1|json|md)$'
}
function Is-AllowedExcludedPath([string]$Path, [string]$TaskId) {
  $canonical = Canonical $Path
  $taskIdPattern = [regex]::Escape($TaskId)
  if ($canonical -match '^docs/agent-handoff/.*\.log$') { return $true }
  if ($canonical -match '^docs/agent-handoff/TASK-\d+-(SPEC|IMPLEMENTATION|TEST|REVIEW)\.md$') { return $true }
  if ($canonical -match "^docs/agent-handoff/$taskIdPattern-BASELINE\.json$") { return $true }
  return $canonical -match '(?i)^scripts/run-task\.ps1\.task\d+-backup$'
}
function Content-HasLiveEnablement([string]$Path, $baseline) {
  $text = ""
  $workingTreeOnly = Is-WorkingTreeOnlyAddition $Path
  if ($workingTreeOnly -and (Test-Path -LiteralPath $Path -PathType Leaf)) {
    $text = Get-Content -LiteralPath $Path -Raw -Encoding utf8 -ErrorAction SilentlyContinue
  } elseif ($null -ne $baseline) {
    $text += (Invoke-Git @("diff", "--no-ext-diff", $baseline.baselineHead, "--", $Path) | Out-String)
    $text += (Invoke-Git @("diff", "--no-ext-diff", "--cached", $baseline.baselineHead, "--", $Path) | Out-String)
  } elseif (Test-Path -LiteralPath $Path -PathType Leaf) { $text = Get-Content -LiteralPath $Path -Raw -Encoding utf8 -ErrorAction SilentlyContinue }
  $assignment = '(?:RUN_MODE\s*=\s*[^\r\n]*\blive\b|LIVE_TRADING\s*=\s*True\b)'
  if ($workingTreeOnly) { return $text -match "(?m)^\s*$assignment" }
  return $text -match "(?m)^\+\s*$assignment"
}
$branch = (@(Invoke-Git @("branch", "--show-current")) -join "").Trim()
if ([string]::IsNullOrWhiteSpace($branch)) { throw "Detached HEAD is not allowed for automated work." }
if ($branch -in @("main", "master")) { throw "Refusing to run automation on protected branch '$branch'." }
$baseline = Load-Baseline $BaselinePath; $changed = @(Changed-Paths $baseline); $baselineSet = @{}
foreach ($path in $baseline.baselinePaths) {
  $canonical = Canonical $path
  $hashProperty = $baseline.baselineHashes.PSObject.Properties.Item($canonical)
  $recordedHash = if ($null -ne $hashProperty) { $hashProperty.Value } else { $null }
  if ($recordedHash -and $recordedHash -eq (File-Hash $canonical)) { $baselineSet[$canonical] = $true }
}
$repoRoot = (Invoke-Git @("rev-parse", "--show-toplevel")).Trim()
$baselineFullPath = (Resolve-Path -LiteralPath $BaselinePath).Path
$baselineRelative = $baselineFullPath.Substring($repoRoot.Length).TrimStart('\', '/')
$baselineSet[(Canonical $baselineRelative)] = $true
$newPaths = @($changed | Where-Object { -not $baselineSet.ContainsKey((Canonical $_)) })
$forbidden = @($newPaths | Where-Object { $_ -match '(^|/)\.env($|\.)' -or $_ -match '(^|/)broker/' })
if ($forbidden.Count -gt 0) { throw "Forbidden files detected: $($forbidden -join ', ')" }
foreach ($path in ($newPaths | Where-Object { $_ -notmatch '^docs/agent-handoff/' })) { if (Content-HasLiveEnablement $path $baseline) { throw "Live-trading enablement detected in new change: $path" } }
$scope = $null
if (-not [string]::IsNullOrWhiteSpace($ScopePath)) {
  if (-not (Test-Path -LiteralPath $ScopePath -PathType Leaf)) { throw "Scope metadata not found: $ScopePath" }
  $scope = Load-Scope $ScopePath
  if ($scope.baselineHead -ne $baseline.baselineHead -or $scope.taskId -ne $baseline.taskId -or $null -eq $scope.reviewPaths -or $null -eq $scope.excludedPaths -or $null -eq $scope.untrackedTests) { throw "Baseline/scope metadata is missing or inconsistent." }
  $reviewPaths = @($scope.reviewPaths | ForEach-Object { Canonical $_ } | Sort-Object -Unique)
  $excludedPaths = @($scope.excludedPaths | ForEach-Object { Canonical $_ } | Sort-Object -Unique)
  $invalidReviewPaths = @($reviewPaths | Where-Object { -not (Is-AllowedReviewPath $_ $scope.taskId) })
  if ($invalidReviewPaths.Count -gt 0) { throw "Review paths are outside the TASK allowlist: $($invalidReviewPaths -join ', ')" }
  $invalidExcludedPaths = @($excludedPaths | Where-Object {
      -not $baselineSet.ContainsKey($_) -and -not (Is-AllowedExcludedPath $_ $scope.taskId)
    })
  if ($invalidExcludedPaths.Count -gt 0) { throw "Paths are not allowed in the excluded section: $($invalidExcludedPaths -join ', ')" }
  $overlap = @($reviewPaths | Where-Object { $_ -in $excludedPaths })
  if ($overlap.Count -gt 0) { throw "Scope paths overlap review and excluded sections: $($overlap -join ', ')" }
  $declaredUntrackedTests = @($scope.untrackedTests | ForEach-Object { Canonical $_ } | Sort-Object -Unique)
  $invalidUntrackedTests = @($declaredUntrackedTests | Where-Object {
      $_ -notmatch '(^|/)tests/' -or $_ -notin $reviewPaths -or -not (Is-WorkingTreeOnlyAddition $_)
    })
  if ($invalidUntrackedTests.Count -gt 0) { throw "Invalid untrackedTests paths: $($invalidUntrackedTests -join ', ')" }
  $missingUntrackedTests = @($reviewPaths | Where-Object {
      $_ -match '(^|/)tests/' -and (Is-WorkingTreeOnlyAddition $_) -and $_ -notin $declaredUntrackedTests
    })
  if ($missingUntrackedTests.Count -gt 0) { throw "untrackedTests is missing review paths: $($missingUntrackedTests -join ', ')" }
}
if ($Mode -eq "post") {
  if ($null -eq $scope) { throw "Post safety requires a scope manifest." }
  if ($reviewPaths.Count -eq 0) { throw "Scope manifest contains no review paths." }
  $actual = @(Changed-Paths $baseline | Where-Object { -not $baselineSet.ContainsKey((Canonical $_)) } | ForEach-Object { Canonical $_ } | Sort-Object -Unique)
  $declared = @($reviewPaths + $scope.excludedPaths | ForEach-Object { Canonical $_ } | Sort-Object -Unique | Where-Object { -not $baselineSet.ContainsKey($_) })
  if ((@($actual) -join "`n") -ne (@($declared) -join "`n")) { throw "Scope manifest is stale or inconsistent." }
  Invoke-Git (@("diff", "--check", $baseline.baselineHead, "--") + $reviewPaths) | Out-Null
  Invoke-Git (@("diff", "--cached", "--check", "--") + $reviewPaths) | Out-Null
  foreach ($path in $reviewPaths) {
    if ($path -in $newPaths -and (Test-Path -LiteralPath $path -PathType Leaf) -and (Is-WorkingTreeOnlyAddition $path)) {
      if ((Get-Content -LiteralPath $path -Raw -Encoding utf8) -match '(?m)[ \t]+(?:\r?$)') { throw "Whitespace errors found in untracked review path: $path" }
    }
  }
}
$untrackedTests = if ($null -ne $scope) { @($scope.untrackedTests) } else { @($newPaths | Where-Object { $_ -match '(^|/)tests/' -and (Is-WorkingTreeOnlyAddition $_) }) }
$reviewCount = if ($null -ne $scope) { @($scope.reviewPaths).Count } else { 0 }; $excludedCount = if ($null -ne $scope) { @($scope.excludedPaths).Count } else { 0 }
Write-Output "SAFETY_OK mode=$Mode branch=$branch baselineHead=$($baseline.baselineHead) reviewPaths=$reviewCount excludedPaths=$excludedCount untrackedTests=$($untrackedTests.Count)"

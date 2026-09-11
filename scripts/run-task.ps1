param(
  [Parameter(Mandatory = $true)]
  [string]$TaskId,

  [Parameter(Mandatory = $true)]
  [string]$Goal,

  [string]$RepoRoot = (Get-Location).Path,

  [switch]$AutoPublish,

  [switch]$CreatePullRequest
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

# Keep native OpenCode output and handoff logs UTF-8 on Windows PowerShell 7.
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $Name"
  }
}

function Get-StatusPath([string]$Line) {
  if ([string]::IsNullOrWhiteSpace($Line) -or $Line.Length -lt 4) {
    return $null
  }
  $path = $Line.Substring(3).Trim().Trim('"')
  if ($path -match " -> ") {
    return @($path -split " -> " | ForEach-Object { $_.Trim('"') })
  }
  return @($path)
}

function Canonical([string]$Path) { return (($Path -replace '\\', '/') -replace '^\./', '').Trim() }

function Write-AtomicJson([string]$Path, $Value) {
  $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
  try {
    $json = $Value | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($temporary, "$json$([Environment]::NewLine)", $utf8)
    Move-Item -LiteralPath $temporary -Destination $Path -Force
  } catch {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    throw "Unable to write metadata atomically: $Path. $($_.Exception.Message)"
  }
}

function Write-AtomicText([string]$Path, [string]$Text) {
  $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
  try {
    [System.IO.File]::WriteAllText($temporary, "$Text$([Environment]::NewLine)", $utf8)
    Move-Item -LiteralPath $temporary -Destination $Path -Force
  } catch {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    throw "Unable to write manifest atomically: $Path. $($_.Exception.Message)"
  }
}

function Is-SecretOrForbidden([string]$Path) {
  $p = Canonical $Path
  return $p -match '(^|/)\.env($|\.)' -or $p -eq 'broker/kiwoom_broker.py' -or $p -eq 'broker/kiwoom.py'
}

function Is-ReviewCandidate([string]$Path) {
  $p = Canonical $Path
  $taskIdPattern = [regex]::Escape($TaskId)
  if ($p -match '(^|/)\.env($|\.)' -or $p -match '(^|/)broker/(kiwoom_broker|kiwoom)\.py$') { return $false }
  if ($p -match '(^|/)docs/agent-handoff/.*\.log$') { return $false }
  if ($p -in @(
      'docs/agent-handoff/README.md',
      'scripts/run-task.ps1',
      'scripts/safety-check.ps1',
      '.opencode/agents/reviewer.md'
    )) { return $true }
  if ($p -match "^docs/agent-handoff/$taskIdPattern-(SPEC|SCOPE-MANIFEST|IMPLEMENTATION|TEST)\.md$") { return $true }
  return $p -match '^tests?/.*\.(py|ps1|json|md)$'
}

function Get-TaskFileHash([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return "<missing>"
  }
  return (& git hash-object -- $Path).Trim()
}

function Expose-UntrackedForReview([string[]]$Paths) {
  # Do not alter the index. The exact paths, including untracked test content,
  # are supplied to the reviewer explicitly in its prompt.
  foreach ($path in $Paths) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Review path is unreadable: $path" }
  }
}

function Write-ScopeManifest(
  [string]$ManifestPath,
  [string]$BaseHead,
  [hashtable]$BaselineHashes,
  [string[]]$BaselinePaths
) {
  $candidate = @(
    (& git diff --name-only $BaseHead)
    (& git diff --cached --name-only $BaseHead)
    (& git ls-files --others --exclude-standard)
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique

  $reviewPaths = @(); $excludedPaths = @()
  $baselineMetadataPath = Canonical "docs/agent-handoff/$TaskId-BASELINE.json"
  $reviewArtifactPath = Canonical "docs/agent-handoff/$TaskId-REVIEW.md"
  foreach ($path in $candidate) {
    $path = Canonical $path
    if ($path -eq $baselineMetadataPath) { continue }
    if ($path -eq $reviewArtifactPath) { $excludedPaths += $path; continue }
    if ($BaselineHashes.ContainsKey($path) -and
        $BaselineHashes[$path] -eq (Get-TaskFileHash $path)) { $excludedPaths += $path; continue }
    if (Is-SecretOrForbidden $path) { throw "Forbidden or secret path detected in TASK scope: $path" }
    if (-not (Is-ReviewCandidate $path)) {
      if ($path -match '(^|/)docs/agent-handoff/.*\.log$' -or $path -match '^docs/agent-handoff/TASK-\d+-') { $excludedPaths += $path; continue }
      throw "New path is outside the TASK review allowlist: $path"
    }

    $currentHash = Get-TaskFileHash $path
    if ($BaselineHashes.ContainsKey($path) -and
        $BaselineHashes[$path] -eq $currentHash) {
      $excludedPaths += $path; continue
    }

    $reviewPaths += $path
  }

  $untrackedLike = @{}
  foreach ($path in (& git ls-files --others --exclude-standard)) {
    if (-not [string]::IsNullOrWhiteSpace($path)) { $untrackedLike[(Canonical $path)] = $true }
  }
  foreach ($line in (& git status --porcelain=v1 --untracked-files=all)) {
    if ($line.Length -ge 4 -and $line.Substring(0, 2) -eq ' A') {
      foreach ($path in (Get-StatusPath $line)) { $untrackedLike[(Canonical $path)] = $true }
    }
  }
  $untrackedTests = @($reviewPaths | Where-Object {
      $_ -match '(^|/)tests/' -and $untrackedLike.ContainsKey((Canonical $_))
    })
  $reviewPaths = @($reviewPaths | Sort-Object -Unique)
  $excludedPaths = @($excludedPaths | Sort-Object -Unique)
  $manifestLines = @(
    "# $TaskId review scope manifest",
    "",
    "- task_id: $TaskId",
    "- base_head: $BaseHead",
    "- generated_at: $([DateTime]::UtcNow.ToString('o'))",
    "",
    "## Baseline paths excluded from this task"
  )
  $manifestLines += @($excludedPaths | ForEach-Object { "- $_" })
  $manifestLines += @("", "## reviewPaths")
  $manifestLines += @($reviewPaths | ForEach-Object { "- $_" })
  $manifestLines += @("", "## untrackedTests")
  $manifestLines += @($untrackedTests | ForEach-Object { "- $_" })
  $manifestLines += @(
    "",
    "## Review rule",
    "- Review only the current TASK delta in reviewPaths.",
    "- Prior baseline paths are context, not current TASK deliverables.",
    "- Handoff .log files are evidence artifacts and are excluded from code diff scope."
  )
  $manifest = $manifestLines -join "`n"
  Write-AtomicText $ManifestPath $manifest
  return @($reviewPaths | Sort-Object -Unique)
}

Require-Command "git"
Require-Command "opencode"

$branch = (& git branch --show-current).Trim()
if ([string]::IsNullOrWhiteSpace($branch) -or $branch -in @("main", "master")) {
  throw "Automation requires a non-protected branch."
}

$handoff = Join-Path $RepoRoot "docs/agent-handoff"
New-Item -ItemType Directory -Force -Path $handoff | Out-Null

$baseHead = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($baseHead)) { throw "Unable to record baseline HEAD." }
$baselineStatus = @(& git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw "Unable to record baseline status." }
$baselinePaths = @($baselineStatus | ForEach-Object { Get-StatusPath $_ } | Where-Object { $_ })
$baselineHashes = @{}
foreach ($path in $baselinePaths) {
  $baselineHashes[(Canonical $path)] = Get-TaskFileHash $path
}

$baselinePath = Join-Path $handoff "$TaskId-BASELINE.json"
if (Test-Path -LiteralPath $baselinePath -PathType Leaf) {
  throw "Baseline metadata already exists; refusing to overwrite: $baselinePath"
}
$baselineMetadata = [ordered]@{ taskId=$TaskId; baselineHead=$baseHead; baselineStatus=@($baselineStatus); baselinePaths=@($baselinePaths | ForEach-Object { Canonical $_ } | Sort-Object -Unique); baselineHashes=$baselineHashes; branch=$branch; recordedAt=[DateTime]::UtcNow.ToString('o') }
Write-AtomicJson $baselinePath $baselineMetadata
$manifestPath = Join-Path $handoff "$TaskId-SCOPE-MANIFEST.md"

function Run-SafetyCheck([ValidateSet("pre", "post")][string]$Mode) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/safety-check.ps1") -Mode $Mode -BaselinePath $baselinePath -ScopePath $manifestPath
  if ($LASTEXITCODE -ne 0) {
    $label = if ($Mode -eq "pre") { "Pre" } else { "Post" }
    throw "$label safety check failed."
  }
}

# Establish an initial scope before the first safety check. Later stages
# regenerate it, so this is only a pre-stage consistency check.
@(Write-ScopeManifest -ManifestPath $manifestPath -BaseHead $baseHead -BaselineHashes $baselineHashes -BaselinePaths $baselineMetadata.baselinePaths) | Out-Null

Run-SafetyCheck "pre"

function Run-Stage([string]$Agent, [string]$Prompt, [string]$OutputPath) {
  $logPath = Join-Path $handoff "$TaskId-$Agent.log"
  Write-Host "=== $Agent ==="
  $savedErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $stageOutput = @(& opencode run --agent $Agent --auto $Prompt 2>&1)
    $stageExitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $savedErrorActionPreference
  }
  $stageOutput | ForEach-Object { Write-Host $_ }
  $logLines = @($stageOutput | ForEach-Object { "$_" })
  [System.IO.File]::WriteAllLines($logPath, [string[]]$logLines, $utf8)
  if ($stageExitCode -ne 0) {
    throw "OpenCode stage failed: $Agent. See $logPath"
  }
  if (-not (Test-Path $OutputPath)) {
    throw "Stage completed without required handoff file: $OutputPath"
  }
}

$specPath = Join-Path $handoff "$TaskId-SPEC.md"
$implementationPath = Join-Path $handoff "$TaskId-IMPLEMENTATION.md"
$testPath = Join-Path $handoff "$TaskId-TEST.md"
$reviewPath = Join-Path $handoff "$TaskId-REVIEW.md"

Run-Stage "analyzer" @"
Task ID: $TaskId
Task goal: $Goal

Write the specification to:
$specPath
"@ $specPath

Run-Stage "implementer" @"
Task ID: $TaskId
Read the specification at:
$specPath

Implement it in the current branch. Write the implementation report to:
$implementationPath
"@ $implementationPath

Run-Stage "tester" @"
Task ID: $TaskId
Read:
$specPath
$implementationPath

Run the relevant tests and write the test report to:
$testPath
"@ $testPath

$reviewPaths = @(Write-ScopeManifest -ManifestPath $manifestPath -BaseHead $baseHead -BaselineHashes $baselineHashes -BaselinePaths $baselineMetadata.baselinePaths)
Expose-UntrackedForReview $reviewPaths

if ($reviewPaths.Count -gt 0) {
  & git diff --check -- $reviewPaths
  if ($LASTEXITCODE -ne 0) {
    throw "Whitespace errors found in current TASK review paths."
  }
}

Run-SafetyCheck "post"

$manifestHashBeforeReview = Get-TaskFileHash $manifestPath
Run-Stage "reviewer" @"
Task ID: $TaskId
Read:
$specPath
$implementationPath
$testPath
$manifestPath

Review only the current TASK paths listed under reviewPaths in the scope manifest.
Use baseline HEAD/metadata as context, but do not treat prior baseline changes as this TASK deliverables.
Use only these exact reviewPaths as the current TASK evidence:
$($reviewPaths -join "`n")
Use path-scoped git diff and git diff --check only; do not use a branch-wide diff or whole-repository status as PASS/failure evidence.
Read every untracked source/test file in reviewPaths, including its content.

Untracked source and test files in reviewPaths are part of the review. Handoff .log files are evidence only. Check scope, tests, and trading safety. Write the verdict to:
$reviewPath
"@ $reviewPath

if ((Get-TaskFileHash $manifestPath) -ne $manifestHashBeforeReview) {
  throw "Scope manifest changed during review. No publish was attempted."
}
$review = Get-Content -Raw -Encoding utf8 $reviewPath
$verdicts = [regex]::Matches($review, '(?mi)^\s*#*\s*(PASS|CHANGES_REQUESTED|BLOCKED)\b')
if ($verdicts.Count -ne 1) {
  throw "Review did not contain exactly one verdict. No publish was attempted."
}
if ($verdicts[0].Groups[1].Value.ToUpperInvariant() -ne "PASS") {
  throw "Review did not PASS. No publish was attempted."
}

$reviewPathsAfter = @(Write-ScopeManifest -ManifestPath $manifestPath -BaseHead $baseHead -BaselineHashes $baselineHashes -BaselinePaths $baselineMetadata.baselinePaths)
if ((@($reviewPathsAfter) -join "`n") -ne (@($reviewPaths) -join "`n")) { throw "Review scope changed after reviewer; no publish was attempted." }
Run-SafetyCheck "post"

if ($AutoPublish) {
  $publishPaths = @($reviewPathsAfter)
  $publishPaths += Canonical "docs/agent-handoff/$TaskId-REVIEW.md"
  $publishPaths = @($publishPaths | Sort-Object -Unique)
  & git add -- $publishPaths
  if ($LASTEXITCODE -ne 0) { throw "git add failed" }
  & git commit --only -m "automation($TaskId): $Goal" -- $publishPaths
  if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
  & git push --set-upstream origin $branch
  if ($LASTEXITCODE -ne 0) { throw "git push failed" }

  if ($CreatePullRequest) {
    Require-Command "gh"
    & gh pr create --base main --head $branch --title "automation($TaskId): $Goal" --body "Automated OpenCode implementation. Review: docs/agent-handoff/$TaskId-REVIEW.md"
    if ($LASTEXITCODE -ne 0) { throw "gh pr create failed" }
  }
}

Write-Host "TASK_COMPLETE id=$TaskId branch=$branch review=PASS autoPublish=$AutoPublish"

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
  $path = $Line.Substring(3).Trim()
  if ($path -match " -> ") {
    $path = ($path -split " -> ")[-1]
  }
  return $path
}

function Get-FileHash([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return "<missing>"
  }
  return (& git hash-object -- $Path).Trim()
}

function Expose-UntrackedForReview {
  $untracked = @(& git ls-files --others --exclude-standard)
  foreach ($path in $untracked) {
    if ($path -match "(^|/)\.env($|\.)") {
      throw "Refusing to expose a secret-like untracked file: $path"
    }
    if ($path -match "^docs/agent-handoff/.*\.log$") {
      continue
    }
    & git add --intent-to-add -- $path
    if ($LASTEXITCODE -ne 0) {
      throw "Unable to expose untracked file for review: $path"
    }
  }
}

function Write-ScopeManifest(
  [string]$ManifestPath,
  [string]$BaseHead,
  [hashtable]$BaselineHashes
) {
  $candidate = @(
    (& git diff --name-only $BaseHead)
    (& git diff --cached --name-only $BaseHead)
    (& git ls-files --others --exclude-standard)
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique

  $reviewPaths = @()
  foreach ($path in $candidate) {
    if ($path -match "^docs/agent-handoff/.*\.log$") {
      continue
    }

    $currentHash = Get-FileHash $path
    if ($BaselineHashes.ContainsKey($path) -and
        $BaselineHashes[$path] -eq $currentHash) {
      continue
    }

    $reviewPaths += $path
  }

  $lines = @(
    "# $TaskId review scope manifest"
    ""
    "- task_id: $TaskId"
    "- base_head: $BaseHead"
    "- generated_at: $([DateTime]::UtcNow.ToString("o"))"
    ""
    "## Baseline paths excluded from this task"
    if ($BaselineHashes.Count -eq 0) { "- (none)" }
    else { $BaselineHashes.Keys | Sort-Object | ForEach-Object { "- $_" } }
    ""
    "## reviewPaths"
    if ($reviewPaths.Count -eq 0) { "- (none)" }
    else { $reviewPaths | ForEach-Object { "- $_" } }
    ""
    "## Review rule"
    "- Review only the current TASK delta in reviewPaths."
    "- Prior baseline paths are context, not new deliverables."
    "- Handoff .log files are evidence artifacts and are excluded from code diff scope."
  )
  $lines | Set-Content -LiteralPath $ManifestPath -Encoding utf8
  return $reviewPaths
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
$baselineStatus = @(& git status --short --untracked-files=all)
$baselinePaths = @($baselineStatus | ForEach-Object { Get-StatusPath $_ } | Where-Object { $_ })
$baselineHashes = @{}
foreach ($path in $baselinePaths) {
  $baselineHashes[$path] = Get-FileHash $path
}

$manifestPath = Join-Path $handoff "$TaskId-SCOPE.md"
@(
  "# $TaskId baseline"
  ""
  "- task_id: $TaskId"
  "- base_head: $baseHead"
  "- created_at: $([DateTime]::UtcNow.ToString("o"))"
  ""
  "## Baseline paths"
  if ($baselinePaths.Count -eq 0) { "- (none)" }
  else { $baselinePaths | Sort-Object | ForEach-Object { "- $_" } }
) | Set-Content -LiteralPath $manifestPath -Encoding utf8

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/safety-check.ps1") -Mode pre

function Run-Stage([string]$Agent, [string]$Prompt, [string]$OutputPath) {
  $logPath = Join-Path $handoff "$TaskId-$Agent.log"
  Write-Host "=== $Agent ==="
  & opencode run --agent $Agent --auto $Prompt 2>&1 |
    Tee-Object -FilePath $logPath -Encoding utf8
  if ($LASTEXITCODE -ne 0) {
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

Expose-UntrackedForReview
$reviewPaths = @(Write-ScopeManifest -ManifestPath $manifestPath -BaseHead $baseHead -BaselineHashes $baselineHashes)

if ($reviewPaths.Count -gt 0) {
  & git diff --check -- $reviewPaths
  if ($LASTEXITCODE -ne 0) {
    throw "Whitespace errors found in current TASK review paths."
  }
}

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/safety-check.ps1") -Mode post

Run-Stage "reviewer" @"
Task ID: $TaskId
Read:
$specPath
$implementationPath
$testPath
$manifestPath

Review only the current TASK paths listed under reviewPaths in the scope manifest.
Use the baseline paths as context, but do not treat prior baseline changes as this TASK deliverables.
Use:
- git diff main
- git status --short --untracked-files=all
- the scope manifest

Untracked source and test files in reviewPaths are part of the review. Handoff .log files are evidence only. Check scope, tests, and trading safety. Write the verdict to:
$reviewPath
"@ $reviewPath

$review = Get-Content -Raw -Encoding utf8 $reviewPath
if ($review -notmatch "(?m)^PASS\b") {
  throw "Review did not PASS. No publish was attempted."
}

if ($AutoPublish) {
  & git add --all
  if ($LASTEXITCODE -ne 0) { throw "git add failed" }
  & git commit -m "automation($TaskId): $Goal"
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

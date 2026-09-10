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

function Expose-UntrackedForReview {
  $untracked = @(& git ls-files --others --exclude-standard)
  foreach ($path in $untracked) {
    if ($path -match "(^|/)\.env($|\.)") {
      throw "Refusing to expose a secret-like untracked file: $path"
    }
    & git add --intent-to-add -- $path
    if ($LASTEXITCODE -ne 0) {
      throw "Unable to expose untracked file for review: $path"
    }
  }
}

Require-Command "git"
Require-Command "opencode"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/safety-check.ps1") -Mode pre

$branch = (& git branch --show-current).Trim()
$handoff = Join-Path $RepoRoot "docs/agent-handoff"
New-Item -ItemType Directory -Force -Path $handoff | Out-Null

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
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/safety-check.ps1") -Mode post

Run-Stage "reviewer" @"
Task ID: $TaskId
Read:
$specPath
$implementationPath
$testPath

Review the complete working-tree change against main. Use both:
- git diff main
- git status --short
Untracked files exposed by the runner are part of the review and must not be ignored. Check scope, tests, and trading safety. Write the verdict to:
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

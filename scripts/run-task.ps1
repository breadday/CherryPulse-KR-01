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

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $Name"
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
  & opencode run --agent $Agent --auto $Prompt 2>&1 | Tee-Object -FilePath $logPath
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

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/safety-check.ps1") -Mode post

Run-Stage "reviewer" @"
Task ID: $TaskId
Read:
$specPath
$implementationPath
$testPath

Review the complete diff against main and write the review verdict to:
$reviewPath
"@ $reviewPath

$review = Get-Content -Raw $reviewPath
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

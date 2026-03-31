# backup_project.ps1
$ErrorActionPreference = "Stop"

# 현재 스크립트 기준 프로젝트 루트
$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectName = Split-Path $ProjectPath -Leaf

# 백업 저장 폴더
$BackupRoot = Join-Path $ProjectPath "_backups"
if (!(Test-Path $BackupRoot)) {
    New-Item -ItemType Directory -Path $BackupRoot | Out-Null
}

# 날짜 문자열
$Now = Get-Date -Format "yyyy-MM-dd_HHmmss"

# 임시 작업 폴더
$TempRoot = Join-Path $env:TEMP "${ProjectName}_backup_$Now"
if (Test-Path $TempRoot) {
    Remove-Item $TempRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $TempRoot | Out-Null

# robocopy로 제외 복사
$Source = $ProjectPath
$Dest = Join-Path $TempRoot $ProjectName

$ExcludeDirs = @(".venv", "__pycache__", ".git", ".idea", ".vscode", "_backups")
$ExcludeFiles = @("*.log", "*.pyc")

$RoboArgs = @(
    $Source
    $Dest
    "/E"
    "/R:1"
    "/W:1"
    "/XD"
) + $ExcludeDirs + @(
    "/XF"
) + $ExcludeFiles

Write-Host "백업용 파일 복사 중..."
robocopy @RoboArgs | Out-Null

# zip 생성
$ZipPath = Join-Path $BackupRoot "${ProjectName}_$Now.zip"

Write-Host "압축 생성 중..."
Compress-Archive -Path $Dest -DestinationPath $ZipPath -Force

# 임시 폴더 삭제
Remove-Item $TempRoot -Recurse -Force

Write-Host ""
Write-Host "백업 완료 👍"
Write-Host "파일 위치: $ZipPath"
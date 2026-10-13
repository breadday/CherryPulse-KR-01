@echo off
chcp 65001 >nul
echo ===============================================
echo  CherryPulse FID 아침 수집 (09:05, 120초)
echo ===============================================
cd /d E:\hermes-local\workspace\CherryPulse-KR-01
if errorlevel 1 (echo 폴더를 찾지 못했습니다. & pause & exit /b 1)
if not exist "%LOCALAPPDATA%\Programs\Python\Python310-32\python.exe" (echo Python 3.10 32비트를 찾지 못했습니다. & pause & exit /b 1)
echo.
echo 키움 OpenAPI 로그인 창이 뜨면 로그인하세요.
echo 모의투자 검증 중이면 모의투자 접속을 선택하세요.
echo 로그인 후 이 창을 열어 두면 09:05에 120초 수집합니다.
echo 주문·조회(TR)·계좌 변경은 하지 않습니다.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%LOCALAPPDATA%\Programs\Python\Python310-32\python.exe' tools\inspect_kiwoom_realtime.py 005930 --start-at 09:05 --seconds 120 2>&1 ^| Tee-Object -FilePath (Join-Path ([Environment]::GetFolderPath('Desktop')) ('CherryPulse-quote-' + (Get-Date -Format yyyyMMdd) + '.txt'))"
echo.
echo 종료됐습니다. 바탕화면의 CherryPulse-quote-날짜.txt를 확인하세요.
echo 계좌·개인 정보가 없는지 확인 후 공유하세요.
pause

@echo off
chcp 65001 >nul
rem คลิกขวาไฟล์นี้ แล้วเลือก Run as administrator
net session >nul 2>&1
if errorlevel 1 (
  echo ต้องคลิกขวาไฟล์นี้ แล้วเลือก Run as administrator
  pause
  exit /b 1
)
powershell -NoProfile -Command "if (-not (Get-NetFirewallRule -DisplayName 'Jig Board 8080' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'Jig Board 8080' -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private | Out-Null }; 'เปิดพอร์ต 8080 สำหรับเครือข่าย Private แล้ว'"
pause

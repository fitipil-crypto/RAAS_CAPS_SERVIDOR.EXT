@echo off
net session >nul 2>&1
if errorlevel 1 (
    echo Solicitando elevacao...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
if not exist "logs" mkdir "logs"

echo Parando o RAAS-CAPS...

rem Avisa o iniciar_servidor.bat que a parada e intencional; sem isso ele
rem reiniciaria o servidor logo depois.
>"logs\parar.flag" echo parar

rem Encerra quem esta escutando na porta do servidor (padrao 8000). Isso atinge
rem so o RAAS-CAPS, mesmo que haja outros programas Python rodando.
powershell -NoProfile -Command "$p = 8000; if ($env:PORT) { $p = [int]$env:PORT }; $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if (-not $c) { Write-Host 'Nenhum servidor encontrado na porta' $p } else { $c | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force; Write-Host 'Servidor encerrado (PID' $_.OwningProcess ')' } }"

echo Concluido.
pause

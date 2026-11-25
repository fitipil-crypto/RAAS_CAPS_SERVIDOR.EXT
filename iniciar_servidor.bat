@echo off
setlocal EnableExtensions
title RAAS-CAPS
cd /d "%~dp0"

rem ==============================================================
rem  RAAS-CAPS - inicia o servidor
rem
rem  Uso:  iniciar_servidor.bat          modo normal (com janela)
rem        iniciar_servidor.bat /auto    sem janela (tarefa agendada):
rem                                      nunca usa pause nem abre o navegador
rem
rem  Variaveis opcionais (defina antes de rodar):
rem        PORT          porta do servidor (padrao 8000)
rem        DATABASE_URL  banco de dados (padrao sqlite:///./raas_caps.db)
rem
rem  Este script: confere se ja ha servidor rodando, cria o ambiente
rem  virtual, instala as dependencias so quando o requirements.txt muda,
rem  gera a chave de seguranca, faz um backup diario do banco, gira os
rem  logs e REINICIA o servidor se ele cair (parar_servidor.bat avisa
rem  que a parada e intencional).
rem ==============================================================

set "AUTO=0"
if /i "%~1"=="/auto" set "AUTO=1"
if not defined PORT set "PORT=8000"

if not exist "logs" mkdir "logs"
set "BOOTLOG=logs\boot.log"
set "SERVERLOG=logs\server.log"
set "STOPFLAG=logs\parar.flag"
set "PY=.venv\Scripts\python.exe"

call :log "iniciar_servidor.bat iniciado - auto=%AUTO% porta=%PORT%"

echo ==============================================
echo   RAAS-CAPS - Iniciando servidor
echo ==============================================

rem --- Ja existe um servidor nesta porta? (independe do idioma do Windows)
netstat -ano -p tcp | findstr /R /C:":%PORT% .*0\.0\.0\.0:0" >nul 2>&1
if not errorlevel 1 (
    call :log "porta %PORT% ja esta em uso - nada a fazer"
    echo [AVISO] Ja existe um servidor em execucao na porta %PORT%.
    echo Acesse http://localhost:%PORT% ou rode parar_servidor.bat para encerra-lo.
    call :pausar
    exit /b 0
)

rem --- Ambiente virtual
if exist "%PY%" goto :venv_pronto

rem Ainda nao existe: precisamos de um Python 3.10+ para cria-lo. A conta
rem SYSTEM (tarefa de inicio automatico) nao enxerga o PATH do usuario, por
rem isso tentamos primeiro o caminho salvo por instalar_inicio_automatico.bat.
call :log ".venv nao existe, procurando python para cria-lo"
call :achar_python
if not defined PYTHON_BOOTSTRAP (
    call :log "ERRO: python 3.10 ou mais novo nao encontrado"
    echo [ERRO] Python 3.10 ou mais novo nao foi encontrado.
    echo Instale o Python em https://python.org e marque a opcao
    echo "Add python.exe to PATH" durante a instalacao.
    echo Depois rode este script uma vez manualmente, antes de instalar
    echo o inicio automatico.
    call :pausar
    exit /b 1
)

echo [1/5] Criando ambiente virtual...
%PYTHON_BOOTSTRAP% -m venv .venv
if errorlevel 1 (
    call :log "ERRO: falha ao criar o ambiente virtual"
    echo [ERRO] Falha ao criar o ambiente virtual. Veja logs\boot.log
    call :pausar
    exit /b 1
)
call :log "ambiente virtual criado"

:venv_pronto

rem --- Dependencias: so reinstala quando o requirements.txt mudou
echo [2/5] Verificando dependencias...
set "REQ_MARK=.venv\requirements.sha"
set "REQ_HASH="
set "REQ_OLD="
for /f %%h in ('%PY% -m sistema.manutencao requisitos') do set "REQ_HASH=%%h"
if exist "%REQ_MARK%" set /p REQ_OLD=<"%REQ_MARK%"
if defined REQ_HASH if "%REQ_HASH%"=="%REQ_OLD%" (
    call :log "dependencias inalteradas"
    goto :deps_ok
)
echo       Instalando pacotes, pode demorar na primeira vez...
"%PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    call :log "AVISO: pip install terminou com erro - seguindo com o que ja esta instalado"
    echo [AVISO] Nao foi possivel instalar ou atualizar as dependencias. Veja logs\boot.log
) else (
    call :log "dependencias instaladas"
    if defined REQ_HASH >"%REQ_MARK%" echo %REQ_HASH%
)
:deps_ok

rem --- Chave de seguranca (sessoes) e configuracao
echo [3/5] Preparando chave de seguranca e backup do banco...
set "SECRET_FILE=secret.key"
if exist "%SECRET_FILE%" for %%F in ("%SECRET_FILE%") do if %%~zF EQU 0 del "%SECRET_FILE%"
if not exist "%SECRET_FILE%" (
    "%PY%" -c "import secrets;print(secrets.token_hex(32))" > "%SECRET_FILE%"
    call :log "chave de seguranca gerada"
)
set /p SECRET_KEY=<"%SECRET_FILE%"

if not defined DATABASE_URL set "DATABASE_URL=sqlite:///./raas_caps.db"
set "DEBUG=false"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem --- Backup diario do banco (pasta backups_auto, guarda 14 dias)
"%PY%" -m sistema.manutencao backup >> "%BOOTLOG%" 2>&1

set "LOCAL_IP="
for /f %%i in ('%PY% -m sistema.manutencao ip') do set "LOCAL_IP=%%i"

echo [4/5] Servidor iniciando em:
echo    - Neste computador: http://localhost:%PORT%
if defined LOCAL_IP echo    - Na rede local:      http://%LOCAL_IP%:%PORT%
echo.
echo Logs: logs\server.log ^(servidor^) e logs\boot.log ^(inicializacao^)
echo Para encerrar: rode parar_servidor.bat, ou pressione Ctrl+C e responda S.
echo ==============================================

if "%AUTO%"=="0" start "" /b "%PY%" -m sistema.manutencao abrir http://localhost:%PORT% 5

echo [5/5] Em execucao.
if exist "%STOPFLAG%" del "%STOPFLAG%" >nul 2>&1
set "CRASHES=0"

:rodar
if exist "%STOPFLAG%" goto :fim
"%PY%" -m sistema.manutencao rotacionar "%SERVERLOG%" 10 5 >> "%BOOTLOG%" 2>&1
set "T0="
for /f %%t in ('%PY% -m sistema.manutencao agora') do set "T0=%%t"

call :log "iniciando python main.py"
"%PY%" main.py >> "%SERVERLOG%" 2>&1
set "EXITCODE=%errorlevel%"

set "T1="
for /f %%t in ('%PY% -m sistema.manutencao agora') do set "T1=%%t"
call :log "python main.py encerrou com codigo %EXITCODE%"

if exist "%STOPFLAG%" (
    call :log "parada solicitada por parar_servidor.bat"
    goto :fim
)
if "%EXITCODE%"=="0" goto :fim
if "%EXITCODE%"=="-1073741510" (
    call :log "interrompido com Ctrl+C"
    goto :fim
)

rem Caiu: reinicia. Se rodou mais de 5 minutos nao foi falha de partida,
rem entao o contador de falhas seguidas e zerado.
set /a RODOU=0
if defined T0 if defined T1 set /a RODOU=T1-T0
if %RODOU% GEQ 300 set "CRASHES=0"
set /a CRASHES+=1
if %CRASHES% GEQ 5 (
    call :log "ERRO: o servidor caiu %CRASHES% vezes seguidas - desistindo"
    echo [ERRO] O servidor caiu varias vezes seguidas. Veja logs\server.log
    call :pausar
    exit /b 1
)
call :log "reiniciando em 5 segundos - falha %CRASHES% de 5"
echo [AVISO] O servidor encerrou com codigo %EXITCODE%. Reiniciando em 5 segundos...
ping -n 6 127.0.0.1 >nul
goto :rodar

:fim
call :log "iniciar_servidor.bat finalizado"
exit /b 0

rem ---------------------------------------------------------------
:log
>>"%BOOTLOG%" echo [%date% %time%] %~1
exit /b 0

:pausar
if "%AUTO%"=="0" pause
exit /b 0

:achar_python
set "PYTHON_BOOTSTRAP="
set "CAND="
if exist "python_path.txt" set /p CAND=<python_path.txt
if defined CAND (
    "%CAND%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set PYTHON_BOOTSTRAP="%CAND%"
)
if not defined PYTHON_BOOTSTRAP (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set PYTHON_BOOTSTRAP=python
)
if not defined PYTHON_BOOTSTRAP (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set PYTHON_BOOTSTRAP=py -3
)
exit /b 0

@echo off
setlocal EnableExtensions
title RAAS-CAPS - ngrok
cd /d "%~dp0"

rem ==============================================================
rem  RAAS-CAPS - cria uma conexao publica (tunel) via ngrok
rem
rem  Uso:  iniciar_ngrok.bat
rem
rem  Requisitos:
rem    - ngrok instalado (https://ngrok.com/download) e no PATH
rem    - conta ngrok gratuita; o token fica em https://dashboard.ngrok.com
rem    - servidor do RAAS-CAPS rodando (iniciar_servidor.bat)
rem
rem  Variaveis opcionais (defina antes de rodar):
rem        PORT              porta do servidor (padrao 8000)
rem        NGROK_AUTHTOKEN   token da conta (se ainda nao configurado)
rem        NGROK_DOMAIN      dominio fixo da sua conta ngrok
rem
rem  ATENCAO: o endereco do ngrok e PUBLICO na internet. Antes de usar,
rem  troque a senha padrao do admin (admin/admin) em Controle de Acesso.
rem ==============================================================

if not defined PORT set "PORT=8000"

where ngrok >nul 2>&1
if errorlevel 1 (
    echo [ERRO] ngrok nao encontrado.
    echo Baixe em https://ngrok.com/download e deixe o ngrok.exe no PATH
    echo ^(ou na pasta do projeto^).
    pause
    exit /b 1
)

netstat -ano -p tcp | findstr /R /C:":%PORT% .*0\.0\.0\.0:0" >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Nenhum servidor encontrado na porta %PORT%.
    echo Rode iniciar_servidor.bat antes ^(o tunel abre mesmo assim, mas nao havera resposta^).
    echo.
)

if defined NGROK_AUTHTOKEN (
    ngrok config add-authtoken %NGROK_AUTHTOKEN% >nul
)

echo ==============================================
echo   RAAS-CAPS - Conexao via ngrok
echo ==============================================
echo O endereco publico aparece abaixo, na linha "Forwarding".
echo Para encerrar: feche esta janela ou pressione Ctrl+C.
echo.
echo [ATENCAO] Qualquer pessoa com o link chega a tela de login.
echo Use senhas fortes e nao deixe o admin com a senha padrao.
echo Como o ngrok usa HTTPS, coloque no arquivo .env do servidor:
echo     COOKIE_SECURE=true
echo     TRUST_PROXY=true
echo e reinicie o servidor. Detalhes em docs\LGPD.md.
echo ==============================================
echo.

if defined NGROK_DOMAIN (
    ngrok http --url=%NGROK_DOMAIN% %PORT%
) else (
    ngrok http %PORT%
)
pause
exit /b 0

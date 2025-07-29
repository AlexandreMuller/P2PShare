@echo off
cls
echo ========================================
echo   SERVIDOR P2P + NGROK AUTOMATICO
echo ========================================
echo.

REM Verificar se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo Python nao encontrado!
    echo Por favor, instale Python 3.7+ e tente novamente.
    pause
    exit /b 1
)

REM Verificar se ngrok existe
if not exist "ngrok.exe" (
    echo Ngrok nao encontrado!
    echo Baixe em: https://ngrok.com/downloads
    pause
    exit /b 1
)

echo Dependencias verificadas!
echo.

REM Matar processos antigos se existirem
taskkill /f /im python.exe 2>nul
taskkill /f /im ngrok.exe 2>nul
timeout /t 2 /nobreak >nul

echo [1/3] Iniciando servidor P2P...
start /b python servidor.py
timeout /t 3 /nobreak >nul

echo [2/3] Aguardando servidor inicializar...
:wait_server
netstat -an | findstr ":5000" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_server
)
echo Servidor P2P rodando na porta 5000

echo [3/3] Criando tunel Ngrok...
start /b .\ngrok.exe http 5000

echo.
echo Aguardando Ngrok conectar...
timeout /t 5 /nobreak >nul

REM Tentar obter URL do Ngrok
for /f "tokens=*" %%i in ('curl -s http://localhost:4040/api/tunnels 2^>nul ^| findstr "public_url"') do (
    set ngrok_info=%%i
)

echo.
echo ========================================
echo        SERVIDOR P2P ATIVO!
echo ========================================
echo.
echo Acesso Mundial: Verificando...
echo Acesso Local: http://localhost:5000
echo.
echo O servidor detectara automaticamente o Ngrok
echo Links serao gerados com a URL publica
echo.
echo Para parar:
echo    - Pressione Ctrl+C nesta janela
echo    - Ou feche esta janela
echo.
echo ========================================

REM Manter janela aberta e monitorar
:monitor
timeout /t 10 /nobreak >nul
netstat -an | findstr ":5000" >nul 2>&1
if errorlevel 1 (
    echo Servidor P2P parou de responder!
    goto cleanup
)
echo Servidor ainda ativo... %time%
goto monitor

:cleanup
echo.
echo Encerrando serviços...
taskkill /f /im python.exe 2>nul
taskkill /f /im ngrok.exe 2>nul
echo Encerrado com sucesso!
pause

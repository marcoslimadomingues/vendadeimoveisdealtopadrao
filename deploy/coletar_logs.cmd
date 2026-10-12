@echo off
rem Executado diariamente pelo Agendador de Tarefas: baixa os access logs do cPanel,
rem e gera logs\servidor\relatorio-AAAA-MM-DD.md.
rem Credenciais: arquivo .ftp.env na raiz do projeto (FTP_HOST, FTP_USER, FTP_PASS).
setlocal
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
if not exist logs\servidor mkdir logs\servidor
set PY=python
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe
echo ===== %date% %time% >> logs\servidor\coleta.log
"%PY%" tools\coletar_logs.py --dominio vendadeimoveisdealtopadrao.com.br >> logs\servidor\coleta.log 2>&1

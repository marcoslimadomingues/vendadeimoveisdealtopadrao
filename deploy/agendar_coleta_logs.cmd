@echo off
rem Registra a coleta diaria de access logs as 11:30 (o cPanel atualiza os arquivos em ~/logs por volta das 10:30).
rem Remover:  schtasks /Delete /TN "AltoPadrao - Coleta de Access Logs" /F
schtasks /Create /F /SC DAILY /ST 11:30 /TN "AltoPadrao - Coleta de Access Logs" /TR "\"%~dp0coletar_logs.cmd\""

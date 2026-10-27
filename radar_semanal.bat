@echo off
rem ============================================================================
rem  Radar semanal de imoveis de alto padrao em Fortaleza - roda aqui, sem nuvem.
rem
rem  Duplo clique (ou no terminal):   radar_semanal.bat
rem  So conferir se esta tudo pronto: radar_semanal.bat simular
rem
rem  O que faz: pesquisa, confere cada fato na fonte, publica a edicao no site
rem  (commit e push na main; o GitHub Actions atualiza o site e avisa o Bing),
rem  grava a postagem do Google em postagens\DATA\ e o relatorio interno em
rem  radar_interno\ (pasta local, fora do GitHub). No fim abre tudo para voce.
rem  O roteiro que o Claude segue esta em tools\radar_prompt.md.
rem ============================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "MODELO=opus"
set "PY=py -3.14"
set "FERRAMENTAS=Read Write Edit Glob Grep WebSearch WebFetch Bash(git *) Bash(py *) Bash(python *) Bash(curl *) Bash(TZ=America/Fortaleza date *) Bash(date *) Bash(ls *) Bash(cat *) Bash(mkdir *) Bash(sleep *) Bash(head *) Bash(grep *) Bash(rtk *)"

for /f %%i in ('powershell -nologo -noprofile -command "Get-Date -Format yyyy-MM-dd"') do set "HOJE=%%i"
set "SIMULAR=0"
if /i "%~1"=="simular" set "SIMULAR=1"

echo.
echo === Radar Alto Padrao Fortaleza - %HOJE% ===
echo.

where claude >nul 2>&1
if errorlevel 1 (
  echo ERRO: o comando "claude" nao foi encontrado. Instale o Claude Code e faca login.
  goto :fim
)
where git >nul 2>&1
if errorlevel 1 (
  echo ERRO: o git nao foi encontrado.
  goto :fim
)
%PY% -c "import flask, pytest, matplotlib" >nul 2>&1
if errorlevel 1 (
  echo ERRO: faltam pacotes no Python do projeto. Rode uma vez:
  echo   %PY% -m pip install -r requirements.txt matplotlib
  goto :fim
)
if not exist "tools\radar_prompt.md" (
  echo ERRO: tools\radar_prompt.md nao foi encontrado.
  goto :fim
)

rem o repositorio precisa estar limpo (a pasta epic\ nao versionada nao conta)
git status --porcelain --untracked-files=no > "%TEMP%\radar_status.txt"
for %%A in ("%TEMP%\radar_status.txt") do set "TAM=%%~zA"
if not "%TAM%"=="0" (
  echo ERRO: ha alteracoes nao salvas no repositorio. Peca ajuda antes de rodar o radar:
  type "%TEMP%\radar_status.txt"
  goto :fim
)
git pull --ff-only
if errorlevel 1 (
  echo ERRO: nao consegui atualizar o repositorio com o GitHub.
  goto :fim
)

if not exist "radar_interno" mkdir "radar_interno"
set "LOG=radar_interno\log-%HOJE%.txt"

if "%SIMULAR%"=="1" (
  echo SIMULACAO: tudo pronto. O comando seria:
  echo   claude -p --model %MODELO% --permission-mode acceptEdits --allowedTools "%FERRAMENTAS%" ^< tools\radar_prompt.md ^> %LOG%
  goto :fim
)

echo Pesquisando e conferindo as fontes. Leva de 5 a 20 minutos; nao feche esta janela.
echo.
claude -p --model %MODELO% --permission-mode acceptEdits --allowedTools "%FERRAMENTAS%" < "tools\radar_prompt.md" > "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo.
echo ----- Resumo do Claude -----
type "%LOG%"
echo ----------------------------
if not "%RC%"=="0" echo AVISO: o Claude terminou com erro (codigo %RC%). Veja o log: %LOG%

rem abre o que ficou pronto hoje
if exist "postagens\%HOJE%\postagem.md" (
  echo.
  echo Edicao publicada. Abrindo a postagem do Google, a imagem e o relatorio.
  start "" notepad "postagens\%HOJE%\postagem.md"
  if exist "postagens\%HOJE%\imagem-4x3.png" start "" "postagens\%HOJE%\imagem-4x3.png"
  if exist "radar_interno\%HOJE%-relatorio.md" start "" notepad "radar_interno\%HOJE%-relatorio.md"
  start "" "https://vendadeimoveisdealtopadrao.com.br/radar/%HOJE%/"
) else (
  echo.
  echo Nenhuma edicao nova hoje: semana sem novidade confirmada, ou algo travou. Leia o resumo acima.
  if exist "radar_interno\%HOJE%-relatorio.md" start "" notepad "radar_interno\%HOJE%-relatorio.md"
)

:fim
echo.
pause
endlocal

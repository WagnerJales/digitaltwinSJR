@echo off
REM ===========================================================================
REM  SJR-Geo - abre o aplicativo servido por HTTP.
REM
REM  Por que existe: web/index.html le os dados de data/processados por fetch,
REM  e o navegador BLOQUEIA fetch quando a pagina vem de file:// (duplo clique).
REM  Este atalho sobe um servidor local e abre o navegador ja no endereco certo.
REM
REM  Alternativa sem servidor: dist\SJR-Geo.html, que tem os dados
REM  embutidos e abre com duplo clique.
REM ===========================================================================
cd /d "%~dp0"
if not exist "data\processados\zoneamento.geojson" (
  echo.
  echo  Os dados ainda nao foram gerados.
  echo  Rode primeiro:  python pipeline\run_all.py
  echo.
  pause
  exit /b 1
)
echo.
echo  SJR-Geo - servindo em http://localhost:8080/web/
echo  Feche esta janela para encerrar o servidor.
echo.
start "" http://localhost:8080/web/
python -m http.server 8080

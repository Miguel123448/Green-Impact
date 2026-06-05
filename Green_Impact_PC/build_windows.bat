@echo off
setlocal

echo Instalando dependencias...
py -m pip install -r requirements.txt
py -m pip install pyinstaller

echo.
echo Limpando builds antigos...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul

echo.
echo Gerando GreenImpactServidor.exe...
py -m PyInstaller --onefile --name GreenImpactServidor --icon "assets\app_icon.ico" --add-data "data;data" --collect-submodules websockets server_entry.py

if errorlevel 1 (
    echo Erro ao gerar o servidor.
    pause
    exit /b 1
)

echo.
echo Gerando GreenImpactCliente.exe...
py -m PyInstaller --onefile --name GreenImpactCliente --icon "assets\app_icon.ico" --add-data "assets;assets" --add-data "data;data" --collect-submodules websockets --collect-submodules pygame --hidden-import green_impact.server client_entry.py

if errorlevel 1 (
    echo Erro ao gerar o cliente.
    pause
    exit /b 1
)

echo.
echo Pronto! Os executaveis estao na pasta dist:
echo - dist\GreenImpactServidor.exe
echo - dist\GreenImpactCliente.exe
echo.
pause

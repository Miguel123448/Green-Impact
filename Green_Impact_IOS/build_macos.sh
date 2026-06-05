#!/usr/bin/env bash
set -euo pipefail

# Execute este arquivo no macOS, dentro da pasta do projeto:
# chmod +x build_macos.sh
# ./build_macos.sh

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements_macos.txt

# Gera o aplicativo macOS em dist/Green Impact.app
python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name "Green Impact" \
  --icon "assets/app_icon.icns" \
  --add-data "assets:assets" \
  --add-data "data:data" \
  --collect-submodules websockets \
  --collect-data kivy \
  --hidden-import green_impact.server \
  main.py

# Gera também um executável separado do servidor, útil se quiser deixar
# o servidor rodando em um Mac e conectar de outros aparelhos.
python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --console \
  --name "GreenImpactServidor" \
  --icon "assets/app_icon.icns" \
  --add-data "data:data" \
  --collect-submodules websockets \
  server_entry.py

echo ""
echo "Build finalizado. Arquivos gerados:"
echo "- dist/Green Impact.app"
echo "- dist/GreenImpactServidor"
echo ""
echo "Para abrir o jogo: open \"dist/Green Impact.app\""
echo "Para abrir o servidor: ./dist/GreenImpactServidor --host 0.0.0.0 --port 8765"

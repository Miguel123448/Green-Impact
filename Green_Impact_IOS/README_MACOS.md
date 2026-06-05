# Green Impact — versão macOS

Esta versão foi ajustada para rodar e ser empacotada no macOS.

## O que foi adaptado

- O jogo agora localiza `assets/` e `data/` tanto no código-fonte quanto dentro de um app empacotado pelo PyInstaller.
- O servidor local também consegue encontrar os arquivos JSON das perguntas dentro do `.app`.
- Foi adicionado um script `build_macos.sh` para gerar:
  - `dist/Green Impact.app`
  - `dist/GreenImpactServidor`

## Testar no macOS sem compilar

No Terminal, entre na pasta do projeto e rode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements_macos.txt
python main.py
```

## Gerar o app macOS

```bash
chmod +x build_macos.sh
./build_macos.sh
```

Depois abra:

```bash
open "dist/Green Impact.app"
```

## Rodar servidor separado no macOS

O jogo já consegue abrir servidor local pelo menu. Mesmo assim, o build também gera um servidor separado:

```bash
./dist/GreenImpactServidor --host 0.0.0.0 --port 8765
```

Outros jogadores na mesma rede podem entrar usando o IP local do Mac e a porta `8765`.

## Observação sobre iOS

Compilar para iPhone/iPad não é a mesma coisa que gerar app para macOS. Para iOS ainda é necessário usar macOS + Xcode + kivy-ios, e provavelmente configurar dependências pelo projeto Xcode. Este pacote deixa o jogo pronto para macOS desktop; para iOS o empacotamento é outro.


## Ícone do aplicativo

Esta versão já inclui `assets/app_icon.png` e `assets/app_icon.icns`. O `build_macos.sh` usa `assets/app_icon.icns` no PyInstaller para gerar o `.app` com ícone.

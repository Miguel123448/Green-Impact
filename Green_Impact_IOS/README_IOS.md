# Green Impact — versão preparada para iOS/macOS com ícone

Esta pasta inclui a versão Kivy do Green Impact com o novo ícone em:

- `assets/app_icon.png`
- `assets/app_icon.icns`

## Importante

Para iOS, a compilação precisa ser feita em um Mac com Xcode e ferramentas do Kivy iOS. Este pacote deixa o código e os assets prontos, mas a geração do projeto Xcode/IPA deve ser feita no macOS.

## Testar no macOS sem empacotar

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements_macos.txt
python main.py
```

## Gerar .app para macOS

```bash
chmod +x build_macos.sh
./build_macos.sh
open "dist/Green Impact.app"
```

O script `build_macos.sh` já usa `assets/app_icon.icns` como ícone do `.app`.

## Base para iOS

Use este mesmo `main.py`, a pasta `assets/` e a pasta `data/` ao criar o projeto com `kivy-ios`. Depois, no Xcode, configure o ícone usando `assets/app_icon.png` ou gere os tamanhos exigidos pelo asset catalog do Xcode.

## Atualização: multijogador local e novo tabuleiro

Incluído modo **Multijogador local** para 2 a 4 jogadores no mesmo dispositivo, além do multijogador online com o novo tabuleiro (`assets/board_new.jpg`). O multijogador agora usa dado, casas de pergunta por dificuldade e casas de sorte/revés com símbolo de planta. O modo **Um jogador** mantém o tabuleiro original.

# Green Impact - versão Android refeita

Esta versão foi refeita para usar um HUD responsivo com rolagem, evitando sobreposição entre pergunta, alternativas, botões e histórico.

## O que mudou

- Menu principal: **Um jogador**, **Multijogador** e **Como jogar**.
- Layout da partida refeito com cards e ScrollView.
- Botões das respostas e ajudas maiores para toque no celular.
- Histórico separado no fim da tela, sem sobrepor a pergunta.
- Pausa antes de cada pergunta mantida.
- IP padrão: `147.15.100.214`.
- `buildozer.spec` ajustado conforme a configuração usada para compilar:

```ini
android.api = 35
android.minapi = 26
android.ndk = 28c
android.archs = arm64-v8a
```

## Testar no PC

```bash
python -m pip install -r requirements.txt
python main.py
```

## Gerar APK pelo WSL/Linux

```bash
python3 -m pip install --user buildozer cython
export PATH=$PATH:$HOME/.local/bin
buildozer android debug
```

O APK sai na pasta `bin/`.

## Observação

O modo **Um jogador** abre um servidor local no próprio aparelho. Para multiplayer, o servidor precisa estar aberto no IP informado e na porta `8765`, ou no endereço que você configurar no menu.


## Ícone do aplicativo

Esta versão já inclui `assets/app_icon.png`, configurado em `buildozer.spec` por `icon.filename = assets/app_icon.png`.

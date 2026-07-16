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

## Atualização: multijogador local e novo tabuleiro

Incluído modo **Multijogador local** para 2 a 4 jogadores no mesmo aparelho, além do multijogador online com o novo tabuleiro (`assets/board_new.jpg`). O multijogador agora usa dado, casas de pergunta por dificuldade e casas de sorte/revés com símbolo de planta. O modo **Um jogador** mantém o tabuleiro original.

## Configuração manual do servidor

No **Multijogador online**, toque ou clique na engrenagem ao lado de **Servidor**. Informe o IP/domínio e a porta, pressione **Salvar** e depois crie ou entre em uma sala. URLs completas `ws://` e `wss://` também são aceitas.

## Correção do HUD Android — engrenagem do servidor

A configuração manual foi implementada diretamente em `main.py`, que é a interface Kivy usada pelo APK. A engrenagem é desenhada pelo canvas do Kivy, sem depender do caractere Unicode `⚙`, e aparece no cabeçalho do **Multijogador online**, ao lado de **Servidor**.

Ao tocar nela, abre-se uma janela adaptada à resolução do aparelho com:

- IP ou domínio;
- porta;
- prévia da URL de conexão;
- validação da porta entre 1 e 65535;
- botões **Salvar**, **Usar padrão** e **Fechar**.

## Correção da área segura do Android — versão 0.3

Em celulares que exibem a barra de navegação na lateral durante o modo paisagem, o Android pode entregar ao Kivy a área física inteira da tela. Com `android.api = 35`, isso permite que a interface seja desenhada por baixo dos botões **Voltar**, **Início** e **Recentes**.

A versão 0.3 consulta os `WindowInsets` nativos do Android e reserva automaticamente espaço para:

- barra de navegação lateral ou inferior;
- barra de status;
- recorte/notch da tela;
- alterações de orientação e retorno do aplicativo ao primeiro plano.

A correção é dinâmica e funciona tanto com navegação por três botões quanto por gestos. A janela de configuração do servidor também usa as dimensões úteis da tela.


## Melhorias da versão 0.4

- Banner grande para identificar o jogador da vez.
- Respostas, ajudas e ação Parar em blocos visualmente diferentes.
- Saldo de carbono e custo das ajudas em destaque.
- Tela de consequência após acerto, erro, tempo esgotado, pular, parar e sorte/revés.
- Expiração do tempo controlada também pelo servidor, evitando tela parada.

## Frontend mobile 0.5 — mapa em tela cheia

A interface de partida do Android foi redesenhada para usar o tabuleiro em tela cheia. As ações aparecem em popups responsivos: lançamento de dado, preparação da pergunta, pergunta, ajudas, consequência e resultado final.

A barra superior mostra sala, jogador da vez, saldo de carbono e posição. A barra inferior permite reabrir a ação atual e consultar jogadores, histórico, regras ou voltar ao menu. O popup pode ser ocultado para visualizar o mapa e reaberto pelo botão **Ação/Pergunta**.

A área segura respeita barras do sistema, navegação por gestos e recortes/notches.

# Green Impact - versão PC

Esta versão adiciona um menu principal com três opções:

- **Um jogador**: abre um servidor local automaticamente e cria uma sala para jogar sozinho.
- **Multijogador online**: permite criar ou entrar em uma sala; a engrenagem abre a configuração manual de IP/domínio e porta.
- **Como jogar**: mostra as regras principais dentro do jogo.

## Rodar pelo Python

No Windows, dentro da pasta do projeto:

```powershell
py -m pip install -r requirements.txt
py -m green_impact.client
```

## Gerar executáveis no Windows

```powershell
.\build_windows.bat
```

Os executáveis serão criados em:

```text
dist\GreenImpactServidor.exe
dist\GreenImpactCliente.exe
```

Para a maioria dos testes, basta abrir o `GreenImpactCliente.exe` e usar o menu do próprio jogo.

## Multiplayer na mesma rede

No computador que vai hospedar a partida, escolha **Multijogador** e depois **Abrir servidor local e criar sala**.
Os outros jogadores devem abrir o cliente, escolher **Multijogador online**, clicar na **engrenagem**, preencher o IP mostrado na tela do host, a porta `8765`, salvar e informar o código da sala.

## IP padrão

A configuração aberta pela **engrenagem** vem preenchida por padrão com `147.15.100.214` e porta `8765`. Ela aceita IP, domínio ou uma URL completa `ws://`/`wss://`.
A opção **Abrir servidor local e criar sala** continua usando `127.0.0.1` internamente para conectar ao servidor aberto no próprio computador.


## Ícone do aplicativo

Esta versão já inclui `assets/app_icon.png` e `assets/app_icon.ico`. O `build_windows.bat` usa esse ícone ao gerar os executáveis com PyInstaller.

## Atualização: multijogador local e novo tabuleiro

Esta versão inclui:

- Modo **Multijogador local**, para 2 a 4 jogadores no mesmo dispositivo.
- Modo **Multijogador online** usando o novo tabuleiro (`assets/board_new.jpg`).
- Implementação de **dado** no multijogador: o jogador lança o dado e anda a quantidade sorteada.
- Casas 1 a 5: perguntas fáceis; casas 6 a 9: perguntas médias; casas 10 a 12: perguntas difíceis.
- Casas com símbolo de planta: eventos de **sorte/revés**, com bônus ou perda de créditos de carbono.
- O modo **Um jogador** permanece com o tabuleiro original e a regra anterior.

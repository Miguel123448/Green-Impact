# Green Impact v0.9.9

## Caixas de texto com altura dinâmica

Esta versão corrige situações em que textos maiores ultrapassavam os limites visuais de seus cartões ou botões.

### PC/Windows

- A quebra de texto passou a considerar a **largura real do texto renderizado em pixels**, em vez de estimar somente pela quantidade de caracteres.
- O cartão do enunciado da pergunta agora aumenta automaticamente de altura quando o texto ocupa mais linhas.
- As alternativas deixam de ser cortadas por limite de caracteres.
- Cada botão de resposta aumenta verticalmente conforme a quantidade de linhas necessária para mostrar a alternativa completa.
- A mesma lógica foi aplicada tanto ao modo clássico quanto ao tabuleiro com dado.
- Na tela de **gabarito**, o enunciado e as alternativas verde/vermelhas passam a calcular a altura usando a dimensão real da fonte, reduzindo casos em que o texto saía da caixa.
- A mensagem de espera do gabarito também passa a quebrar em linhas quando necessário.
- O cabeçalho da área de **Ajudas** pode crescer quando a mensagem de estado for maior, como nos casos de saldo insuficiente ou ajuda já usada na rodada.
- A área **Parar** também ajusta sua altura quando a descrição precisar ocupar mais de uma linha.
- Os botões do PC agora sabem quebrar automaticamente textos maiores dentro da largura disponível.

### Android e iOS/macOS

- Os botões do frontend Kivy agora ajustam automaticamente a própria altura de acordo com o tamanho do texto renderizado.
- Alternativas longas podem ocupar duas ou mais linhas sem ultrapassar o botão.
- Botões curtos mantêm a altura mínima original, evitando aumento desnecessário da interface.
- Os cartões de pergunta e gabarito continuam usando labels de altura dinâmica e passam a combinar com os novos botões autoajustáveis.

## Compatibilidade

- As regras introduzidas nas versões anteriores, incluindo o gabarito antes da consequência e o sorteio sem repetição até esgotar o nível, permanecem inalteradas.
- Esta versão altera apenas a camada visual dos clientes; o protocolo e as regras do servidor permanecem compatíveis com a v0.9.8.
- Se o servidor online já estiver atualizado para a v0.9.8, **não é necessário atualizar o servidor da Oracle apenas por causa desta correção visual**.

## Validação

- Compilação sintática validada para PC, Android e iOS/macOS.
- Testes adicionados para verificar caixas dinâmicas no PC e botões autoajustáveis no mobile.
- Testes anteriores de gabarito, perguntas sem repetição, multijogador, dica do especialista, Sorte/Revés, regras e configurações de vídeo mantidos.
- **47 testes direcionados das funcionalidades recentes foram aprovados.**

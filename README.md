# PyGame Raspberry — Titanic vs Icebergs + Memory

Este projeto é um mini arcade feito em **Python + PyGame** com integração a um **Raspberry Pi Pico W** usado como controle físico (dois botões).  
O programa roda no PC (Windows) e se comunica com o Pico via **porta serial USB**.

Há dois jogos em um só executável:

- **TITANIC vs ICEBERGS**  
  Um endless runner em que um navio precisa desviar de icebergs e coletar estrelas, com sistema de vidas, níveis de dificuldade e HUD com pontuação.
- **MEMORY**  
  Um jogo de memória tipo *Genius*, mas apenas com “CIMA” e “BAIXO”. A sequência é exibida na tela e o jogador deve reproduzir usando as setas do teclado ou os botões do Pico.

Ambos os jogos podem ser controlados tanto pelo teclado quanto pelos **dois botões físicos** conectados ao Pico.

---

## 1. Funcionalidades principais

### Titanic vs Icebergs

- Navio fixo na parte esquerda da tela, movimentando-se apenas **para cima e para baixo**.
- Icebergs surgem do lado direito e atravessam a tela para a esquerda.
- Estrelas aparecem entre os icebergs; ao coletar, o jogador ganha pontos.
- Sistema de **3 vidas** com ícones de coração.
- **10 níveis de dificuldade**: conforme a pontuação aumenta, os icebergs vêm mais rápido, o espaçamento diminui e o desafio cresce.
- Hitbox do navio reduzida (20%) e hitbox dos icebergs extremamente fina na horizontal (1% da largura visual) para deixar a jogabilidade mais justa.
- Tela de **Game Over** com pontuação final, nível alcançado e opções de recomeçar ou voltar ao menu principal.

### Memory

- Cada nível gera uma sequência aleatória de “CIMA” (`U`) e “BAIXO` (`D`).
- Fase 1: a sequência é exibida na tela com **triângulos animados** subindo (setas).  
  Não aparece texto com a sequência, apenas a animação.
- Fase 2: o jogador deve repetir a sequência.  
  A cada clique válido, surge uma seta estática na linha central, na ordem em que ele aperta.
- Quando o número de entradas do jogador iguala o tamanho da sequência:
  - Se estiver **correta**: aparece uma tela rápida “Correto! Próximo nível…”, mostrando a sequência correta e a digitada, todas em verde; o nível aumenta.
  - Se estiver **errada**: tela de **Game Over – Memory**, mostrando:
    - linha de cima: sequência correta;
    - linha de baixo: sequência digitada;
    - posições erradas destacadas em vermelho;
    - instruções para recomeçar ou voltar ao menu principal.
- Registro de **recorde de nível** (melhor nível já alcançado).
- Debounce de **200 ms** na leitura dos botões do Pico para evitar múltiplos cliques indesejados (bounce).

---

## 2. Arquitetura geral

O projeto tem duas partes:

1. **Código no PC (Python/PyGame)**  
   - Arquivo principal: `src/main.py`  
   - Usa:
     - `pygame` para gráficos, input de teclado e loop do jogo;
     - `pyserial` para ler bytes enviados pelo Pico (`'U'` para cima, `'D'` para baixo);
   - Abre uma janela 960x540, renderiza o fundo, os sprites, o HUD e gerencia os estados:
     - `mode_select` (menu principal: escolher TITANIC ou MEMORY);
     - `titanic_menu`, `titanic_playing`, `titanic_game_over`;
     - `memory_ready`, `memory_show`, `memory_input`, `memory_success`, `memory_game_over`.

2. **Código no Raspberry Pi Pico W (MicroPython)**  
   - Pico atua como um **controle simples** de dois botões:
     - GP14 = CIMA  
     - GP15 = BAIXO
   - Cada botão é configurado como entrada com **resistor de pull-up interno**  
     (`Pin.IN, Pin.PULL_UP`).
   - Os botões ligam o pino ao **GND** quando pressionados.
   - O script no Pico fica em um loop lendo os GPIOs; quando detecta transição 1 → 0:
     - envia `'U'` pela serial se o GP14 foi pressionado;
     - envia `'D'` pela serial se o GP15 foi pressionado.

O PyGame, no PC, combina essas entradas do Pico com as teclas do teclado (W/S ou ↑/↓) para comandar o navio ou o jogo de memória.

---

## 3. Hardware necessário

- 1x **Raspberry Pi Pico W** (ou Pico comum, se estiver usando MicroPython com USB-serial).
- 1x **protoboard**.
- 2x **botões de pressão (push button)** de 4 pinos.
- 3 ou mais **jumpers macho–macho** (recomendável usar alguns extras para organizar o layout).
- Cabo **micro-USB** para ligar o Pico ao computador.

---

## 4. Montagem do circuito (resumo)

1. Posicione o Raspberry Pi Pico W **centralizado na protoboard**, de forma que cada fileira de pinos fique em uma trilha separada.
2. Conecte os botões:
   - Primeiro botão (CIMA) em uma linha da protoboard;
   - Segundo botão (BAIXO) em outra linha abaixo.
   - Em cada botão, use os dois pinos de um lado (vertical) ligados à mesma trilha, e os dois do outro lado na trilha seguinte (como é padrão de push button).
3. Ligue os GPIOs:
   - Um jumper de **GP14** do Pico até um lado do botão de CIMA.
   - Um jumper de **GP15** do Pico até um lado do botão de BAIXO.
4. Ligue o GND:
   - Do outro lado de cada botão, ligue à mesma linha de **GND** da protoboard.
   - Essa linha de GND é conectada a um pino GND do Pico (por exemplo, o GND físico 38).
5. No código do Pico, os pinos GP14 e GP15 são configurados com `Pin.PULL_UP`, então o botão simplesmente **fecha o circuito para GND** quando pressionado.

Se o teste de botões no Thonny imprimir “UP pressionado” / “DOWN pressionado” de forma consistente, a parte de hardware está correta.

---

## 5. Estrutura de pastas do projeto

```text
pygame_raspberry/
├─ .venv/                  # ambiente virtual Python (local)
├─ assets/
│  ├─ background.png       # fundo (mar, céu etc.)
│  ├─ ship.png             # sprite do navio
│  ├─ iceberg.png          # sprite de iceberg
│  ├─ star.png             # estrela (pontuação)
│  ├─ heart.png            # coração (vida cheia)
│  └─ deadheart.png        # coração vazio (vida perdida)
├─ src/
│  └─ main.py              # jogo principal (TITANIC + MEMORY)
├─ run_pygame_raspberry.ps1  # script de atalho para rodar o jogo (opcional)
└─ README.md

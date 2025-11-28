# file: src/main.py
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pygame

# --- Configuração geral ---
WIDTH, HEIGHT = 960, 540
FPS = 60

HUD_BLUE = (8, 35, 90)
HUD_TEXT = (220, 230, 255)
WHITE = (240, 240, 255)
RED = (230, 60, 80)

# Titanic
PIPE_WIDTH = 120
PIPE_GAP_BASE = 220
PIPE_BASE_SPEED = 4.0
PIPE_SPAWN_BASE_MS = 1500

PLAYER_SPEED = 4.5
PLAYER_MARGIN_TOP_BOTTOM = 20
INITIAL_LIVES = 3

# Serial Pico
SERIAL_BAUDRATE = 115200
SERIAL_FALLBACK_PORT = "COM3"
SERIAL_DEBUG = False

# Assets
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
BACKGROUND_IMAGE_NAME = "background.png"
SHIP_IMAGE_NAME = "ship.png"
ICEBERG_IMAGE_NAME = "iceberg.png"
STAR_IMAGE_NAME = "star.png"
HEART_IMAGE_NAME = "heart.png"
DEADHEART_IMAGE_NAME = "deadheart.png"

# Hitboxes
ICEBERG_HITBOX_SCALE_X = 0.01
PLAYER_HITBOX_SHRINK = 0.2

# MEMORY
MEM_SHOW_MS = 650
MEM_GAP_MS = 350
MEM_DEBOUNCE_MS = 200

# Serial libs (se existirem)
try:
    import serial  # type: ignore
    import serial.tools.list_ports as list_ports  # type: ignore
except Exception:
    serial = None
    list_ports = None


# =========================
#   Modelos de jogo
# =========================
@dataclass
class Player:
    image: pygame.Surface
    rect: pygame.Rect

    def update(self, move_up: bool, move_down: bool, dt: float) -> None:
        dy = 0.0
        if move_up:
            dy -= PLAYER_SPEED * dt
        if move_down:
            dy += PLAYER_SPEED * dt
        self.rect.y += int(round(dy))

        if self.rect.top < PLAYER_MARGIN_TOP_BOTTOM:
            self.rect.top = PLAYER_MARGIN_TOP_BOTTOM
        if self.rect.bottom > HEIGHT - PLAYER_MARGIN_TOP_BOTTOM:
            self.rect.bottom = HEIGHT - PLAYER_MARGIN_TOP_BOTTOM

    def draw(self, surf: pygame.Surface) -> None:
        surf.blit(self.image, self.rect)

    def collision_rect(self) -> pygame.Rect:
        r = self.rect.copy()
        shrink_w = int(r.width * PLAYER_HITBOX_SHRINK)
        shrink_h = int(r.height * PLAYER_HITBOX_SHRINK)
        return r.inflate(-shrink_w, -shrink_h)


@dataclass
class IcebergPair:
    x: float
    gap_y: float
    width: int
    gap: int
    passed: bool = False
    star_y: Optional[float] = None
    star_collected: bool = False

    def rects(self) -> Tuple[pygame.Rect, pygame.Rect]:
        top_height = int(self.gap_y - self.gap / 2)
        bottom_y = int(self.gap_y + self.gap / 2)
        bottom_height = HEIGHT - bottom_y
        top_rect = pygame.Rect(int(self.x), 0, self.width, top_height)
        bottom_rect = pygame.Rect(int(self.x), bottom_y, self.width, bottom_height)
        return top_rect, bottom_rect

    def collision_rects(self) -> Tuple[pygame.Rect, pygame.Rect]:
        top_rect, bottom_rect = self.rects()

        def shrink_x(rect: pygame.Rect) -> pygame.Rect:
            new_w = int(rect.width * ICEBERG_HITBOX_SCALE_X)
            if new_w <= 0:
                return rect
            shrink_total = rect.width - new_w
            return rect.inflate(-shrink_total, 0)

        return shrink_x(top_rect), shrink_x(bottom_rect)

    def update(self, speed: float, dt: float) -> None:
        self.x -= speed * dt

    def is_off_screen(self) -> bool:
        return self.x + self.width < -10

    def star_rect(self, star_img: pygame.Surface) -> Optional[pygame.Rect]:
        if self.star_y is None or self.star_collected:
            return None
        r = star_img.get_rect()
        r.centerx = int(self.x + self.width / 2)
        r.centery = int(self.star_y)
        return r

    def draw_icebergs(self, surf: pygame.Surface, iceberg_img: pygame.Surface) -> None:
        top_rect, bottom_rect = self.rects()
        if top_rect.height > 0:
            top_sprite = pygame.transform.smoothscale(iceberg_img, top_rect.size)
            top_sprite = pygame.transform.flip(top_sprite, False, True)
            surf.blit(top_sprite, top_rect)
        if bottom_rect.height > 0:
            bottom_sprite = pygame.transform.smoothscale(iceberg_img, bottom_rect.size)
            surf.blit(bottom_sprite, bottom_rect)


# =========================
#   Utilidades
# =========================
def compute_level(score: int) -> int:
    return max(1, min(10, score // 5 + 1))


def detect_pico_port() -> Optional[str]:
    if serial is None or list_ports is None:
        return None
    for p in list_ports.comports():
        desc = (p.description or "").lower()
        if "pico" in desc or "rp2040" in desc or "board" in desc:
            return p.device
    if SERIAL_FALLBACK_PORT:
        return SERIAL_FALLBACK_PORT
    return None


def open_pico_serial() -> Optional["serial.Serial"]:
    if serial is None:
        return None
    port = detect_pico_port()
    if not port:
        return None
    try:
        ser = serial.Serial(port, SERIAL_BAUDRATE, timeout=0)
        print(f"[INFO] Conectado ao Pico na porta {port}.")
        return ser
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Falha ao abrir porta {port}: {exc}")
        return None


def read_pico_flags(ser: Optional["serial.Serial"]) -> Tuple[bool, bool]:
    if ser is None:
        return False, False
    try:
        data = ser.read(64)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Erro na serial: {exc}")
        return False, False
    if not data:
        return False, False
    if SERIAL_DEBUG:
        print(f"[RAW SERIAL] {data!r}")
    up = b"U" in data
    down = b"D" in data
    return up, down


def load_image(
    name: str,
    size: Optional[Tuple[int, int]] = None,
    *,
    convert_alpha: bool = True,
) -> pygame.Surface:
    path = ASSETS_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Imagem não encontrada: {path}\n"
            f"Crie a pasta 'assets' e salve o arquivo como '{name}'."
        )
    img = pygame.image.load(str(path))
    img = img.convert_alpha() if convert_alpha else img.convert()
    if size is not None:
        img = pygame.transform.smoothscale(img, size)
    return img


def create_player(ship_image: pygame.Surface) -> Player:
    target_h = 64
    aspect = ship_image.get_width() / ship_image.get_height()
    size = (int(target_h * aspect), target_h)
    img = pygame.transform.smoothscale(ship_image, size)
    rect = img.get_rect()
    rect.centerx = WIDTH // 4
    rect.centery = HEIGHT // 2
    return Player(img, rect)


def create_iceberg_pair(
    gap_y: float,
    gap: int,
    star_img: pygame.Surface,
) -> IcebergPair:
    star_margin = star_img.get_height() // 2 + 8
    top_limit = gap_y - gap / 2 + star_margin
    bottom_limit = gap_y + gap / 2 - star_margin
    if top_limit >= bottom_limit:
        star_y = gap_y
    else:
        star_y = random.uniform(top_limit, bottom_limit)
    return IcebergPair(
        x=float(WIDTH + 40),
        gap_y=float(gap_y),
        width=PIPE_WIDTH,
        gap=gap,
        star_y=star_y,
    )


def reset_titanic(ship_image: pygame.Surface):
    player = create_player(ship_image)
    icebergs: list[IcebergPair] = []
    score = 0
    next_spawn = float(pygame.time.get_ticks() + 1000)
    lives_left = INITIAL_LIVES
    return player, icebergs, score, next_spawn, lives_left


# ----- MEMORY: desenho de setas -----
def draw_memory_arrow(surface: pygame.Surface, direction: str, progress: float) -> None:
    """Seta animada (subindo) para mostrar a sequência."""
    progress = max(0.0, min(1.0, progress))
    x = WIDTH // 2
    size = 60
    start_y = HEIGHT + size
    end_y = HEIGHT // 2
    y = int(start_y + (end_y - start_y) * progress)
    color = (250, 250, 255)
    if direction == "U":
        pts = [
            (x, y - size // 2),
            (x - size // 3, y + size // 3),
            (x + size // 3, y + size // 3),
        ]
    else:
        pts = [
            (x, y + size // 2),
            (x - size // 3, y - size // 3),
            (x + size // 3, y - size // 3),
        ]
    pygame.draw.polygon(surface, color, pts)


def draw_memory_seq_row(
    surface: pygame.Surface,
    seq: list[str],
    y: int,
    mismatch: Optional[list[int]] = None,
    all_green: bool = False,
) -> None:
    """Desenha uma linha de setas estáticas (para mostrar resposta / comparação)."""
    if mismatch is None:
        mismatch_set: set[int] = set()
    else:
        mismatch_set = set(mismatch)

    gap = 70
    size = 40
    total_w = (len(seq) - 1) * gap if seq else 0
    start_x = WIDTH // 2 - total_w // 2

    for i, d in enumerate(seq):
        x = start_x + i * gap

        if all_green:
            color = (0, 230, 120)
        elif i in mismatch_set:
            color = (230, 70, 90)
        else:
            color = (240, 240, 255)

        if d == "U":
            pts = [
                (x, y - size // 2),
                (x - size // 3, y + size // 3),
                (x + size // 3, y + size // 3),
            ]
        else:
            pts = [
                (x, y + size // 2),
                (x - size // 3, y - size // 3),
                (x + size // 3, y - size // 3),
            ]
        pygame.draw.polygon(surface, color, pts)


# =========================
#   Loop principal
# =========================
def main() -> None:
    pygame.init()
    pygame.display.set_caption("PyGame Raspberry  Titanic + Memory")

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    font_small = pygame.font.SysFont("consolas", 18)
    font_main = pygame.font.SysFont("consolas", 28)
    font_big = pygame.font.SysFont("consolas", 60, bold=True)

    # Imagens
    bg_img = load_image(BACKGROUND_IMAGE_NAME, (WIDTH, HEIGHT), convert_alpha=False)
    ship_raw = load_image(SHIP_IMAGE_NAME)
    iceberg_raw = load_image(ICEBERG_IMAGE_NAME)
    star_img = load_image(STAR_IMAGE_NAME, (32, 32), convert_alpha=True)
    heart_img = load_image(HEART_IMAGE_NAME, (28, 28), convert_alpha=True)
    deadheart_img = load_image(DEADHEART_IMAGE_NAME, (28, 28), convert_alpha=True)

    # Transparência nos corações (usa cor do canto como key)
    for img in (heart_img, deadheart_img):
        corner_color = img.get_at((0, 0))
        img.set_colorkey(corner_color)

    bg_x = 0.0

    # Serial
    pico_serial = open_pico_serial()

    # Titanic
    player, icebergs, score, next_spawn, lives_left = reset_titanic(ship_raw)

    # Memory
    mem_level = 1
    mem_best_level = 0
    mem_sequence: list[str] = []
    mem_show_index = 0
    mem_showing_arrow = False
    mem_last_change = 0
    mem_player_inputs: list[str] = []
    mem_last_input_time = 0
    mem_mismatch_positions: list[int] = []

    # Estado global
    state = "mode_select"  # mode_select, titanic_*, memory_*
    prev_move_up = False
    prev_move_down = False

    running = True
    while running:
        dt_ms = clock.tick(FPS)
        dt = dt_ms / 16.6667

        move_up = move_down = False

        # Eventos
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                if state == "titanic_game_over":
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_r):
                        player, icebergs, score, next_spawn, lives_left = reset_titanic(
                            ship_raw
                        )
                        state = "titanic_playing"
                    elif event.key == pygame.K_m:
                        state = "mode_select"

                elif state == "memory_game_over":
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_r):
                        mem_level = 1
                        mem_sequence = []
                        mem_show_index = 0
                        mem_showing_arrow = False
                        mem_last_change = 0
                        mem_player_inputs = []
                        mem_last_input_time = 0
                        mem_mismatch_positions = []
                        state = "memory_ready"
                    elif event.key == pygame.K_m:
                        state = "mode_select"

        # Teclado contínuo
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move_up = True
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move_down = True

        # Pico
        pico_up, pico_down = read_pico_flags(pico_serial)
        move_up = move_up or pico_up
        move_down = move_down or pico_down

        # Borda de subida (press) para MEMORY
        pressed_up = move_up and not prev_move_up
        pressed_down = move_down and not prev_move_down

        # ========= Lógica de estados =========
        if state == "mode_select":
            # Escolha: CIMA => Titanic, BAIXO => Memory
            if move_up:
                player, icebergs, score, next_spawn, lives_left = reset_titanic(
                    ship_raw
                )
                state = "titanic_menu"
            elif move_down:
                mem_level = 1
                mem_sequence = []
                mem_show_index = 0
                mem_showing_arrow = False
                mem_last_change = 0
                mem_player_inputs = []
                mem_last_input_time = 0
                mem_mismatch_positions = []
                state = "memory_ready"

        # ----- Titanic -----
        elif state == "titanic_menu":
            if keys[pygame.K_SPACE] or keys[pygame.K_RETURN] or move_up or move_down:
                state = "titanic_playing"

        elif state == "titanic_playing":
            level = compute_level(score)

            # Player
            player.update(move_up, move_down, dt)

            # Dificuldade
            gap = max(140, int(PIPE_GAP_BASE - (level - 1) * 8))
            speed = PIPE_BASE_SPEED + (level - 1) * 0.45
            spawn_interval_ms = max(700, int(PIPE_SPAWN_BASE_MS - (level - 1) * 80))

            now = pygame.time.get_ticks()
            if now >= next_spawn:
                gap_y = random.randint(140, HEIGHT - 140)
                icebergs.append(create_iceberg_pair(gap_y, gap, star_img))
                next_spawn = now + spawn_interval_ms

            for ib in icebergs:
                ib.update(speed, dt)
            icebergs = [ib for ib in icebergs if not ib.is_off_screen()]

            # Colisão
            hit = False
            pcb = player.collision_rect()
            for ib in icebergs:
                t_rect, b_rect = ib.collision_rects()
                if pcb.colliderect(t_rect) or pcb.colliderect(b_rect):
                    hit = True
                    break

            if not hit and (player.rect.top <= 0 or player.rect.bottom >= HEIGHT):
                hit = True

            if hit:
                lives_left -= 1
                if lives_left <= 0:
                    state = "titanic_game_over"
                else:
                    player = create_player(ship_raw)
                    icebergs.clear()
                    next_spawn = float(pygame.time.get_ticks() + 1000)

            # Estrelas
            if state == "titanic_playing":
                for ib in icebergs:
                    star_rect = ib.star_rect(star_img)
                    if star_rect and player.rect.colliderect(star_rect):
                        ib.star_collected = True
                        score += 1

        elif state == "titanic_game_over":
            pass

        # ----- MEMORY -----
        elif state == "memory_ready":
            # gera nova sequência
            mem_sequence = [random.choice(["U", "D"]) for _ in range(mem_level)]
            mem_show_index = 0
            mem_showing_arrow = True
            mem_last_change = pygame.time.get_ticks()
            mem_player_inputs = []
            mem_mismatch_positions = []
            state = "memory_show"

        elif state == "memory_show":
            now = pygame.time.get_ticks()
            if mem_showing_arrow:
                if now - mem_last_change >= MEM_SHOW_MS:
                    mem_showing_arrow = False
                    mem_last_change = now
            else:
                if now - mem_last_change >= MEM_GAP_MS:
                    mem_show_index += 1
                    if mem_show_index >= len(mem_sequence):
                        mem_player_inputs = []
                        state = "memory_input"
                    else:
                        mem_showing_arrow = True
                        mem_last_change = now

        elif state == "memory_input":
            # Coleta entradas, mas só avalia depois de completar toda a sequência
            now = pygame.time.get_ticks()
            step = None
            if now - mem_last_input_time >= MEM_DEBOUNCE_MS:
                if pressed_up:
                    step = "U"
                elif pressed_down:
                    step = "D"

            if step is not None:
                mem_last_input_time = now
                mem_player_inputs.append(step)

                if len(mem_player_inputs) >= len(mem_sequence):
                    mismatch = [
                        i
                        for i in range(len(mem_sequence))
                        if mem_player_inputs[i] != mem_sequence[i]
                    ]
                    if mismatch:
                        mem_mismatch_positions = mismatch
                        last_success = mem_level - 1
                        if last_success < 0:
                            last_success = 0
                        mem_best_level = max(mem_best_level, last_success)
                        state = "memory_game_over"
                    else:
                        mem_best_level = max(mem_best_level, mem_level)
                        mem_level += 1
                        mem_last_change = now
                        state = "memory_success"

        elif state == "memory_success":
            # Tela rápida de "Correto!" antes do próximo nível
            now = pygame.time.get_ticks()
            if now - mem_last_change >= 1000:
                state = "memory_ready"

        elif state == "memory_game_over":
            pass

        # =========================
        #   DESENHO
        # =========================
        # Fundo
        bg_x -= 0.3 * dt
        if bg_x <= -WIDTH:
            bg_x += WIDTH
        screen.blit(bg_img, (int(bg_x), 0))
        screen.blit(bg_img, (int(bg_x) + WIDTH, 0))

        # ----- Titanic draw -----
        if state in ("titanic_menu", "titanic_playing", "titanic_game_over"):
            for ib in icebergs:
                ib.draw_icebergs(screen, iceberg_raw)
                s_rect = ib.star_rect(star_img)
                if s_rect:
                    screen.blit(star_img, s_rect)

            player.draw(screen)

            level = compute_level(score)
            hud_rect = pygame.Rect(10, 10, 260, 60)
            pygame.draw.rect(screen, HUD_BLUE, hud_rect, border_radius=12)

            text_score = font_main.render(f"Pontos: {score}", True, HUD_TEXT)
            text_level = font_small.render(f"Nível: {level}/10", True, HUD_TEXT)
            screen.blit(text_score, (20, 16))
            screen.blit(text_level, (20, 40))

            # Vidas
            heart_w = heart_img.get_width()
            spacing = 8
            for i in range(INITIAL_LIVES):
                img = heart_img if i < lives_left else deadheart_img
                x = WIDTH - (i + 1) * (heart_w + spacing) + spacing
                y = 14
                screen.blit(img, (x, y))

            if state == "titanic_menu":
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 170))
                screen.blit(overlay, (0, 0))

                title = font_big.render("TITANIC", True, WHITE)
                line1 = font_main.render(
                    "Desvie dos icebergs e colete estrelas!",
                    True,
                    WHITE,
                )
                line2 = font_small.render(
                    "W/S, / ou botões do Pico.",
                    True,
                    HUD_TEXT,
                )
                line3 = font_small.render(
                    "ESPAÇO / ENTER / botão para começar.",
                    True,
                    HUD_TEXT,
                )
                line4 = font_small.render(
                    "M para voltar ao menu principal.",
                    True,
                    HUD_TEXT,
                )

                screen.blit(
                    title,
                    (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 110),
                )
                screen.blit(
                    line1,
                    (WIDTH // 2 - line1.get_width() // 2, HEIGHT // 2 - 40),
                )
                screen.blit(
                    line2,
                    (WIDTH // 2 - line2.get_width() // 2, HEIGHT // 2),
                )
                screen.blit(
                    line3,
                    (WIDTH // 2 - line3.get_width() // 2, HEIGHT // 2 + 40),
                )
                screen.blit(
                    line4,
                    (WIDTH // 2 - line4.get_width() // 2, HEIGHT // 2 + 80),
                )

            elif state == "titanic_game_over":
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 180))
                screen.blit(overlay, (0, 0))

                level_final = compute_level(score)

                title = font_big.render("GAME OVER  TITANIC", True, RED)
                txt_score = font_main.render(f"Pontos: {score}", True, WHITE)
                txt_level = font_main.render(
                    f"Nível alcançado: {level_final}/10",
                    True,
                    WHITE,
                )
                txt_lives = font_small.render("Vidas esgotadas!", True, HUD_TEXT)
                txt_restart = font_small.render(
                    "ESPAÇO / ENTER / R para recomeçar",
                    True,
                    HUD_TEXT,
                )
                txt_menu = font_small.render(
                    "M para voltar ao menu principal  |  ESC para sair",
                    True,
                    HUD_TEXT,
                )

                screen.blit(
                    title,
                    (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 120),
                )
                screen.blit(
                    txt_score,
                    (WIDTH // 2 - txt_score.get_width() // 2, HEIGHT // 2 - 50),
                )
                screen.blit(
                    txt_level,
                    (WIDTH // 2 - txt_level.get_width() // 2, HEIGHT // 2 - 10),
                )
                screen.blit(
                    txt_lives,
                    (WIDTH // 2 - txt_lives.get_width() // 2, HEIGHT // 2 + 20),
                )
                screen.blit(
                    txt_restart,
                    (WIDTH // 2 - txt_restart.get_width() // 2, HEIGHT // 2 + 50),
                )
                screen.blit(
                    txt_menu,
                    (WIDTH // 2 - txt_menu.get_width() // 2, HEIGHT // 2 + 80),
                )

        # ----- MEMORY draw -----
        elif state in (
            "memory_ready",
            "memory_show",
            "memory_input",
            "memory_success",
            "memory_game_over",
        ):
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            screen.blit(overlay, (0, 0))

            title = font_big.render("MEMORY", True, WHITE)
            screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 60))

            txt_level = font_main.render(f"Nível: {mem_level}", True, HUD_TEXT)
            txt_best = font_small.render(f"Recorde: {mem_best_level}", True, HUD_TEXT)
            screen.blit(txt_level, (WIDTH // 2 - txt_level.get_width() // 2, 140))
            screen.blit(txt_best, (WIDTH // 2 - txt_best.get_width() // 2, 180))

            if state == "memory_show":
                if mem_showing_arrow and mem_show_index < len(mem_sequence):
                    now = pygame.time.get_ticks()
                    elapsed = now - mem_last_change
                    progress = min(1.0, max(0.0, elapsed / MEM_SHOW_MS))
                    direction = mem_sequence[mem_show_index]
                    draw_memory_arrow(screen, direction, progress)

                desc = font_small.render(
                    "Memorize a sequência de setas.",
                    True,
                    WHITE,
                )
                screen.blit(desc, (WIDTH // 2 - desc.get_width() // 2, HEIGHT - 80))

            elif state == "memory_input":
                desc = font_small.render(
                    "Sua vez! Use botões do Pico ou W/S, /.",
                    True,
                    WHITE,
                )
                screen.blit(desc, (WIDTH // 2 - desc.get_width() // 2, HEIGHT - 80))
                # Mostra apenas o que o jogador já digitou
                draw_memory_seq_row(screen, mem_player_inputs, HEIGHT // 2)

            elif state == "memory_success":
                desc = font_small.render("Correto! Próximo nível...", True, WHITE)
                screen.blit(desc, (WIDTH // 2 - desc.get_width() // 2, HEIGHT - 80))
                draw_memory_seq_row(
                    screen,
                    mem_sequence,
                    HEIGHT // 2 - 30,
                    all_green=True,
                )
                draw_memory_seq_row(
                    screen,
                    mem_player_inputs,
                    HEIGHT // 2 + 30,
                    all_green=True,
                )

            elif state == "memory_game_over":
                overlay2 = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay2.fill((0, 0, 0, 200))
                screen.blit(overlay2, (0, 0))

                last_success = max(0, mem_level - 1)

                title_go = font_big.render("GAME OVER  MEMORY", True, RED)
                txt_last = font_main.render(
                    f"Nível alcançado: {last_success}",
                    True,
                    WHITE,
                )
                txt_best2 = font_main.render(
                    f"Recorde: {mem_best_level}",
                    True,
                    WHITE,
                )
                txt_info = font_small.render(
                    "Cima: sequência correta  |  Baixo: sua sequência (erros em vermelho)",
                    True,
                    HUD_TEXT,
                )
                txt_restart = font_small.render(
                    "ESPAÇO / ENTER / R para recomeçar MEMORY",
                    True,
                    HUD_TEXT,
                )
                txt_menu = font_small.render(
                    "M para voltar ao menu principal  |  ESC para sair",
                    True,
                    HUD_TEXT,
                )

                screen.blit(
                    title_go,
                    (WIDTH // 2 - title_go.get_width() // 2, HEIGHT // 2 - 130),
                )
                screen.blit(
                    txt_last,
                    (WIDTH // 2 - txt_last.get_width() // 2, HEIGHT // 2 - 60),
                )
                screen.blit(
                    txt_best2,
                    (WIDTH // 2 - txt_best2.get_width() // 2, HEIGHT // 2 - 25),
                )
                screen.blit(
                    txt_info,
                    (WIDTH // 2 - txt_info.get_width() // 2, HEIGHT // 2 + 5),
                )

                # Sequência correta vs digitada (erros em vermelho)
                draw_memory_seq_row(
                    screen,
                    mem_sequence,
                    HEIGHT // 2 + 50,
                    mismatch=mem_mismatch_positions,
                )
                draw_memory_seq_row(
                    screen,
                    mem_player_inputs,
                    HEIGHT // 2 + 110,
                    mismatch=mem_mismatch_positions,
                )

                screen.blit(
                    txt_restart,
                    (WIDTH // 2 - txt_restart.get_width() // 2, HEIGHT // 2 + 150),
                )
                screen.blit(
                    txt_menu,
                    (WIDTH // 2 - txt_menu.get_width() // 2, HEIGHT // 2 + 180),
                )

            else:  # memory_ready
                desc = font_small.render(
                    "Preparando próxima sequência...",
                    True,
                    WHITE,
                )
                screen.blit(desc, (WIDTH // 2 - desc.get_width() // 2, HEIGHT - 80))

        # ----- Menu principal (modo) -----
        if state == "mode_select":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 190))
            screen.blit(overlay, (0, 0))

            title = font_big.render("ESCOLHA O JOGO", True, WHITE)
            opt1 = font_main.render("CIMA (W /  / GP14)    TITANIC", True, HUD_TEXT)
            opt2 = font_main.render("BAIXO (S /  / GP15)   MEMORY", True, HUD_TEXT)
            info = font_small.render("ESC para sair", True, HUD_TEXT)

            screen.blit(
                title,
                (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 120),
            )
            screen.blit(
                opt1,
                (WIDTH // 2 - opt1.get_width() // 2, HEIGHT // 2 - 20),
            )
            screen.blit(
                opt2,
                (WIDTH // 2 - opt2.get_width() // 2, HEIGHT // 2 + 20),
            )
            screen.blit(
                info,
                (WIDTH // 2 - info.get_width() // 2, HEIGHT // 2 + 80),
            )

        pygame.display.flip()

        # Atualiza flags de "pressed"
        prev_move_up = move_up
        prev_move_down = move_down

    if pico_serial is not None:
        try:
            pico_serial.close()
        except Exception:
            pass

    pygame.quit()


if __name__ == "__main__":
    main()

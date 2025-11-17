#!/usr/bin/env python3
# Ultra Mario 2D Bros (Sim) — Pygame single-file edition
# One window, one file. No external assets. 32 original procedurally generated levels.
# Controls: Left/Right to move • Z or Space to jump • R to reset • [ / ] to prev/next level
# Menu: "ULTRA MARIO 2D BROS — Press Z or Space" (string only; no Nintendo assets are used).

import sys, math, random, pygame

WIDTH, HEIGHT = 960, 540
TILE = 32
GRAVITY = 1800.0
MOVE_SPEED = 240.0
JUMP_VELOCITY = -680.0
MAX_FALL = 1200.0
FPS = 60

# Colors
COL_BG_TOP = (147, 197, 253)
COL_BG_BOTTOM = (96, 165, 250)
COL_BLOCK_DARK = (15, 23, 42)
COL_BLOCK_LIGHT = (31, 41, 55)
COL_SPIKE = (239, 68, 68)
COL_PLAYER_OUT = (17, 24, 39)
COL_PLAYER = (34, 211, 238)
COL_UI = (233, 238, 241)
COL_UI_PANEL = (0, 0, 0, 160)

def clamp(a, lo, hi):
    return lo if a < lo else hi if a > hi else a

class Level:
    def __init__(self, idx, width, height, rows, start, exit):
        self.idx = idx
        self.width = width
        self.height = height
        self.rows = rows  # list[str]
        self.start = start  # (x, y) tile coords
        self.exit = exit    # (x, y) tile coords

    def tile(self, x, y):
        if y < 0 or y >= self.height or x < 0 or x >= self.width:
            return ' '
        return self.rows[y][x]

    def is_solid(self, x, y):
        return self.tile(x, y) == '#'

    def is_hazard(self, x, y):
        return self.tile(x, y) == 'X'

def mulberry_seed(idx):
    # Deterministic seed per level
    return 0xC0FFEE + idx * 1337

def generate_levels():
    H = 18
    MIN_W, MAX_W = 80, 150
    levels = []
    for i in range(32):
        difficulty = i
        W = min(MIN_W + i*3, MAX_W)
        rng = random.Random(mulberry_seed(i))
        # grid as list[list[str]]
        grid = [[' ' for _ in range(W)] for __ in range(H)]
        # ground
        for x in range(W):
            grid[H-1][x] = '#'
        # start and end safe runways
        for x in range(1, 9):
            grid[H-2][x] = ' '
            grid[H-1][x] = '#'
        for x in range(W-10, W-2):
            grid[H-2][x] = ' '
            grid[H-1][x] = '#'
        # place gaps in ground
        reserved = 10
        used = []
        gap_count = min(2 + int(difficulty * 1.2), max(2, W//7))
        for _ in range(gap_count):
            tries = 0
            while tries < 100:
                tries += 1
                w = min(2 + difficulty//4 + rng.randint(0,2), 6)
                x = rng.randint(reserved, W - reserved - w - 1)
                # avoid overlap
                conflict = False
                for gx, gw in used:
                    if x <= gx + gw + 3 and gx <= x + w + 3:
                        conflict = True
                        break
                if not conflict:
                    used.append((x, w))
                    for k in range(w):
                        grid[H-1][x+k] = ' '  # pit
                    break
        # platforms
        bands = min(2 + difficulty//6, 5)
        for b in range(bands):
            y = rng.randint(8, 14 - (b//2))
            runs = 3 + difficulty//4
            for r in range(runs):
                length = rng.randint(3, 8 + difficulty//6)
                x = rng.randint(6, max(6, W - 6 - length))
                for k in range(length):
                    grid[y][x+k] = '#'
                # occasional spike on top
                if rng.random() < 0.2 + difficulty*0.01:
                    sx = x + length//2
                    if 0 <= y-1 < H: grid[y-1][sx] = 'X'
        # stairs
        stair_sets = 1 + difficulty//5
        for s in range(stair_sets):
            base_x = rng.randint(14, max(14, W-20))
            steps = rng.randint(3, 6)
            for n in range(steps):
                y = (H-1) - n
                x = base_x + n
                if 0 <= x < W and 0 <= y < H:
                    grid[y][x] = '#'
        # hazards on ground
        count = 4 + difficulty*2
        for _ in range(count):
            x = rng.randint(12, W-12)
            if grid[H-1][x] == '#':
                grid[H-2][x] = 'X'
                if rng.random() < 0.4 and x+1 < W:
                    grid[H-2][x+1] = 'X'
        # start/exit
        start = (2, H-2)
        exit = (W-4, H-2)
        grid[start[1]][start[0]] = 'P'
        grid[exit[1]][exit[0]] = 'E'
        rows = [''.join(row) for row in grid]
        levels.append(Level(i, W, H, rows, start, exit))
    return levels

def main():
    pygame.init()
    pygame.display.set_caption("Ultra Mario 2D Bros (Sim) — Pygame")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font_big = pygame.font.SysFont(None, 64, bold=True)
    font_mid = pygame.font.SysFont(None, 28, bold=True)
    font_small = pygame.font.SysFont(None, 20)
    levels = generate_levels()

    state = 'menu'   # 'menu' | 'play' | 'clear' | 'end'
    level_index = 0
    level = None
    camera_x = 0.0
    deaths = 0

    # player dict
    player = {
        'x': 0.0, 'y': 0.0, 'w': 20, 'h': 30,
        'vx': 0.0, 'vy': 0.0,
        'on_ground': False,
        'just_jumped': False
    }

    def load_level(i):
        nonlocal level_index, level, camera_x, player
        level_index = i
        lvl = levels[i]
        # clone rows and locate P/E
        rows = [list(r) for r in lvl.rows]
        sx, sy = 2, lvl.height-2
        ex, ey = lvl.width-4, lvl.height-2
        for y in range(lvl.height):
            row = rows[y]
            for x, ch in enumerate(row):
                if ch == 'P':
                    sx, sy = x, y
                    rows[y][x] = ' '
                elif ch == 'E':
                    ex, ey = x, y
                    rows[y][x] = ' '
        level = Level(lvl.idx, lvl.width, lvl.height, [''.join(r) for r in rows], (sx, sy), (ex, ey))
        player.update({
            'x': sx * TILE + 8,
            'y': sy * TILE - 1,
            'vx': 0.0, 'vy': 0.0,
            'on_ground': False,
            'just_jumped': False
        })
        camera_x = max(0.0, player['x'] - WIDTH/2)

    def solid_at(px, py):
        tx = int(px // TILE); ty = int(py // TILE)
        if level is None: return False
        return level.is_solid(tx, ty)

    def hazard_at(px, py):
        tx = int(px // TILE); ty = int(py // TILE)
        if level is None: return False
        return level.is_hazard(tx, ty)

    def aabb(ax, ay, aw, ah, bx, by, bw, bh):
        return (ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by)

    def update_play(dt, keys):
        nonlocal state, deaths, camera_x
        # input
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        jump_pressed = keys[pygame.K_z] or keys[pygame.K_SPACE]
        # level switching and reset
        if keys[pygame.K_r]:
            load_level(level_index)
            return
        if keys[pygame.K_LEFTBRACKET]:
            if level_index > 0:
                load_level(level_index-1)
            return
        if keys[pygame.K_RIGHTBRACKET]:
            if level_index < len(levels)-1:
                load_level(level_index+1)
            return

        # horizontal
        target_vx = (-MOVE_SPEED if left else MOVE_SPEED if right else 0.0)
        player['vx'] += (target_vx - player['vx']) * min(1.0, dt*10.0)

        # gravity
        player['vy'] += GRAVITY * dt
        player['vy'] = min(player['vy'], MAX_FALL)

        # jump
        if jump_pressed and player['on_ground'] and not player['just_jumped']:
            player['vy'] = JUMP_VELOCITY
            player['on_ground'] = False
            player['just_jumped'] = True
        if not jump_pressed:
            player['just_jumped'] = False

        # move X
        next_x = player['x'] + player['vx'] * dt
        if player['vx'] > 0:
            test_x = next_x + player['w']
            y1 = player['y'] + 2; y2 = player['y'] + player['h']/2; y3 = player['y'] + player['h'] - 2
            if solid_at(test_x, y1) or solid_at(test_x, y2) or solid_at(test_x, y3):
                tile_x = int(test_x // TILE)
                next_x = tile_x * TILE - player['w'] - 0.01
                player['vx'] = 0.0
        elif player['vx'] < 0:
            test_x = next_x
            y1 = player['y'] + 2; y2 = player['y'] + player['h']/2; y3 = player['y'] + player['h'] - 2
            if solid_at(test_x, y1) or solid_at(test_x, y2) or solid_at(test_x, y3):
                tile_x = int(test_x // TILE) + 1
                next_x = tile_x * TILE + 0.01
                player['vx'] = 0.0
        player['x'] = next_x

        # move Y
        next_y = player['y'] + player['vy'] * dt
        player['on_ground'] = False
        if player['vy'] > 0:
            test_y = next_y + player['h']
            x1 = player['x'] + 4; x2 = player['x'] + player['w']/2; x3 = player['x'] + player['w'] - 4
            if solid_at(x1, test_y) or solid_at(x2, test_y) or solid_at(x3, test_y):
                tile_y = int(test_y // TILE)
                next_y = tile_y * TILE - player['h'] - 0.01
                player['vy'] = 0.0
                player['on_ground'] = True
        elif player['vy'] < 0:
            test_y = next_y
            x1 = player['x'] + 4; x2 = player['x'] + player['w']/2; x3 = player['x'] + player['w'] - 4
            if solid_at(x1, test_y) or solid_at(x2, test_y) or solid_at(x3, test_y):
                tile_y = int(test_y // TILE) + 1
                next_y = tile_y * TILE + 0.01
                player['vy'] = 0.0
        player['y'] = next_y

        # hazards
        corners = [
            (player['x']+2, player['y']+2),
            (player['x']+player['w']-2, player['y']+2),
            (player['x']+2, player['y']+player['h']-2),
            (player['x']+player['w']-2, player['y']+player['h']-2),
        ]
        for (cx, cy) in corners:
            if hazard_at(cx, cy):
                deaths += 1
                load_level(level_index)
                return

        # fell out
        if player['y'] > level.height * TILE + 200:
            deaths += 1
            load_level(level_index)
            return

        # exit
        exit_rect = (level.exit[0]*TILE, (level.exit[1]-2)*TILE, TILE, TILE*3)
        if aabb(player['x'], player['y'], player['w'], player['h'], *exit_rect):
            if level_index < len(levels)-1:
                nonlocal_state_set('clear')
            else:
                nonlocal_state_set('end')

        # camera
        world_w = level.width * TILE
        camera = player['x'] + player['w']/2 - WIDTH/2
        camera_x = clamp(camera, 0, max(0, world_w - WIDTH))

    # helper to set outer state from inner scope (Python 3.8 workaround)
    def nonlocal_state_set(new_state):
        nonlocal state
        state = new_state

    def draw_gradient_background():
        # simple vertical gradient
        for y in range(0, HEIGHT, 4):
            t = y / HEIGHT
            r = int(COL_BG_TOP[0]*(1-t) + COL_BG_BOTTOM[0]*t)
            g = int(COL_BG_TOP[1]*(1-t) + COL_BG_BOTTOM[1]*t)
            b = int(COL_BG_TOP[2]*(1-t) + COL_BG_BOTTOM[2]*t)
            pygame.draw.rect(screen, (r,g,b), (0,y,WIDTH,4))

    def draw_parallax():
        # mountains
        offset = (camera_x * 0.3) % 400
        col = (96, 165, 250)
        for i in range(5):
            x = i*400 - offset
            points = [(x, HEIGHT-160), (x+140, HEIGHT-260), (x+280, HEIGHT-160)]
            pygame.draw.polygon(screen, col, points)
        # hills (near)
        offset2 = (camera_x * 0.6) % 260
        col2 = (134, 239, 172)
        for i in range(8):
            x = int(i*260 - offset2)
            pygame.draw.circle(screen, col2, (x, HEIGHT-90), 90)

    def draw_tiles():
        if level is None: return
        first_tx = max(0, int(camera_x // TILE))
        last_tx = min(level.width-1, int((camera_x + WIDTH) // TILE) + 1)
        for y in range(level.height):
            row = level.rows[y]
            for tx in range(first_tx, last_tx+1):
                ch = row[tx]
                px = tx * TILE - camera_x
                py = y * TILE
                if ch == '#':
                    pygame.draw.rect(screen, COL_BLOCK_DARK, (px, py, TILE, TILE))
                    pygame.draw.rect(screen, COL_BLOCK_LIGHT, (px+2, py+2, TILE-4, TILE-4))
                elif ch == 'X':
                    spikes = 4
                    base = [(0, TILE)] * spikes  # placeholder
                    for i in range(spikes):
                        sx = px + i*(TILE/spikes)
                        tri = [(sx, py+TILE), (sx + TILE/spikes/2, py+TILE-14), (sx + TILE/spikes, py+TILE)]
                        pygame.draw.polygon(screen, COL_SPIKE, tri)

    def draw_exit():
        if level is None: return
        px = level.exit[0]*TILE - camera_x
        py = (level.exit[1]-2)*TILE
        pygame.draw.rect(screen, (236, 239, 247), (px + TILE-6, py, 4, TILE*3))  # pole
        pygame.draw.polygon(screen, (251, 191, 36), [(px + TILE-2, py+6), (px + TILE-2 + 28, py+14), (px + TILE-2, py+22)])

    def draw_player():
        px = int(player['x'] - camera_x)
        py = int(player['y'])
        pygame.draw.rect(screen, COL_PLAYER_OUT, (px-2, py-2, player['w']+4, player['h']+4))
        pygame.draw.rect(screen, COL_PLAYER, (px, py, player['w'], player['h']))
        # eyes
        pygame.draw.rect(screen, (11,18,32), (px+4, py+6, 4, 6))
        pygame.draw.rect(screen, (11,18,32), (px+player['w']-8, py+6, 4, 6))

    def draw_hud():
        panel = pygame.Surface((220, 70), pygame.SRCALPHA)
        panel.fill(COL_UI_PANEL)
        screen.blit(panel, (WIDTH-230, 10))
        txt1 = font_mid.render(f"Level {level_index+1}/32", True, COL_UI)
        txt2 = font_mid.render(f"Deaths: {deaths}", True, COL_UI)
        screen.blit(txt1, (WIDTH-220, 16))
        screen.blit(txt2, (WIDTH-220, 42))

    def draw_menu():
        # sky
        screen.fill(COL_BG_TOP)
        # ground bar
        pygame.draw.rect(screen, (134, 239, 172), (0, HEIGHT-100, WIDTH, 100))
        # moving hills
        t = pygame.time.get_ticks()/30 % 1400
        for i in range(8):
            x = int((i*140 + t) % (WIDTH+160) - 80)
            pygame.draw.circle(screen, (74, 222, 128), (x, HEIGHT-100), 80)
        # title
        shadow = font_big.render("ULTRA MARIO 2D BROS", True, (11,18,32))
        title = font_big.render("ULTRA MARIO 2D BROS", True, (255,255,255))
        screen.blit(shadow, (WIDTH//2 - shadow.get_width()//2 + 2, 154+2))
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 154))
        sub = font_mid.render("Press Z or Space to Start", True, (255,255,255))
        screen.blit(sub, (WIDTH//2 - sub.get_width()//2, 210))
        hint = font_small.render("Arrow keys to move • Z/Space to jump • R to reset", True, (255,255,255))
        screen.blit(hint, (WIDTH//2 - hint.get_width()//2, 242))

    def draw_overlay(text1, text2):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,160))
        screen.blit(overlay, (0,0))
        a = font_big.render(text1, True, (255,255,255))
        b = font_mid.render(text2, True, (255,255,255))
        screen.blit(a, (WIDTH//2 - a.get_width()//2, HEIGHT//2 - 22))
        screen.blit(b, (WIDTH//2 - b.get_width()//2, HEIGHT//2 + 18))

    # initial
    camera_x = 0.0

    running = True
    while running:
        dt = min(0.033, clock.tick(FPS) / 1000.0)
        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if state == 'menu' and (event.key in (pygame.K_z, pygame.K_SPACE)):
                    load_level(0)
                    state = 'play'
                elif state == 'clear' and (event.key in (pygame.K_z, pygame.K_SPACE)):
                    if level_index < len(levels)-1:
                        load_level(level_index+1)
                        state = 'play'
                    else:
                        state = 'end'

        if state == 'play':
            update_play(dt, keys)

        # draw
        if state == 'menu':
            draw_menu()
        else:
            draw_gradient_background()
            draw_parallax()
            draw_tiles()
            draw_exit()
            draw_player()
            draw_hud()
            if state == 'clear':
                draw_overlay("Course Clear!", "Press Z or Space for the next level")
            elif state == 'end':
                draw_overlay("The End — Thanks for playing!", "")

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import sys
import os
import time
import random
from pynput import keyboard
from coolmapmaker import Room, Dungeon

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"

my_keys = []   # filled automatically when bosses die

BOX_W    = 32   # arena width  (columns)
BOX_H    = 12   # arena height (rows)
MAX_HP   = 20
dmg      = 4    # damage per bullet hit
spd      = 1.0  # how fast the soul (@) moves per frame
i_frames = 67   # immunity frames after a hit (~2 seconds)
wave_len = 40   # frames per bullet wave (3 waves per dodge phase)


def clr():
    os.system("cls" if os.name == "nt" else "clear")


# =============================================================================
# ATTACK CLASS
# each attack is a class with a spawn() method that returns a list of bullets.
#
# to make your own attack:
#   1. make a new class that extends Attack
#   2. override spawn() to return a list of bullet dicts
#   3. each bullet needs: x, y, dx, dy, char
#        x    = starting column (0=left edge, BOX_W-1=right edge)
#        y    = starting row    (0=top  edge, BOX_H-1=bottom edge)
#        dx   = speed per frame going RIGHT  (negative = going left)
#        dy   = speed per frame going DOWN   (negative = going up)
#        char = the symbol drawn on screen
# =============================================================================

class Attack:
    def spawn(self):
        return []   # override this


class BonesAttack(Attack):
    """rows of dashes sweeping left and right alternately"""
    def spawn(self):
        bullets = []
        for row in range(0, BOX_H, 2):
            if (row // 2) % 2 == 0:
                bullets.append({'x': 0.0,            'y': float(row), 'dx':  1.0, 'dy': 0.0, 'char': '-'})
            else:
                bullets.append({'x': float(BOX_W-1), 'y': float(row), 'dx': -1.0, 'dy': 0.0, 'char': '-'})
        return bullets


class DropsAttack(Attack):
    """stars falling from random spots at the top"""
    def spawn(self):
        bullets = []
        cols = random.sample(range(1, BOX_W - 1), BOX_W // 4)
        for c in cols:
            bullets.append({'x': float(c), 'y': 0.0, 'dx': 0.0, 'dy': 0.5, 'char': '*'})
        return bullets


class SpiralAttack(Attack):
    """8 bullets from the centre, one in each direction"""
    def spawn(self):
        cx = float(BOX_W // 2)
        cy = float(BOX_H // 2)
        dirs = [
            ( 0.5,  0.0),   # right
            ( 0.4,  0.4),   # down-right
            ( 0.0,  0.5),   # down
            (-0.4,  0.4),   # down-left
            (-0.5,  0.0),   # left
            (-0.4, -0.4),   # up-left
            ( 0.0, -0.5),   # up
            ( 0.4, -0.4),   # up-right
        ]
        return [{'x': cx, 'y': cy, 'dx': dx, 'dy': dy, 'char': '+'} for dx, dy in dirs]


class CornersAttack(Attack):
    """one bullet from each corner heading toward the centre"""
    def spawn(self):
        corner_bullets = [
            (0.0,              0.0,               0.4,  0.4),   # top-left  → right+down
            (float(BOX_W - 1), 0.0,              -0.4,  0.4),   # top-right → left+down
            (0.0,              float(BOX_H - 1),  0.4, -0.4),   # bot-left  → right+up
            (float(BOX_W - 1), float(BOX_H - 1), -0.4, -0.4),  # bot-right → left+up
        ]
        return [{'x': x, 'y': y, 'dx': dx, 'dy': dy, 'char': 'o'} for x, y, dx, dy in corner_bullets]


class CrossAttack(Attack):
    """rain from the top + streams shooting in from both sides"""
    def spawn(self):
        bullets = []
        for i in range(0, BOX_W, 4):
            bullets.append({'x': float(i), 'y': 0.0, 'dx': 0.0, 'dy': 0.5, 'char': '|'})
        for j in range(0, BOX_H, 3):
            bullets.append({'x': 0.0,              'y': float(j), 'dx':  0.5, 'dy': 0.0, 'char': '='})
            bullets.append({'x': float(BOX_W - 1), 'y': float(j), 'dx': -0.5, 'dy': 0.0, 'char': '='})
        return bullets


# pre-built attack instances — use these in attacks=[...] below
BONES   = BonesAttack()
DROPS   = DropsAttack()
SPIRAL  = SpiralAttack()
CORNERS = CornersAttack()
CROSS   = CrossAttack()


# =============================================================================
# BOSS CLASS
# create a boss like:   Boss(room_id="...", name="...", ...)
# create the final boss: FinalBoss(room_id="...", name="...", ...)
# =============================================================================

class Boss:
    def __init__(self, *,
                 room_id, room_name, room_desc, room_w=2, room_h=2,
                 name, hp, dialog, act_name, act_txt, mercy, attacks,
                 key, dead_msg, win_msg, lose_msg):
        self.room_id   = room_id
        self.room_name = room_name
        self.room_desc = room_desc
        self.room_w    = room_w
        self.room_h    = room_h
        self.name      = name
        self.hp        = hp
        self.dialog    = dialog
        self.act_name  = act_name   # label on the ACT button
        self.act_txt   = act_txt    # lines shown when player picks ACT
        self.mercy     = mercy      # mercy unlocks below this fraction of max hp
        self.attacks   = attacks    # list of Attack instances
        self.key       = key        # key name dropped on win
        self.dead_msg  = dead_msg   # shown if player re-enters after winning
        self.win_msg   = win_msg    # shown when boss is beaten
        self.lose_msg  = lose_msg   # shown when player dies
        self.dead      = False      # dont set this — updated automatically


class FinalBoss:
    def __init__(self, *,
                 room_id, room_name, room_desc, entry_msg="", room_w=2, room_h=2,
                 name, hp, dialog, act_name, act_txt, mercy, attacks, win_lines):
        self.room_id   = room_id
        self.room_name = room_name
        self.room_desc = room_desc
        self.entry_msg = entry_msg
        self.room_w    = room_w
        self.room_h    = room_h
        self.name      = name
        self.hp        = hp
        self.dialog    = dialog
        self.act_name  = act_name
        self.act_txt   = act_txt
        self.mercy     = mercy
        self.attacks   = attacks
        self.win_lines = win_lines  # lines printed on the win screen
        self.dead      = False


# =============================================================================
# DRAW FUNCTIONS — dont touch these
#
# draw_menu  = the turn screen where you pick FIGHT / ACT / MERCY
# draw_dodge = the bullet arena where you move @ to dodge
# =============================================================================

def draw_menu(boss, boss_cur_hp, player_hp, message, menu_index, can_mercy):
    """draws the turn menu screen — pick FIGHT, ACT or MERCY."""
    clr()
    out = []

    filled = int(max(0.0, boss_cur_hp / boss.hp) * 24)
    bar    = GREEN + "#" * filled + RED + "-" * (24 - filled) + RESET

    out.append("")
    out.append(f"  {BOLD}{YELLOW}{boss.name}{RESET}   [{bar}]  {boss_cur_hp}/{boss.hp}")
    out.append("")
    out.append(f"  {WHITE}{message}{RESET}")
    out.append("")

    labels  = ["FIGHT", boss.act_name.upper(), "MERCY"]
    colours = [RED, CYAN, YELLOW if can_mercy else DIM]
    row_str = "   "
    for i in range(3):
        lbl = labels[i]
        col = colours[i]
        if i == menu_index:
            row_str += f"{BOLD}[ {col}{lbl}{RESET}{BOLD} ]{RESET}   "
        else:
            row_str += f"  {col}{lbl}{RESET}    "
    out.append(row_str)

    out.append("")
    pf   = int((player_hp / MAX_HP) * 20)
    pbar = GREEN + "#" * pf + DIM + "-" * (20 - pf) + RESET
    out.append(f"  YOUR HP  [{pbar}]  {player_hp}/{MAX_HP}")

    print("\n".join(out))
    sys.stdout.flush()


def draw_dodge(boss, boss_cur_hp, player_hp, bullets, soul_x, soul_y, wave_number, immune_frames):
    """draws the bullet dodge arena — move @ to survive."""
    clr()
    out = []

    filled = int(max(0.0, boss_cur_hp / boss.hp) * 24)
    bar    = GREEN + "#" * filled + RED + "-" * (24 - filled) + RESET

    out.append("")
    out.append(f"  {BOLD}{YELLOW}{boss.name}{RESET}   [{bar}]  {boss_cur_hp}/{boss.hp}")
    out.append("")
    out.append(f"  {WHITE}* dodge!! (wave {wave_number}/3){RESET}")
    out.append("")

    out.append("  +" + "-" * BOX_W + "+")
    grid = [[" "] * BOX_W for _ in range(BOX_H)]

    for b in bullets:
        bx = int(round(b['x']))
        by = int(round(b['y']))
        if 0 <= bx < BOX_W and 0 <= by < BOX_H:
            grid[by][bx] = CYAN + b['char'] + RESET

    # soul flickers while immune
    sx = max(0, min(BOX_W - 1, int(round(soul_x))))
    sy = max(0, min(BOX_H - 1, int(round(soul_y))))
    if not (immune_frames > 0 and immune_frames % 4 < 2):
        grid[sy][sx] = RED + BOLD + "@" + RESET

    for row in grid:
        out.append("  |" + "".join(row) + "|")
    out.append("  +" + "-" * BOX_W + "+")

    if immune_frames > 0:
        out.append(f"  {YELLOW}  (invincible! {immune_frames} frames){RESET}")

    out.append("")
    pf   = int((player_hp / MAX_HP) * 20)
    pbar = GREEN + "#" * pf + DIM + "-" * (20 - pf) + RESET
    out.append(f"  YOUR HP  [{pbar}]  {player_hp}/{MAX_HP}")

    print("\n".join(out))
    sys.stdout.flush()


def do_fight(boss):
    bhp      = boss.hp
    php      = MAX_HP
    act_done = False
    held     = set()
    pressed  = []

    def on_press(key):
        try:
            c = key.char.lower()
            if c in ('w', 's'): held.add(c)
            if c == 'a': held.add('a'); pressed.append('left')
            if c == 'd': held.add('d'); pressed.append('right')
            if c in ('z', ' '): pressed.append('ok')
        except Exception: pass
        if key == keyboard.Key.up:    held.add('w')
        if key == keyboard.Key.down:  held.add('s')
        if key == keyboard.Key.left:  held.add('a'); pressed.append('left')
        if key == keyboard.Key.right: held.add('d'); pressed.append('right')
        if key == keyboard.Key.enter: pressed.append('ok')

    def on_release(key):
        try: held.discard(key.char.lower())
        except Exception: pass
        if key == keyboard.Key.up:    held.discard('w')
        if key == keyboard.Key.down:  held.discard('s')
        if key == keyboard.Key.left:  held.discard('a')
        if key == keyboard.Key.right: held.discard('d')

    lst    = keyboard.Listener(on_press=on_press, on_release=on_release)
    lst.start()
    midx   = 0
    didx   = 0
    result = False

    while True:
        can_mercy = bhp / boss.hp <= boss.mercy or act_done
        msg       = boss.dialog[didx % len(boss.dialog)]
        didx     += 1
        pressed.clear()
        choice    = None

        while choice is None:
            draw_menu(boss, bhp, php, msg, midx, can_mercy)
            time.sleep(0.05)
            now = list(pressed); pressed.clear()
            for k in now:
                if k == 'left':    midx = (midx - 1) % 3
                elif k == 'right': midx = (midx + 1) % 3
                elif k == 'ok':    choice = midx

        if choice == 0:
            bhp -= 15
            rmsg = f"* You attack!  * {boss.name} takes 15 damage!"
            if bhp <= 0:
                draw_menu(boss, bhp, php, f"* {boss.name} is defeated!!", midx, can_mercy)
                time.sleep(2.5); result = True; break
        elif choice == 1:
            act_done = True
            rmsg = "  ".join(boss.act_txt)
        else:
            if can_mercy:
                draw_menu(boss, bhp, php, f"* You spared {boss.name}.  * They step aside.", midx, True)
                time.sleep(2.5); result = True; break
            else:
                rmsg = f"* {boss.name} doesnt want to stop yet."

        draw_menu(boss, bhp, php, rmsg, midx, can_mercy)
        time.sleep(1.3)

        attack = random.choice(boss.attacks)
        sol_x  = float(BOX_W // 2)
        sol_y  = float(BOX_H // 2)
        itimer = 0
        held.clear()

        for wave in range(3):
            bullets = attack.spawn()
            for frame in range(wave_len):
                if 'w' in held: sol_y -= spd
                if 's' in held: sol_y += spd
                if 'a' in held: sol_x -= spd
                if 'd' in held: sol_x += spd
                sol_x = max(0.0, min(float(BOX_W - 1), sol_x))
                sol_y = max(0.0, min(float(BOX_H - 1), sol_y))
                if itimer > 0: itimer -= 1
                gx = int(round(sol_x))
                gy = int(round(sol_y))
                for b in bullets:
                    b['x'] += b['dx']; b['y'] += b['dy']
                    if int(round(b['x'])) == gx and int(round(b['y'])) == gy and itimer == 0:
                        php    = max(0, php - dmg)
                        itimer = i_frames
                draw_dodge(boss, bhp, php, bullets, sol_x, sol_y, wave + 1, itimer)
                if php <= 0:
                    draw_menu(boss, bhp, 0, "* you died lol  * back to the entrance you go", 0, False)
                    time.sleep(2.5); lst.stop(); return False
                time.sleep(0.03)

    lst.stop()
    return result


def make_trigger(boss):
    def trigger(dungeon):
        if boss.dead:
            dungeon.print(boss.dead_msg)
            return
        won = do_fight(boss)
        dungeon._key_queue.clear()
        dungeon._needs_redraw = True
        if won:
            boss.dead = True
            my_keys.append(boss.key)
            dungeon.print(boss.win_msg)
            dungeon.print(f"* keys: {len(my_keys)}/3")
        else:
            dungeon.print(boss.lose_msg)
    return trigger


def make_final_trigger(boss):
    def trigger(dungeon):
        if boss.dead:
            dungeon.print("* you already won. go home.")
            return
        if len(my_keys) < 3:
            dungeon.print("* the door has 3 locks.")
            dungeon.print(f"* you have {len(my_keys)}/3 keys." if my_keys else "* you have no keys.")
            dungeon.print("* beat all 3 bosses first.")
            return
        dungeon.print("* you put all 3 keys in the locks.")
        dungeon.print("* the door opens.")
        time.sleep(2.0)
        won = do_fight(boss)
        dungeon._key_queue.clear()
        dungeon._needs_redraw = True
        if won:
            boss.dead = True
            clr()
            print()
            print(f"  {BOLD}{YELLOW}*** YOU WIN!!! ***{RESET}")
            print()
            for line in boss.win_lines:
                print(f"  {WHITE}{line}{RESET}")
            print()
            time.sleep(5)
            sys.exit(0)
        else:
            dungeon.print("* you lost.")
            dungeon.print("* your hp is restored. the keys are still in your pocket.")
            dungeon.print("* try again.")
    return trigger


# =============================================================================
# YOUR GAME — edit BOSSES and FINAL_BOSS
# =============================================================================

BOSSES = [
    Boss(
        room_id   = "boss1_room",
        room_name = "Example Room",
        room_desc = "Replace this with your room description.",
        room_w    = 2,
        room_h    = 2,
        name      = "EXAMPLE BOSS",
        hp        = 60,
        dialog    = [
            "* EXAMPLE BOSS: i am an example boss.",
            "* EXAMPLE BOSS: replace my dialogue.",
            "* EXAMPLE BOSS: im just placeholder text.",
        ],
        act_name  = "Wave",
        act_txt   = [
            "* you wave at the example boss.",
            "* EXAMPLE BOSS: ...hi.",
        ],
        mercy     = 0.4,
        attacks   = [BONES, DROPS],
        key       = "example key",
        dead_msg  = "* example boss is already dead.",
        win_msg   = "* example boss crumbles. you pick up a key.",
        lose_msg  = "* you lost. your hp is restored. try again.",
    ),

    Boss(
        room_id   = "boss2_room",
        room_name = "Boss 2 Room",
        room_desc = "TODO: replace this description.",
        room_w    = 2,
        room_h    = 2,
        name      = "BOSS 2",
        hp        = 60,
        dialog    = [
            "* BOSS 2: TODO add dialogue.",
        ],
        act_name  = "Act",
        act_txt   = [
            "* TODO add act text.",
        ],
        mercy     = 0.4,
        attacks   = [DROPS, CORNERS],
        key       = "key 2",
        dead_msg  = "* boss 2 is already dead.",
        win_msg   = "* boss 2 defeated. you pick up a key.",
        lose_msg  = "* you lost. your hp is restored. try again.",
    ),

    # TODO: paste another Boss(...) here for your third boss
]


FINAL_BOSS = FinalBoss(
    room_id   = "final_room",
    room_name = "The Final Room",
    room_desc = "Three keyholes in the door ahead. The air feels wrong.",
    entry_msg = "A horrible feeling washes over you.",
    room_w    = 2,
    room_h    = 2,
    name      = "FINAL BOSS",
    hp        = 120,
    dialog    = [
        "* FINAL BOSS: you actually made it.",
        "* FINAL BOSS: TODO add more dialogue.",
    ],
    act_name  = "Defy",
    act_txt   = [
        "* TODO add act text.",
    ],
    mercy     = 0.2,
    attacks   = [BONES, SPIRAL, CROSS],
    win_lines = [
        "TODO: write your win message here.",
        "the dungeon is free.",
    ],
)


# =============================================================================
# ROOMS + RUN — dont touch
# =============================================================================

ENTRY_LINES = [
    "You step through the doorway.",
    "You go forward carefully.",
    "The passage opens into something.",
    "You duck under a low arch.",
    "A cold draught pulls you forward.",
    "The floor groans under your feet.",
]

EVENT_LINES = [
    "Something skitters in the dark.",
    "A torch flares up then settles.",
    "Claw marks on the door frame. Fresh.",
    "Its really cold in here.",
    "A low moaning sound. Probably wind.",
    "A coin wedged in a crack in the floor.",
]


def make_rooms():
    b_rooms = []
    for boss in BOSSES:
        b_rooms.append(Room(
            room_id     = boss.room_id,
            name        = boss.room_name,
            description = boss.room_desc,
            width       = boss.room_w,
            height      = boss.room_h,
            on_enter    = make_trigger(boss),
        ))
    b_rooms.append(Room(
        room_id       = FINAL_BOSS.room_id,
        name          = FINAL_BOSS.room_name,
        description   = FINAL_BOSS.room_desc,
        width         = FINAL_BOSS.room_w,
        height        = FINAL_BOSS.room_h,
        entry_message = FINAL_BOSS.entry_msg,
        on_enter      = make_final_trigger(FINAL_BOSS),
    ))
    n_rooms = [
        Room(room_id="hall1", name="Dark Hall",
             description="A dark corridor. Nothing special.",
             width=2, height=1, events=random.sample(EVENT_LINES, 2)),
        Room(room_id="hall2", name="Stone Chamber",
             description="Cold stone walls. A dead torch on the floor.",
             width=1, height=2, events=random.sample(EVENT_LINES, 2)),
        Room(room_id="hall3", name="Junction",
             description="Passages split off in multiple directions.",
             width=2, height=2, events=random.sample(EVENT_LINES, 2)),
        Room(room_id="hall4", name="Collapsed Room",
             description="Half the ceiling has caved in.",
             width=2, height=1, events=random.sample(EVENT_LINES, 2)),
    ]
    return b_rooms + n_rooms


Dungeon(make_rooms(), entry_lines=ENTRY_LINES, event_chance=0.55).run()

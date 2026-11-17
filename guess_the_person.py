#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUESS THE PERSON  -  Futuristic Edition  (NEURAL INTERFACE v1.0)
================================================================

A single-file Pygame game with two modes:

  * AI GUESSES  - you think of one of 15 famous people, the AI asks questions
                  (greedy "most balanced YES/NO split" heuristic on HARD,
                  random useful question on EASY) and eliminates candidates.
  * YOU GUESS   - the AI secretly picks someone; you have 10 questions
                  (hints cost one question) to work out who it is.

Run:        python guess_the_person.py
Self-test:  python guess_the_person.py --selftest      (no window is opened)

Only Pygame and the Python standard library are used. All graphics are drawn
procedurally. The AI is classical rule-based elimination plus a greedy
information-gain-style heuristic: no machine learning, no decision-tree
learning.
"""

import colorsys
import functools
import hashlib
import math
import random
import sys

try:  # The self-test and the data/AI logic do not need pygame at all.
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

# =============================================================================
# CONSTANTS
# =============================================================================
WIDTH, HEIGHT = 1280, 720
FPS = 60
MAX_QUESTIONS = 10


def hexc(value):
    """Convert '#RRGGBB' into an (r, g, b) tuple."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


C_BG = hexc("#080D1F")
C_BG2 = hexc("#111A32")
C_CARD = hexc("#17243D")
C_CARD_HOVER = hexc("#243653")
C_CYAN = hexc("#22D3EE")
C_PURPLE = hexc("#A78BFA")
C_GREEN = hexc("#22C55E")
C_RED = hexc("#EF4444")
C_TEXT = hexc("#E2E8F0")
C_MUTED = hexc("#94A3B8")
C_AMBER = (250, 204, 21)

# =============================================================================
# DATABASE  (exactly 15 people, 18 boolean tags each)
# =============================================================================
TAGS = [
    "male", "alive", "bd", "bengali", "south_asia", "science", "cs", "ai",
    "writer", "artist", "athlete", "leader", "nobel", "pre1950", "pre1900",
    "inventor", "british", "turing_award",
]

QUESTION_TEXT = {
    "male": "Is this person male?",
    "alive": "Is this person alive today?",
    "bd": "Is this person from Bangladesh?",
    "bengali": "Is this person Bengali?",
    "south_asia": "Is this person from South Asia?",
    "science": "Is this person a scientist or in science?",
    "cs": "Is this person connected to computer science?",
    "ai": "Is this person connected to artificial intelligence?",
    "writer": "Is this person a writer or author?",
    "artist": "Is this person an artist or musician?",
    "athlete": "Is this person an athlete?",
    "leader": "Is this person a political leader?",
    "nobel": "Did this person win a Nobel Prize?",
    "pre1950": "Was this person born before 1950?",
    "pre1900": "Was this person born before 1900?",
    "inventor": "Is this person an inventor?",
    "british": "Is this person British?",
    "turing_award": "Did this person win the Turing Award?",
}

QUESTION_SHORT = {
    "male": "Male?", "alive": "Alive today?", "bd": "From Bangladesh?",
    "bengali": "Bengali?", "south_asia": "South Asian?", "science": "Scientist?",
    "cs": "Computer science?", "ai": "Artificial intelligence?",
    "writer": "Writer?", "artist": "Artist / musician?", "athlete": "Athlete?",
    "leader": "Political leader?", "nobel": "Nobel Prize?",
    "pre1950": "Born before 1950?", "pre1900": "Born before 1900?",
    "inventor": "Inventor?", "british": "British?", "turing_award": "Turing Award?",
}

_RAW_PEOPLE = [
    ("Alan Turing", "Father of theoretical computer science",
     ["male", "science", "cs", "ai", "pre1950", "british"]),
    ("Ada Lovelace", "First computer programmer",
     ["science", "cs", "pre1950", "pre1900", "british"]),
    ("Geoffrey Hinton", "Deep learning pioneer",
     ["male", "alive", "science", "cs", "ai", "nobel", "pre1950", "turing_award"]),
    ("Tim Berners-Lee", "Inventor of the World Wide Web",
     ["male", "alive", "science", "cs", "inventor", "british", "turing_award"]),
    ("Albert Einstein", "Theory of relativity",
     ["male", "science", "nobel", "pre1950", "pre1900"]),
    ("Marie Curie", "Radioactivity researcher",
     ["science", "nobel", "pre1950", "pre1900"]),
    ("Stephen Hawking", "Black hole physicist and author",
     ["male", "science", "writer", "pre1950", "british"]),
    ("Nikola Tesla", "AC electricity inventor",
     ["male", "science", "pre1950", "pre1900", "inventor"]),
    ("Muhammad Yunus", "Microcredit pioneer",
     ["male", "alive", "bd", "bengali", "south_asia", "leader", "nobel", "pre1950"]),
    ("Sheikh Mujibur Rahman", "Founding father of Bangladesh",
     ["male", "bd", "bengali", "south_asia", "leader", "pre1950"]),
    ("Rabindranath Tagore", "Poet, wrote Bangladesh's national anthem",
     ["male", "bd", "bengali", "south_asia", "writer", "artist", "nobel",
      "pre1950", "pre1900"]),
    ("Kazi Nazrul Islam", "National poet of Bangladesh",
     ["male", "bd", "bengali", "south_asia", "writer", "artist", "pre1950",
      "pre1900"]),
    ("Runa Laila", "Legendary singer",
     ["alive", "bd", "bengali", "south_asia", "artist"]),
    ("Tamim Iqbal", "Cricketer",
     ["male", "alive", "bd", "bengali", "south_asia", "athlete"]),
    ("Lionel Messi", "Footballer", ["male", "alive", "athlete"]),
]


def _build_people():
    """Build the database as a list of dicts; missing tags become False."""
    return [
        {"name": name, "description": desc,
         "tags": {tag: (tag in tag_list) for tag in TAGS}}
        for name, desc, tag_list in _RAW_PEOPLE
    ]


PEOPLE = _build_people()

# Category badge shown on each card (first matching tag wins).
BADGE_PRIORITY = [
    ("athlete", "ATHLETE"), ("leader", "LEADER"), ("artist", "ARTIST"),
    ("ai", "AI"), ("cs", "COMPUTING"), ("inventor", "INVENTOR"),
    ("science", "SCIENCE"), ("writer", "WRITER"),
]


# =============================================================================
# PURE GAME LOGIC (shared by the game and the self-test)
# =============================================================================
def remaining_split(candidates, tag):
    """Return (yes_count, no_count) of `tag` among candidate indices."""
    yes = sum(1 for i in candidates if PEOPLE[i]["tags"][tag])
    return yes, len(candidates) - yes


def useful_questions(candidates, asked):
    """Unasked tags whose answer differs among the remaining candidates."""
    useful = []
    for tag in TAGS:
        if tag in asked:
            continue
        yes, no = remaining_split(candidates, tag)
        if yes > 0 and no > 0:
            useful.append(tag)
    return useful


def choose_hard(candidates, asked, rng):
    """Greedy heuristic: the question whose YES/NO split is closest to 50/50.
    Ties are broken randomly. Returns None when no useful question exists."""
    useful = useful_questions(candidates, asked)
    if not useful:
        return None
    scores = {}
    for tag in useful:
        yes, no = remaining_split(candidates, tag)
        scores[tag] = abs(yes - no)
    best = min(scores.values())
    return rng.choice([t for t in useful if scores[t] == best])


def choose_easy(candidates, asked, rng):
    """Random question among the useful, unasked ones."""
    useful = useful_questions(candidates, asked)
    return rng.choice(useful) if useful else None


def filter_candidates(candidates, tag, answer):
    """Keep only candidates consistent with the YES/NO answer (new list)."""
    return [i for i in candidates if PEOPLE[i]["tags"][tag] == answer]


# =============================================================================
# SELF-TEST (headless)
# =============================================================================
def run_selftest():
    """Run tests A-C without opening a window. Returns True if all pass."""
    results = []

    def report(name, ok, detail=""):
        results.append(ok)
        print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))

    # ---- Test A: database integrity ----
    ok_count = len(PEOPLE) == 15
    ok_tags = all(
        list(p["tags"].keys()) == TAGS and len(p["tags"]) == 18
        and all(isinstance(v, bool) for v in p["tags"].values())
        for p in PEOPLE)
    combos = {tuple(p["tags"][t] for t in TAGS) for p in PEOPLE}
    ok_unique = len(combos) == len(PEOPLE)
    report("Test A1: exactly 15 people", ok_count, "(found %d)" % len(PEOPLE))
    report("Test A2: every person has exactly 18 boolean tags", ok_tags)
    report("Test A3: every tag combination is unique", ok_unique,
           "(%d unique combos)" % len(combos))

    # ---- Test B & C: simulate the Hard AI with truthful answers ----
    trials_per_person = 30
    worst = 0
    ok_identify = True
    ok_no_repeat = True
    ok_consistent = True
    for target in range(len(PEOPLE)):
        for seed in range(trials_per_person):
            rng = random.Random(seed * 1000 + target)
            cands = list(range(len(PEOPLE)))
            asked, answers = [], {}
            while len(cands) > 1 and len(asked) < 10:
                tag = choose_hard(cands, set(asked), rng)
                if tag is None:
                    break
                if tag in asked:
                    ok_no_repeat = False
                asked.append(tag)
                ans = PEOPLE[target]["tags"][tag]
                answers[tag] = ans
                cands = filter_candidates(cands, tag, ans)
                # Test C: nobody inconsistent may survive elimination
                for i in cands:
                    if any(PEOPLE[i]["tags"][t] != a for t, a in answers.items()):
                        ok_consistent = False
                if target not in cands:
                    ok_consistent = False
            if cands != [target]:
                ok_identify = False
                print("   miss: target=%s seed=%d left=%s asked=%d" % (
                    PEOPLE[target]["name"], seed, cands, len(asked)))
            worst = max(worst, len(asked))
    report("Test B: Hard AI identifies all 15 people within 10 questions",
           ok_identify and worst <= 10,
           "(%d trials each, worst case %d questions)" % (trials_per_person, worst))
    report("Test C1: no selected question repeats", ok_no_repeat)
    report("Test C2: elimination never retains an inconsistent person", ok_consistent)

    all_ok = all(results)
    print("\nSELF-TEST RESULT: %s (%d/%d checks passed)" % (
        "ALL PASS" if all_ok else "FAILURES", sum(results), len(results)))
    return all_ok


# =============================================================================
# SMALL HELPERS
# =============================================================================
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_col(c1, c2, t):
    t = clamp(t, 0.0, 1.0)
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def approach(cur, target, rate, dt):
    """Frame-rate independent exponential smoothing toward `target`."""
    value = cur + (target - cur) * (1.0 - math.exp(-rate * dt))
    return target if abs(target - value) < 0.002 else value


def name_color(name):
    """Deterministic, pleasant colour derived from a person's name."""
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    hue = (h % 360) / 360.0
    sat = 0.50 + ((h >> 9) % 30) / 100.0
    r, g, b = colorsys.hsv_to_rgb(hue, sat, 0.92)
    return (int(r * 255), int(g * 255), int(b * 255))


def initials(name):
    parts = name.replace("-", " ").split()
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def badge_for(person):
    for tag, label in BADGE_PRIORITY:
        if person["tags"][tag]:
            return label
    return "PERSON"


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


@functools.lru_cache(maxsize=256)
def glow_surface(w, h, color, radius, spread, level):
    """Cached soft glow ring around a w*h rounded rect (level 1..4)."""
    surf = pygame.Surface((w + spread * 2, h + spread * 2), pygame.SRCALPHA)
    peak = 95 * (level / 4.0)
    for i in range(spread, 0, -1):
        alpha = int(peak * (1.0 - i / float(spread)) ** 2)
        pygame.draw.rect(
            surf, (color[0], color[1], color[2], alpha),
            pygame.Rect(spread - i, spread - i, w + 2 * i, h + 2 * i),
            border_radius=radius + i)
    return surf


@functools.lru_cache(maxsize=64)
def glass_surface(w, h, radius=18, tint=(14, 22, 44), alpha=205, border=C_CYAN):
    """Cached glass-style translucent panel."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, tint + (alpha,), (0, 0, w, h), border_radius=radius)
    light = lerp_col(tint, (255, 255, 255), 0.07)
    pygame.draw.rect(surf, light + (min(255, alpha + 10),),
                     (3, 3, w - 6, max(4, h // 3)), border_radius=max(2, radius - 3))
    pygame.draw.rect(surf, border + (110,), (0, 0, w, h), 2, border_radius=radius)
    return surf


@functools.lru_cache(maxsize=1)
def dim_overlay():
    surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    surf.fill((4, 6, 16, 175))
    return surf


def wrap_text(text, font, max_w):
    """Greedy word wrap; a single over-long word is kept on its own line."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if cur and font.size(trial)[0] > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_text(surf, font, text, color, pos, anchor="topleft"):
    img = font.render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def fit_font(fonts, text, max_w, start, minimum, bold=True):
    for size in range(start, minimum - 1, -1):
        font = fonts.get(size, bold)
        if font.size(text)[0] <= max_w:
            return font
    return fonts.get(minimum, bold)


def draw_wrapped(surf, fonts, text, color, rect, size, align="left",
                 valign="top", min_size=10, bold=True, gap=2):
    """Wrap `text` inside `rect`, shrinking the font until everything fits.
    Text is clipped to `rect` so it can never spill outside."""
    rect = pygame.Rect(rect)
    font, lines = None, None
    for s in range(size, min_size - 1, -1):
        f = fonts.get(s, bold)
        ls = wrap_text(text, f, rect.w)
        total = len(ls) * f.get_linesize() + (len(ls) - 1) * gap
        if total <= rect.h and all(f.size(l)[0] <= rect.w for l in ls):
            font, lines = f, ls
            break
    if font is None:
        font = fonts.get(min_size, bold)
        lines = wrap_text(text, font, rect.w)
    lh = font.get_linesize()
    total = len(lines) * lh + (len(lines) - 1) * gap
    y = rect.y if valign == "top" else rect.y + (rect.h - total) // 2
    old = surf.get_clip()
    surf.set_clip(rect.clip(old))
    for line in lines:
        img = font.render(line, True, color)
        if align == "center":
            x = rect.centerx - img.get_width() // 2
        elif align == "right":
            x = rect.right - img.get_width()
        else:
            x = rect.x
        surf.blit(img, (x, y))
        y += lh + gap
    surf.set_clip(old)


def build_background():
    """Pre-render gradient + grid + circuit traces once (fast per frame)."""
    bg = pygame.Surface((WIDTH, HEIGHT))
    top, bottom = C_BG, (26, 14, 58)
    for y in range(HEIGHT):
        pygame.draw.line(bg, lerp_col(top, bottom, (y / HEIGHT) ** 1.3), (0, y), (WIDTH, y))
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for x in range(0, WIDTH, 40):
        pygame.draw.line(overlay, (90, 130, 220, 14), (x, 0), (x, HEIGHT))
    for y in range(0, HEIGHT, 40):
        pygame.draw.line(overlay, (90, 130, 220, 14), (0, y), (WIDTH, y))
    rng = random.Random(11)
    for n in range(16):
        x, y = rng.randrange(0, WIDTH // 40) * 40, rng.randrange(0, HEIGHT // 40) * 40
        col = (34, 211, 238, 46) if n % 2 == 0 else (167, 139, 250, 46)
        horizontal = rng.random() < 0.5
        for _ in range(rng.randint(3, 5)):
            length = rng.randint(2, 5) * 40 * rng.choice((-1, 1))
            nx, ny = (x + length, y) if horizontal else (x, y + length)
            pygame.draw.line(overlay, col, (x, y), (nx, ny), 2)
            x, y, horizontal = nx, ny, not horizontal
        pygame.draw.circle(overlay, col[:3] + (110,), (x, y), 5, 2)
    bg.blit(overlay, (0, 0))
    return bg


# =============================================================================
# FONTS
# =============================================================================
class FontBook:
    """Caches system fonts. Fallback: segoeui -> arial -> dejavusans -> default."""
    NAMES = "segoeui,arial,dejavusans"

    def __init__(self):
        self._cache = {}

    def get(self, size, bold=True):
        key = (int(size), bold)
        if key not in self._cache:
            try:
                font = pygame.font.SysFont(self.NAMES, int(size), bold=bold)
            except Exception:  # extremely defensive: fall back to pygame default
                font = pygame.font.Font(None, int(size * 1.25))
            self._cache[key] = font
        return self._cache[key]


# =============================================================================
# BACKGROUND PARTICLE
# =============================================================================
class BackgroundParticle:
    """A softly twinkling dot drifting upward behind the UI."""

    def __init__(self, rng):
        self.rng = rng
        self.x = rng.uniform(0, WIDTH)
        self.y = rng.uniform(0, HEIGHT)
        self.vx = rng.uniform(-6, 6)
        self.vy = rng.uniform(-18, -5)
        self.radius = rng.choice((1, 1, 2, 2, 3))
        self.color = C_CYAN if rng.random() < 0.6 else C_PURPLE
        self.phase = rng.uniform(0, math.tau)
        self.speed = rng.uniform(0.8, 2.2)
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y < -8:
            self.y = HEIGHT + 8
            self.x = self.rng.uniform(0, WIDTH)
        if self.x < -8:
            self.x = WIDTH + 8
        elif self.x > WIDTH + 8:
            self.x = -8

    def draw(self, surf):
        tw = 0.5 + 0.5 * math.sin(self.t * self.speed + self.phase)
        col = lerp_col((14, 20, 44), self.color, 0.15 + 0.6 * tw)
        pygame.draw.circle(surf, col, (int(self.x), int(self.y)), self.radius)


# =============================================================================
# CONFETTI
# =============================================================================
class Confetti:
    """One piece of confetti with gravity, drag, spin and tumbling flutter."""
    COLORS = [C_CYAN, C_PURPLE, C_GREEN, C_AMBER, (251, 113, 133), (255, 255, 255)]

    def __init__(self, rng):
        angle = math.radians(rng.uniform(200, 340))  # upward cone
        speed = rng.uniform(250, 820)
        self.x = WIDTH / 2 + rng.uniform(-120, 120)
        self.y = 300 + rng.uniform(-30, 30)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.w = rng.uniform(6, 12)
        self.h = rng.uniform(8, 16)
        self.rot = rng.uniform(0, math.tau)
        self.spin = rng.uniform(-9, 9)
        self.color = rng.choice(self.COLORS)

    def update(self, dt):
        """Advance physics. Returns False once the piece has left the screen."""
        self.vy += 900.0 * dt
        drag = max(0.0, 1.0 - 0.9 * dt)
        self.vx *= drag
        self.vy *= (1.0 - 0.25 * dt)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.spin * dt
        return self.y < HEIGHT + 30 and -40 < self.x < WIDTH + 40

    def draw(self, surf):
        flutter = abs(math.cos(self.rot * 1.7)) * 0.8 + 0.2
        hw, hh = self.w / 2, self.h / 2 * flutter
        c, s = math.cos(self.rot), math.sin(self.rot)
        pts = [(self.x + px * c - py * s, self.y + px * s + py * c)
               for px, py in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        pygame.draw.polygon(surf, self.color, pts)


# =============================================================================
# BUTTON
# =============================================================================
class Button:
    """Reusable button: hover animation, colour transition, pressed offset,
    rounded corners, optional glow, disabled look and a callback."""

    def __init__(self, rect, text, callback, color=C_CYAN, font_size=18,
                 glow=False, align="center", wrap=False, radius=12):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.callback = callback
        self.color = color
        self.font_size = font_size
        self.glow = glow
        self.align = align
        self.wrap = wrap
        self.radius = radius
        self.enabled = True
        self.visible = True
        self.hover_t = 0.0
        self.press = False
        self.clip = None      # optional visible region (scroll lists)
        self.badge = None     # optional (text, colour) pill on the right

    def _inside(self, pos):
        return self.rect.collidepoint(pos) and (self.clip is None or self.clip.collidepoint(pos))

    def update(self, dt, mouse_pos):
        target = 1.0 if (self.enabled and self.visible and self._inside(mouse_pos)) else 0.0
        self.hover_t = approach(self.hover_t, target, 16.0, dt)
        if not self.enabled:
            self.press = False

    def handle_event(self, event):
        """Returns True if the event was consumed by this button."""
        if not (self.enabled and self.visible):
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self._inside(event.pos):
            self.press = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_pressed, self.press = self.press, False
            if was_pressed:
                if self._inside(event.pos) and callable(self.callback):
                    self.callback()
                return True
        return False

    def draw(self, surf, fonts):
        if not self.visible:
            return
        r = self.rect.copy()
        if self.press and self.enabled:
            r.y += 2
        h = self.hover_t
        if self.enabled:
            fill = lerp_col(C_CARD, self.color, 0.14 + 0.28 * h)
            edge = lerp_col(lerp_col(self.color, C_CARD, 0.40), self.color, h)
            txt = lerp_col(C_TEXT, (255, 255, 255), h)
            level = max(int(round(h * 4)), 1 if self.glow else 0)
        else:
            fill = lerp_col(C_BG2, C_CARD, 0.45)
            edge = (42, 54, 80)
            txt = (104, 116, 140)
            level = 0
        if level > 0:
            g = glow_surface(r.w, r.h, self.color, self.radius, 12, level)
            surf.blit(g, (r.x - 12, r.y - 12))
        pygame.draw.rect(surf, fill, r, border_radius=self.radius)
        band = pygame.Rect(r.x + 2, r.y + 2, r.w - 4, max(2, r.h // 2 - 2))
        pygame.draw.rect(surf, lerp_col(fill, (255, 255, 255), 0.06), band,
                         border_top_left_radius=self.radius - 2,
                         border_top_right_radius=self.radius - 2)
        pygame.draw.rect(surf, edge, r, 2, border_radius=self.radius)
        area = r.inflate(-20, -8)
        if self.badge:
            area.w -= 56
        if self.wrap:
            draw_wrapped(surf, fonts, self.text, txt, area, self.font_size,
                         align=self.align, valign="middle", min_size=10)
        else:
            font = fit_font(fonts, self.text, area.w, self.font_size, 9)
            img = font.render(self.text, True, txt)
            pos = img.get_rect(center=area.center)
            if self.align == "left":
                pos.left = area.left
            old = surf.get_clip()
            surf.set_clip(area.clip(old))
            surf.blit(img, pos)
            surf.set_clip(old)
        if self.badge:
            label, col = self.badge
            pill = pygame.Rect(r.right - 56, r.centery - 12, 46, 24)
            pygame.draw.rect(surf, lerp_col(C_BG, col, 0.28), pill, border_radius=12)
            pygame.draw.rect(surf, col, pill, 2, border_radius=12)
            font = fonts.get(13, True)
            draw_text(surf, font, label, col, pill.center, "center")


# =============================================================================
# PERSON CARD
# =============================================================================
class PersonCard:
    """Gallery card: hover lift/glow, circular avatar, badge, elimination
    fade/shrink with a diagonal red line, and a user cross-out overlay."""
    W, H = 160, 145

    def __init__(self, index, person, pos):
        self.index = index
        self.person = person
        self.base = pygame.Rect(pos[0], pos[1], self.W, self.H)
        self.color = name_color(person["name"])
        self.initials = initials(person["name"])
        self.badge = badge_for(person)
        self.hover_t = 0.0
        self.elim_t = 0.0
        self.cross_t = 0.0
        self.eliminated = False
        self.crossed = False

    def reset(self):
        self.eliminated = False
        self.crossed = False
        self.elim_t = 0.0
        self.cross_t = 0.0

    def hit(self, pos):
        return self.base.collidepoint(pos)

    def update(self, dt, mouse_pos):
        hovering = self.base.collidepoint(mouse_pos)
        self.hover_t = approach(self.hover_t, 1.0 if hovering else 0.0, 14.0, dt)
        self.elim_t = approach(self.elim_t, 1.0 if self.eliminated else 0.0, 5.0, dt)
        self.cross_t = approach(self.cross_t, 1.0 if self.crossed else 0.0, 9.0, dt)

    def draw(self, surf, fonts, time, final_mode=False):
        e, x = self.elim_t, self.cross_t
        scale = 1.0 - 0.08 * e
        w, h = int(self.W * scale), int(self.H * scale)
        rect = pygame.Rect(0, 0, w, h)
        rect.center = self.base.center
        rect.y -= int(7 * self.hover_t * (1.0 - e))
        accent = C_PURPLE if final_mode else C_CYAN

        # Soft shadow
        shadow = glow_surface(w, h, (0, 0, 0), 16, 10, 4)
        surf.blit(shadow, (rect.x - 10, rect.y - 4))
        # Hover / selection glow
        level = int(round(self.hover_t * 4 * (1.0 - 0.6 * e)))
        if final_mode and e < 0.5:
            level = max(level, 1 + int(1.6 * (0.5 + 0.5 * math.sin(time * 4.5))))
        if level > 0:
            surf.blit(glow_surface(w, h, accent, 16, 14, min(4, level)), (rect.x - 14, rect.y - 14))

        grey = (50, 56, 70)
        fill = lerp_col(C_CARD, C_CARD_HOVER, self.hover_t)
        fill = lerp_col(fill, grey, e * 0.9)
        fill = lerp_col(fill, (74, 38, 52), x * 0.35)
        border = lerp_col((46, 64, 96), accent, self.hover_t)
        border = lerp_col(border, (70, 76, 90), e)
        pygame.draw.rect(surf, fill, rect, border_radius=16)
        inner = rect.inflate(-8, -8)
        inner_fill = lerp_col(fill, self.color, 0.10 * (1.0 - e))
        pygame.draw.rect(surf, inner_fill, inner, border_radius=12)
        pygame.draw.rect(surf, lerp_col(inner_fill, (255, 255, 255), 0.06),
                         (inner.x, inner.y, inner.w, max(4, inner.h // 3)),
                         border_top_left_radius=12, border_top_right_radius=12)
        pygame.draw.rect(surf, border, rect, 2, border_radius=16)

        # Avatar
        cx, cy, r = rect.centerx, rect.y + int(46 * scale), int(30 * scale)
        ring = lerp_col(self.color, grey, e)
        pygame.draw.circle(surf, lerp_col(self.color, C_BG, 0.55) if e < 0.01 else lerp_col(lerp_col(self.color, C_BG, 0.55), (60, 64, 78), e),
                           (cx, cy), r + 3)
        pygame.draw.circle(surf, lerp_col(lerp_col(self.color, C_BG, 0.62), (44, 48, 60), e), (cx, cy), r)
        pygame.draw.circle(surf, ring, (cx, cy), r, 3)
        font = fonts.get(max(10, int(24 * scale)), True)
        draw_text(surf, font, self.initials, lerp_col((255, 255, 255), (150, 156, 170), e), (cx, cy), "center")

        # Name (auto shrink / wrap) and badge
        name_rect = pygame.Rect(rect.x + 8, rect.y + int(80 * scale), rect.w - 16, int(34 * scale))
        draw_wrapped(surf, fonts, self.person["name"], lerp_col(C_TEXT, (130, 138, 154), e),
                     name_rect, 15, align="center", valign="middle", min_size=10)
        badge_font = fonts.get(max(8, int(10 * scale)), True)
        bw = badge_font.size(self.badge)[0] + 18
        pill = pygame.Rect(0, 0, bw, int(17 * scale))
        pill.midbottom = (rect.centerx, rect.bottom - 7)
        bcol = lerp_col(self.color, grey, e)
        pygame.draw.rect(surf, lerp_col(C_BG, bcol, 0.30), pill, border_radius=9)
        pygame.draw.rect(surf, bcol, pill, 1, border_radius=9)
        draw_text(surf, badge_font, self.badge, lerp_col(C_TEXT, (130, 138, 154), e), pill.center, "center")

        # Elimination diagonal
        if e > 0.01:
            p1 = (rect.x + 12, rect.y + 12)
            p2 = (rect.right - 12, rect.bottom - 12)
            end = (lerp(p1[0], p2[0], e), lerp(p1[1], p2[1], e))
            pygame.draw.line(surf, (110, 28, 40), p1, end, 9)
            pygame.draw.line(surf, C_RED, p1, end, 4)
        # User cross-out (X)
        if x > 0.01:
            a1, a2 = (rect.x + 16, rect.y + 16), (rect.right - 16, rect.bottom - 16)
            b1, b2 = (rect.right - 16, rect.y + 16), (rect.x + 16, rect.bottom - 16)
            for s, t in ((a1, a2), (b1, b2)):
                end = (lerp(s[0], t[0], x), lerp(s[1], t[1], x))
                pygame.draw.line(surf, (110, 28, 40), s, end, 9)
                pygame.draw.line(surf, C_RED, s, end, 4)


# =============================================================================
# GAME
# =============================================================================
class Game:
    """Owns the window, state machine, both game modes and all drawing."""

    MENU, AI_GUESS, USER_GUESS, RESULT = "MENU", "AI_GUESS", "USER_GUESS", "RESULT"
    PANEL = pygame.Rect(900, 20, 356, 680) if pygame else None
    GALLERY_X, GALLERY_Y, GAP = 24, 88, 12

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Guess the Person  -  NEURAL INTERFACE v1.0")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.fonts = FontBook()
        self.rng = random.Random()
        self.has_wheel_event = hasattr(pygame, "MOUSEWHEEL")
        self.running = True
        self.state = self.MENU
        self.time = 0.0
        self.input_lock = 0.0
        self.difficulty = "HARD"
        self.diff_t = 1.0
        self.wins = 0
        self.losses = 0
        self.bg = build_background()
        self.particles = [BackgroundParticle(self.rng) for _ in range(70)]
        self.confetti = []
        self.glow_cache = {}
        # Screen transition (fade through black)
        self.fade, self.fade_dir, self.pending = 1.0, -1, None
        self.fade_surf = pygame.Surface((WIDTH, HEIGHT))
        self.fade_surf.fill((4, 6, 14))
        # Gallery
        self.cards = []
        for i, person in enumerate(PEOPLE):
            col, row = i % 5, i // 5
            pos = (self.GALLERY_X + col * (PersonCard.W + self.GAP),
                   self.GALLERY_Y + row * (PersonCard.H + self.GAP))
            self.cards.append(PersonCard(i, person, pos))
        # Menu geometry
        self.menu_card_rects = [pygame.Rect(210, 186, 400, 266), pygame.Rect(670, 186, 400, 266)]
        self.menu_hover = [0.0, 0.0]
        self.toggle_rect = pygame.Rect(520, 468, 240, 42)
        # AI mode state
        self.ai_candidates, self.ai_asked, self.ai_history, self.ai_stack = [], set(), [], []
        self.ai_phase, self.ai_tag, self.ai_explain = "ask", None, ""
        self.ai_notice, self.ai_guess, self.ai_fallback = "", None, False
        self.prog_t = 1.0
        # User mode state
        self.secret = 0
        self.u_asked, self.u_order, self.u_hints = {}, [], set()
        self.final_mode, self.confirm_idx = False, None
        self.u_message = ""
        self.q_scroll, self.q_scroll_target = 0.0, 0.0
        self.q_view = pygame.Rect(908, 90, 340, 462)
        self.result = None
        self._create_buttons()

    # ------------------------------------------------------------------ setup
    def _create_buttons(self):
        """Create every button once; per-frame code only toggles state."""
        x0 = 908
        self.quit_btn = Button((1156, 22, 100, 38), "QUIT", self.quit_game, C_RED, 16)
        self.menu_buttons = [self.quit_btn]
        # AI mode
        self.ai_menu_btn = Button((762, 26, 110, 38), "MENU", self.go_menu, C_PURPLE, 16)
        self.yes_btn = Button((x0, 162, 108, 56), "YES", lambda: self.process_ai_answer(True), C_GREEN, 22, glow=True)
        self.no_btn = Button((x0 + 116, 162, 108, 56), "NO", lambda: self.process_ai_answer(False), C_RED, 22, glow=True)
        self.ns_btn = Button((x0 + 232, 162, 108, 56), "NOT SURE", lambda: self.process_ai_answer(None), C_PURPLE, 15, glow=True)
        self.correct_btn = Button((x0, 162, 166, 56), "CORRECT", lambda: self.ai_confirm_guess(True), C_GREEN, 20, glow=True)
        self.wrong_btn = Button((x0 + 174, 162, 166, 56), "WRONG", lambda: self.ai_confirm_guess(False), C_RED, 20, glow=True)
        self.undo_btn = Button((x0, 636, 166, 44), "UNDO", self.undo_last_answer, C_CYAN, 18)
        self.restart_btn = Button((x0 + 174, 636, 166, 44), "RESTART", self.start_ai_game, C_AMBER, 18)
        # User mode
        self.user_menu_btn = Button((762, 26, 110, 38), "MENU", self.go_menu, C_PURPLE, 16)
        self.hint_btn = Button((x0, 636, 166, 44), "HINT (-1)", self.use_hint, C_PURPLE, 17)
        self.final_btn = Button((x0 + 174, 636, 166, 44), "FINAL GUESS", self.make_final_guess, C_CYAN, 17, glow=True)
        self.q_buttons = []
        for tag in TAGS:
            b = Button((0, 0, 326, 46), QUESTION_TEXT[tag], functools.partial(self.ask_user_question, tag),
                       C_CYAN, 14, align="left", wrap=True, radius=10)
            self.q_buttons.append(b)
        self.confirm_btn = Button((420, 402, 200, 50), "CONFIRM", lambda: self.resolve_guess(True), C_GREEN, 20, glow=True)
        self.cancel_btn = Button((660, 402, 200, 50), "CANCEL", lambda: self.resolve_guess(False), C_RED, 20)
        # Result
        self.again_btn = Button((430, 612, 200, 56), "PLAY AGAIN", self.play_again, C_GREEN, 20, glow=True)
        self.menu2_btn = Button((650, 612, 200, 56), "MAIN MENU", self.go_menu, C_CYAN, 20, glow=True)
        self.all_buttons = ([self.quit_btn, self.ai_menu_btn, self.yes_btn, self.no_btn, self.ns_btn,
                             self.correct_btn, self.wrong_btn, self.undo_btn, self.restart_btn,
                             self.user_menu_btn, self.hint_btn, self.final_btn, self.confirm_btn,
                             self.cancel_btn, self.again_btn, self.menu2_btn] + self.q_buttons)

    def active_buttons(self):
        """Buttons that are currently visible AND receive events."""
        if self.state == self.MENU:
            return list(self.menu_buttons)
        if self.state == self.AI_GUESS:
            act = [self.ai_menu_btn, self.undo_btn, self.restart_btn]
            if self.ai_phase == "ask":
                act += [self.yes_btn, self.no_btn, self.ns_btn]
            elif self.ai_phase == "guess":
                act += [self.correct_btn, self.wrong_btn]
            return act
        if self.state == self.USER_GUESS:
            if self.confirm_idx is not None:
                return [self.confirm_btn, self.cancel_btn]
            return [self.user_menu_btn, self.hint_btn, self.final_btn] + self.q_buttons
        if self.state == self.RESULT:
            return [self.again_btn, self.menu2_btn]
        return []

    # ------------------------------------------------------------- transitions
    @property
    def transitioning(self):
        return self.pending is not None or self.fade_dir != 0

    def transition(self, callback):
        """Fade to black, run `callback`, fade back in."""
        if self.pending is None:
            self.pending = callback
            self.fade_dir = 1

    def quit_game(self):
        self.running = False

    def go_menu(self):
        self.transition(self._enter_menu)

    def _enter_menu(self):
        self.state = self.MENU
        self.confetti = []

    def play_again(self):
        if self.result and self.result.get("mode") == "USER":
            self.transition(self.start_user_game)
        else:
            self.transition(self.start_ai_game)

    # ------------------------------------------------------------------- AI mode
    def start_ai_game(self):
        """Reset all AI-mode state and ask the first question."""
        self.state = self.AI_GUESS
        self.ai_candidates = list(range(len(PEOPLE)))
        self.ai_asked, self.ai_history, self.ai_stack = set(), [], []
        self.ai_phase, self.ai_tag, self.ai_explain = "ask", None, ""
        self.ai_notice, self.ai_guess, self.ai_fallback = "", None, False
        self.input_lock = 0.25
        for c in self.cards:
            c.reset()
        self.prog_t = 1.0
        self.select_ai_question()

    def select_ai_question(self):
        """Pick the next question (or switch to guess / empty phase)."""
        cands = self.ai_candidates
        self.ai_tag, self.ai_guess = None, None
        if not cands:
            self.ai_phase = "empty"
            self.ai_explain = "No candidate matches the answers given."
            return
        if len(cands) == 1:
            self.ai_phase, self.ai_guess = "guess", cands[0]
            self.ai_explain = "Only one candidate remains."
            return
        if self.difficulty == "HARD":
            tag = choose_hard(cands, self.ai_asked, self.rng)
        else:
            tag = choose_easy(cands, self.ai_asked, self.rng)
        if tag is None:  # nothing useful left: fallback guess
            self.ai_phase = "guess"
            self.ai_guess = self.rng.choice(cands)
            self.ai_fallback = True
            self.ai_explain = "No useful question remains. Making a fallback guess."
            return
        self.ai_phase, self.ai_tag = "ask", tag
        if self.difficulty == "HARD":
            yes, no = remaining_split(cands, tag)
            self.ai_explain = "%d YES / %d NO \u2014 Most balanced split" % (yes, no)
        else:
            self.ai_explain = "Random useful question"

    def _ai_snapshot(self):
        return {"cands": list(self.ai_candidates), "asked": set(self.ai_asked),
                "history": list(self.ai_history), "phase": self.ai_phase,
                "tag": self.ai_tag, "explain": self.ai_explain, "guess": self.ai_guess,
                "notice": self.ai_notice, "fallback": self.ai_fallback}

    def process_ai_answer(self, answer):
        """Handle YES (True), NO (False) or NOT SURE (None)."""
        if self.input_lock > 0 or self.ai_phase != "ask":
            return
        tag = self.ai_tag
        if tag is None or tag in self.ai_asked or tag not in TAGS:
            return
        self.input_lock = 0.25
        self.ai_stack.append(self._ai_snapshot())
        self.ai_asked.add(tag)
        if answer is not None:
            self.ai_candidates = filter_candidates(self.ai_candidates, tag, answer)
        self.ai_history.append((tag, answer))
        self.ai_notice = "Noted: NOT SURE keeps everyone in play." if answer is None else ""
        self._sync_ai_cards()
        self.select_ai_question()

    def undo_last_answer(self):
        """Pop the history stack and restore the previous AI state."""
        if self.input_lock > 0 or not self.ai_stack:
            return
        self.input_lock = 0.2
        snap = self.ai_stack.pop()
        self.ai_candidates, self.ai_asked = snap["cands"], snap["asked"]
        self.ai_history, self.ai_phase = snap["history"], snap["phase"]
        self.ai_tag, self.ai_explain, self.ai_guess = snap["tag"], snap["explain"], snap["guess"]
        self.ai_notice, self.ai_fallback = snap["notice"], snap["fallback"]
        self._sync_ai_cards()

    def _sync_ai_cards(self):
        alive = set(self.ai_candidates)
        for c in self.cards:
            c.eliminated = c.index not in alive

    def ai_confirm_guess(self, correct):
        """CORRECT / WRONG buttons for the AI's final guess."""
        if self.input_lock > 0 or self.ai_phase != "guess" or self.ai_guess is None:
            return
        self.input_lock = 0.3
        guess = self.ai_guess
        n = len(self.ai_history)
        if correct:
            self.show_result(True, "AI VICTORY", C_PURPLE, "Got it in %s!" % plural(n, "question"),
                             guess, "YOUR PERSON IS", "Better luck next time, human.", False, "AI")
            return
        others = [i for i in self.ai_candidates if i != guess]
        if self.ai_fallback and others:  # fallback mode: try the next best guess
            self.ai_candidates = others
            self._sync_ai_cards()
            self.ai_guess = self.rng.choice(others)
            self.ai_notice = "Hmm, let me try someone else..."
            return
        self.show_result(True, "YOU WIN!", C_GREEN, "You outsmarted the AI!", guess,
                         "MY LAST GUESS WAS", "Great job \u2014 I couldn't crack it.", True, "AI")

    # ----------------------------------------------------------------- user mode
    def start_user_game(self):
        """The AI secretly picks someone."""
        self.state = self.USER_GUESS
        self.secret = self.rng.randrange(len(PEOPLE))
        self.u_asked, self.u_order, self.u_hints = {}, [], set()
        self.final_mode, self.confirm_idx = False, None
        self.u_message = "Ask a question, use a hint, or click cards to cross people out."
        self.q_scroll = self.q_scroll_target = 0.0
        self.input_lock = 0.25
        for c in self.cards:
            c.reset()

    @property
    def u_used(self):
        return len(self.u_order)

    def _unasked_tags(self):
        return [t for t in TAGS if t not in self.u_asked]

    def ask_user_question(self, tag):
        """Reveal the truthful answer for one question."""
        if self.input_lock > 0 or self.confirm_idx is not None:
            return
        if tag not in TAGS or tag in self.u_asked or self.u_used >= MAX_QUESTIONS:
            return
        self.input_lock = 0.2
        ans = PEOPLE[self.secret]["tags"][tag]
        self.u_asked[tag] = ans
        self.u_order.append((tag, ans, False))
        self.u_message = "%s  \u2192  %s" % (QUESTION_TEXT[tag], "YES" if ans else "NO")
        self._after_question_used()

    def use_hint(self):
        """Reveal one extra TRUE attribute (costs one question)."""
        if self.input_lock > 0 or self.confirm_idx is not None or self.u_used >= MAX_QUESTIONS:
            return
        tags = self._unasked_tags()
        if not tags:
            return
        true_tags = [t for t in tags if PEOPLE[self.secret]["tags"][t]]
        tag = self.rng.choice(true_tags or tags)
        self.input_lock = 0.25
        ans = PEOPLE[self.secret]["tags"][tag]
        self.u_asked[tag] = ans
        self.u_hints.add(tag)
        self.u_order.append((tag, ans, True))
        self.u_message = "HINT: the answer to \"%s\" is %s." % (QUESTION_TEXT[tag], "YES" if ans else "NO")
        self._after_question_used()

    def _after_question_used(self):
        if self.u_used >= MAX_QUESTIONS:
            self.final_mode = True
            self.u_message += "   No questions left: pick your final guess!"

    def make_final_guess(self, idx=None):
        """Without `idx`: toggle person-selection mode. With `idx`: open the
        confirmation dialog for that card."""
        if self.input_lock > 0 and idx is not None:
            return
        if idx is None:
            if self.confirm_idx is None and self.u_used < MAX_QUESTIONS:
                self.final_mode = not self.final_mode
                self.u_message = ("Select a person card to make your final guess."
                                  if self.final_mode else "Final guess cancelled.")
            return
        if self.final_mode and 0 <= idx < len(PEOPLE) and self.confirm_idx is None:
            self.confirm_idx = idx
            self.input_lock = 0.2

    def resolve_guess(self, confirmed):
        """Confirm or cancel the guess dialog."""
        if self.confirm_idx is None or self.input_lock > 0:
            return
        idx, self.confirm_idx = self.confirm_idx, None
        self.input_lock = 0.25
        if not confirmed:
            return
        n = self.u_used
        secret = PEOPLE[self.secret]
        if idx == self.secret:
            self.show_result(True, "VICTORY", C_GREEN, "Got it in %s!" % plural(n, "question"),
                             self.secret, "THE SECRET PERSON", "", True, "USER")
        else:
            self.show_result(False, "NOT QUITE", C_RED,
                             "So close! Even great minds need another try.", self.secret,
                             "THE SECRET PERSON WAS", "You guessed %s." % PEOPLE[idx]["name"], False, "USER")
        del secret

    # ------------------------------------------------------------------- result
    def show_result(self, celebrate, heading, color, line, person_idx, label, detail, player_won, mode):
        if self.pending is not None:
            return
        self.result = {"celebrate": celebrate, "heading": heading, "color": color, "line": line,
                       "person": person_idx, "label": label, "detail": detail, "mode": mode}
        if player_won:
            self.wins += 1
        else:
            self.losses += 1
        self.transition(self._enter_result)

    def _enter_result(self):
        self.state = self.RESULT
        self.confetti = [Confetti(self.rng) for _ in range(150)] if self.result["celebrate"] else []
        self.input_lock = 0.3

    # -------------------------------------------------------------------- events
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if self.transitioning:
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._handle_escape()
                continue
            # Scrolling (mouse wheel)
            if self.state == self.USER_GUESS and self.confirm_idx is None:
                if event.type == pygame.MOUSEWHEEL and self.PANEL.collidepoint(pygame.mouse.get_pos()):
                    self._scroll_questions(-event.y * 52)
                elif (not self.has_wheel_event and event.type == pygame.MOUSEBUTTONDOWN
                      and event.button in (4, 5) and self.PANEL.collidepoint(event.pos)):
                    self._scroll_questions(-52 if event.button == 4 else 52)
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_DOWN):
                    self._scroll_questions(-52 if event.key == pygame.K_UP else 52)
            consumed = False
            for b in self.active_buttons():
                if b.handle_event(event):
                    consumed = True
                    break
            if consumed or self.transitioning:
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _handle_escape(self):
        if self.state == self.MENU:
            self.running = False
        elif self.state == self.USER_GUESS and self.confirm_idx is not None:
            self.confirm_idx = None
        else:
            self.go_menu()

    def _scroll_questions(self, delta):
        total = len(self.q_buttons) * 52 - 6
        max_scroll = max(0, total - self.q_view.h)
        self.q_scroll_target = clamp(self.q_scroll_target + delta, 0, max_scroll)

    def _handle_click(self, pos):
        if self.state == self.MENU:
            for i, rect in enumerate(self.menu_card_rects):
                if rect.collidepoint(pos):
                    self.transition(self.start_ai_game if i == 0 else self.start_user_game)
                    return
            if self.toggle_rect.collidepoint(pos):
                self.difficulty = "EASY" if pos[0] < self.toggle_rect.centerx else "HARD"
        elif self.state == self.USER_GUESS and self.confirm_idx is None:
            for card in self.cards:
                if card.hit(pos):
                    if self.final_mode:
                        self.make_final_guess(card.index)
                    else:
                        card.crossed = not card.crossed
                    return

    # -------------------------------------------------------------------- update
    def update(self, dt):
        self.time += dt
        self.input_lock = max(0.0, self.input_lock - dt)
        mouse = pygame.mouse.get_pos()
        for p in self.particles:
            p.update(dt)
        # Transition
        if self.fade_dir == 1:
            self.fade = min(1.0, self.fade + dt / 0.22)
            if self.fade >= 1.0:
                cb, self.pending, self.fade_dir = self.pending, None, -1
                if callable(cb):
                    cb()
        elif self.fade_dir == -1:
            self.fade = max(0.0, self.fade - dt / 0.28)
            if self.fade <= 0.0:
                self.fade_dir = 0
        # Buttons
        active = {id(b) for b in self.active_buttons()}
        self._update_state_buttons(dt)
        for b in self.all_buttons:
            b.update(dt, mouse if id(b) in active else (-999, -999))
        # State specific
        if self.state == self.MENU:
            for i, rect in enumerate(self.menu_card_rects):
                self.menu_hover[i] = approach(self.menu_hover[i], 1.0 if rect.collidepoint(mouse) and not self.transitioning else 0.0, 12.0, dt)
            self.diff_t = approach(self.diff_t, 1.0 if self.difficulty == "HARD" else 0.0, 10.0, dt)
        elif self.state in (self.AI_GUESS, self.USER_GUESS):
            m = mouse if (self.confirm_idx is None and not self.transitioning) else (-999, -999)
            for c in self.cards:
                c.update(dt, m)
            if self.state == self.AI_GUESS:
                self.prog_t = approach(self.prog_t, len(self.ai_candidates) / float(len(PEOPLE)), 6.0, dt)
            else:
                self.q_scroll = approach(self.q_scroll, self.q_scroll_target, 14.0, dt)
        self.confetti = [c for c in self.confetti if c.update(dt)]

    def _update_state_buttons(self, dt):
        """Per-frame enabled flags, labels, badges and scroll positions."""
        if self.state == self.AI_GUESS:
            self.undo_btn.enabled = bool(self.ai_stack)
        elif self.state == self.USER_GUESS:
            left = MAX_QUESTIONS - self.u_used
            dialog = self.confirm_idx is not None
            self.hint_btn.enabled = left > 0 and bool(self._unasked_tags()) and not dialog
            self.final_btn.enabled = not dialog and left > 0
            self.final_btn.text = "CANCEL GUESS" if self.final_mode else "FINAL GUESS"
            if left <= 0:
                self.final_btn.text = "PICK A CARD"
            self.final_btn.color = C_RED if (self.final_mode and left > 0) else C_CYAN
            for i, (tag, b) in enumerate(zip(TAGS, self.q_buttons)):
                b.rect.topleft = (self.q_view.x, self.q_view.y + i * 52 - int(round(self.q_scroll)))
                b.clip = self.q_view
                if tag in self.u_asked:
                    ans = self.u_asked[tag]
                    b.enabled = False
                    col = C_PURPLE if tag in self.u_hints else (C_GREEN if ans else C_RED)
                    b.badge = ("YES" if ans else "NO", col)
                else:
                    b.badge = None
                    b.enabled = left > 0 and not dialog

    # ---------------------------------------------------------------------- draw
    def draw(self):
        s = self.screen
        s.blit(self.bg, (0, 0))
        for p in self.particles:
            p.draw(s)
        if self.state == self.MENU:
            self.draw_menu()
        elif self.state == self.AI_GUESS:
            self.draw_ai_mode()
        elif self.state == self.USER_GUESS:
            self.draw_user_mode()
        elif self.state == self.RESULT:
            self.draw_result()
        for c in self.confetti:
            c.draw(s)
        if self.fade > 0.0:
            self.fade_surf.set_alpha(int(255 * self.fade))
            s.blit(self.fade_surf, (0, 0))
        pygame.display.flip()

    # ---- shared drawing helpers
    def glow_text(self, text, size, color, center, pulse=1.0, core=(235, 250, 255)):
        """Large text with a cached blurred glow behind it."""
        key = (text, size, color)
        if key not in self.glow_cache:
            font = self.fonts.get(size, True)
            core_img = font.render(text, True, core)
            tint = font.render(text, True, color)
            pad = 40
            big = pygame.Surface((tint.get_width() + pad * 2, tint.get_height() + pad * 2), pygame.SRCALPHA)
            big.blit(tint, (pad, pad))
            small = pygame.transform.smoothscale(big, (max(1, big.get_width() // 6), max(1, big.get_height() // 6)))
            blur = pygame.transform.smoothscale(small, big.get_size())
            self.glow_cache[key] = (core_img, blur)
        core_img, blur = self.glow_cache[key]
        blur.set_alpha(int(255 * clamp(pulse, 0.0, 1.0)))
        rect = blur.get_rect(center=center)
        self.screen.blit(blur, rect)
        self.screen.blit(blur, rect)
        self.screen.blit(core_img, core_img.get_rect(center=center))

    def draw_panel(self, rect, tint=(14, 22, 44), alpha=205, border=C_CYAN, radius=18):
        self.screen.blit(glass_surface(rect.w, rect.h, radius, tint, alpha, border), rect.topleft)

    def draw_gallery(self, final_mode=False):
        for c in sorted(self.cards, key=lambda k: k.hover_t):
            c.draw(self.screen, self.fonts, self.time, final_mode)

    def draw_progress(self, rect, frac):
        s = self.screen
        pygame.draw.rect(s, (8, 14, 30), rect, border_radius=rect.h // 2)
        fw = max(rect.h, int(rect.w * clamp(frac, 0.0, 1.0)))
        fill = pygame.Rect(rect.x, rect.y, fw, rect.h)
        pygame.draw.rect(s, C_CYAN, fill, border_radius=rect.h // 2)
        old = s.get_clip()
        s.set_clip(pygame.Rect(fill.x + fw // 2, fill.y, fw - fw // 2, fill.h).clip(old))
        pygame.draw.rect(s, C_PURPLE, fill, border_radius=rect.h // 2)
        s.set_clip(fill.clip(old))
        sx = fill.x + int(((self.time * 0.8) % 1.4 - 0.2) * fw)
        pygame.draw.rect(s, (200, 245, 255), (sx, fill.y, 14, fill.h))
        s.set_clip(old)
        pygame.draw.rect(s, (60, 90, 140), rect, 1, border_radius=rect.h // 2)

    def _label(self, text, pos, color=C_MUTED, size=13, anchor="topleft"):
        draw_text(self.screen, self.fonts.get(size, True), text, color, pos, anchor)

    # ------------------------------------------------------------------- MENU
    def draw_menu(self):
        s, f, t = self.screen, self.fonts, self.time
        # Title block
        self.glow_text("GUESS THE PERSON", 74, C_CYAN, (WIDTH // 2, 74), 0.75 + 0.25 * math.sin(t * 2.0))
        draw_text(s, f.get(19, True), "CAN YOUR MIND OUTSMART ARTIFICIAL INTELLIGENCE?", C_PURPLE, (WIDTH // 2, 128), "center")
        # Animated glowing underline
        ux0, ux1, uy = WIDTH // 2 - 270, WIDTH // 2 + 270, 152
        pygame.draw.line(s, (20, 70, 90), (ux0, uy), (ux1, uy), 3)
        sx = ux0 - 80 + ((t * 0.55) % 1.0) * (ux1 - ux0 + 160)
        for k in range(24):
            a = 1.0 - abs(k - 12) / 12.0
            x = sx - 60 + k * 5
            if ux0 <= x <= ux1:
                pygame.draw.line(s, lerp_col((20, 70, 90), (190, 250, 255), a), (x, uy), (x + 5, uy), 3)
        # Counters
        self.draw_panel(pygame.Rect(24, 20, 230, 46), radius=14)
        self._label("WINS", (40, 34), C_MUTED, 13)
        draw_text(s, f.get(20, True), str(self.wins), C_GREEN, (92, 31))
        self._label("LOSSES", (130, 34), C_MUTED, 13)
        draw_text(s, f.get(20, True), str(self.losses), C_RED, (196, 31))
        # Mode cards
        self._draw_mode_card(0, "AI GUESSES", "Think of someone. The AI reads your mind in 10 questions or fewer.", C_CYAN)
        self._draw_mode_card(1, "YOU GUESS", "The AI hides a secret person. Interrogate it, then make your final guess.", C_PURPLE)
        # Difficulty toggle
        r = self.toggle_rect
        draw_text(s, f.get(15, True), "DIFFICULTY", C_MUTED, (r.x - 16, r.centery), "midright")
        pygame.draw.rect(s, (10, 16, 34), r, border_radius=21)
        knob_col = lerp_col(C_GREEN, C_RED, self.diff_t)
        kx = r.x + 3 + int(self.diff_t * (r.w // 2 - 3))
        knob = pygame.Rect(kx, r.y + 3, r.w // 2, r.h - 6)
        s.blit(glow_surface(knob.w, knob.h, knob_col, 17, 10, 3), (knob.x - 10, knob.y - 10))
        pygame.draw.rect(s, lerp_col(C_CARD, knob_col, 0.55), knob, border_radius=18)
        pygame.draw.rect(s, knob_col, knob, 2, border_radius=18)
        pygame.draw.rect(s, (60, 90, 140), r, 2, border_radius=21)
        draw_text(s, f.get(16, True), "EASY", lerp_col(C_MUTED, (255, 255, 255), 1 - self.diff_t), (r.x + r.w // 4, r.centery), "center")
        draw_text(s, f.get(16, True), "HARD", lerp_col(C_MUTED, (255, 255, 255), self.diff_t), (r.x + 3 * r.w // 4, r.centery), "center")
        draw_text(s, f.get(13, True), "EASY: random useful questions  \u2022  HARD: best split", C_MUTED, (r.right + 16, r.centery), "midleft")
        # How to play
        hp = pygame.Rect(210, 526, 860, 152)
        self.draw_panel(hp, radius=18)
        draw_text(s, f.get(17, True), "HOW TO PLAY", C_CYAN, (hp.x + 24, hp.y + 14))
        pygame.draw.line(s, (34, 90, 110), (hp.x + 24, hp.y + 40), (hp.right - 24, hp.y + 40), 1)
        draw_text(s, f.get(15, True), "AI GUESSES", C_CYAN, (hp.x + 24, hp.y + 50))
        draw_wrapped(s, f, "Pick one of the 15 people in your head. Answer YES, NO or NOT SURE. "
                     "The AI eliminates candidates until only one is left.",
                     C_TEXT, pygame.Rect(hp.x + 24, hp.y + 74, 390, 68), 15, min_size=11, bold=False)
        draw_text(s, f.get(15, True), "YOU GUESS", C_PURPLE, (hp.x + 450, hp.y + 50))
        draw_wrapped(s, f, "Ask up to 10 questions (a hint costs one). Click cards to cross people "
                     "out, then press FINAL GUESS and pick your suspect.",
                     C_TEXT, pygame.Rect(hp.x + 450, hp.y + 74, 386, 68), 15, min_size=11, bold=False)
        draw_text(s, f.get(12, True), "NEURAL INTERFACE v1.0", C_MUTED, (WIDTH - 16, HEIGHT - 12), "bottomright")
        for b in self.menu_buttons:
            b.draw(s, f)

    def _draw_mode_card(self, i, title, desc, color):
        s, f = self.screen, self.fonts
        h = self.menu_hover[i]
        rect = self.menu_card_rects[i].move(0, -int(8 * h))
        s.blit(glow_surface(rect.w, rect.h, (0, 0, 0), 20, 12, 4), (rect.x - 12, rect.y - 6))
        s.blit(glow_surface(rect.w, rect.h, color, 20, 16, max(1, int(round(h * 4)))), (rect.x - 16, rect.y - 16))
        self.draw_panel(rect, tint=lerp_col((14, 22, 44), color, 0.08 + 0.08 * h), alpha=235, border=color, radius=20)
        art = pygame.Rect(rect.x + 16, rect.y + 16, rect.w - 32, 120)
        pygame.draw.rect(s, lerp_col(C_BG, C_CARD, 0.5), art, border_radius=14)
        old = s.get_clip()
        s.set_clip(art.clip(old))
        if i == 0:
            self._draw_ai_art(art)
        else:
            self._draw_vs_art(art)
        s.set_clip(old)
        pygame.draw.rect(s, lerp_col(color, C_CARD, 0.4), art, 2, border_radius=14)
        draw_text(s, f.get(30, True), title, lerp_col(color, (255, 255, 255), 0.35), (rect.centerx, rect.y + 160), "center")
        draw_wrapped(s, f, desc, C_MUTED, pygame.Rect(rect.x + 30, rect.y + 182, rect.w - 60, 44), 15,
                     align="center", valign="middle", min_size=11, bold=False)
        pill = pygame.Rect(0, 0, 130, 30)
        pill.midbottom = (rect.centerx, rect.bottom - 12)
        pygame.draw.rect(s, lerp_col(C_BG, color, 0.25 + 0.3 * h), pill, border_radius=15)
        pygame.draw.rect(s, color, pill, 2, border_radius=15)
        draw_text(s, f.get(14, True), "PLAY", (255, 255, 255), (pill.centerx + 10, pill.centery), "center")
        tx = pill.centerx - 28
        pygame.draw.polygon(s, (255, 255, 255), [(tx, pill.centery - 6), (tx, pill.centery + 6), (tx + 10, pill.centery)])

    def _draw_ai_art(self, art):
        """Animated neural network."""
        s, t = self.screen, self.time
        layers = [3, 4, 3]
        xs = [art.x + int(art.w * fr) for fr in (0.2, 0.5, 0.8)]
        nodes = []
        for xi, n in zip(xs, layers):
            nodes.append([(xi, art.y + int(art.h * (k + 1) / (n + 1))) for k in range(n)])
        k = 0
        for a_layer, b_layer in zip(nodes, nodes[1:]):
            for a in a_layer:
                for b in b_layer:
                    pygame.draw.line(s, (24, 80, 104), a, b, 1)
                    u = (t * 0.55 + k * 0.137) % 1.0
                    if k % 2 == 0:
                        pygame.draw.circle(s, (170, 245, 255), (int(lerp(a[0], b[0], u)), int(lerp(a[1], b[1], u))), 2)
                    k += 1
        for li, layer in enumerate(nodes):
            for ni, (x, y) in enumerate(layer):
                pulse = 0.5 + 0.5 * math.sin(t * 3 + li * 1.3 + ni)
                pygame.draw.circle(s, lerp_col((14, 60, 84), C_CYAN, 0.3 + 0.6 * pulse), (x, y), 8)
                pygame.draw.circle(s, C_CYAN, (x, y), 8, 2)

    def _draw_vs_art(self, art):
        """Human vs robot."""
        s, t = self.screen, self.time
        cy = art.centery
        hx, rx = art.x + 90, art.right - 90
        pygame.draw.circle(s, C_PURPLE, (hx, cy - 20), 17)
        pygame.draw.ellipse(s, C_PURPLE, pygame.Rect(hx - 32, cy + 2, 64, 52))
        head = pygame.Rect(0, 0, 62, 48)
        head.center = (rx, cy - 8)
        pygame.draw.line(s, C_CYAN, (rx, head.top), (rx, head.top - 14), 3)
        pygame.draw.circle(s, C_AMBER if int(t * 2) % 2 else C_CYAN, (rx, head.top - 16), 4)
        pygame.draw.rect(s, lerp_col(C_BG, C_CYAN, 0.25), head, border_radius=10)
        pygame.draw.rect(s, C_CYAN, head, 2, border_radius=10)
        blink = 0.5 + 0.5 * math.sin(t * 4)
        for ex in (-12, 12):
            pygame.draw.circle(s, lerp_col((10, 80, 100), (200, 250, 255), blink), (rx + ex, head.centery - 5), 6)
        pygame.draw.line(s, C_CYAN, (rx - 12, head.bottom - 11), (rx + 12, head.bottom - 11), 2)
        pygame.draw.rect(s, lerp_col(C_BG, C_CYAN, 0.25), (rx - 30, head.bottom + 6, 60, 22), border_radius=6)
        draw_text(s, self.fonts.get(28, True), "VS", lerp_col(C_AMBER, (255, 255, 255), blink * 0.5), (art.centerx, cy), "center")

    # ---------------------------------------------------------------- AI MODE
    def _ai_question_text(self):
        if self.ai_phase == "ask" and self.ai_tag in QUESTION_TEXT:
            return QUESTION_TEXT[self.ai_tag]
        if self.ai_phase == "guess" and self.ai_guess is not None:
            return "Is it %s?" % PEOPLE[self.ai_guess]["name"]
        return "Hmm... nobody matches your answers. Did a reply slip? Press UNDO to fix it, or RESTART."

    def draw_ai_mode(self):
        s, f = self.screen, self.fonts
        draw_text(s, f.get(30, True), "AI GUESSES", C_CYAN, (24, 20))
        draw_text(s, f.get(15, False), "Think of someone in the gallery and answer honestly.", C_MUTED, (24, 58))
        self.ai_menu_btn.draw(s, f)
        self.draw_gallery()
        self._draw_ai_strip()
        panel = self.PANEL
        self.draw_panel(panel, radius=20)
        x = 908
        if self.ai_phase == "ask":
            label, lcol = "QUESTION %d" % (len(self.ai_history) + 1), C_CYAN
        elif self.ai_phase == "guess":
            label, lcol = ("I CAN'T TELL THEM APART", C_AMBER) if self.ai_fallback else ("FINAL ANSWER", C_PURPLE)
        else:
            label, lcol = "NO MATCH", C_RED
        draw_text(s, f.get(15, True), label, lcol, (x + 4, 34))
        box = pygame.Rect(x, 58, 340, 94)
        pygame.draw.rect(s, (8, 14, 32), box, border_radius=14)
        pygame.draw.rect(s, lerp_col(lcol, C_CARD, 0.35 + 0.15 * math.sin(self.time * 3)), box, 2, border_radius=14)
        draw_wrapped(s, f, self._ai_question_text(), C_TEXT, box.inflate(-24, -14), 21,
                     align="center", valign="middle", min_size=12)
        for b in self.active_buttons():
            if b in (self.yes_btn, self.no_btn, self.ns_btn, self.correct_btn, self.wrong_btn):
                b.draw(s, f)
        n = len(self.ai_candidates)
        draw_text(s, f.get(12, True), "CANDIDATES REMAINING", C_MUTED, (x + 4, 236))
        draw_text(s, f.get(24, True), "%d / %d" % (n, len(PEOPLE)), C_CYAN, (x + 340, 226), "topright")
        self.draw_progress(pygame.Rect(x, 262, 340, 14), self.prog_t)
        draw_text(s, f.get(12, True), "DIFFICULTY", C_MUTED, (x + 4, 290))
        dcol = C_GREEN if self.difficulty == "EASY" else C_RED
        draw_text(s, f.get(15, True), self.difficulty, dcol, (x + 340, 287), "topright")
        draw_text(s, f.get(12, True), "WHY THIS QUESTION", C_MUTED, (x + 4, 316))
        draw_wrapped(s, f, self.ai_explain, C_TEXT, pygame.Rect(x + 4, 334, 332, 42), 15, min_size=11, bold=False)
        pygame.draw.line(s, (34, 60, 96), (x, 382), (x + 340, 382), 1)
        draw_text(s, f.get(12, True), "QUESTION HISTORY", C_MUTED, (x + 4, 390))
        recent = self.ai_history[-8:]
        if not recent:
            draw_text(s, f.get(14, False), "No questions yet.", C_MUTED, (x + 4, 414))
        base = len(self.ai_history) - len(recent)
        for k, (tag, ans) in enumerate(recent):
            y = 412 + k * 26
            text = "%d. %s" % (base + k + 1, QUESTION_SHORT.get(tag, tag))
            draw_wrapped(s, f, text, C_TEXT, pygame.Rect(x + 4, y, 252, 24), 14, valign="middle", min_size=10, bold=False)
            lab, col = ("YES", C_GREEN) if ans is True else ("NO", C_RED) if ans is False else ("NOT SURE", C_PURPLE)
            draw_text(s, f.get(13, True), lab, col, (x + 336, y + 12), "midright")
        self.undo_btn.draw(s, f)
        self.restart_btn.draw(s, f)

    def _draw_ai_strip(self):
        s, f = self.screen, self.fonts
        strip = pygame.Rect(24, 563, 848, 137)
        self.draw_panel(strip, radius=16)
        pulse = 0.5 + 0.5 * math.sin(self.time * 3)
        pygame.draw.circle(s, lerp_col((10, 70, 40), C_GREEN, pulse), (46, 583), 5)
        draw_text(s, f.get(13, True), "AI CORE ONLINE", C_MUTED, (60, 575))
        tiles = [("QUESTIONS ASKED", str(len(self.ai_history)), C_CYAN),
                 ("CANDIDATES", str(len(self.ai_candidates)), C_PURPLE),
                 ("MODE", self.difficulty, C_GREEN if self.difficulty == "EASY" else C_RED)]
        for k, (lab, val, col) in enumerate(tiles):
            r = pygame.Rect(40 + k * 278, 598, 270, 52)
            pygame.draw.rect(s, (8, 14, 32), r, border_radius=10)
            pygame.draw.rect(s, lerp_col(col, C_CARD, 0.5), r, 1, border_radius=10)
            draw_text(s, f.get(11, True), lab, C_MUTED, (r.x + 12, r.y + 6))
            draw_text(s, f.get(24, True), val, col, (r.x + 12, r.y + 20))
        if self.ai_notice:
            msg, mcol = self.ai_notice, C_AMBER
        elif self.ai_phase == "ask":
            msg, mcol = "Answer honestly. NOT SURE skips a question without eliminating anyone.", C_MUTED
        elif self.ai_phase == "guess":
            msg, mcol = "Tell me whether my guess is CORRECT or WRONG.", C_MUTED
        else:
            msg, mcol = "No candidate matches. Use UNDO to change an answer, or RESTART.", C_AMBER
        draw_wrapped(s, f, msg, mcol, pygame.Rect(40, 656, 816, 36), 15, valign="middle", min_size=11, bold=False)

    # -------------------------------------------------------------- USER MODE
    def draw_user_mode(self):
        s, f = self.screen, self.fonts
        draw_text(s, f.get(30, True), "YOU GUESS", C_PURPLE, (24, 20))
        left = MAX_QUESTIONS - self.u_used
        if self.final_mode:
            a = 0.5 + 0.5 * math.sin(self.time * 5)
            draw_text(s, f.get(16, True), "SELECT A PERSON CARD TO MAKE YOUR FINAL GUESS",
                      lerp_col(C_PURPLE, (255, 255, 255), a * 0.6), (24, 58))
        else:
            draw_text(s, f.get(15, False), "Find the secret person. Click cards to cross them out.", C_MUTED, (24, 58))
        self.user_menu_btn.draw(s, f)
        self.draw_gallery(self.final_mode)
        # Investigation log
        strip = pygame.Rect(24, 563, 848, 137)
        self.draw_panel(strip, radius=16)
        draw_text(s, f.get(13, True), "INVESTIGATION LOG", C_MUTED, (42, 573))
        if not self.u_order:
            draw_text(s, f.get(14, False), "Nothing asked yet. Pick a question on the right.", C_MUTED, (42, 602))
        for k, (tag, ans, hint) in enumerate(self.u_order[:12]):
            col_i, row_i = k // 4, k % 4
            x, y = 42 + col_i * 278, 598 + row_i * 24
            text = "%d. %s%s" % (k + 1, "HINT " if hint else "", QUESTION_SHORT[tag])
            draw_wrapped(s, f, text, C_TEXT, pygame.Rect(x, y, 200, 22), 14, valign="middle", min_size=10, bold=False)
            draw_text(s, f.get(13, True), "YES" if ans else "NO", C_GREEN if ans else C_RED, (x + 262, y + 11), "midright")
        # Right panel
        panel = self.PANEL
        self.draw_panel(panel, radius=20)
        x = 908
        draw_text(s, f.get(17, True), "ASK A QUESTION", C_CYAN, (x + 4, 32))
        draw_text(s, f.get(15, True), "%d LEFT" % left, C_AMBER if left <= 3 else C_TEXT, (x + 340, 33), "topright")
        for i in range(MAX_QUESTIONS):
            cx, cy = x + 17 + i * 34, 72
            if i < self.u_used:
                pygame.draw.circle(s, C_PURPLE, (cx, cy), 7)
            else:
                pygame.draw.circle(s, (8, 14, 32), (cx, cy), 7)
                pygame.draw.circle(s, C_CYAN, (cx, cy), 7, 2)
        # Scrollable question list
        view = self.q_view
        old = s.get_clip()
        s.set_clip(view.clip(old))
        for b in self.q_buttons:
            if b.rect.bottom > view.top - 6 and b.rect.top < view.bottom + 6:
                b.draw(s, f)
        s.set_clip(old)
        total = len(self.q_buttons) * 52 - 6
        if total > view.h:
            track = pygame.Rect(view.right - 5, view.y, 5, view.h)
            pygame.draw.rect(s, (10, 18, 38), track, border_radius=3)
            th = max(30, int(view.h * view.h / total))
            max_scroll = total - view.h
            ty = view.y + int((view.h - th) * (self.q_scroll / max_scroll if max_scroll else 0))
            pygame.draw.rect(s, C_CYAN, (track.x, ty, track.w, th), border_radius=3)
        # Message box
        box = pygame.Rect(x, 560, 340, 66)
        pygame.draw.rect(s, (8, 14, 32), box, border_radius=12)
        pygame.draw.rect(s, (44, 70, 110), box, 1, border_radius=12)
        draw_wrapped(s, f, self.u_message, C_TEXT, box.inflate(-20, -10), 15, valign="middle", min_size=10, bold=False)
        self.hint_btn.draw(s, f)
        self.final_btn.draw(s, f)
        if self.confirm_idx is not None:
            self._draw_confirm_dialog()

    def _draw_confirm_dialog(self):
        s, f = self.screen, self.fonts
        s.blit(dim_overlay(), (0, 0))
        dlg = pygame.Rect(390, 232, 500, 240)
        s.blit(glow_surface(dlg.w, dlg.h, C_CYAN, 20, 18, 3), (dlg.x - 18, dlg.y - 18))
        self.draw_panel(dlg, tint=(16, 26, 52), alpha=250, radius=20)
        person = PEOPLE[self.confirm_idx]
        draw_text(s, f.get(16, True), "CONFIRM FINAL GUESS", C_CYAN, (dlg.centerx, dlg.y + 28), "center")
        draw_wrapped(s, f, "Is it %s?" % person["name"], C_TEXT, pygame.Rect(dlg.x + 24, dlg.y + 52, dlg.w - 48, 50), 32,
                     align="center", valign="middle", min_size=16)
        draw_text(s, f.get(14, False), "This ends the round. You cannot undo it.", C_MUTED, (dlg.centerx, dlg.y + 120), "center")
        self.confirm_btn.draw(s, f)
        self.cancel_btn.draw(s, f)

    # ---------------------------------------------------------------- RESULT
    def draw_result(self):
        s, f = self.screen, self.fonts
        res = self.result or {"heading": "", "color": C_CYAN, "line": "", "person": 0, "label": "", "detail": ""}
        person = PEOPLE[clamp(res["person"], 0, len(PEOPLE) - 1)]
        self.glow_text(res["heading"], 84, res["color"], (WIDTH // 2, 92), 0.7 + 0.3 * math.sin(self.time * 2.5))
        draw_text(s, f.get(30, True), res["line"], C_TEXT, (WIDTH // 2, 168), "center")
        card = pygame.Rect(340, 204, 600, 388)
        self.draw_panel(card, radius=24, border=res["color"])
        color = name_color(person["name"])
        cx, cy = card.centerx, card.y + 82
        s.blit(glow_surface(100, 100, color, 50, 16, 3), (cx - 66, cy - 66))
        pygame.draw.circle(s, lerp_col(color, C_BG, 0.6), (cx, cy), 50)
        pygame.draw.circle(s, color, (cx, cy), 50, 4)
        draw_text(s, f.get(44, True), initials(person["name"]), (255, 255, 255), (cx, cy), "center")
        draw_text(s, f.get(14, True), res["label"], C_MUTED, (cx, card.y + 156), "center")
        draw_wrapped(s, f, person["name"], (255, 255, 255), pygame.Rect(card.x + 30, card.y + 172, card.w - 60, 56), 44,
                     align="center", valign="middle", min_size=20)
        draw_wrapped(s, f, person["description"], C_CYAN, pygame.Rect(card.x + 40, card.y + 236, card.w - 80, 64), 24,
                     align="center", valign="middle", min_size=13, bold=False)
        if res["detail"]:
            draw_wrapped(s, f, res["detail"], C_MUTED, pygame.Rect(card.x + 40, card.y + 312, card.w - 80, 40), 17,
                         align="center", valign="middle", min_size=11, bold=False)
        draw_text(s, f.get(13, True), "WINS %d   \u2022   LOSSES %d" % (self.wins, self.losses), C_MUTED,
                  (card.centerx, card.bottom - 20), "center")
        self.again_btn.draw(s, f)
        self.menu2_btn.draw(s, f)

    # ------------------------------------------------------------------ main loop
    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        sys.exit(0 if run_selftest() else 1)
    if pygame is None:
        print("Pygame is required. Install it with:  pip install pygame")
        sys.exit(1)
    Game().run()


if __name__ == "__main__":
    main()
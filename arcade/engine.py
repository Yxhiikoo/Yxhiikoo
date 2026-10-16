"""Arcade jouable depuis le profil GitHub.

Chaque ticket (issue) dont le titre commence par « arcade| » est un coup :
    arcade|slots|spin
    arcade|roulette|<rouge|noir|pair|impair|manque|passe|0|17>
    arcade|bj|<new|hit|stand>
Le workflow .github/workflows/arcade-play.yml appelle ce script, qui met à jour
arcade/state.json, régénère les SVG animés et la section ARCADE du README,
et écrit la réponse au joueur dans comment.md.

Usage : python arcade/engine.py "<titre>" <login>      (joue un coup)
        python arcade/engine.py --render                (régénère seulement)
"""
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
ARCADE = ROOT / "arcade"
STATE = ARCADE / "state.json"
README = ROOT / "README.md"
REPO = "Yxhiikoo/Yxhiikoo"
START_CHIPS = 1000
BET = {"slots": 50, "roulette": 100, "bj": 100}

# ---------------------------------------------------------------- état

def load():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"version": 0, "players": {}, "log": [],
            "slots": {"last": ["7️⃣", "7️⃣", "7️⃣"], "who": None, "text": "Tire le levier !", "win": False},
            "roulette": {"last": None, "who": None, "text": "Choisis ta mise !", "history": [], "win": False},
            "bj": {"active": False, "who": None, "player": [], "dealer": [], "deck": [], "text": "Lance une partie !", "started": 0, "win": None}}


def save(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def player(st, who):
    p = st["players"].setdefault(who, {"chips": START_CHIPS, "plays": 0, "wins": 0, "best": 0})
    return p


def charge(st, who, game):
    """Prend la mise. Recharge gratuitement un joueur à sec."""
    p = player(st, who)
    note = ""
    if p["chips"] < BET[game]:
        p["chips"] = START_CHIPS
        note = "\n\n> 🪙 Tu étais à sec : je t'ai rechargé **1 000 jetons** gratuits !"
    p["chips"] -= BET[game]
    p["plays"] += 1
    return note


def pay(st, who, amount):
    p = player(st, who)
    p["chips"] += amount
    if amount > 0:
        p["wins"] += 1
    p["best"] = max(p["best"], p["chips"])


def log(st, who, emoji, text):
    st["log"].insert(0, {"who": who, "e": emoji, "t": text, "at": int(time.time())})
    del st["log"][10:]

# ---------------------------------------------------------------- machine à sous

SYMS = ["7️⃣", "💎", "👾", "⭐", "🔔", "🍇", "🍋", "🍒"]
WEIGHTS = [1, 2, 3, 4, 5, 6, 7, 8]
PAY = {"7️⃣": 50, "💎": 25, "👾": 15, "⭐": 12, "🔔": 10, "🍇": 8, "🍋": 5, "🍒": 4}


def play_slots(st, who, move):
    note = charge(st, who, "slots")
    r = random.choices(SYMS, WEIGHTS, k=3)
    if r[0] == r[1] == r[2]:
        mult = PAY[r[0]]
    elif r.count("🍒") == 2:
        mult = 2
    elif r[0] == r[1] or r[1] == r[2] or r[0] == r[2]:
        mult = 1
    else:
        mult = 0
    gain = BET["slots"] * mult
    pay(st, who, gain)
    line = " ".join(r)
    if mult >= 25:
        text = f"JACKPOT ! +{gain}"
    elif mult > 1:
        text = f"GAGNÉ x{mult} · +{gain}"
    elif mult == 1:
        text = "Mise remboursée"
    else:
        text = "Perdu…"
    st["slots"] = {"last": r, "who": who, "text": text, "win": mult > 1}
    log(st, who, "🎰", f"{line} → {text}")
    return f"## 🎰 {line}\n\n**{text}** (mise : {BET['slots']} 🪙){note}"

# ---------------------------------------------------------------- roulette

ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
RBETS = {
    "rouge": ("🔴 Rouge", 2, lambda n: n in REDS),
    "noir": ("⚫ Noir", 2, lambda n: n != 0 and n not in REDS),
    "pair": ("Pair", 2, lambda n: n != 0 and n % 2 == 0),
    "impair": ("Impair", 2, lambda n: n % 2 == 1),
    "manque": ("1-18", 2, lambda n: 1 <= n <= 18),
    "passe": ("19-36", 2, lambda n: n >= 19),
    "0": ("Plein 0", 36, lambda n: n == 0),
    "17": ("Plein 17", 36, lambda n: n == 17),
}


def color(n):
    return "vert" if n == 0 else "rouge" if n in REDS else "noir"


def play_roulette(st, who, move):
    if move not in RBETS:
        return f"❓ Mise inconnue « {move} ». Choix possibles : {', '.join(RBETS)}."
    label, mult, ok = RBETS[move]
    note = charge(st, who, "roulette")
    n = random.choice(ORDER)
    win = ok(n)
    gain = BET["roulette"] * mult if win else 0
    pay(st, who, gain)
    text = f"+{gain - BET['roulette']}" if win else f"-{BET['roulette']}"
    hist = [n] + st["roulette"].get("history", [])
    st["roulette"] = {"last": n, "who": who, "bet": label, "text": text, "win": win, "history": hist[:10]}
    log(st, who, "🎡", f"{label} → {n} {color(n)} ({text})")
    verdict = f"**Gagné !** +{gain - BET['roulette']} 🪙" if win else f"Perdu… -{BET['roulette']} 🪙"
    return f"## 🎡 La bille tombe sur **{n} {color(n).upper()}**\n\nTa mise : {label} (x{mult}) → {verdict}{note}"

# ---------------------------------------------------------------- blackjack

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["♠", "♥", "♦", "♣"]


def total(hand):
    t = sum(1 if c[:-1] == "A" else 10 if c[:-1] in "JQK" or c[:-1] == "10" else int(c[:-1]) for c in hand)
    if any(c[:-1] == "A" for c in hand) and t + 10 <= 21:
        t += 10
    return t


def bj_finish(st, kind):
    g = st["bj"]
    who = g["who"]
    stake = BET["bj"]
    gain = {"bj": int(stake * 2.5), "win": stake * 2, "dbust": stake * 2, "push": stake}.get(kind, 0)
    pay(st, who, gain)
    net = gain - stake
    text = {"bj": f"BLACKJACK ! +{net}", "win": f"GAGNÉ ! +{net}", "dbust": f"Le croupier saute ! +{net}",
            "push": "Égalité", "lose": f"Le croupier gagne -{stake}", "bust": f"Tu sautes ! -{stake}"}[kind]
    g.update(active=False, text=text, win=net > 0 if net else None)
    log(st, who, "🃏", f"{total(g['player'])} contre {total(g['dealer'])} → {text}")
    return text


def play_bj(st, who, move):
    g = st["bj"]
    now = int(time.time())
    if move == "new":
        if g["active"] and g["who"] != who and now - g["started"] < 1800:
            return f"⏳ Une main est en cours pour @{g['who']}. Réessaie dans quelques minutes (elle expire au bout de 30 min)."
        if g["active"] and g["who"] == who:
            return "🃏 Tu as déjà une main en cours ! Choisis **Tirer** ou **Rester** sur le profil."
        note = charge(st, who, "bj")
        deck = [r + s for r in RANKS for s in SUITS] * 2
        random.shuffle(deck)
        g.update(active=True, who=who, started=now, deck=deck, player=[], dealer=[], win=None)
        for _ in range(2):
            g["player"].append(g["deck"].pop())
            g["dealer"].append(g["deck"].pop())
        p, d = total(g["player"]), total(g["dealer"])
        if p == 21 or d == 21:
            text = bj_finish(st, "push" if p == d else "bj" if p == 21 else "lose")
            return f"## 🃏 {' '.join(g['player'])} contre {' '.join(g['dealer'])}\n\n**{text}**{note}"
        g["text"] = "Tirer ou rester ?"
        return (f"## 🃏 Ta main : {' '.join(g['player'])} (**{p}**)\n\nLe croupier montre **{g['dealer'][0]}**.\n\n"
                f"Retourne sur [mon profil](https://github.com/Yxhiikoo) et clique **Tirer** ou **Rester** !{note}")

    if not g["active"]:
        return "🃏 Aucune main en cours. Clique **Nouvelle main** sur le profil !"
    if g["who"] != who:
        return f"✋ Cette main appartient à @{g['who']}. Lance la tienne quand elle sera finie !"

    if move == "hit":
        g["player"].append(g["deck"].pop())
        p = total(g["player"])
        if p > 21:
            text = bj_finish(st, "bust")
            return f"## 🃏 {' '.join(g['player'])} = **{p}**\n\n**{text}**"
        if p < 21:
            g["text"] = f"{p} · Tirer ou rester ?"
            return f"## 🃏 {' '.join(g['player'])} = **{p}**\n\nTirer encore ou rester ? Retourne sur [le profil](https://github.com/Yxhiikoo) !"
        move = "stand"

    if move == "stand":
        while total(g["dealer"]) < 17:
            g["dealer"].append(g["deck"].pop())
        p, d = total(g["player"]), total(g["dealer"])
        kind = "dbust" if d > 21 else "win" if p > d else "lose" if p < d else "push"
        text = bj_finish(st, kind)
        return f"## 🃏 Toi : {' '.join(g['player'])} (**{p}**) · Croupier : {' '.join(g['dealer'])} (**{d}**)\n\n**{text}**"

    return f"❓ Coup inconnu « {move} »."

# ---------------------------------------------------------------- SVG

FONT = "'Press Start 2P','Courier New',monospace"
EMOJI = "'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def frame(w, h, title, color, body, style=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs>
 <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d0640"/><stop offset="1" stop-color="#07010f"/></linearGradient>
 <filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
 <style>
  .t{{font-family:{FONT};font-weight:900}} .e{{font-family:{EMOJI}}}
  .blink{{animation:blink 1s steps(2) infinite}} @keyframes blink{{50%{{opacity:.25}}}}
  .pop{{animation:pop .5s ease-out both;transform-box:fill-box;transform-origin:center}} @keyframes pop{{from{{opacity:0;transform:scale(.6)}}}}
  {style}
 </style>
</defs>
<rect width="{w}" height="{h}" rx="18" fill="url(#bg)"/>
<rect x="1.5" y="1.5" width="{w-3}" height="{h-3}" rx="17" fill="none" stroke="{color}" stroke-width="3" filter="url(#glow)"/>
<text x="{w/2}" y="40" text-anchor="middle" class="t" font-size="20" fill="{color}" filter="url(#glow)">{esc(title)}</text>
{body}
</svg>'''


def svg_slots(s):
    reels, css = [], []
    for i, sym in enumerate(s["last"]):
        strip = [random.choice(SYMS) for _ in range(14)] + [sym]
        x = 160 + i * 190
        items = "".join(f'<text x="{x + 75}" y="{150 + k * 100}" text-anchor="middle" class="e" font-size="64">{esc(c)}</text>' for k, c in enumerate(strip))
        dist = (len(strip) - 1) * 100
        dur = 1.6 + i * 0.6
        css.append(f".r{i}{{animation:r{i} {dur}s cubic-bezier(.15,.85,.3,1.02) both}} @keyframes r{i}{{from{{transform:translateY(0)}}to{{transform:translateY(-{dist}px)}}}}")
        reels.append(f'''<g><rect x="{x}" y="72" width="150" height="120" rx="12" fill="#05010d" stroke="{'#39FF14' if s['win'] else '#E100FF'}" stroke-width="3"/>
<clipPath id="c{i}"><rect x="{x}" y="72" width="150" height="120" rx="12"/></clipPath>
<g clip-path="url(#c{i})"><g class="r{i}">{items}</g></g></g>''')
    who = f"@{s['who']}" if s["who"] else "Personne n'a encore joué"
    color = "#39FF14" if s["win"] else "#FFD23F"
    body = "".join(reels) + f'''
<line x1="150" y1="132" x2="710" y2="132" stroke="#FF2E63" stroke-width="2" opacity=".5"/>
<g class="pop" style="animation-delay:2.9s"><text x="430" y="232" text-anchor="middle" class="t" font-size="18" fill="{color}" filter="url(#glow)">{esc(s['text'])}</text></g>
<text x="430" y="262" text-anchor="middle" class="t" font-size="10" fill="#A88BD6">DERNIER TIRAGE : {esc(who)}</text>'''
    lights = "".join(f'<circle cx="{30 + k * 40}" cy="285" r="4" fill="#FFD23F" class="blink" style="animation-delay:{(k % 2) * .5}s"/>' for k in range(21))
    return frame(860, 300, "🎰 MACHINE À SOUS", "#FFD23F", body + lights, "".join(css))


def svg_roulette(r):
    import math
    cx, cy, ro, ri, rt = 220, 175, 125, 85, 106
    seg = 360 / 37
    def p(rad, a):
        a = math.radians(a)
        return f"{cx + rad * math.sin(a):.1f},{cy - rad * math.cos(a):.1f}"
    parts = []
    for i, n in enumerate(ORDER):
        a0, a1 = (i - .5) * seg, (i + .5) * seg
        fill = "#0fa024" if n == 0 else "#d0103a" if n in REDS else "#1a0833"
        parts.append(f'<path d="M{p(ri, a0)} L{p(ro, a0)} A{ro},{ro} 0 0 1 {p(ro, a1)} L{p(ri, a1)} A{ri},{ri} 0 0 0 {p(ri, a0)}Z" fill="{fill}" stroke="#FFD23F" stroke-width="1"/>')
        tx, ty = p(rt, i * seg).split(",")
        parts.append(f'<text x="{tx}" y="{ty}" transform="rotate({i * seg:.1f} {tx} {ty})" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-weight="bold" font-size="11" fill="#fff">{n}</text>')
    last = r["last"]
    idx = ORDER.index(last) if last is not None else 0
    final = -(idx * seg) - 1440
    css = (f".wheel{{transform-origin:{cx}px {cy}px;animation:spin 5s cubic-bezier(.1,.7,.2,1) both}} @keyframes spin{{to{{transform:rotate({final:.2f}deg)}}}}"
           f".ball{{transform-origin:{cx}px {cy}px;animation:ball 5s cubic-bezier(.1,.7,.2,1) both}} @keyframes ball{{from{{transform:rotate(1800deg)}}to{{transform:rotate(0)}}}}")
    wheel = f'''<circle cx="{cx}" cy="{cy}" r="{ro + 14}" fill="#12052a" stroke="#E100FF" stroke-width="4" filter="url(#glow)"/>
<g class="wheel">{''.join(parts)}<circle cx="{cx}" cy="{cy}" r="{ri}" fill="#2a0b55" stroke="#00D4FF" stroke-width="3"/>
<circle cx="{cx}" cy="{cy}" r="22" fill="#FFD23F"/><path d="M{cx - 50},{cy} H{cx + 50} M{cx},{cy - 50} V{cy + 50}" stroke="#FFD23F" stroke-width="5" stroke-linecap="round"/></g>
<g class="ball"><circle cx="{cx}" cy="{cy - ro + 30}" r="8" fill="#fff" filter="url(#glow)"/></g>
<path d="M{cx - 10},{cy - ro - 22} L{cx + 10},{cy - ro - 22} L{cx},{cy - ro - 6}Z" fill="#00D4FF" filter="url(#glow)"/>'''
    if last is None:
        info = '<text x="610" y="170" text-anchor="middle" class="t" font-size="14" fill="#fff">À TOI DE JOUER !</text>'
    else:
        col = {"vert": "#39FF14", "rouge": "#FF2E63", "noir": "#c9b6ff"}[color(last)]
        res = "#39FF14" if r["win"] else "#FF2E63"
        pills = "".join(
            f'<circle cx="{470 + k * 30}" cy="296" r="12" fill="{"#0fa024" if h == 0 else "#d0103a" if h in REDS else "#1a0833"}" stroke="#fff6"/>'
            f'<text x="{470 + k * 30}" y="300" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="10" fill="#fff">{h}</text>'
            for k, h in enumerate(r["history"][:10]))
        info = f'''<g class="pop" style="animation-delay:5s">
<text x="610" y="140" text-anchor="middle" class="t" font-size="56" fill="{col}" filter="url(#glow)">{last}</text>
<text x="610" y="175" text-anchor="middle" class="t" font-size="14" fill="{col}">{color(last).upper()}</text>
<text x="610" y="212" text-anchor="middle" class="t" font-size="11" fill="#A88BD6">@{esc(r['who'])} · {esc(r['bet'])}</text>
<text x="610" y="245" text-anchor="middle" class="t" font-size="16" fill="{res}" filter="url(#glow)">{esc(r['text'])} 🪙</text></g>
<text x="610" y="275" text-anchor="middle" class="t" font-size="8" fill="#A88BD6">DERNIERS NUMÉROS</text>{pills}'''
    return frame(780, 330, "🎡 ROULETTE", "#E100FF", wheel + info, css)


def svg_card(x, y, card, delay, hidden=False):
    if hidden:
        return (f'<g class="pop" style="animation-delay:{delay}s"><rect x="{x}" y="{y}" width="70" height="98" rx="8" fill="#3a0a6e" stroke="#E100FF" stroke-width="2.5" filter="url(#glow)"/>'
                f'<text x="{x + 35}" y="{y + 60}" text-anchor="middle" class="t" font-size="22" fill="#fff">G</text></g>')
    rank, suit = card[:-1], card[-1]
    col = "#FF2E63" if suit in "♥♦" else "#EDE6FF"
    return (f'<g class="pop" style="animation-delay:{delay}s"><rect x="{x}" y="{y}" width="70" height="98" rx="8" fill="#140828" stroke="{col}" stroke-width="2.5" filter="url(#glow)"/>'
            f'<text x="{x + 8}" y="{y + 22}" font-family="Arial" font-weight="bold" font-size="16" fill="{col}">{rank}</text>'
            f'<text x="{x + 35}" y="{y + 66}" text-anchor="middle" font-family="Arial" font-size="34" fill="{col}">{suit}</text></g>')


def svg_bj(g):
    body = []
    dealer, playr = g["dealer"], g["player"]
    hide = g["active"]
    for k, c in enumerate(dealer):
        body.append(svg_card(250 + k * 80, 80, c, 0.2 + k * 0.4, hidden=hide and k == 1))
    for k, c in enumerate(playr):
        body.append(svg_card(250 + k * 80, 205, c, 0.4 + k * 0.4))
    dtot = total(dealer[:1]) if hide else total(dealer) if dealer else ""
    ptot = total(playr) if playr else ""
    status = "#39FF14" if g.get("win") else "#FF2E63" if g.get("win") is False else "#FFD23F"
    who = f"@{g['who']}" if g["who"] else "—"
    body.append(f'''<text x="60" y="135" class="t" font-size="11" fill="#00D4FF">CROUPIER</text><text x="60" y="160" class="t" font-size="18" fill="#fff">{dtot}{" + ?" if hide else ""}</text>
<text x="60" y="260" class="t" font-size="11" fill="#00D4FF">{esc(who)}</text><text x="60" y="285" class="t" font-size="18" fill="#fff">{ptot}</text>
<g class="pop" style="animation-delay:1.6s"><text x="430" y="335" text-anchor="middle" class="t" font-size="16" fill="{status}" filter="url(#glow)">{esc(g['text'])}</text></g>''')
    return frame(860, 360, "🃏 BLACKJACK", "#39FF14", "".join(body))

# ---------------------------------------------------------------- README

def link(title, label, color):
    body = quote("👉 Clique simplement sur **Submit new issue** (« Soumettre ») sans rien changer.\n\n"
                 "🤖 Le robot joue ton coup en ~30 secondes, te répond ici et met à jour le profil de @Yxhiikoo !")
    url = f"https://github.com/{REPO}/issues/new?title={quote(title)}&body={body}"
    badge = f"https://img.shields.io/badge/{quote(label.replace('-', '--').replace('_', '__').replace(' ', '_'))}-{color}?style=for-the-badge"
    return f'<a href="{url}"><img src="{badge}" alt="{esc(label)}" /></a>'


def section(st):
    v = st["version"]
    g = st["bj"]
    if g["active"]:
        bj_links = f'''{link("arcade|bj|hit", "➕ Tirer", "39FF14")}
  {link("arcade|bj|stand", "✋ Rester", "E100FF")}'''
        bj_note = f"Main en cours pour **@{g['who']}** — seul ce joueur peut tirer ou rester (elle expire au bout de 30 min)."
    else:
        bj_links = link("arcade|bj|new", "🃏 Nouvelle main (100 🪙)", "39FF14")
        bj_note = "Lance une main, puis reviens ici pour tirer ou rester."
    roul = "\n  ".join(link(f"arcade|roulette|{k}", f"{lab} x{m}", c) for (k, (lab, m, _)), c in
                       zip(RBETS.items(), ["FF2E63", "1a0833", "7F00FF", "7F00FF", "00D4FF", "00D4FF", "0fa024", "E100FF"]))
    top = sorted(st["players"].items(), key=lambda kv: -kv[1]["chips"])[:8]
    medals = ["🥇", "🥈", "🥉"] + ["🎖️"] * 10
    board = "\n".join(f"| {medals[i]} | [@{esc(w)}](https://github.com/{w}) | {p['chips']:,} 🪙 | {p['plays']} | {p['wins']} |".replace(",", " ")
                      for i, (w, p) in enumerate(top)) or "| — | Personne pour l'instant… sois le premier ! | | | |"
    recent = "\n".join(f"- {e['e']} **@{esc(e['who'])}** : {esc(e['t'])}" for e in st["log"][:6]) or "- Aucun coup joué pour l'instant."
    return f'''<!-- ARCADE:START -->
<p align="center"><b>Clique sur un bouton → valide le ticket → mon robot joue ton coup et met à jour ce profil en ~30 s.</b><br /><sub>Tu commences avec 1 000 🪙 fictifs. Aucun argent réel.</sub></p>

<p align="center"><img src="arcade/slots.svg?v={v}" width="100%" alt="Machine à sous" /></p>
<p align="center">
  {link("arcade|slots|spin", "🎰 Tirer le levier (50 🪙)", "FFD23F")}
</p>

<p align="center"><img src="arcade/roulette.svg?v={v}" width="100%" alt="Roulette" /></p>
<p align="center">
  {roul}
</p>

<p align="center"><img src="arcade/blackjack.svg?v={v}" width="100%" alt="Blackjack" /></p>
<p align="center">
  {bj_links}
</p>
<p align="center"><sub>{bj_note}</sub></p>

<details>
<summary><b>🏆 Classement des joueurs & derniers coups</b></summary>

| | Joueur | Jetons | Parties | Victoires |
|:-:|:--|--:|--:|--:|
{board}

**Derniers coups :**
{recent}
</details>
<!-- ARCADE:END -->'''


def render(st):
    (ARCADE / "slots.svg").write_text(svg_slots(st["slots"]), encoding="utf-8")
    (ARCADE / "roulette.svg").write_text(svg_roulette(st["roulette"]), encoding="utf-8")
    (ARCADE / "blackjack.svg").write_text(svg_bj(st["bj"]), encoding="utf-8")
    text = README.read_text(encoding="utf-8")
    new = re.sub(r"<!-- ARCADE:START -->.*?<!-- ARCADE:END -->", lambda m: section(st), text, flags=re.S)
    README.write_text(new, encoding="utf-8", newline="\n")


def main():
    st = load()
    if sys.argv[1:] == ["--render"]:
        render(st)
        save(st)
        return
    title, who = sys.argv[1], sys.argv[2]
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", who):
        raise SystemExit("login invalide")
    parts = [x.strip().lower() for x in title.split("|")]
    game, move = (parts + ["", "", ""])[1:3]
    games = {"slots": play_slots, "roulette": play_roulette, "bj": play_bj}
    if game in games:
        reply = games[game](st, who, move)
    else:
        reply = f"❓ Jeu inconnu « {game} »."
    st["version"] += 1
    render(st)
    save(st)
    chips = player(st, who)["chips"] if who in st["players"] else START_CHIPS
    (ROOT / "comment.md").write_text(
        f"{reply}\n\n---\n💰 Ton solde : **{chips:,} 🪙**".replace(",", " ")
        + f"\n\n👉 [Retour sur le profil pour rejouer](https://github.com/Yxhiikoo#-arcade-jouable-ici-même)\n\n<sub>🤖 Coup joué automatiquement. Jetons fictifs, aucun argent réel.</sub>",
        encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
roBa.keymap から、キーマップの図（keymap-drawer/roBa.png）を自動で作る。
GitHub Actions（.github/workflows/draw.yml）から、キーマップを保存するたびに呼ばれる。

ポイント
  ・自作のタップダンス／マクロ／長押しキーの名前は、キーマップの中身から自動で読み取って日本語ラベルにする
  ・同時押し（コンボ）とエンコーダーの一覧も、キーマップから自動で下に書く
  ・図に出すレイヤーは SHOW_LAYERS で選ぶ
"""
import os
import re
import subprocess
import sys
import tempfile

import yaml
from PIL import Image, ImageDraw, ImageFont

KEYMAP = "config/roBa.keymap"
LAYOUT = "config/roBa.json"
OUT = "keymap-drawer/roBa.png"

# 図に出すレイヤー（名前で指定。無い名前は飛ばす）
SHOW_LAYERS = ["default", "NUM_and_ARROW", "SYMBOL", "LEFT_HAND"]
COLUMNS = 2
BG = "#0d1117"
FG = "#c9d1d9"

# 自動で付く名前が気に入らない独自キーだけ、ここで上書きできる
LABEL_OVERRIDES = {
    "&kinkyu_taihi": "緊急退避",
    "&nami_kakko": "{ }",
    "&kakko": "( )",
    "&sh_gobaku_taisaku": "sh",
    "&night_modo": "夜間",
    "&sleep": "スリープ",
    "&henkan_Secret": "こまんど",
}
# キーそのものの名前の上書き（バインディング全体で一致したら使う）
KEY_OVERRIDES = {
    "&kp LC(LA(LG(K)))": {"t": "この図", "h": "押す間"},
}

# ---------------------------------------------------------------- 名前の辞書
MODS = {
    "LCTRL": "Ctrl", "LCTL": "Ctrl", "RCTRL": "Ctrl", "RCTL": "Ctrl", "LEFT_CONTROL": "Ctrl", "RIGHT_CONTROL": "Ctrl",
    "LSHIFT": "Shift", "LSHFT": "Shift", "RSHIFT": "Shift", "RSHFT": "Shift", "LEFT_SHIFT": "Shift", "RIGHT_SHIFT": "Shift",
    "LALT": "Alt", "RALT": "Alt", "LEFT_ALT": "Alt", "RIGHT_ALT": "Alt",
    "LGUI": "Win", "RGUI": "Win", "LWIN": "Win", "RWIN": "Win", "LEFT_WIN": "Win", "RIGHT_WIN": "Win",
    "LEFT_GUI": "Win", "RIGHT_GUI": "Win",
}
WRAP = {"LC": "Ctrl", "LS": "Shift", "LA": "Alt", "LG": "Win", "RC": "Ctrl", "RS": "Shift", "RA": "Alt", "RG": "Win"}
KEYS = {
    "COMMA": ",", "DOT": ".", "PERIOD": ".", "SEMICOLON": ";", "SEMI": ";", "COLON": ":", "SINGLE_QUOTE": "'", "SQT": "'",
    "APOS": "'", "DOUBLE_QUOTES": '"', "DQT": '"', "SLASH": "/", "FSLH": "/", "BACKSLASH": "\\", "BSLH": "\\",
    "MINUS": "-", "EQUAL": "=", "PLUS": "+", "UNDER": "_", "UNDERSCORE": "_", "QUESTION": "?", "EXCLAMATION": "!",
    "TILDE": "~", "GRAVE": "`", "LEFT_BRACE": "{", "RIGHT_BRACE": "}", "LBRC": "{", "RBRC": "}",
    "LEFT_BRACKET": "[", "RIGHT_BRACKET": "]", "LBKT": "[", "RBKT": "]",
    "LEFT_PARENTHESIS": "(", "RIGHT_PARENTHESIS": ")", "LPAR": "(", "RPAR": ")",
    "LESS_THAN": "<", "GREATER_THAN": ">", "LT": "<", "GT": ">", "PIPE": "|", "AT": "@", "AT_SIGN": "@",
    "HASH": "#", "POUND": "#", "DOLLAR": "$", "PERCENT": "%", "CARET": "^", "AMPERSAND": "&", "ASTERISK": "*", "ASTRK": "*",
    "SPACE": "Space", "ENTER": "Enter", "RETURN": "Enter", "ESCAPE": "Esc", "ESC": "Esc", "TAB": "Tab",
    "BACKSPACE": "BS", "BSPC": "BS", "DELETE": "Del", "DEL": "Del", "HOME": "Home", "END": "End",
    "PAGE_UP": "PgUp", "PAGE_DOWN": "PgDn", "PG_UP": "PgUp", "PG_DN": "PgDn",
    "LEFT_ARROW": "←", "RIGHT_ARROW": "→", "UP_ARROW": "↑", "DOWN_ARROW": "↓", "LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓",
    "C_MUTE": "ミュート", "C_VOL_UP": "音量+", "C_VOL_DN": "音量-", "C_VOLUME_UP": "音量+", "C_VOLUME_DOWN": "音量-",
    "C_BRI_UP": "明るく", "C_BRI_DN": "暗く", "C_PP": "再生/停止", "C_PLAY_PAUSE": "再生/停止",
    "C_NEXT": "次の曲", "C_PREV": "前の曲", "PRINTSCREEN": "PrtSc", "PSCRN": "PrtSc",
    "LANG1": "かな", "LANG2": "英数", "KP_SLASH": "/", "KP_DIVIDE": "/", "KP_DOT": ".", "KP_MINUS": "-",
    "KP_PLUS": "+", "KP_ASTERISK": "*", "KP_MULTIPLY": "*", "KP_COMMA": ",", "KP_EQUAL": "=", "KP_NUMLOCK": "NumLock",
    "F": "F",
}
MOUSE = {"LCLK": "左クリ", "RCLK": "右クリ", "MCLK": "中クリ", "MB1": "左クリ", "MB2": "右クリ", "MB3": "中クリ",
         "MB4": "戻る", "MB5": "進む"}
ENCODERS = {
    "&encoder_msc_down_up": "スクロール",
    "&encoder_mmv_left_right": "カーソル左右",
    "&encoder_mmv_left_right_x2": "カーソル左右×2",
}


def keyname(code):
    """キーコード（LC(Z) など）を人が読める形に。"""
    code = code.strip()
    mods = []
    while True:
        m = re.match(r"^(L[CSAG]|R[CSAG])\((.*)\)$", code)
        if not m:
            break
        mods.append(WRAP[m.group(1)])
        code = m.group(2)
    base = KEYS.get(code)
    if base is None:
        d = re.match(r"^(?:KP_)?(?:N|NUMBER_|NUM_)(\d)$", code)
        base = d.group(1) if d else code
    if len(base) > 1 and base.isupper() and "_" in base:
        base = base.replace("_", " ").title() if base not in KEYS.values() else base
    return "+".join(mods + [base])


# ---------------------------------------------------------------- キーマップの読み取り
def strip_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"//[^\n]*", "", s)


def block_end(s, open_idx):
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("括弧が閉じていません")


HEAD = re.compile(r"(?<![\w-])(?:([A-Za-z_][\w-]*)\s*:\s*)?([A-Za-z_][\w-]*)\s*\{")


def children(body):
    """body の直下にあるノードを (ラベル, 中身) で返す。"""
    out, i = [], 0
    while True:
        m = HEAD.search(body, i)
        if not m:
            break
        end = block_end(body, m.end() - 1)
        out.append((m.group(1) or m.group(2), body[m.end():end]))
        i = end + 1
    return out


def groups(s):
    """bindings = <...>, <...>; の <> の中身を順に返す。"""
    m = re.search(r"(?<![\w-])bindings\s*=\s*((?:<[^>]*>\s*,?\s*)+);", s)
    return re.findall(r"<([^>]*)>", m.group(1)) if m else []


def tokens(s):
    return [" ".join(t.split()) for t in re.findall(r"&[\w]+(?:\s+(?!&)[^\s&]+)*", s)]


class Km:
    def __init__(self, text):
        src = strip_comments(text)
        k = re.search(r"(?<![\w-])keymap\s*\{", src)
        self.layers = children(src[k.end():block_end(src, k.end() - 1)])
        self.layer_names = [n for n, _ in self.layers]
        self.defs = {}
        for kind in ("behaviors", "macros"):
            for m in re.finditer(r"(?<![\w-])" + kind + r"\s*\{", src):
                for name, body in children(src[m.end():block_end(src, m.end() - 1)]):
                    comp = re.search(r'compatible\s*=\s*"([^"]+)"', body)
                    cells = re.search(r"#binding-cells\s*=\s*<(\d+)>", body)
                    self.defs[name] = {
                        "compat": comp.group(1) if comp else "",
                        "cells": int(cells.group(1)) if cells else -1,
                        "groups": groups(body),
                    }

    # ---- 1つのバインディング → (タップ, 長押し)
    def short(self, b, depth=0):
        t = b.split()
        if not t or depth > 4:
            return (b, None)
        name = t[0][1:]
        if name == "kp" and len(t) > 1:
            return (keyname(t[1]), None)
        if name == "mkp" and len(t) > 1:
            return (MOUSE.get(t[1], t[1]), None)
        if name in ("to", "mo", "tog", "sl") and len(t) > 1:
            return (self.layer_label(t[1]), None)
        hold_tap = name in ("mt", "lt") or self.defs.get(name, {}).get("compat") == "zmk,behavior-hold-tap"
        if hold_tap and len(t) >= 3:
            d = self.defs.get(name)
            hold_beh = "&mo" if name == "lt" else "&kp"
            if d and d["groups"]:
                hold_beh = d["groups"][0].split()[0] if d["groups"][0].split() else hold_beh
            hold = self.layer_label(t[1]) if hold_beh == "&mo" else MODS.get(t[1], keyname(t[1]))
            return (keyname(t[2]), hold)
        d = self.defs.get(name)
        if d and d["cells"] == 0:
            return self.custom(name, depth + 1)
        return (b, None)

    def layer_label(self, idx):
        try:
            return self.layer_names[int(idx)]
        except (ValueError, IndexError):
            return str(idx)

    # ---- 引数なしの自作キー（タップダンス・マクロ）→ キーの見た目
    def custom(self, name, depth=0):
        if "&" + name in LABEL_OVERRIDES:
            return (LABEL_OVERRIDES["&" + name], None)
        d = self.defs[name]
        if d["compat"] == "zmk,behavior-tap-dance":
            parts = [self.short(g.strip(), depth) for g in d["groups"]]
            return (parts[0][0], parts[0][1]) if parts else (name, None)
        if d["compat"] == "zmk,behavior-macro":
            toks = [x for g in d["groups"] for x in tokens(g) if not x.startswith("&macro_")]
            if 0 < len(toks) <= 3:
                return ("".join(self.short(x, depth)[0] for x in toks), None)
            return (name, None)
        return (name, None)

    def raw_binding_map(self):
        out = dict(KEY_OVERRIDES)
        for name, d in self.defs.items():
            if d["cells"] != 0:
                continue
            key = "&" + name
            if key in LABEL_OVERRIDES:
                out[key] = LABEL_OVERRIDES[key]
                continue
            if d["compat"] == "zmk,behavior-tap-dance":
                parts = [self.short(g.strip()) for g in d["groups"]]
                if not parts:
                    continue
                spec = {"t": parts[0][0]}
                if parts[0][1]:
                    spec["h"] = parts[0][1]
                if len(parts) > 1:
                    spec["s"] = " ".join(f"{i + 2}回:{p[0]}" for i, p in enumerate(parts[1:]))
                out[key] = spec
            elif d["compat"] == "zmk,behavior-macro":
                out[key] = self.custom(name)[0]
        return out

    # ---- エンコーダー一覧
    def encoder_legend(self):
        items = []
        for lname, body in self.layers:
            m = re.search(r"sensor-bindings\s*=\s*<([^>]*)>", body)
            if not m:
                continue
            tk = tokens(m.group(1))
            if not tk or tk[0] == "&trans":
                continue
            b = tk[0]
            nm = b.split()[0]
            if nm == "&inc_dec_kp" and len(b.split()) >= 3:
                a, c = b.split()[1], b.split()[2]
                pair = {a, c}
                if any("VOL" in x for x in pair):
                    lab = "音量"
                elif {a, c} <= {"LC(MINUS)", "LC(EQUAL)", "LC(PLUS)"}:
                    lab = "拡大縮小"
                elif {a, c} <= {"LG(MINUS)", "LG(EQUAL)", "LG(PLUS)"}:
                    lab = "拡大鏡"
                elif {a, c} == {"LC(PAGE_UP)", "LC(PAGE_DOWN)"}:
                    lab = "タブ移動"
                else:
                    lab = f"{keyname(a)}/{keyname(c)}"
            else:
                lab = ENCODERS.get(nm, nm)
            items.append(f"{'default' if lname == self.layer_names[0] else lname}:{lab}")
        return items


# ---------------------------------------------------------------- 描画
def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stderr or r.stdout)
        raise SystemExit(f"失敗: {' '.join(cmd)}")
    return r


def find_font(size):
    for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        p = run(["fc-match", "-f", "%{file}", "Noto Sans CJK JP"]).stdout.strip()
        return ImageFont.truetype(p, size)
    except Exception:
        return ImageFont.load_default()


def wrap_text(draw, text, font, width):
    lines, cur = [], ""
    for chunk in text.split("　"):
        trial = (cur + "　" + chunk) if cur else chunk
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = chunk
    if cur:
        lines.append(cur)
    return lines


def main():
    text = open(KEYMAP, encoding="utf-8").read()
    km = Km(text)
    tmp = tempfile.mkdtemp()
    cfg = {
        "parse_config": {"raw_binding_map": km.raw_binding_map()},
        "draw_config": {
            "dark_mode": True, "key_w": 62, "key_h": 58,
            "svg_extra_style": 'svg.keymap { font-family: "Noto Sans CJK JP", sans-serif; font-size: 13px; }\n'
                               "text.hold { font-size: 10px; }\ntext.shifted { font-size: 10px; }\n",
        },
    }
    cfg_path = os.path.join(tmp, "cfg.yaml")
    yaml.safe_dump(cfg, open(cfg_path, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)

    ymp = os.path.join(tmp, "km.yaml")
    run(["keymap", "-c", cfg_path, "parse", "-z", KEYMAP, "-o", ymp])
    data = yaml.safe_load(open(ymp, encoding="utf-8"))
    combos = data.pop("combos", [])           # 図の中には描かず、下に一覧で書く

    def humanize(k):
        """'&...' のまま残った名前を読める形にする（変えられなければそのまま）。"""
        if isinstance(k, str) and k.startswith("&"):
            tap, hold = km.short(k)
            if tap != k:
                return {"t": tap, "h": hold} if hold else tap
        elif isinstance(k, dict) and str(k.get("t", "")).startswith("&"):
            tap, hold = km.short(k["t"])
            if tap != k["t"]:
                k = dict(k, t=tap)
                if hold and not k.get("h"):
                    k["h"] = hold
        return k

    for lname in data["layers"]:
        data["layers"][lname] = [humanize(k) for k in data["layers"][lname]]
    default = data["layers"].get("default", [])

    def keytext(k):
        if isinstance(k, dict):
            return str(k.get("t", ""))
        return str(k)

    ym2 = os.path.join(tmp, "km_nocombo.yaml")
    yaml.safe_dump(data, open(ym2, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)

    shown = [n for n in SHOW_LAYERS if n in data["layers"]]
    if not shown:
        raise SystemExit("SHOW_LAYERS に合うレイヤーがありません")
    pngs = []
    for n in shown:
        svg = os.path.join(tmp, f"{n}.svg")
        png = os.path.join(tmp, f"{n}.png")
        r = run(["keymap", "-c", cfg_path, "draw", "-j", LAYOUT, ym2, "-s", n])
        open(svg, "w", encoding="utf-8").write(r.stdout)
        run(["rsvg-convert", "-z", "1.0", "-b", BG, svg, "-o", png])
        pngs.append(Image.open(png).convert("RGB"))

    cw, ch = max(i.width for i in pngs), max(i.height for i in pngs)
    rows = (len(pngs) + COLUMNS - 1) // COLUMNS
    grid = Image.new("RGB", (cw * COLUMNS, ch * rows), BG)
    for i, im in enumerate(pngs):
        grid.paste(im, ((i % COLUMNS) * cw, (i // COLUMNS) * ch))

    # 下の一覧（同時押し・エンコーダー）
    def spec_text(k):
        k = humanize(k)
        if isinstance(k, dict):
            t = str(k.get("t", ""))
            if k.get("h") in ("toggle", "to", "tog"):
                return f"→{t}"
            return f"{t}({k['h']})" if k.get("h") else t
        return KEYS.get(str(k), str(k))

    combo_items = []
    for c in combos:
        names = "+".join(keytext(default[p]) if p < len(default) else str(p) for p in c.get("p", []))
        combo_items.append(f"{names}:{spec_text(c.get('k', ''))}")
    legend = []
    if combo_items:
        legend.append("同時押し　" + "　".join(combo_items))
    enc = km.encoder_legend()
    if enc:
        legend.append("エンコーダー　" + "　".join(enc))

    font = find_font(17)
    probe = ImageDraw.Draw(grid)
    lines = []
    for t in legend:
        lines += wrap_text(probe, t, font, grid.width - 56)
    lh = 26
    full = Image.new("RGB", (grid.width, grid.height + lh * len(lines) + 24), BG)
    full.paste(grid, (0, 0))
    d = ImageDraw.Draw(full)
    y = grid.height + 8
    for ln in lines:
        d.text((28, y), ln, font=font, fill=FG)
        y += lh
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    full.save(OUT, optimize=True)
    print(f"保存: {OUT} ({full.width}x{full.height}) レイヤー: {', '.join(shown)}")


if __name__ == "__main__":
    main()

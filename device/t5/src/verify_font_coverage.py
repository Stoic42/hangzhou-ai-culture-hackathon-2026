"""Verify the codepoint maps in the fonts linked into the firmware."""
import re
from pathlib import Path

src = Path(__file__).resolve().parent
gen = src / "generated"
macros = dict(re.findall(r'^#define (\w+) "(.*)"$', (src/"ui_text.h").read_text(encoding="utf-8"), re.M))
embedded = (gen/"builtin_presets.c").read_text(encoding="utf-8")
all_text = ''.join(macros.values()) + embedded
cjk = {c for c in all_text if ord(c)>127}
assert cjk == set((gen/"font_symbols.txt").read_text(encoding="utf-8"))
full = cjk | set(map(chr,range(32,127)))
roles = {
    "buddy_font": full,
    "buddy_display": full,
    "buddy_caption": set(macros["UI_HOME_INDEX_FMT"].replace("%d","0123456789")),
    "buddy_heading": set(macros["UI_APP_TITLE"]),
    "buddy_button": set(''.join(macros[k] for k in ("UI_BTN_GENERATE","UI_BTN_BACK","UI_GAME_BACK","UI_HOME_PLAY","UI_BTN_RESTART"))),
}
for name, required in roles.items():
    font = (gen/(name+".c")).read_text(encoding="utf-8")
    start = int(re.search(r"\.range_start=(\d+)",font)[1])
    offsets = re.search(r"uint16_t offsets\[\] = \{(.*?)\};",font,re.S)[1]
    codes = {chr(start + int(v)) for v in re.findall(r"\d+", offsets)}
    assert required <= codes, (name,required-codes)
    assert f"const lv_font_t {name} =" in font
    print(f"{name}: {len(codes)} glyphs, all required codepoints present")

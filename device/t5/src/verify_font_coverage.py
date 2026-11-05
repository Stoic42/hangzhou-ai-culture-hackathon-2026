# Verification: every char used by ui_text.h and preset JSONs is covered by
# generated/font_symbols.txt (non-ASCII) or the baked ASCII range 0x20-0x7E.
import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent
syms = set((SRC / "generated/font_symbols.txt").read_text(encoding="utf-8"))

print("baked CJK symbol count:", len(syms))
ok = True


def check(name, text):
    global ok
    miss_nonascii = sorted({c for c in text if ord(c) > 0x7F and c not in syms})
    miss_ascii = sorted({c for c in text if ord(c) <= 0x7F and not (0x20 <= ord(c) <= 0x7E)})
    ok &= not miss_nonascii and not miss_ascii
    print(f"{name}: non-ASCII missing={miss_nonascii or 'NONE'}; "
          f"ASCII outside 0x20-0x7E={miss_ascii or 'NONE'}")


# 1) every string literal in ui_text.h (escape sequences like \n are ASCII,
#    so scanning raw literal content is sufficient)
hdr = (SRC / "ui_text.h").read_text(encoding="utf-8")
ui = "".join(re.findall(r'"(?:[^"\\]|\\.)*"', hdr))
check("ui_text.h", ui)

# 2) preset JSONs exactly as embedded (minified, ensure_ascii=False)
for p in ("last-one.json", "do-now.json", "decide-now.json"):
    data = json.loads((SRC.parent.parent.parent / "shared/presets" / p)
                      .read_text(encoding="utf-8"))
    check(f"preset {p}", json.dumps(data, ensure_ascii=False, separators=(",", ":")))

# 3) generated font really baked the ASCII range and keeps the buddy_font name
font = (SRC / "generated/buddy_font.c").read_text(encoding="utf-8")
hdr_opts = font[:2000]
assert "-r 0x20-0x7E" in hdr_opts, "ASCII range missing from font opts"
assert "const lv_font_t buddy_font = {" in font, "font symbol not renamed"
for ch in "%d/s#():,;.- 0123456789ABCDEF":
    assert 0x20 <= ord(ch) <= 0x7E
print("font header: -r 0x20-0x7E present; renamed to buddy_font: OK")

print("RESULT:", "ALL COVERED" if ok else "MISSING FOUND")
raise SystemExit(0 if ok else 1)

import sys

import generate_video as g

MODS = {"assets": "generate_assets", "harder_to_ignore": "generate_hardertoignore",
        "lifestyle": "generate_lifestyle", "lee": "generate_lee", "dan": "style_dan", "flash": "style_flash"}

if len(sys.argv) > 1:
    key = sys.argv[1]
    if key in MODS:
        __import__(MODS[key]).apply_to(g)
    else:
        print(f"unknown story '{key}', known: {list(MODS)} (or omit for income_vs_wealth)")
        sys.exit(1)

for c in g.CLIPS:
    n = len(list((g.FRAMES_DIR / f"clip{c['id']}").glob("frame_*.png")))
    c["total_frames"] = n
    print(f"clip{c['id']} frames={n} sec={round(n / g.FPS, 2)}")

g.compile_video()

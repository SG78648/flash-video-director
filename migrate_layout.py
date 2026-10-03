"""migrate_layout.py - one-time move of an old Flash Studio data layout into the project layout.

    python migrate_layout.py          show what would move
    python migrate_layout.py --do     move it (stop the studio server first)

Old layout                                   New layout
  studio_data/state.json                       projects/Lifestyle Inflation/project.json
  output/adi/, output/dan/ (working files)     projects/Lifestyle Inflation/adi|dan/
  output/adi|dan/*.mp4 (finished videos)       output/<Project>_<style>_<format>_<time>[_music].mp4
  output/audio, output/timing                  library/cache/narration-original/ (copied)
  output/sfx                                   library/cache/sfx/
  studio_data/voices|presets|music             library/voices|presets|music
  studio_data/voice_cache                      library/cache/voice
  old working leftovers in output/             archive/legacy-output/   (nothing is deleted)

Finished videos of the older stories (output/income_vs_wealth_*.mp4 ...) stay in output/.
"""
import re
import shutil
import sys

import projects

DO = "--do" in sys.argv
ROOT = projects.ROOT
PROJECT = projects.DEFAULT_PROJECT
OLD_FINAL = re.compile(r"^lifestyle_inflation_(?P<style>adi|dan)(?:_(?P<fmt>1x1|16x9))?_(?P<stamp>\d{4}-\d{2}-\d{2}_\d{6})(?P<music>_music)?\.mp4$")
moves = []


def plan(src, dst, copy=False):
    if src.exists():
        moves.append((src, dst, copy))


def run():
    pdir = projects.PROJECTS_DIR / PROJECT
    out = ROOT / "output"
    data = projects.DATA_DIR
    arch = ROOT / "archive" / "legacy-output"

    plan(data / "state.json", pdir / "project.json")
    for style in projects.STYLES:
        old = out / style
        if not old.is_dir():
            continue
        for item in sorted(old.iterdir()):
            m = OLD_FINAL.match(item.name)
            if m:
                fmt = m["fmt"] or "9x16"
                plan(item, out / f"{PROJECT}_{style}_{fmt}_{m['stamp']}{m['music'] or ''}.mp4")
            else:
                plan(item, pdir / style / item.name)
    plan(out / "audio", projects.ORIGINAL_NARRATION / "audio", copy=True)
    plan(out / "timing", projects.ORIGINAL_NARRATION / "timing", copy=True)
    plan(out / "sfx", projects.LIB_CACHE / "sfx")
    for kind, dst in (("voices", projects.LIB_VOICES), ("presets", projects.LIB_PRESETS), ("music", projects.LIB_MUSIC)):
        plan(data / kind, dst)
    plan(data / "voice_cache", projects.LIB_CACHE / "voice")
    # working leftovers of the first scripts (kept, just out of the way of the finished videos)
    for name in ("clip%d.mp4" % i for i in range(1, 12)):
        plan(out / name, arch / name)
    for name in ("intro.mp4", "outro.mp4", "concat.txt", "qa_report.json", "layoutcheck", "preview_glow.png", "spotcheck_rework",
                 "silent_intro.mp3", "silent_outro.mp3", "sfx_src", "turn_income_into_assets_prompts.md", "audio", "timing", "frames"):
        plan(out / name, arch / name)

    for src, dst, copy in moves:
        print(("copy " if copy else "move ") + str(src.relative_to(ROOT)) + "  ->  " + str(dst.relative_to(ROOT)))
        if not DO:
            continue
        if dst.exists():
            print("   skipped: the target already exists")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        else:
            shutil.move(str(src), str(dst))
    if DO:
        for style in projects.STYLES:
            (pdir / style).mkdir(parents=True, exist_ok=True)
        (pdir / "music").mkdir(parents=True, exist_ok=True)
        for d in (projects.LIB_VOICES, projects.LIB_PRESETS, projects.LIB_MUSIC):
            d.mkdir(parents=True, exist_ok=True)
        for style in projects.STYLES:                       # the old, now empty, style folders
            old = out / style
            if old.is_dir() and not any(old.iterdir()):
                old.rmdir()
        projects.set_active(PROJECT)
    print(f"\n{len(moves)} item(s) {'moved' if DO else 'would move (run with --do)'}.")


if __name__ == "__main__":
    run()

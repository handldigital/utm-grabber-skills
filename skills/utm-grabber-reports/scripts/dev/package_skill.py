"""
Dev tool: snapshot the working copy into Skills/v{X.Y}/ and build the upload zip.

    python scripts/dev/package_skill.py [SKILLS_DIR]

SKILLS_DIR defaults to ../../Skills (next to the working copy). Writes:
  Skills/v{X.Y}/utm-grabber-reports/          full source snapshot (archive)
  Skills/utm-grabber-reports-v{X.Y}.zip       upload zip, root folder utm-grabber-reports/
Excludes virtualenvs, caches, macOS/Google Drive clutter (.DS_Store, Icon\\r) and .claude folders.
"""
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, "..", ".."))

SKIP_DIRS = {".venv", "__pycache__", ".claude", ".git", "node_modules"}


def _skip_file(name):
    return (name in (".DS_Store",) or name.startswith("Icon") and len(name) <= 5 or name.endswith(".pyc")
            or name.endswith(".tmp"))


def main():
    skills = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.normpath(os.path.join(SKILL, "..", "Skills"))
    with open(os.path.join(SKILL, "VERSION.md")) as f:
        version = f.read().strip()
    short = ".".join(version.split(".")[:2])
    dest_root = os.path.join(skills, "v" + short)
    dest = os.path.join(dest_root, "utm-grabber-reports")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    count = 0
    for root, dirs, files in os.walk(SKILL):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(root, SKILL)
        for fn in files:
            if _skip_file(fn):
                continue
            src = os.path.join(root, fn)
            out = os.path.join(dest, rel, fn) if rel != "." else os.path.join(dest, fn)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(src, out)
            count += 1
    zpath = os.path.join(skills, "utm-grabber-reports-v%s.zip" % short)
    if os.path.exists(zpath):
        os.unlink(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(dest):
            for fn in files:
                p = os.path.join(root, fn)
                z.write(p, os.path.relpath(p, dest_root))
    size = os.path.getsize(zpath)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        bad = [n for n in names if "__pycache__" in n or ".venv" in n or n.endswith(".pyc") or "/Icon" in n
               or ".DS_Store" in n]
        ver = z.read("utm-grabber-reports/VERSION.md").decode().strip()
    print("snapshot: %s (%d files)" % (dest, count))
    print("zip: %s (%d KB, %d entries, VERSION %s, junk %d)" % (zpath, size // 1024, len(names), ver, len(bad)))


if __name__ == "__main__":
    main()

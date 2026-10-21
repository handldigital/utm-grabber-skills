"""
Dev tool (macOS only): open decks in Microsoft PowerPoint, save each as PDF.

    python scripts/dev/powerpoint_check.py OUT_DIR deck1.pptx [deck2.pptx ...]

PowerPoint is sandboxed, so decks are copied into its container first. Needs
the Bash sandbox off (AppleScript).
"""
import os
import shutil
import subprocess
import sys

CONTAINER = os.path.expanduser("~/Library/Containers/com.microsoft.Powerpoint/Data/Documents/utmg-check")

SCRIPT = '''
on run argv
  set inPath to item 1 of argv
  set outPath to item 2 of argv
  with timeout of 120 seconds
    tell application "Microsoft PowerPoint"
      open (POSIX file inPath)
      delay 2
      set p to active presentation
      save p in (POSIX file outPath) as save as PDF
      delay 1
      close p saving no
    end tell
  end timeout
  return "ok"
end run
'''


def check(paths, out_dir):
    os.makedirs(CONTAINER, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    for p in paths:
        name = os.path.basename(p)
        src = os.path.join(CONTAINER, name)
        shutil.copy(p, src)
        pdf = os.path.join(CONTAINER, os.path.splitext(name)[0] + "-pp.pdf")
        if os.path.exists(pdf):
            os.unlink(pdf)
        try:
            r = subprocess.run(["osascript", "-e", SCRIPT, src, pdf], capture_output=True, text=True, timeout=150)
            msg = (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            msg = "timeout"
        ok = os.path.exists(pdf)
        if ok:
            shutil.copy(pdf, os.path.join(out_dir, os.path.basename(pdf)))
        print(("OK  " if ok else "FAIL") + " " + name + ("" if ok else "  " + msg))


if __name__ == "__main__":
    check(sys.argv[2:], sys.argv[1])

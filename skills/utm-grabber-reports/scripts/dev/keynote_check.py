"""
Dev tool (macOS only): open decks in Keynote, export each to PDF, report failures.

    python scripts/dev/keynote_check.py OUT_DIR deck1.pptx [deck2.pptx ...]

Keynote is sandboxed, so decks are copied into its container first. Import
errors ("can't be imported") are detected and dismissed automatically. Needs
the Bash sandbox off (AppleScript + Launch Services).
"""
import os
import shutil
import subprocess
import sys
import time

CONTAINER = os.path.expanduser("~/Library/Containers/com.apple.Keynote/Data/Documents/utmg-check")

SCRIPT = '''
on run argv
  set inPath to item 1 of argv
  set outPath to item 2 of argv
  with timeout of 120 seconds
    tell application id "com.apple.Keynote"
      set theDoc to open (POSIX file inPath as alias)
      if theDoc is missing value then return "OPEN-FAILED"
      delay 0.5
      export theDoc to (POSIX file outPath) as PDF
      close theDoc saving no
    end tell
  end timeout
  return "ok"
end run
'''

DISMISS = '''
tell application "System Events"
  set msgs to ""
  repeat with p in (every process whose name contains "Keynote")
    repeat with w in windows of p
      try
        set allEls to entire contents of w
        repeat with e in allEls
          try
            if class of e is static text then set msgs to msgs & (value of e as text) & " | "
            if class of e is button and (name of e as text) is "OK" then click e
          end try
        end repeat
      end try
    end repeat
  end repeat
  return msgs
end tell
'''


def check(paths, out_dir):
    os.makedirs(CONTAINER, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    results = {}
    for p in paths:
        name = os.path.basename(p)
        src = os.path.join(CONTAINER, name)
        shutil.copy(p, src)
        pdf = os.path.join(CONTAINER, os.path.splitext(name)[0] + ".pdf")
        if os.path.exists(pdf):
            os.unlink(pdf)
        subprocess.run(["osascript", "-e", DISMISS], capture_output=True, text=True, timeout=30)
        try:
            r = subprocess.run(["osascript", "-e", SCRIPT, src, pdf], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            r = subprocess.CompletedProcess([], 1, "", "timeout")
        ok = os.path.exists(pdf)
        msg = (r.stdout + r.stderr).strip()
        if not ok:
            time.sleep(0.5)
            d = subprocess.run(["osascript", "-e", DISMISS], capture_output=True, text=True, timeout=30)
            msg += " || dialog: " + d.stdout.strip()[:200]
        else:
            shutil.copy(pdf, os.path.join(out_dir, os.path.basename(pdf)))
        results[name] = (ok, msg)
        print(("OK  " if ok else "FAIL") + " " + name + ("" if ok else "  " + msg))
    return results


if __name__ == "__main__":
    check(sys.argv[2:], sys.argv[1])

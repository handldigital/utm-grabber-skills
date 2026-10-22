"""Dev tool: PDF -> contact sheet PNG.  python scripts/dev/sheet.py file.pdf out.png [cols] [dpi]"""
import glob
import os
import subprocess
import sys
import tempfile

from PIL import Image


def sheet(pdf, out, cols=4, dpi=36):
    d = tempfile.mkdtemp()
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", pdf, os.path.join(d, "p")], check=True)
    fs = sorted(glob.glob(os.path.join(d, "p-*.png")), key=lambda f: int(f.rsplit("-", 1)[1].split(".")[0]))
    ims = [Image.open(f) for f in fs]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    s = Image.new("RGB", (cols * (w + 8), rows * (h + 8)), "#777")
    for i, im in enumerate(ims):
        s.paste(im, ((i % cols) * (w + 8), (i // cols) * (h + 8)))
    s.save(out)
    return len(ims)


if __name__ == "__main__":
    a = sys.argv[1:]
    print(sheet(a[0], a[1], int(a[2]) if len(a) > 2 else 4, int(a[3]) if len(a) > 3 else 36))

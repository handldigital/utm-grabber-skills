"""
Embed the theme's fonts inside a .pptx so PowerPoint shows the real typefaces on
machines that don't have them installed.

PowerPoint stores embedded fonts as Embedded OpenType (EOT) parts
(`ppt/fonts/fontN.fntdata`, content type application/x-fontdata) listed in
presentation.xml under <p:embeddedFontLst>. We write uncompressed, unobfuscated
EOT (version 0x00020001) wrapping the TrueType subsets that ship with the skill.
All bundled typefaces are SIL Open Font License, so embedding is permitted.

Google Slides ignores embedded fonts but maps these Google Fonts family names to
its own copies, so it renders correctly too. Keynote substitutes missing fonts,
which is why the slide layout also sizes text with substitution headroom.
"""
import io
import os
import struct
import zipfile


_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "fonts", "ttf"))

FONT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
FONT_CT = "application/x-fontdata"


def _utf16(s):
    return s.encode("utf-16-le")


def _ttf_info(data):
    """Read the few TrueType fields an EOT header needs (no fontTools dependency)."""
    num = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for i in range(num):
        rec = data[12 + 16 * i: 28 + 16 * i]
        tag = rec[:4].decode("latin-1")
        off, ln = struct.unpack(">II", rec[8:16])
        tables[tag] = (off, ln)
    head_off = tables["head"][0]
    checksum_adj = struct.unpack(">I", data[head_off + 8: head_off + 12])[0]
    o = tables["OS/2"][0]
    os2_ver = struct.unpack(">H", data[o:o + 2])[0]
    weight = struct.unpack(">H", data[o + 4:o + 6])[0]
    panose = data[o + 32:o + 42]
    ur = struct.unpack(">IIII", data[o + 42:o + 58])
    fs_sel = struct.unpack(">H", data[o + 62:o + 64])[0]
    cp = struct.unpack(">II", data[o + 78:o + 86]) if os2_ver >= 1 else (0, 0)
    names = {}
    n_off = tables["name"][0]
    count, str_off = struct.unpack(">HH", data[n_off + 2:n_off + 6])
    for i in range(count):
        r = data[n_off + 6 + 12 * i: n_off + 18 + 12 * i]
        pid, eid, lid, nid, ln, off = struct.unpack(">HHHHHH", r)
        raw = data[n_off + str_off + off: n_off + str_off + off + ln]
        if pid == 3 and lid == 0x409 and nid in (1, 2, 4, 5) and nid not in names:
            names[nid] = raw.decode("utf-16-be", "replace")
        elif pid == 1 and nid in (1, 2, 4, 5) and nid not in names:
            names[nid] = raw.decode("latin-1", "replace")
    return {"checksum_adj": checksum_adj, "weight": weight, "panose": panose, "ur": ur,
            "italic": 1 if fs_sel & 1 else 0, "cp": cp, "names": names}


def make_eot(ttf_bytes):
    """Wrap raw TrueType bytes in an EOT 0x00020001 header (no compression, no XOR)."""
    info = _ttf_info(ttf_bytes)
    nm = info["names"]
    family, style, version, full = nm.get(1, ""), nm.get(2, ""), nm.get(5, ""), nm.get(4, "")
    body = b""
    body += info["panose"]
    body += struct.pack("<BB", 1, info["italic"])                 # charset DEFAULT_CHARSET, italic
    body += struct.pack("<I", info["weight"])
    body += struct.pack("<H", 0)                                  # fsType: installable
    body += struct.pack("<H", 0x504C)                             # magic
    body += struct.pack("<IIII", *info["ur"])
    body += struct.pack("<II", *info["cp"])
    body += struct.pack("<I", info["checksum_adj"])
    body += struct.pack("<IIII", 0, 0, 0, 0)                      # reserved
    body += struct.pack("<H", 0)                                  # padding1
    for s_ in (family, style, version, full):
        b = _utf16(s_)
        body += struct.pack("<H", len(b)) + b + struct.pack("<H", 0)
    body = body[:-2]                                              # FullName has no padding after it...
    body += struct.pack("<H", 0)                                  # ...padding5 follows instead
    body += struct.pack("<H", 0)                                  # RootStringSize = 0
    eot_size = 16 + len(body) + len(ttf_bytes)
    header = struct.pack("<IIII", eot_size, len(ttf_bytes), 0x00020001, 0)
    return header + body + ttf_bytes


# family (as written in slides) -> {style: font file stem}
def _family_files(family):
    from .fonts import FACES
    out = {}
    for stem, (fam, wt, style) in FACES.items():
        if fam != family:
            continue
        if style == "italic":
            key = "bolditalic" if wt >= 600 else "italic"
        else:
            key = "bold" if wt >= 700 else ("regular" if wt == 400 else None)
        if key and key not in out:
            out[key] = stem
    # no 700 face: the heaviest face of 600+ stands in as bold
    if "bold" not in out:
        heavy = sorted((wt, stem) for stem, (fam, wt, style) in FACES.items()
                       if fam == family and style == "normal" and wt >= 600)
        if heavy:
            out["bold"] = heavy[-1][1]
    # families without a 400 weight (e.g. Barlow Condensed) use their lightest as regular
    if "regular" not in out:
        cands = sorted((wt, stem) for stem, (fam, wt, style) in FACES.items() if fam == family and style == "normal")
        if cands:
            out["regular"] = cands[0][1]
            if "bold" not in out and len(cands) > 1:
                out["bold"] = cands[-1][1]
    return out


def embed_fonts(pptx_path, families):
    """Rewrite pptx_path in place with the given font families embedded."""
    entries = []
    for fam in families:
        files = _family_files(fam)
        for style in ("regular", "bold", "italic", "bolditalic"):
            stem = files.get(style)
            if not stem:
                continue
            p = os.path.join(_ROOT, stem + ".ttf")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    entries.append((fam, style, make_eot(f.read())))
    if not entries:
        return pptx_path
    zin = zipfile.ZipFile(pptx_path)
    items = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    # parts + rels
    rels = items["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    ids = [int(x) for x in __import__("re").findall(r'Id="rId(\d+)"', rels)]
    nxt = max(ids or [0]) + 1
    font_xml = {}
    new_rels = []
    for i, (fam, style, data) in enumerate(entries, 1):
        part = "ppt/fonts/font%d.fntdata" % i
        items[part] = data
        rid = "rId%d" % nxt
        nxt += 1
        new_rels.append('<Relationship Id="%s" Type="%s" Target="fonts/font%d.fntdata"/>' % (rid, FONT_REL, i))
        font_xml.setdefault(fam, []).append((style, rid))
    rels = rels.replace("</Relationships>", "".join(new_rels) + "</Relationships>")
    items["ppt/_rels/presentation.xml.rels"] = rels.encode("utf-8")
    ct = items["[Content_Types].xml"].decode("utf-8")
    if 'Extension="fntdata"' not in ct:
        ct = ct.replace("<Default ", '<Default Extension="fntdata" ContentType="%s"/><Default ' % FONT_CT, 1)
    items["[Content_Types].xml"] = ct.encode("utf-8")
    pres = items["ppt/presentation.xml"].decode("utf-8")
    lst = ["<p:embeddedFontLst>"]
    for fam, styles in font_xml.items():
        lst.append('<p:embeddedFont><p:font typeface="%s" charset="0"/>' % fam)
        order = {"regular": 0, "bold": 1, "italic": 2, "bolditalic": 3}
        for style, rid in sorted(styles, key=lambda x: order[x[0]]):
            lst.append('<p:%s r:id="%s"/>' % (style, rid))
        lst.append("</p:embeddedFont>")
    lst.append("</p:embeddedFontLst>")
    block = "".join(lst)
    # schema order: ... sldSz, notesSz, smartTags?, embeddedFontLst, custShowLst?, ..., defaultTextStyle
    import re as _re
    m = _re.search(r"<p:notesSz[^>]*/>", pres)
    if m:
        pres = pres[:m.end()] + block + pres[m.end():]
    head_end = pres.index(">", pres.index("<p:presentation"))
    head = pres[:head_end]
    add = ""
    if "embedTrueTypeFonts" not in head:
        add += 'embedTrueTypeFonts="1" '
    if "saveSubsetFonts" not in head:
        add += 'saveSubsetFonts="1" '
    if add:
        pres = pres.replace("<p:presentation ", "<p:presentation " + add, 1)
    items["ppt/presentation.xml"] = pres.encode("utf-8")
    tmp = pptx_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        # [Content_Types].xml first, as Office expects
        zout.writestr("[Content_Types].xml", items.pop("[Content_Types].xml"))
        for n, d in items.items():
            zout.writestr(n, d)
    os.replace(tmp, pptx_path)
    return pptx_path

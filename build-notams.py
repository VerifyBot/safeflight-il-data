#!/usr/bin/env python3
"""Fetch active Israeli NOTAMs from the IAA Mobile AeroInfo service → notams.json.

Source: https://brin.iaa.gov.il/MobileAeroinfo/maiNotam.aspx (IAA — the same backend
DronesIL links to; recon 2026-08-31, decision D-015). It sits behind an Imperva WAF that
allows a normal browser User-Agent, so a scheduled server-side fetch works. The mobile
feed truncates E-lines server-side, but closure/UAS NOTAMs keep coordinate + radius, which
is enough to place a caution circle and a summary; the full text lives at the source URL.

This runs OUTSIDE the browser (a GitHub Action, every few hours) because the endpoint has
no CORS headers — see decision D-017. Output is committed and the app fetches it live from
the public data repo's raw URL, with the bundled copy as fallback.

Run: python3 tools/build-notams.py [path/to/local.html]   (arg = offline parse for testing)
Output: <repo>/src/data/notams.json
"""
import html as htmllib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://brin.iaa.gov.il/MobileAeroinfo/maiNotam.aspx"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
OUT = Path(__file__).resolve().parent / "notams.json"

ROW_RE = re.compile(r'<table id="TBL\d+"[^>]*>(.*?)</table>', re.S)
COORD_RE = re.compile(r"(\d{6})([NS])\s?(\d{6,7})([EW])")
RADIUS_RE = re.compile(r"(?:WI\s+)?([\d.]+)\s?(NM|KM)\s+RAD", re.I)
ID_RE = re.compile(r"\b([A-Z]\d{4}/\d{2})\b")


def dms(tok, hemi):
    d, m, s = int(tok[:-4]), int(tok[-4:-2]), int(tok[-2:])
    v = d + m / 60 + s / 3600
    return -v if hemi in "SW" else v


def strip(htmlfrag):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", htmlfrag))).strip()


def parse(html):
    notams = []
    for frag in ROW_RE.findall(html):
        text = strip(frag)
        idm = ID_RE.search(text)
        if not idm:
            continue
        nid = idm.group(1)
        loc_m = re.search(re.escape(nid) + r"\s+([A-Z]{4})", text)
        loc = loc_m.group(1) if loc_m else "LLLL"
        # Summary = the E-line, which the feed truncates server-side ("..."). Start it at
        # "E)" so we drop the repeated location/nbsp prefix.
        em = re.search(r"E\)\s*(.*)", text)
        eline = (em.group(1) if em else text[idm.end():]).strip()
        cm = COORD_RE.search(text)
        coord = None
        if cm:
            lon = cm.group(3) if len(cm.group(3)) == 7 else "0" + cm.group(3)
            coord = [round(dms(lon, cm.group(4)), 5), round(dms(cm.group(1), cm.group(2)), 5)]
        rm = RADIUS_RE.search(text)
        radius_km = None
        if rm:
            radius_km = round(float(rm.group(1)) * (1.852 if rm.group(2).upper() == "NM" else 1), 3)
        up = "categories"  # classify for the UI / engine
        is_uas = bool(re.search(r"\bUAS|UAV|DRONE\b", text, re.I))
        is_closure = bool(re.search(r"\bCLSD|CLOSED|PROHIBITED|RESTRICT", text, re.I))
        gnd_up = bool(re.search(r"GND\s+UP|SFC|GROUND", text, re.I))
        notams.append({
            "id": nid,
            "loc": loc,
            "summary": eline[:200],
            "coord": coord,
            "radiusKm": radius_km,
            "isUAS": is_uas,
            "isClosure": is_closure,
            "groundUp": gnd_up,
            # A NOTAM is a drone-relevant caution zone if it has a location + closure/UAS
            # nature; those with coordinates get a caution circle on the map.
            "mapZone": bool(coord and (is_closure or is_uas)),
        })
    return notams


def main():
    if len(sys.argv) > 1:  # offline parse for testing
        html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": UA,
                                                    "Accept-Language": "en,he"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    notams = parse(html)
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "IAA Mobile AeroInfo (brin.iaa.gov.il) — summaries; full text at the source",
        "sourceUrl": URL,
        "count": len(notams),
        "mapZoneCount": sum(1 for n in notams if n["mapZone"]),
        "notams": notams,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT} — {doc['count']} NOTAMs, {doc['mapZoneCount']} with map geometry")


if __name__ == "__main__":
    main()

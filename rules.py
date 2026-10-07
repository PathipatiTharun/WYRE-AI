"""Step 5: cheap rule-based SIGNALS. These never decide a verdict on their own;
they are evidence passed to the LLM judge and recorded in the spreadsheet."""
import re
import pymupdf

PHONE_RE = re.compile(r"\b\d{3}[.\- ]\d{3}[.\- ]\d{4}\b")
URL_RE = re.compile(r"https?://|www\.|\.com\b", re.I)
ADDRESS_RE = re.compile(r"\b(Inc\.|LLC|Way|Street|St\.|Ave|Suite|Utah \d{5}|\d{5})\b")
DIMENSION_RE = re.compile(r"^[\d\s'\"\-/.]+$|^\d+'\s*-\s*\d")                 # 7' - 11 3/8"
DIM_NOTE_RE = re.compile(r"^(F\.?O\.?S\.?|F\.?O\.?F\.?|TYP\.?|EQ\.?|CLR\.?|NIC)$", re.I)
NOTE_RE = re.compile(r"^([A-Z]|\d{1,2})\.\s")                                  # 'A. ALL NEW WALL...'
HEADING_RE = re.compile(r"(LEGEND|^NOTES:?$|SCHEDULE$|^GENERAL NOTES)", re.I)
ELEVATION_RE = re.compile(r"^(FF|TOC|TOW|BOW|INV|RIM)\s*=", re.I)
GRID_TEXT_RE = re.compile(r"^[A-Z]{1,2}\d{0,2}(\.\d)?$|^\d{1,2}(\.\d)?$")       # A, B1, 12, C.1
ROOM_RE = re.compile(r"^(LIVING|KITCHEN|BATH|BEDROOM|PRIMARY BEDROOM|HALL|CLOSET|LAUNDRY|MECH|ELECTRICAL|STORAGE|LOBBY|CORRIDOR|STAIR|IDF)\b", re.I)
CODE_TOKEN_RE = re.compile(r"\b[A-Z]{1,3}\d+(?:\.\d+)?[A-Z]{0,2}\b")

_circles = {}


def small_circles(doc, page_number):
    """Small closed curved shapes (bubbles). Boxes returned in the SEEN coordinate space."""
    if page_number not in _circles:
        page = doc[page_number - 1]
        m = page.rotation_matrix
        out = []
        for d in page.get_drawings():
            r = d["rect"]
            curvy = sum(1 for it in d["items"] if it[0] == "c") >= 4
            if curvy and 15 < r.width < 90 and 0.8 < (r.width / max(r.height, 1e-6)) < 1.25:
                out.append(r * m)
        _circles[page_number] = out
    return _circles[page_number]


def box(quad):
    xs, ys = quad[0::2], quad[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def in_bubble(doc, page_number, quad):
    x0, y0, x1, y1 = box(quad)
    for c in small_circles(doc, page_number):
        if c.x0 <= x0 and c.y0 <= y0 and c.x1 >= x1 and c.y1 >= y1:
            return True
    return False


def region_signals(doc, page_number, region, glossary, page_w=3024, page_h=2160):
    t = region["text"].strip()
    x0, y0, x1, y1 = box(region["quad_px"])
    cx, cy = (x0 + x1) / 2 / page_w, (y0 + y1) / 2 / page_h
    s = []
    if PHONE_RE.search(t) or URL_RE.search(t) or (ADDRESS_RE.search(t) and cx > 0.85):
        s.append("title_block_text")
    if DIMENSION_RE.search(t) or DIM_NOTE_RE.match(t):
        s.append("dimension_or_annotation")
    if NOTE_RE.match(t):
        s.append("general_note")
    if HEADING_RE.search(t):
        s.append("legend_or_heading")
    if ELEVATION_RE.match(t):
        s.append("elevation_label")
    if ROOM_RE.match(t):
        s.append("room_label")
    if GRID_TEXT_RE.match(t) and in_bubble(doc, page_number, region["quad_px"]):
        s.append("text_in_bubble")          # grid bubble OR a real keyed tag; the LLM decides
    if min(cx, 1 - cx, cy, 1 - cy) < 0.04:
        s.append("near_sheet_edge")
    for code in set(CODE_TOKEN_RE.findall(t)):
        if code in glossary["assembly_codes"]:
            s.append(f"code:{code}={glossary['assembly_codes'][code]['category']}")
    return s

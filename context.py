"""Step 4: nearby text around a region, read from the PDF and mapped into the SEEN (rotated) space."""
import pymupdf

_cache = {}


def page_words(doc, page_number):
    """Words with boxes in the same 3024 x 2160 'as seen' space as quad_px.
    PyMuPDF extracts in the unrotated space, so we apply page.rotation_matrix."""
    if page_number not in _cache:
        page = doc[page_number - 1]
        m = page.rotation_matrix
        words = []
        for x0, y0, x1, y1, w, *_ in page.get_text("words"):
            r = pymupdf.Rect(x0, y0, x1, y1) * m
            words.append((r.x0, r.y0, r.x1, r.y1, w))
        _cache[page_number] = words
    return _cache[page_number]


def nearby_text(doc, page_number, quad, radius=120, limit=60):
    xs, ys = quad[0::2], quad[1::2]
    x0, y0, x1, y1 = min(xs) - radius, min(ys) - radius, max(xs) + radius, max(ys) + radius
    hits = [w for w in page_words(doc, page_number) if w[0] < x1 and w[2] > x0 and w[1] < y1 and w[3] > y0]
    hits.sort(key=lambda w: (round(w[1] / 10), w[0]))       # reading order: rows, then left to right
    return " ".join(w[4] for w in hits[:limit])

"""Step 2: render pages as images (as SEEN, rotation applied) and crop context around regions."""
import os
import pymupdf
from PIL import Image, ImageDraw

ZOOM = 2  # 1 pt = 1 quad_px unit, so pixels = quad_px * ZOOM


def render_pages(pdf_path, out_dir="pages"):
    """Render every page once. PyMuPDF applies /Rotate, so the image matches the 3024 x 2160 quad_px space."""
    os.makedirs(out_dir, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    paths = {}
    for page in doc:
        path = os.path.join(out_dir, f"page_{page.number + 1:02d}.png")
        if not os.path.exists(path):
            page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM)).save(path)
        paths[page.number + 1] = path
    return paths


def quad_to_box(quad):
    xs, ys = quad[0::2], quad[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def crop_region(page_img, quad, margin=150, out_path=None):
    """Crop the area around one region and draw a red box on the exact spot."""
    x0, y0, x1, y1 = (v * ZOOM for v in quad_to_box(quad))
    m = margin * ZOOM
    W, H = page_img.size
    box = (max(0, x0 - m), max(0, y0 - m), min(W, x1 + m), min(H, y1 + m))
    crop = page_img.crop(box).convert("RGB")
    draw = ImageDraw.Draw(crop)
    draw.rectangle([x0 - box[0] - 4, y0 - box[1] - 4, x1 - box[0] + 4, y1 - box[1] + 4], outline="red", width=5)
    if out_path:
        crop.save(out_path)
    return crop


def locate(quad, page_w=3024, page_h=2160):
    """Where on the sheet the region sits, useful for spotting title blocks and grid bubbles."""
    x0, y0, x1, y1 = quad_to_box(quad)
    cx, cy = (x0 + x1) / 2 / page_w, (y0 + y1) / 2 / page_h
    return {"cx": round(cx, 3), "cy": round(cy, 3),
            "near_edge": min(cx, 1 - cx, cy, 1 - cy) < 0.04,
            "in_title_block_strip": cx > 0.90}   # many sheets keep the title block down the right edge

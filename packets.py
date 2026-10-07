"""Step 6: build one 'evidence packet' per scope item for the judge:
item details + rule signals + nearby PDF text + one image with crops of its regions."""
import json
import os
from PIL import Image
import pymupdf
import context
import render
import rules

Image.MAX_IMAGE_PIXELS = None
MAX_REGIONS = 4          # judge a sample of distinct regions per item, not all 900 shrub tags


def distinct_regions(regions, k=MAX_REGIONS):
    """Pick regions with different text first, so mixed items show both good and bad evidence."""
    seen, picked = set(), []
    for r in regions:
        key = r["text"].strip()
        if key not in seen:
            seen.add(key)
            picked.append(r)
        if len(picked) == k:
            break
    return picked


def build_packets(pdf_path, results_path, glossary, skip_sheets, work_dir="work"):
    out_dir = os.path.join(work_dir, "packets")
    os.makedirs(out_dir, exist_ok=True)
    doc = pymupdf.open(pdf_path, encoding="utf-8")
    page_imgs = render.render_pages(pdf_path, out_dir=os.path.join(work_dir, "pages"))
    sheets = json.load(open(results_path, encoding="utf-8"))["drawings_processing_results"]
    packets = []
    for sh in sheets:
        if sh["sheet_number"] in skip_sheets:
            continue
        img = Image.open(page_imgs[sh["page_number"]], encoding="utf-8")
        for pkg, items in sh["bid_items"].items():
            for idx, it in enumerate(items):
                pid = f"{sh['sheet_number']}__{pkg}__{idx}".replace(" ", "_").replace("/", "-")
                regs = distinct_regions(it["regions"])
                ev, crops = [], []
                for n, r in enumerate(regs):
                    ev.append({
                        "n": n + 1,
                        "text": r["text"][:400],
                        "signals": rules.region_signals(doc, sh["page_number"], r, glossary,
                                                      sh.get("page_width") or 3024, sh.get("page_height") or 2160),
                        "nearby_text": context.nearby_text(doc, sh["page_number"], r["quad_px"])[:500],
                    })
                    crops.append(render.crop_region(img, r["quad_px"]))
                img_path = os.path.join(out_dir, pid + ".png")
                stitch(crops, img_path)
                packets.append({
                    "id": pid, "sheet_number": sh["sheet_number"], "sheet_name": sh["sheet_name"],
                    "discipline": sh["discipline"], "scope_package": pkg, "item_index": idx,
                    "bid_item": it["bid_item"], "subheading": it["subheading"],
                    "n_regions_total": len(it["regions"]), "evidence": ev, "image": img_path,
                })
    json.dump(packets, open(os.path.join(out_dir, "packets.json"), "w", encoding="utf-8"), indent=1)
    return packets


def stitch(crops, path, height=500):
    """Place crops side by side, numbered left to right in the same order as the evidence list."""
    resized = [c.resize((int(c.width * height / c.height), height)) for c in crops]
    total = sum(c.width for c in resized) + 20 * (len(resized) - 1)
    canvas = Image.new("RGB", (max(total, 1), height), "white")
    x = 0
    for c in resized:
        canvas.paste(c, (x, 0))
        x += c.width + 20
    canvas.save(path)


if __name__ == "__main__":
    import sys
    import glossary as gl
    g = gl.build_glossary(sys.argv[1], sys.argv[2])
    p = build_packets(sys.argv[1], sys.argv[2], g, gl.legend_sheet_numbers(sys.argv[1], sys.argv[2]))
    print(len(p), "packets written to work/packets/")

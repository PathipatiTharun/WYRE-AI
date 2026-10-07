"""Step 1: load results.json and flatten it into one row per scope item."""
import json
import sys
import pandas as pd



def load_items(path, legend_sheets=()):
    data = json.load(open(path, encoding="utf-8"))
    sheets = data["drawings_processing_results"]
    rows = []
    for sheet in sheets:
        for package, items in sheet["bid_items"].items():
            for idx, item in enumerate(items):
                texts = [r["text"] for r in item["regions"]]
                rows.append({
                    "sheet_number": sheet["sheet_number"],
                    "sheet_name": sheet["sheet_name"],
                    "discipline": sheet["discipline"],
                    "page_number": sheet["page_number"],
                    "scope_package": package,
                    "item_index": idx,                     # position inside the package list
                    "bid_item": item["bid_item"],
                    "subheading": item["subheading"],
                    "n_regions": len(texts),
                    "unique_texts": " || ".join(dict.fromkeys(texts)),
                    "is_legend_sheet": sheet["sheet_number"] in legend_sheets,
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import glossary as gl
    pdf = sys.argv[2] if len(sys.argv) > 2 else "drawings.pdf"
    res = sys.argv[1] if len(sys.argv) > 1 else "results.json"
    df = load_items(res, gl.legend_sheet_numbers(pdf, res))
    audit = df[~df.is_legend_sheet]
    print(f"{len(df)} items in total, {len(audit)} to audit across {audit.sheet_number.nunique()} sheets")
    audit.to_csv("items_to_audit.csv", index=False)
    print("Saved items_to_audit.csv")

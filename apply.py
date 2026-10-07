"""Step 8: turn verdicts into the two deliverables:
  1. corrected results.json (same structure, wrong items removed, bad regions trimmed in place)
  2. findings spreadsheet (one row per judged item)

Human decisions in overrides.csv always win over the LLM.
"""
import copy
import csv
import json
import os

import pandas as pd


def load_overrides(path="overrides.csv"):
    """CSV with columns: id, verdict (RIGHT/WRONG), note. Written by hand during review."""
    if not os.path.exists(path):
        return {}
    rows = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):       # utf-8-sig: works after saving in Excel
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        if not r.get("id"):
            continue
        if r.get("verdict", "").upper() not in ("RIGHT", "WRONG"):
            print(f"  WARNING overrides: '{r['id']}' has verdict '{r.get('verdict')}', must be RIGHT or WRONG. Ignored.")
            continue
        rows[r["id"]] = r
    return rows


def final_decision(packet, judgement, override):
    if override:
        return override["verdict"].strip().upper(), override.get("note", ""), "human"
    v = judgement["verdict"]
    if v == "REVIEW":
        return "RIGHT", "Not judged (error); kept by default so no real scope is lost", "default"
    return v, judgement["reason"], "llm"


def apply(results_path, packets, judgements, out_dir="out", overrides=None):
    overrides = overrides or {}
    os.makedirs(out_dir, exist_ok=True)
    unknown = set(overrides) - {p["id"] for p in packets}
    for oid in sorted(unknown):
        print(f"  WARNING overrides: id '{oid}' matches no item in this file. Check the spelling (copy it from packet_id in findings).")
    data = json.load(open(results_path, encoding="utf-8"))
    corrected = copy.deepcopy(data)
    by_key = {(p["sheet_number"], p["scope_package"], p["item_index"]): p for p in packets}
    rows = []

    for sheet in corrected["drawings_processing_results"]:
        removed_quads, kept_quads = set(), set()
        for pkg, items in sheet["bid_items"].items():
            new_items = []
            for idx, item in enumerate(items):
                p = by_key.get((sheet["sheet_number"], pkg, idx))
                if p is None:                                   # legend sheets: not audited, untouched
                    new_items.append(item)
                    kept_quads.update((pkg, tuple(r["quad_px"])) for r in item["regions"])
                    continue
                j = judgements.get(p["id"], {"verdict": "REVIEW", "reason": "missing", "bad_regions": [],
                                             "category": "other", "confidence": 0})
                verdict, reason, source = final_decision(p, j, overrides.get(p["id"]))
                bad_texts = {e["text"] for e in p["evidence"] if e["n"] in j.get("bad_regions", [])}
                action = "kept"
                if verdict == "WRONG":
                    removed_quads.update((pkg, tuple(r["quad_px"])) for r in item["regions"])
                    action = "item removed"
                else:
                    keep = [r for r in item["regions"] if r["text"][:400] not in bad_texts]
                    if bad_texts and keep and source != "human":
                        removed_quads.update((pkg, tuple(r["quad_px"])) for r in item["regions"]
                                             if r["text"][:400] in bad_texts)
                        action = f"kept, {len(item['regions']) - len(keep)} bad region(s) removed"
                        item["regions"] = keep
                    kept_quads.update((pkg, tuple(r["quad_px"])) for r in item["regions"])
                    new_items.append(item)
                rows.append({
                    "sheet_number": p["sheet_number"], "sheet_name": p["sheet_name"],
                    "discipline": p["discipline"], "scope_package": pkg, "item_name": p["bid_item"],
                    "subheading": p["subheading"], "n_regions": p["n_regions_total"],
                    "evidence_texts": " || ".join(e["text"][:80] for e in p["evidence"]),
                    "rule_signals": " | ".join(sorted({s for e in p["evidence"] for s in e["signals"]})),
                    "verdict": verdict, "reason": reason, "decided_by": source,
                    "error_category": j.get("category"), "llm_verdict": j.get("verdict"),
                    "llm_confidence": j.get("confidence"), "action": action, "packet_id": p["id"],
                })
            sheet["bid_items"][pkg] = new_items
        sheet["bid_items"] = {k: v for k, v in sheet["bid_items"].items() if v}

        # scopes repeat the regions by package; drop only regions we removed and no kept item still uses
        for scope in sheet["scopes"]:
            scope["regions"] = [r for r in scope["regions"]
                                if (scope["scope"], tuple(r["quad_px"])) not in removed_quads
                                or (scope["scope"], tuple(r["quad_px"])) in kept_quads]
        sheet["scopes"] = [s for s in sheet["scopes"] if s["regions"]]

    json.dump(corrected, open(os.path.join(out_dir, "results_corrected.json"), "w", encoding="utf-8"), indent=1)
    df = pd.DataFrame(rows)
    for name, save in (("findings.xlsx", lambda p: df.to_excel(p, index=False)),
                       ("findings.csv", lambda p: df.to_csv(p, index=False))):
        path = os.path.join(out_dir, name)
        try:
            save(path)
        except PermissionError:                     # file is open in Excel: save a copy instead of crashing
            alt = path.replace(".", "_new.", 1)
            save(alt)
            print(f"  {name} is open in another program, so this run saved {alt} instead. Close Excel to avoid this.")
    return df

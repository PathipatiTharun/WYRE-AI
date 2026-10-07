"""One command for the whole job, on any drawings PDF + results JSON:

    python run.py drawings.pdf results.json                 # uses Gemini (needs GEMINI_API_KEY)
    python run.py drawings.pdf results.json --fake          # test the pipeline without an API key
    python run.py new.pdf new.json --glossary work/<id>/out/glossary.json # new sheets without legend pages

Every drawings file gets its own folder: work/<id>/
    pages/, packets/, judgements.jsonl   (working files)
    overrides.csv                        (your hand decisions for THIS file only)
    out/                                 (results_corrected.json, findings.xlsx, findings.csv, glossary.json)
"""
import argparse
import hashlib
import json
import os

import glossary as gl
import packets as pk
import judge as jd
import apply as ap


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("pdf")
    ap_.add_argument("results")
    ap_.add_argument("--glossary", help="reuse a saved glossary.json (e.g. when the new file has no legend sheets)")
    ap_.add_argument("--fake", action="store_true", help="use the rule-only fake judge (no API calls)")
    ap_.add_argument("--out", help="output folder (default: work/<id>/out)")
    ap_.add_argument("--overrides", help="your hand decisions (default: work/<id>/overrides.csv)")
    args = ap_.parse_args()

    # 0. a work folder tied to these exact input files, so a new file never reuses old pages or verdicts
    h = hashlib.sha1()
    for path in (args.pdf, args.results):
        h.update(open(path, "rb").read())
    work = os.path.join("work", h.hexdigest()[:10])
    os.makedirs(work, exist_ok=True)
    args.out = args.out or os.path.join(work, "out")
    args.overrides = args.overrides or os.path.join(work, "overrides.csv")
    os.makedirs(args.out, exist_ok=True)
    if not os.path.exists(args.overrides):               # empty template, ready to fill in by hand
        open(args.overrides, "w", encoding="utf-8").write("id,verdict,note\n")
    print("work folder:", work)
    print("outputs go to:", args.out)
    print("overrides read from:", args.overrides)

    # 1. glossary: from this file's legend sheets, merged with a saved one if given
    g = gl.build_glossary(args.pdf, args.results)
    if args.glossary:
        saved = json.load(open(args.glossary, encoding="utf-8"))
        for key in ("abbreviations", "assembly_codes"):
            g[key] = {**saved[key], **g[key]}
    json.dump(g, open(os.path.join(args.out, "glossary.json"), "w", encoding="utf-8"), indent=1)
    legend = gl.legend_sheet_numbers(args.pdf, args.results)
    print(f"glossary: {len(g['abbreviations'])} abbreviations, {len(g['assembly_codes'])} assembly codes")
    print("legend sheets (reference only, not judged):", ", ".join(sorted(legend)) or "none found")
    if not g["abbreviations"] and not g["assembly_codes"]:
        print("  note: no legend found in this file. Pass --glossary work/<id>/out/glossary.json from an earlier run to reuse one.")

    # 2. evidence packets (crops, nearby text, rule signals)
    packets = pk.build_packets(args.pdf, args.results, g, legend, work_dir=work)
    print(f"{len(packets)} items to judge")

    # 3. judge (cached per item inside the work folder, so reruns are free)
    judge = jd.FakeJudge() if args.fake else jd.GeminiJudge()
    cache = os.path.join(work, "judgements_fake.jsonl" if args.fake else "judgements.jsonl")
    judgements = jd.judge_all(packets, g, judge, cache_path=cache)

    # 4. outputs
    df = ap.apply(args.results, packets, judgements, out_dir=args.out,
                  overrides=ap.load_overrides(args.overrides))
    print(df.verdict.value_counts().to_string())
    print(f"written: {args.out} (results_corrected.json, findings.xlsx, findings.csv)")


if __name__ == "__main__":
    main()

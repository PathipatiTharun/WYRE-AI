# Wyre scope-item audit

Checks every scope item in a results.json against the drawings and removes items the drawing text does not support.

## Setup
    pip install -r requirements.txt
    set GEMINI_API_KEY=your-key        (Windows)   |   export GEMINI_API_KEY=your-key   (Mac/Linux)

## Run
    python run.py drawings.pdf results.json               # real run with Gemini
    python run.py drawings.pdf results.json --fake        # pipeline test, no API calls
    python run.py new.pdf new.json --glossary work/<id>/out/glossary.json   # new sheets without legend pages

## Pipeline
1. glossary.py  - abbreviations and assembly codes from the legend sheets
2. render.py    - page images (rotation handled) and crops around each region
3. context.py   - nearby PDF text around each region, in the same rotated space
4. rules.py     - cheap signals (title block, grid bubble, dimension, heading, code lookup). Signals only, never verdicts
5. packets.py   - one evidence packet per item: crops + text + signals
6. judge.py     - Gemini judges each item; answers cached in work/<id>/judgements.jsonl
7. apply.py     - corrected JSON + findings spreadsheet; overrides.csv (human review) always wins

Helpers (not part of the run): load_items.py (first look at results.json as a table), list_models.py (which Gemini models your key can use)

## Where things go
Every drawings + results pair gets its own folder, work/<id>/ (the id comes from the file contents, so a new file never reuses old answers):

    work/<id>/pages/            page images
    work/<id>/packets/          one crop image per item
    work/<id>/judgements.jsonl  Gemini answers (cached, so reruns are free)
    work/<id>/overrides.csv     your hand decisions for THIS file (id, verdict, note); always wins over Gemini
    work/<id>/out/              results_corrected.json, findings.xlsx, findings.csv, glossary.json

The run prints the folder it used.

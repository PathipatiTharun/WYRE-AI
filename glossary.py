"""Step 3: build a glossary from the legend sheets (abbreviations + assembly type codes).

Deterministic parsing first; the raw legend text is also kept so the LLM judge can
look up anything the parser missed.
"""
import json
import re
import sys
import pymupdf

CODE_RE = re.compile(r"^[A-Z]{1,3}\d+(\.\d+)?[A-Z]{0,2}$")          # BR1, CG1.14, WD42A, XW6.2
TYPE_LABEL_RE = re.compile(r"^(WALL|CEILING|ROOF|FLOOR) TYPE:$")


def page_text(doc, page_number):
    return doc[page_number - 1].get_text()


def parse_abbreviations(text):
    """The abbreviation list alternates CODE / MEANING lines after 'LIST OF ABBREVIATIONS'."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    try:
        start = lines.index("LIST OF ABBREVIATIONS")
    except ValueError:
        return {}
    abbrevs, i = {}, start + 1
    body = lines[start + 1:]
    k = 0
    while k < len(body) - 1:
        code, meaning = body[k], body[k + 1]
        is_code = len(code) <= 6 and code.upper() == code and len(code.split()) == 1
        if is_code and len(code) > 1 and meaning.upper() == meaning and len(meaning) > len(code):
            # meanings that wrap onto a second line end with a comma or "CONTRACTOR"-style word
            while k + 2 < len(body) and (meaning.endswith(",") or meaning.endswith("CONTRACTOR")):
                meaning += " " + body[k + 2]
                k += 1
            abbrevs.setdefault(code, meaning)
            k += 2
        else:
            k += 1
    return abbrevs


def parse_assembly_codes(text, sheet):
    """Assign each code-looking line to the most recent 'X TYPE:' label on the legend sheet."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    codes, current = {}, None
    for i, line in enumerate(lines):
        m = TYPE_LABEL_RE.match(line)
        if m:
            current = m.group(1)
        elif CODE_RE.match(line) and current:
            desc = " ".join(lines[i + 1:i + 10])
            codes.setdefault(line, {"category": f"{current} TYPE", "sheet": sheet, "context": desc[:300]})
    return codes


LEGEND_NAME_WORDS = ("ASSEMBLY TYPES", "GENERAL INFORMATION", "ABBREVIATIONS", "SYMBOLS", "LEGEND")


def is_legend_sheet(sheet, doc):
    """A legend sheet defines codes instead of showing a place in the building.
    Detected by name, or by its text, so it works on files with other sheet numbers."""
    name = sheet["sheet_name"].upper()
    if any(w in name for w in LEGEND_NAME_WORDS):
        return True
    text = page_text(doc, sheet["page_number"]).upper()
    return "LIST OF ABBREVIATIONS" in text or len(re.findall(r"(WALL|CEILING|ROOF|FLOOR) TYPE:", text)) >= 5


def legend_sheet_numbers(pdf_path, results_path):
    doc = pymupdf.open(pdf_path, encoding="utf-8")
    sheets = json.load(open(results_path, encoding="utf-8"))["drawings_processing_results"]
    return {s["sheet_number"] for s in sheets if is_legend_sheet(s, doc)}


def build_glossary(pdf_path, results_path):
    sheets = json.load(open(results_path, encoding="utf-8"))["drawings_processing_results"]
    doc = pymupdf.open(pdf_path, encoding="utf-8")
    glossary = {"abbreviations": {}, "assembly_codes": {}, "raw_legend_text": {}}
    for s in sheets:
        if not is_legend_sheet(s, doc):
            continue
        text = page_text(doc, s["page_number"])
        glossary["raw_legend_text"][s["sheet_number"]] = text
        glossary["abbreviations"].update(parse_abbreviations(text))
        glossary["assembly_codes"].update(parse_assembly_codes(text, s["sheet_number"]))
    return glossary


if __name__ == "__main__":
    g = build_glossary(sys.argv[1], sys.argv[2])
    json.dump(g, open("glossary.json", "w", encoding="utf-8"), indent=1)
    print(len(g["abbreviations"]), "abbreviations,", len(g["assembly_codes"]), "assembly codes")
    for c in ["OFCI", "CG", "BR", "FOS", "IRR", "FDC", "EM", "PB", "FO", "SD", "SS", "ADA"]:
        print(f"  {c:5} -> {g['abbreviations'].get(c)}")
    for c in ["CG1.14", "BR1", "WD42A", "FB1", "RW4", "XW6", "FG5.1"]:
        print(f"  {c:6} -> {g['assembly_codes'].get(c, {}).get('category')}")

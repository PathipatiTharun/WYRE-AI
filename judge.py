"""Step 7: the LLM judge. One call per scope item: image of its regions + text evidence
+ rule signals + matching legend definitions -> structured verdict.

Every answer is cached in judgements.jsonl, so a crashed or interrupted run resumes
without paying for the same item twice.
"""
import json
import os
import re
from typing import List, Literal

from pydantic import BaseModel, Field

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

CATEGORIES = Literal[
    "supported",                 # RIGHT: the text really calls for this work
    "title_block",               # firm name, phone, address, URL, sheet info
    "grid_bubble",               # column/grid line labels
    "room_label",                # a room name only, no work stated
    "dimension_or_annotation",   # dimensions, F.O.S., TYP., elevation labels
    "legend_or_heading",         # legend titles, 'NOTES:', schedule headers
    "code_misread",              # abbreviation / assembly code read as the wrong thing
    "wrong_trade",               # real work, but not the work this item describes
    "note_does_not_support",     # a general note that does not call for this work
    "other",
]


class Verdict(BaseModel):
    verdict: Literal["RIGHT", "WRONG"]
    category: CATEGORIES
    reason: str = Field(description="One or two plain sentences an estimator could check")
    bad_regions: List[int] = Field(description="Evidence numbers that do NOT support the item (empty if none)")
    confidence: float = Field(ge=0, le=1)


PROMPT = """You are checking construction drawing take-off results for a general contractor.

A scope item is RIGHT if at least one piece of evidence on the drawing genuinely calls for the work
the item describes. It is WRONG if none of the evidence supports it as written.

Common errors:
- Title block text (architect name, phone, address, website) read as work.
- Grid bubbles: letters/numbers in circles at the edge of a plan are column lines, not products.
- Room labels: a room name alone (e.g. ELECTRICAL 118) does not mean that trade works there.
  A room finish tag that lists finish codes (e.g. "KITCHEN B GB-1 P-1 RB-1 LVT-1") DOES support those finishes.
- Dimensions and annotations (7'-11 3/8", F.O.S., TYP.) are not work.
- Codes read the wrong way: the same letters mean different things on different sheets.
  Use the legend definitions below. Assembly codes like CG1.14 are ceiling types, WD42A is a wall type.
- Short tags are often REAL products keyed to a schedule (e.g. TS1 tub surround, plant keys like 'Ec').
  Never mark something wrong just because it is short.
- General notes can be real scope, but only for the work they actually describe.

Sheet: {sheet_number} - {sheet_name} ({discipline})
Scope package: {scope_package}
Item: {bid_item}
Subheading: {subheading}
Total regions tagged: {n_regions_total} (a sample is shown)

Evidence (numbered left to right in the image; the red box marks the exact text):
{evidence}

Legend definitions found for codes in the evidence:
{definitions}
Note: the abbreviation list comes from the ARCHITECTURAL legend. On civil, landscape or electrical
sheets the same letters may mean something else (e.g. SS = sanitary sewer, FO = fiber optic on civil).

Judge the item. List the evidence numbers that do not support it in bad_regions.
"""


def definitions_for(packet, glossary):
    tokens = set()
    for e in packet["evidence"]:
        tokens.update(re.findall(r"[A-Z][A-Z0-9.\-]{0,7}", e["text"].upper()))
    lines = []
    for t in sorted(tokens):
        t = t.rstrip(".")
        if t in glossary["assembly_codes"]:
            a = glossary["assembly_codes"][t]
            lines.append(f"- {t}: {a['category']} (legend {a['sheet']}): {a['context'][:150]}")
        elif t in glossary["abbreviations"]:
            lines.append(f"- {t}: {glossary['abbreviations'][t]}")
    return "\n".join(lines) or "(none found)"


def build_prompt(packet, glossary):
    ev = "\n".join(
        f"[{e['n']}] text: {e['text']!r}\n    signals: {', '.join(e['signals']) or 'none'}\n"
        f"    nearby text: {e['nearby_text'][:300]}"
        for e in packet["evidence"]
    )
    fields = {k: v for k, v in packet.items() if k not in ("evidence", "image")}
    return PROMPT.format(evidence=ev, definitions=definitions_for(packet, glossary), **fields)


class GeminiJudge:
    """Calls Gemini. If the chosen model is busy (503) or gone (404), it moves on to the next
    Flash model your key can use and stays there once one works."""

    BUSY = ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")

    def __init__(self, model=MODEL):
        from google import genai
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.models = [m.strip() for m in model.split(",") if m.strip()]
        try:                                             # add every other Flash model this key can use
            for m in self.client.models.list():
                name = m.name.replace("models/", "")
                actions = getattr(m, "supported_actions", None) or []
                if ("flash" in name and "generateContent" in actions and name not in self.models
                        and not any(x in name for x in ("image", "tts", "audio", "live", "embedding"))):
                    self.models.append(name)
        except Exception as e:
            print("    could not list models:", e)
        print("models to try, in order:", ", ".join(self.models))
        self.current = 0

    @property
    def model(self):
        return self.models[self.current]

    def _call(self, model, image, prompt):
        from google.genai import types
        resp = self.client.models.generate_content(
            model=model,
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=Verdict, temperature=0),
        )
        if resp.parsed is not None:
            return resp.parsed
        return Verdict.model_validate_json(resp.text)    # fallback if the SDK did not parse it

    def __call__(self, prompt, image_path):
        import time
        from google.genai import types
        image = types.Part.from_bytes(data=open(image_path, "rb").read(), mime_type="image/png")
        last = None
        for rnd in range(3):                             # up to 3 rounds over all models
            for i in list(range(self.current, len(self.models))) + list(range(0, self.current)):
                try:
                    v = self._call(self.models[i], image, prompt)
                    if i != self.current:
                        print(f"    switched to {self.models[i]}")
                        self.current = i
                    return v
                except Exception as e:
                    last = e
                    msg = str(e)
                    if any(c in msg for c in self.BUSY) or "404" in msg or "NOT_FOUND" in msg:
                        print(f"    {self.models[i]} unavailable ({msg[:40]}...), trying next model")
                        continue
                    raise                                # a real error: report it
            wait = 30 * (rnd + 1)
            print(f"    all models busy, waiting {wait}s...")
            time.sleep(wait)
        raise last


class FakeJudge:
    """Stand-in used to test the pipeline without an API key. Uses rule signals only.
    Its verdicts are NOT the real findings."""

    def __call__(self, prompt, image_path):
        strong = ["title_block_text", "legend_or_heading", "dimension_or_annotation"]
        if any(s in prompt for s in strong):
            return Verdict(verdict="WRONG", category="other", reason="[fake] strong rule signal",
                           bad_regions=[1], confidence=0.3)
        return Verdict(verdict="RIGHT", category="supported", reason="[fake] no strong signal",
                       bad_regions=[], confidence=0.3)


def judge_all(packets, glossary, judge, cache_path="judgements.jsonl"):
    done = {}
    if os.path.exists(cache_path):
        for line in open(cache_path, encoding="utf-8"):
            row = json.loads(line)
            if row["verdict"] != "REVIEW":               # failed items are retried on the next run
                done[row["id"]] = row
    with open(cache_path, "a", encoding="utf-8") as f:
        for i, p in enumerate(packets, 1):
            if p["id"] in done:
                continue
            try:
                v = judge(build_prompt(p, glossary), p["image"])
                row = {"id": p["id"], **v.model_dump(), "model": getattr(judge, "model", "fake")}
            except Exception as e:                       # keep going; failed items go to manual review
                row = {"id": p["id"], "verdict": "REVIEW", "category": "other",
                       "reason": f"judge error: {e}", "bad_regions": [], "confidence": 0.0, "model": "error"}
            f.write(json.dumps(row) + "\n")
            f.flush()
            done[p["id"]] = row
            print(f"[{i}/{len(packets)}] {p['sheet_number']} | {p['bid_item'][:50]} -> {row['verdict']}")
            if row["verdict"] == "REVIEW":
                print("    ERROR:", row["reason"][:300])
    return done

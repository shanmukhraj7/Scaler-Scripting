# PII Redaction Pipeline

Reads the Red Herring Prospectus **DOCX**, finds personally identifiable information, swaps each value for a realistic fake, and writes a **DOCX that keeps the original tables and headings**. The same original always becomes the same fake.

`input/Enterprise Data - Assignment.docx` is the brief. Do not redact it. The only input is `input/Red Herring Prospectus.docx`.

## What it does

- Detects names, emails, phones, companies, addresses, SSNs, cards, DOBs, IPs, plus Indian PAN / Aadhaar
- Replaces hits with Faker values (`en_IN`) instead of `XXXX` masks
- Keeps a replacement map so `Kushal Subbayya Hegde` does not become three different people
- Writes fakes back into the same Word structure (paragraphs, tables, headers/footers)

## Setup

Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

`en_core_web_md` / `en_core_web_lg` work too. Point at them with `PII_SPACY_MODEL`.

## Run

From the repo root:

```bash
python -m src.main
```

Custom paths:

```bash
python -m src.main \
  --input "input/Red Herring Prospectus.docx" \
  --output output/redacted_prospectus.docx
```

Skip the labeled-subset score:

```bash
python -m src.main --skip-eval
```

## Outputs

| File | What it is |
|---|---|
| `output/redacted_prospectus.docx` | Same layout as the source, with PII replaced |
| `output/replacement_mapping.json` | Original → fake, with entity type |
| `output/detected_entities.json` | Every span the detector kept |
| `output/evaluation_metrics.json` | Precision / recall / F1 / accuracy on `eval/gold_subset.json` |

## Architecture

```
DOCX → extractor (walk blocks) → detector → replacer → exporter (write back in place)
                                 ↘ evaluator (labeled cover/intro strings)
```

| Module | Role |
|---|---|
| `src/extractor.py` | Walk paragraphs, table cells, headers/footers |
| `src/detector.py` | Regex + spaCy NER + Presidio, then overlap merge |
| `src/faker_utils.py` | Typed fake generators |
| `src/replacer.py` | Consistent map, whitespace-tolerant replace |
| `src/exporter.py` | Open the source DOCX and put fakes in the same places |
| `src/evaluator.py` | Entity-level scores against a gold subset |
| `src/config.py` | Paths, thresholds, allowlists |
| `src/models.py` | Shared types |

## Why these libraries

- **python-docx** — read and write the real Word file so tables survive
- **spaCy** — PERSON / ORG / GPE on long legal prose
- **Presidio** — cards (Luhn), SSN, email, IP
- **Faker** — realistic substitutes, seeded so reruns match
- **pytest** — regex, mapping consistency, table round-trip

Regex alone misses names. spaCy alone is weak on emails/phones/cards. Presidio NER on a full prospectus is slow and noisy, so Presidio is used only for structured validators. The merge step keeps the strongest span when they overlap.

## Design choices

- DOCX in, DOCX out. PDF extraction flattened tables and split emails; reviewers would see a dump.
- Walk order is body (paragraphs + tables in document order), then unlinked headers/footers. Extract and write use the same walk.
- Dates are not all PII. Filing dates stay. Only DOB-like context is redacted.
- `India`, `SEBI`, `BSE`, `Companies Act` are allowlisted.
- Company hits usually need a legal hint (`Limited`, `Trust`, `LLP`, …).
- Replacement is case-insensitive and treats extra spaces as the same name.

## Limitations

- A paragraph with mixed bold/italic may flatten to one run. Table structure and heading styles stay.
- Images and QR codes are not redacted.
- `en_core_web_sm` misses some names and orgs that a larger model would catch.
- Gold labels are a cover/intro subset, not every block in the file.

## Tests

```bash
python -m pytest tests/ -q
```

## Config knobs

| Env var | Meaning |
|---|---|
| `PII_INPUT_DIR` | Input folder |
| `PII_OUTPUT_DIR` | Output folder |
| `PII_INPUT_NAME` | Default DOCX filename |
| `PII_SPACY_MODEL` | spaCy model name |
| `PII_FAKER_LOCALE` | Faker locale |
| `PII_FAKER_SEED` | Reproducible fakes |
| `PII_LOG_LEVEL` | `INFO` / `DEBUG` |

## Extending

Add a `PIIType`, a regex or Presidio mapping, a Faker generator, and a gold example. Overlap priority already lives in `TYPE_PRIORITY`.

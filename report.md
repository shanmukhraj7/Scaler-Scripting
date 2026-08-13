# Evaluation Report — PII Redaction Pipeline

Source document: `input/Red Herring Prospectus.docx` (KSH International Limited).
The assignment file is the brief only. It is not redacted.
Run date: 13 August 2026.

## Detection strategy

The pipeline is hybrid. No single method covers this prospectus.

**Regex** handles structured values: email, Indian mobiles and `+91` landlines, SSN, Luhn-checked cards, IPv4/IPv6, PAN, Aadhaar, URLs, and PIN-centred address windows.

**spaCy NER (`en_core_web_sm`)** finds `PERSON`, `ORG`, `GPE`, `LOC`. That is how promoter names and company strings get caught.

**Presidio** is used for email, credit cards (Luhn), SSN, IP, and URL — not as a second NER pass. Full Presidio NER duplicated spaCy, tagged legal jargon as organisations, and was too slow.

Overlapping spans are resolved by type priority (email/phone/card beat person/org), then length, then score.

Precision guards: SEBI/BSE/Companies Act allowlist, org legal-suffix hints, DOB-only dates, skip single-token persons.

## Replacement strategy

Faker `en_IN`, seed `42`. Each `(normalized text, entity type)` maps to one fake for the whole file. Replacement is case-insensitive and treats extra spaces as the same string.

The exporter opens the **original DOCX** and writes those fakes into the same paragraphs and table cells, so the cover table stays a table.

## Evaluation methodology

There is no official gold file for the whole prospectus. Scoring unlabeled blocks would be invented precision.

Cover/intro strings were labeled by hand in `eval/gold_subset.json` (82 entities): contacts, promoters, lead managers, emails, phones, office addresses.

A prediction is a true positive if **type** and normalized text match or one contains the other. Word blocks are not PDF pages, so page number is ignored.

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2PR / (P + R)
- Accuracy = TP / (TP + FP + FN)

True negatives are not counted. Almost every token is “not PII”, so token accuracy would look excellent and mean nothing.

`python -m src.main` writes `output/evaluation_metrics.json`.

## Results (labeled subset)

Scored only on DOCX blocks that contain a labeled name, email, phone, company, or address — not the whole file. Gold is incomplete even on those blocks, so extra real names/orgs count as false positives and **precision looks worse than the system is**. Recall is the fairer number here.

| | Precision | Recall | F1 | Accuracy | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Overall** | **0.210** | **0.744** | **0.328** | **0.196** | 61 | 229 | 21 |
| Email | 0.46 | 1.00 | 0.63 | 0.46 | 10 | 12 | 0 |
| Phone | 0.57 | 0.50 | 0.53 | 0.50 | 4 | 3 | 4 |
| Person | 0.15 | 0.83 | 0.25 | 0.14 | 19 | 109 | 4 |
| Organization | 0.18 | 0.77 | 0.29 | 0.17 | 20 | 90 | 6 |
| Address | 0.50 | 0.29 | 0.36 | 0.22 | 2 | 2 | 5 |
| Location | 0.31 | 0.67 | 0.42 | 0.27 | 4 | 9 | 2 |
| URL | 0.33 | 1.00 | 0.50 | 0.33 | 2 | 4 | 0 |

Email recall is 100% — the Word cell already has `cs.connect@kshinternational.com` intact. Person/org recall is strong; precision is punished by unlabeled PII on the same pages. SSN, card, and IP were not in the gold set; unit tests still cover them.

## Challenges

1. **PDF was the wrong input.** Extracting the PDF flattened 76 tables and split emails. The company already provided a DOCX; that is what we redact.
2. **Legal NER noise.** spaCy tags `Cap Price` and `OFFER` as people or orgs. Allowlists and legal-suffix filters matter.
3. **Dates are not DOB.** Redacting `December 10, 2025` would destroy a prospectus.
4. **Mixed runs.** Replacing inside a paragraph may flatten bold/italic on that paragraph. Tables and heading styles stay.
5. **Presidio NER vs validators.** Pattern-only Presidio is the production trade-off.

## Assumptions

- Issuer, promoters, lead managers, registrars, and their contacts are in scope. Stock exchanges and statutes are not.
- `India` as a jurisdiction word is not a mailing address.
- Consistent fakes matter more than keeping the same character length.
- A structured Word file matters more than cloning the PDF pixel for pixel.
- A labeled subset is an honest eval.

## Scalability

Walking a DOCX is cheap. Detection is the cost (spaCy per block + Presidio patterns). Batch with `nlp.pipe` if the file grows. Keep Presidio on structured entities only.

## Extending to more PII types

1. Add a `PIIType`
2. Add a regex or a Presidio entity name
3. Add a Faker generator in `FakeValueFactory`
4. Put the type in `TYPE_PRIORITY`
5. Add a gold example and a unit test

## Full-run snapshot

After `python -m src.main` on the prospectus DOCX:

- Input: `input/Red Herring Prospectus.docx`
- Blocks walked: 4635 (same count on write-back)
- Spans kept: 779
- Unique replacements: 315
- Output structure: **76 tables, 1006 paragraphs, 85 sections** (matches the source)
- Cover table: `Sarthak Malvadkar` → `Udant Dewan`; email and phone replaced in the same cell
- Output: `output/redacted_prospectus.docx`
- Mapping: `output/replacement_mapping.json`
- Tests: 14 passed (`python -m pytest tests/ -q`)

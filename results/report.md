# MedBurden evaluation

30 made-up medication lists (6 as photos). Labels written by hand; see tests/eval_set/cases.json and eval/verify_10.md.

**Run conditions:** extraction = {'llm:openai': 30}; RxNav = NOT reachable (cache + local brand map only); LLM = openai · gpt-6-luna; OCR = Tesseract not installed. Photo reading without an AI key needs the free Tesseract OCR program. Install it with `brew install tesseract` (Mac) or `sudo apt install tesseract-ocr` (Linux). On Streamlit Cloud it is installed from packages.txt. You can also type or paste the list instead..

| System | Drug extraction (precision / recall) | Ingredient match (exactly right) | ACB total exact | Beers precision | Beers recall |
|---|---|---|---|---|---|
| MedBurden (rules + tables) | 100% / 100% | 99% (90/91 real drugs matched with exactly the right ingredients) | 100% | 100% | 100% |
| LLM only (gpt-6-luna, no tables) | n/a | 100% | 37% | 96% | 81% |

- Fictional drug names correctly left unmatched: **2/2** (wrongly matched: 0).
- Beers counts (MedBurden): {'tp': 63, 'fp': 0, 'fn': 0}.
- Medicines that are unmatched or need review are never scored. MedBurden does not guess.

## Cases with any error
- none

## Caveats
- The same team wrote the tables and the labels, so this measures whether the pipeline applies the cited rules correctly. It does not independently validate the tables. Spot-check the labels with eval/verify_10.md.
- 30 cases is small. Treat these as smoke-test numbers, not clinical accuracy.

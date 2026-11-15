# MedBurden evaluation

31 made-up medication lists (0 as photos). Labels written by hand; see tests/eval_set/cases.json and eval/verify_10.md.

**Run conditions:** extraction = {'llm:openai': 31}; RxNav = NOT reachable (cache + local brand map only); LLM = openai · gpt-6-luna; OCR = Tesseract not installed. Photo reading without an AI key needs the free Tesseract OCR program. Install it with `brew install tesseract` (Mac) or `sudo apt install tesseract-ocr` (Linux). On Streamlit Cloud it is installed from packages.txt. You can also type or paste the list instead.

| System | Drug extraction (precision / recall) | Ingredient match (exactly right) | ACB total exact | Beers precision | Beers recall |
|---|---|---|---|---|---|
| MedBurden (rules + tables) | 99% / 99% | 87% (79/91 real drugs matched with exactly the right ingredients) | 97% | 100% | 86% |
| LLM only (gpt-6-luna, no tables) | n/a | 97% | 29% | 90% | 80% |

- Fictional drug names correctly left unmatched: **2/2** (wrongly matched: 0).
- Beers counts (MedBurden): {'tp': 82, 'fp': 0, 'fn': 13}.
- Medicines that are unmatched or need review are never scored. MedBurden does not guess.

## Cases with any error
- h05 (text, llm:openai): extracted ['Megace', 'Premarin', 'DDAVP'], statuses ['needs_review', 'matched', 'matched']; ACB 0 vs gold 0; missed ['megestrol|all']; extra []
- h06 (text, llm:openai): extracted ['Demerol', 'Toradol', 'Singulair'], statuses ['matched', 'needs_review', 'matched']; ACB 2 vs gold 2; missed ['ketorolac|all']; extra []
- h10 (text, llm:openai): extracted ['Thorazine', 'Compazine', 'Pexeva'], statuses ['matched', 'matched', 'needs_review']; ACB 3 vs gold 6; missed ['paroxetine|all', 'paroxetine|dementia']; extra []
- h12 (text, llm:openai): extracted ['Librium', 'Zyloprim', 'Colcrys'], statuses ['needs_review', 'matched', 'matched']; ACB 1 vs gold 1; missed ['chlordiazepoxide|all', 'chlordiazepoxide|dementia', 'chlordiazepoxide|falls']; extra []
- h13 (text, llm:openai): extracted ['Cordarone', 'Tenex', 'Altace'], statuses ['needs_review', 'needs_review', 'matched']; ACB 0 vs gold 0; missed ['amiodarone|all', 'guanfacine|all']; extra []
- h21 (text, llm:openai): extracted ['doxazocin', 'Tenex', 'Lopid'], statuses ['matched', 'needs_review', 'matched']; ACB 0 vs gold 0; missed ['guanfacine|all']; extra []
- h22 (text, llm:openai): extracted ['Luminal', 'Parafon Forte', 'Zyloprim'], statuses ['needs_review', 'needs_review', 'matched']; ACB 0 vs gold 0; missed ['chlorzoxazone|all', 'phenobarbital|all', 'phenobarbital|falls']; extra []

## Caveats
- The same team wrote the tables and the labels, so this measures whether the pipeline applies the cited rules correctly. It does not independently validate the tables. Spot-check the labels with eval/verify_10.md.
- 30 cases is small. Treat these as smoke-test numbers, not clinical accuracy.

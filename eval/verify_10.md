# Answer-key check: 10 eval cases

For each drug: the expected ACB score and Beers flags, next to the line in the source they come from.
Tick each box after checking it against the PDFs. Sources:
- ACB: ACB scale 2012 update PDF (hii.iu.edu/resources/anticholinergic-cognitive-burden-scale.pdf). Blocks: score 1, score 2, score 3, and 'reviewed but not added'.
- Beers: 2023 AGS Beers Criteria, J Am Geriatr Soc 2023;71:2052-2081 (open access: pmc.ncbi.nlm.nih.gov/articles/PMC12478568).
  Table 2 = drugs to avoid in older adults; Table 3 = drug-disease (dementia, falls); Table 7 = strong anticholinergics.
- Labeling policy: a Beers flag is expected when the ingredient is listed in Table 2 (any patient), or in a Table 3 row
  for a condition the patient has. Dose exemptions printed in Beers (doxepin <= 6 mg/day, digoxin <= 0.125 mg/day,
  immediate-release nifedipine only) are applied. The ACB total sums unique ingredients.

## c01: age 82, conditions: dementia

```
Tylenol PM 2 caplets at bedtime
Lisinopril 10 mg once daily
Atorvastatin 20 mg at night
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Tylenol PM | acetaminophen | 0 — not on the ACB scale | — | [ ] |
| Tylenol PM | diphenhydramine | **3** — score-3 list: "Diphenhydramine (Benadryl)"  | **all** — Table 2: Anticholinergics > First-generation antihistamines<br>**dementia** — Table 3: Dementia or cognitive impairment > Anticholinergics (see Table 7: Antihistamines (first-generation)) | [ ] |
| Lisinopril | lisinopril | 0 — not on the ACB scale | — | [ ] |
| Atorvastatin | atorvastatin | 0 — not on the ACB scale | — | [ ] |

**Expected ACB total: 3** · Expected Beers flags: diphenhydramine|all, diphenhydramine|dementia

## c03: age 74, conditions: none

```
Advil PM 1 tab nightly
Advil 200 mg as needed for pain
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Advil PM | ibuprofen | 0 — not on the ACB scale | **all** — Table 2: Pain medications > Non-COX-selective NSAIDs, oral / Indomethacin, ketorolac | [ ] |
| Advil PM | diphenhydramine | **3** — score-3 list: "Diphenhydramine (Benadryl)"  | **all** — Table 2: Anticholinergics > First-generation antihistamines | [ ] |
| Advil | ibuprofen | 0 — not on the ACB scale | **all** — Table 2: Pain medications > Non-COX-selective NSAIDs, oral / Indomethacin, ketorolac | [ ] |

**Expected ACB total: 3** · Expected Beers flags: ibuprofen|all, diphenhydramine|all

## c05: age 86, conditions: dementia

```
Amitriptyline 25 mg at bedtime
Furosemide 40 mg every morning
Metoprolol tartrate 25 mg twice daily
Warfarin 5 mg daily
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Amitriptyline | amitriptyline | **3** — score-3 list: "Amitriptyline (Elavil)"  | **all** — Table 2: Central nervous system > Antidepressants with strong anticholinergic activity, alone or in combination<br>**dementia** — Table 3: Dementia or cognitive impairment > Anticholinergics (see Table 7: Antidepressants) | [ ] |
| Furosemide | furosemide | **1** — score-1 list: "Furosemide (Lasix)"  | — | [ ] |
| Metoprolol tartrate | metoprolol | **1** — score-1 list: "Metoprolol (Lopressor; Toprol)"  | — | [ ] |
| Warfarin | warfarin | **1** — score-1 list: "Warfarin (Coumadin)"  | **all** — Table 2: Antithrombotics > Warfarin / Rivaroxaban | [ ] |

**Expected ACB total: 6** · Expected Beers flags: amitriptyline|all, amitriptyline|dementia, warfarin|all

## c09: age 80, conditions: falls

```
Norco 5/325 every 6 hrs as needed
Xanax 0.5 mg twice daily
Flexeril 10 mg at bedtime
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Norco | hydrocodone | 0 — not on the ACB scale | **falls** — Table 3: History of falls or fractures > Opioids (class membership per WHO ATC) | [ ] |
| Norco | acetaminophen | 0 — not on the ACB scale | — | [ ] |
| Xanax | alprazolam | **1** — score-1 list: "Alprazolam (Xanax)"  | **all** — Table 2: Central nervous system > Benzodiazepines<br>**falls** — Table 3: History of falls or fractures > Benzodiazepines (class membership per WHO ATC) | [ ] |
| Flexeril | cyclobenzaprine | **2** — score-2 list: "Cyclobenzaprine (Flexeril)"  | **all** — Table 2: Pain medications > Skeletal muscle relaxants<br>**falls** — Table 3: History of falls or fractures > Anticholinergics (see Table 7: Skeletal muscle relaxants) | [ ] |

**Expected ACB total: 3** · Expected Beers flags: alprazolam|all, cyclobenzaprine|all, alprazolam|falls, hydrocodone|falls, cyclobenzaprine|falls

## c12: age 78, conditions: none

```
NyQuil 30 mL at bedtime
Prednisone 10 mg daily
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| NyQuil | acetaminophen | 0 — not on the ACB scale | — | [ ] |
| NyQuil | dextromethorphan | 0 — not on the ACB scale | — | [ ] |
| NyQuil | doxylamine | **3** — score-3 list: "Doxylamine (Unisom)"  | **all** — Table 2: Anticholinergics > First-generation antihistamines | [ ] |
| Prednisone | prednisone | **1** — score-1 list: "Prednisone (Deltasone; Sterapred)"  | — | [ ] |

**Expected ACB total: 4** · Expected Beers flags: doxylamine|all

## c14: age 81, conditions: dementia, falls

```
Paroxetine 20 mg daily
Trazodone 50 mg at bedtime
Lorazepam 0.5 mg as needed
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Paroxetine | paroxetine | **3** — score-3 list: "Paroxetine (Paxil)"  | **all** — Table 2: Central nervous system > Antidepressants with strong anticholinergic activity, alone or in combination<br>**dementia** — Table 3: Dementia or cognitive impairment > Anticholinergics (see Table 7: Antidepressants)<br>**falls** — Table 3: History of falls or fractures > Anticholinergics (see Table 7: Antidepressants) | [ ] |
| Trazodone | trazodone | **1** — score-1 list: "Trazodone (Desyrel)"  | — | [ ] |
| Lorazepam | lorazepam | 0 — not on the ACB scale | **all** — Table 2: Central nervous system > Benzodiazepines<br>**dementia** — Table 3: Dementia or cognitive impairment > Benzodiazepines (class membership per WHO ATC)<br>**falls** — Table 3: History of falls or fractures > Benzodiazepines (class membership per WHO ATC) | [ ] |

**Expected ACB total: 4** · Expected Beers flags: paroxetine|all, paroxetine|dementia, paroxetine|falls, lorazepam|all, lorazepam|dementia, lorazepam|falls

## c16: age 85, conditions: none

```
Digoxin 0.25 mg daily
Furosemide 20 mg daily
Apixaban 5 mg twice daily
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Digoxin | digoxin | **1** — score-1 list: "Digoxin (Lanoxin)"  | **all** — Table 2: Cardiovascular > Digoxin (dose rule: gt:0.125:mg) | [ ] |
| Furosemide | furosemide | **1** — score-1 list: "Furosemide (Lasix)"  | — | [ ] |
| Apixaban | apixaban | 0 — not on the ACB scale | — | [ ] |

**Expected ACB total: 2** · Expected Beers flags: digoxin|all

## c18: age 72, conditions: none

```
Doxepin 3 mg at bedtime
Losartan 50 mg daily
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Doxepin | doxepin | **3** — score-3 list: "Doxepin (Sinequan)"  | none expected: Table 2 Central nervous system > Antidepressants with strong anticholinergic activity, alone or in combination applies only when above 6 mg | [ ] |
| Losartan | losartan | 0 — not on the ACB scale | — | [ ] |

**Expected ACB total: 3** · Expected Beers flags: none

## c24: age 84, conditions: dementia, falls

```
Ambien 10mg qhs
Klonopin 0.5 mg bid
Tramadol 50 mg q6h prn
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Ambien | zolpidem | 0 — not on the ACB scale | **all** — Table 2: Central nervous system > Nonbenzodiazepine benzodiazepine receptor agonist hypnotics (Z-drugs)<br>**dementia** — Table 3: Dementia or cognitive impairment > Z-drugs (class membership per WHO ATC)<br>**falls** — Table 3: History of falls or fractures > Z-drugs (class membership per WHO ATC) | [ ] |
| Klonopin | clonazepam | 0 — not on the ACB scale | **all** — Table 2: Central nervous system > Benzodiazepines<br>**dementia** — Table 3: Dementia or cognitive impairment > Benzodiazepines (class membership per WHO ATC)<br>**falls** — Table 3: History of falls or fractures > Benzodiazepines (class membership per WHO ATC) | [ ] |
| Tramadol | tramadol | 0 — not on the ACB scale | **falls** — Table 3: History of falls or fractures > Opioids (class membership per WHO ATC) | [ ] |

**Expected ACB total: 0** · Expected Beers flags: zolpidem|all, zolpidem|dementia, zolpidem|falls, clonazepam|all, clonazepam|dementia, clonazepam|falls, tramadol|falls

## c25: age 78, conditions: dementia

```
Sinemet 25/100 three times daily
Benztropine 1 mg twice daily
Amantadine 100 mg twice daily
```

| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |
|---|---|---|---|---|
| Sinemet | carbidopa | 0 — not on the ACB scale | — | [ ] |
| Sinemet | levodopa | 0 — not on the ACB scale | — | [ ] |
| Benztropine | benztropine | **3** — score-3 list: "Benztropine (Cogentin)"  | **all** — Table 2: Anticholinergics > Antiparkinsonian agents<br>**dementia** — Table 3: Dementia or cognitive impairment > Anticholinergics (see Table 7: Antiparkinsonian agents) | [ ] |
| Amantadine | amantadine | **2** — score-2 list: "Amantadine (Symmetrel)"  | — | [ ] |

**Expected ACB total: 5** · Expected Beers flags: benztropine|all, benztropine|dementia

## Label change log

No labels were changed in v2. Before v2, a script checked every label against the cited tables (scorer run on
the gold ingredients); all 30 cases agreed. If you change a label, add a line here: case, old value,
new value, why, and the source line.

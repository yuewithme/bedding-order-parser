# Gate 3A-C.2 Size Shadow Calibration Report

## 1. Scope

This gate only calibrates the shadow comparison for `规格`. It does not change Gate 2D production parsing, official 20-field JSON, dictionaries, or any non-size shadow field logic.

## 2. Size Status Before And After

| Status | Before | After |
|---|---:|---:|
| exact_match | 0 | 0 |
| equivalent_match | 0 | 40 |
| dictionary_more_specific | 0 | 0 |
| partial_match | 0 | 6 |
| ambiguous | 0 | 0 |
| conflict | 46 | 0 |
| dictionary_no_match | 3 | 3 |
| source_not_provided | 0 | 0 |

Result: `规格` comparison records remain 49; conflict count is 0.

## 3. Original 46 Conflict Reclassification

| New Status | Count |
|---|---:|
| equivalent_match | 40 |
| partial_match | 6 |

| # | PI File | Line | Source Cells | Python Value | Shadow Candidate | New Status | Reason |
|---:|---|---:|---|---|---|---|---|
| 1 | 20251231 被套 Proforma Invoice（11行）.xlsx | 1 | C13, A13, B13, D13, E13 | 260*340+15cm | 260*340 | partial_match | Source dimensions match the official size, but structural extension evidence was not provided, not safely extractable... |
| 2 | 20251231 被套 Proforma Invoice（11行）.xlsx | 2 | C14, A14, B14, D14, E14 | 273*205cm | 273*205 | equivalent_match | Source size converts to the official normalized size. |
| 3 | 20251231 被套 Proforma Invoice（11行）.xlsx | 3 | C15, A15, B15, D15, E15 | 240*250cm | 240*250 | equivalent_match | Source size converts to the official normalized size. |
| 4 | 20251231 被套 Proforma Invoice（11行）.xlsx | 4 | C16, A16, B16, D16, E16 | 245*215+50cm | 245*215+50cm | equivalent_match | Source size converts to the official normalized size. |
| 5 | 20251231 被套 Proforma Invoice（11行）.xlsx | 5 | C17, A17, B17, D17, E17 | 240*290+15cm | 240*290 | partial_match | Source dimensions match the official size, but structural extension evidence was not provided, not safely extractable... |
| 6 | 20251231 被套 Proforma Invoice（11行）.xlsx | 6 | C18, A18, B18, D18, E18 | 250*155cm | 250*155 | equivalent_match | Source size converts to the official normalized size. |
| 7 | 20251231 被套 Proforma Invoice（11行）.xlsx | 7 | C19, A19, B19, D19, E19 | 240*250cm | 240*250 | equivalent_match | Source size converts to the official normalized size. |
| 8 | 20251231 被套 Proforma Invoice（11行）.xlsx | 8 | C20, A20, B20, D20, E20 | 240*200+15cm | 240*200 | partial_match | Source dimensions match the official size, but structural extension evidence was not provided, not safely extractable... |
| 9 | 20251231 被套 Proforma Invoice（11行）.xlsx | 9 | C21, A21, B21, D21, E21 | 273*225cm | 273*225 | equivalent_match | Source size converts to the official normalized size. |
| 10 | 20251231 被套 Proforma Invoice（11行）.xlsx | 10 | C22, A22, B22, D22, E22 | 251*299cm | 251*299 | equivalent_match | Source size converts to the official normalized size. |
| 11 | 20251231 被套 Proforma Invoice（11行）.xlsx | 11 | C23, A23, B23, D23, E23 | 250*278+50cm | 250*278+50cm | equivalent_match | Source size converts to the official normalized size. |
| 12 | 3402510MG10094 Canasin Proforma Invoice-Blooming_Caption by Hyatt KABUTOCHO-Oct.26.2025 V2.xlsx | 1 | C11, A11, B11, D11, F11, I11 | 270*180cm | 270*180 | equivalent_match | Source size converts to the official normalized size. |
| 13 | 3402510MG10094 Canasin Proforma Invoice-Blooming_Caption by Hyatt KABUTOCHO-Oct.26.2025 V2.xlsx | 2 | C12, A12, B12, F12, I12 | 270*210cm | 270*210 | equivalent_match | Source size converts to the official normalized size. |
| 14 | 3402510MG10094 Canasin Proforma Invoice-Blooming_Caption by Hyatt KABUTOCHO-Oct.26.2025 V2.xlsx | 3 | C13, A13, B13, F13, I13 | 270*250cm | 270*250 | equivalent_match | Source size converts to the official normalized size. |
| 15 | 3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4.xlsx | 2 | C12, A12, B12, F12, I12 | 260*205cm | 260*205 | equivalent_match | Source size converts to the official normalized size. |
| 16 | 3402510MG10095 Canasin Proforma Invoice-Annupuri Garden 2-Sep.23.2025 V4.xlsx | 4 | C14, A14, B14, F14, I14 | 240*300cm | 240*300 | equivalent_match | Source size converts to the official normalized size. |
| 17 | 3402510MH40078 Proforma Invoice for Okura 20251020.xlsx | 3 | C12, A12, B12, D12, E12 | 240*270cm | 240*270 | equivalent_match | Source size converts to the official normalized size. |
| 18 | 3402510MH40078 Proforma Invoice for Okura 20251020.xlsx | 6 | C15, A15, B15, D15, E15 | 245*275cm | 245*275 | equivalent_match | Source size converts to the official normalized size. |
| 19 | 3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023.xlsx | 2 | C10, A10, B10, D10, E10 | 230*185cm | 230*185 | equivalent_match | Source size converts to the official normalized size. |
| 20 | 3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023.xlsx | 4 | C12, A12, B12, D12, E12 | 240*244cm | 240*244 | equivalent_match | Source size converts to the official normalized size. |
| 21 | 3402510MH90180.xlsx | 4 | C13, A13, B13, D13, F13 | 242*277cm | 242*277 | equivalent_match | Source size converts to the official normalized size. |
| 22 | 3402510MH90180.xlsx | 5 | C14, A14, B14, D14, F14 | 240*213cm | 240*213 | equivalent_match | Source size converts to the official normalized size. |
| 23 | 3402510MH90180.xlsx | 14 | C23, A23, B23, D23, F23 | 242*277cm | 242*277 | equivalent_match | Source size converts to the official normalized size. |
| 24 | 3402510MH90180.xlsx | 15 | C24, A24, B24, D24, F24 | 240*213cm | 240*213 | equivalent_match | Source size converts to the official normalized size. |
| 25 | 3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx | 15 | C28, A28, B28, D28, F28 | 240*270+5cm | 240*270+15cm | partial_match | Source dimensions match the official size, but structural extension evidence was not provided, not safely extractable... |
| 26 | 3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx | 16 | C29, A29, B29, F29 | 240*230+5cm | 240*230 | partial_match | Source dimensions match the official size, but structural extension evidence was not provided, not safely extractable... |
| 27 | 3402510MR30051 Proforma Invoice of Double Tree Jeddah - 20251002.xlsx | 17 | C30, A30, B30, F30 | 230*150+5cm | 230*150 | partial_match | Source dimensions match the official size, but structural extension evidence was not provided, not safely extractable... |
| 28 | 3402511MG20056 Proforma Invoice - Welllife PO 1031.2025.xlsx | 25 | E37, A37, B37, C37, F37, I37 | 250*260cm | 250*260 | equivalent_match | Source size converts to the official normalized size. |
| 29 | 3402511MG20056 Proforma Invoice - Welllife PO 1031.2025.xlsx | 26 | E38, A38, B38, C38, F38, I38 | 250*180cm | 250*180 | equivalent_match | Source size converts to the official normalized size. |
| 30 | 3402511MG20056 Proforma Invoice - Welllife PO 1031.2025.xlsx | 27 | E39, A39, B39, C39, F39, I39 | 250*240cm | 250*240 | equivalent_match | Source size converts to the official normalized size. |
| 31 | 3402511MH30095.xlsx | 4 | E11, A11, C11, F11, I11 | 240*255cm | 240*255 | equivalent_match | Source size converts to the official normalized size. |
| 32 | 3402511MH30095.xlsx | 12 | E19, A19, C19, F19, I19 | 240*195cm | 240*195 | equivalent_match | Source size converts to the official normalized size. |
| 33 | 3402511MH30095.xlsx | 20 | E27, A27, C27, F27, I27 | 240*225cm | 240*225 | equivalent_match | Source size converts to the official normalized size. |
| 34 | 3402511MH30095.xlsx | 28 | E35, A35, C35, F35, I35 | 230*195cm | 230*195 | equivalent_match | Source size converts to the official normalized size. |
| 35 | 3402511MH30095.xlsx | 35 | E42, A42, C42, F42, I42 | 220*155cm | 220*155 | equivalent_match | Source size converts to the official normalized size. |
| 36 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 37 | E10, A10, C10, D10, H10 | 260*280cm | 260*280 | equivalent_match | Source size converts to the official normalized size. |
| 37 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 38 | E11, A11, C11, H11 | 260*280cm | 260*280 | equivalent_match | Source size converts to the official normalized size. |
| 38 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 39 | E12, A12, C12, H12 | 260*280cm | 260*280 | equivalent_match | Source size converts to the official normalized size. |
| 39 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 40 | E13, A13, C13, H13 | 260*280cm | 260*280 | equivalent_match | Source size converts to the official normalized size. |
| 40 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 41 | E14, A14, C14, H14 | 260*280cm | 260*280 | equivalent_match | Source size converts to the official normalized size. |
| 41 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 42 | E15, A15, C15, H15 | 260*280cm | 260*280 | equivalent_match | Source size converts to the official normalized size. |
| 42 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 43 | E16, A16, C16, H16 | 240*190cm | 240*190 | equivalent_match | Source size converts to the official normalized size. |
| 43 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 44 | E17, A17, C17, H17 | 240*190cm | 240*190 | equivalent_match | Source size converts to the official normalized size. |
| 44 | 3402511MW30039 Canasin Invoice for MAK LLC Bayarsuren Natsagdorj Makotel project 20250915.xlsx | 45 | E18, A18, C18, H18 | 240*190cm | 240*190 | equivalent_match | Source size converts to the official normalized size. |
| 45 | 3402511MW90145 DW PI- Canasin 20251030.xlsx | 7 | C17, A17, B17, D17, E17 | 250*275cm | 250*275 | equivalent_match | Source size converts to the official normalized size. |
| 46 | 3402511MW90145 DW PI- Canasin 20251030.xlsx | 8 | C18, A18, B18, D18, E18 | 250*180cm | 250*180 | equivalent_match | Source size converts to the official normalized size. |

## 4. Calibrated Evidence Rules

- Parse size as structured evidence: raw first dimension, raw second dimension, normalized length, normalized width, unit, and structural extension in centimeters.
- Treat unlabeled duvet-cover source sizes as raw width x length and compare them against official length x width.
- Normalize `mm`, `cm`, and `inch/in/"` to centimeters before comparison.
- Treat separator differences such as `x`, `X`, `*`, `×`, and spacing as equivalent after parsing.
- For `+Xcm`, supplement only same item-row source cells already present in diagnostics for style/note/color evidence; do not scan other rows.
- Extract structural extension only when safely bound to flap, overlap, inner flap, opening extension, overlapping piece, or approved Chinese counterparts.
- Exclude hand-hole sizes, location counts, row numbers, quantities, thread count, density, yarn count, percentages, color-line widths, and flange widths from structural extension.
- If base dimensions match but extension evidence is ambiguous or incomplete, report `partial_match` instead of `conflict`.

## 5. Non-Size Fields

Non-size field status statistics were compared against the Gate 3A-C baseline and remained unchanged.

| Field | Status Counts After Calibration |
|---|---|
| 币种 | exact_match=36, equivalent_match=0, dictionary_more_specific=0, partial_match=0, ambiguous=0, conflict=0, dictionary_no_match=7, source_not_provided=6 |
| 物料名称 | exact_match=0, equivalent_match=46, dictionary_more_specific=0, partial_match=0, ambiguous=0, conflict=0, dictionary_no_match=3, source_not_provided=0 |
| 颜色 | exact_match=45, equivalent_match=0, dictionary_more_specific=0, partial_match=0, ambiguous=4, conflict=0, dictionary_no_match=0, source_not_provided=0 |
| 面料 | exact_match=0, equivalent_match=18, dictionary_more_specific=0, partial_match=0, ambiguous=29, conflict=2, dictionary_no_match=0, source_not_provided=0 |
| 面料-涤棉成分 | exact_match=0, equivalent_match=39, dictionary_more_specific=0, partial_match=0, ambiguous=0, conflict=0, dictionary_no_match=10, source_not_provided=0 |
| 款式 | exact_match=0, equivalent_match=0, dictionary_more_specific=0, partial_match=0, ambiguous=7, conflict=0, dictionary_no_match=42, source_not_provided=0 |
| 尺寸类型 | exact_match=12, equivalent_match=0, dictionary_more_specific=0, partial_match=0, ambiguous=0, conflict=0, dictionary_no_match=2, source_not_provided=35 |
| 行备注 | exact_match=16, equivalent_match=0, dictionary_more_specific=0, partial_match=8, ambiguous=0, conflict=0, dictionary_no_match=25, source_not_provided=0 |
| 是否绣花 | exact_match=7, equivalent_match=0, dictionary_more_specific=0, partial_match=0, ambiguous=0, conflict=0, dictionary_no_match=0, source_not_provided=42 |

## 6. Protection Checks

- Formal business JSON SHA-256 values: unchanged.
- Gate 2D parse report SHA-256 values: unchanged.
- Original PI Excel SHA-256 values: unchanged.
- Shadow report output remains in ignored directory `data/output/gate3a_c_shadow/`.
- No LLM or API calls were used.
- Dependencies were not modified.
- Day01 was not modified.

## 7. Tests

```text
108 passed
```

New coverage includes width x length equivalence, same-row flap evidence, hand-hole/location/TC exclusions, mm conversion, inch conversion, true mismatch conflict, official JSON non-modification, and non-size field stability.

## 8. Not Addressed In This Gate

面料 ambiguous/conflict and 款式 dictionary_no_match remain intentionally untreated. They were audited in Gate 3A-C.1 and are outside Gate 3A-C.2.


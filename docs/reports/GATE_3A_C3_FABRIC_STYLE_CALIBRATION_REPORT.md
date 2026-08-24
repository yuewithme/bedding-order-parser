# Gate 3A-C.3 Fabric And Style Shadow Calibration Report

## 1. Scope

This gate calibrates only the dictionary shadow comparison for `面料` and `款式`.
Gate 2D production parsing, official 20-field JSON, the two Excel dictionaries,
dependencies, and all other shadow fields remain unchanged.

The real regression corpus contains 12 PI workbooks and 49 records.

## 2. Implementation

### Fabric

- Extract source components independently: category, TC/density, composition,
  yarn count, construction density, weave, stripe width, and color.
- Give `stripe`, `striped`, `sateen stripe`, `缎条`, and `条纹` category
  priority over plain `sateen`/`satin`.
- Filter dictionary rows progressively only when the source supplies the
  corresponding component.
- Separate `dictionary_candidates` as comparable business projections from
  `detailed_candidates` as full Excel dictionary rows.
- Collapse multiple detailed rows that share one comparable projection.
- Preserve ambiguity only when business-distinct projections remain.

### Style

- Extract controlled components for bag/envelope form, flange count, bottom
  opening, flap/no flap, pocket, tie, zipper, hand holes, welcome style, and
  double-opening/overlap structure.
- Recognize only aliases observed in the 12 approved PI files, including
  `no falnge`, `bag style`, `bag model`, `hand holes`, `hand holds`,
  `bottom opening`, `open at/on bottom`, `no flap`, `without inner flap`,
  and `envelope style`.
- Apply negation before positive matching, so `no flap` and `no flange` never
  become positive components.
- Build a canonical style projection from source components and match it to
  structured dictionary rows. Dictionary aliases with the same canonical
  structure no longer create false ambiguity.

## 3. Fabric Status Before And After

| Status | Before | After |
|---|---:|---:|
| exact_match | 0 | 0 |
| equivalent_match | 18 | 32 |
| dictionary_more_specific | 0 | 0 |
| partial_match | 0 | 0 |
| ambiguous | 29 | 1 |
| conflict | 2 | 0 |
| dictionary_no_match | 0 | 16 |
| source_not_provided | 0 | 0 |

All 49 fabric comparison records remain present.

The 16 `dictionary_no_match` results are intentional:

- 3 Blooming records provide a T300 C80/T20 houndstooth/jacquard combination
  not represented by a matching dictionary row.
- 4 Okura/MH90180 records provide a grey T300 satin construction whose color
  and detailed evidence do not match the available dictionary rows.
- 9 MAK records provide plain T300 C80/T20 fabric, while the dictionary does
  not contain that same combination.

The previous matcher treated some of these as equivalent from source
components alone. The calibrated matcher now requires an actual dictionary row
before claiming a dictionary-backed match.

## 4. Original Two Fabric Conflicts

Both conflicts came from the 11-line golden PI:

| PI line | Source evidence | Official value | New status |
|---:|---|---|---|
| 5 | `60% cotton 40% polyester, 4mm sateen stripe, white T250` | `缎条/T250/C60/T40` | equivalent_match |
| 8 | Same fabric expression | `缎条/T250/C60/T40` | equivalent_match |

Root cause fixed: `sateen stripe` now selects the stripe category before the
plain sateen category. The matching detailed row is the 0.4 cm stripe,
T250, C60/T40 dictionary record.

## 5. Original 29 Fabric Ambiguous Results

| New status | Count |
|---|---:|
| equivalent_match | 24 |
| dictionary_no_match | 4 |
| ambiguous | 1 |

The 24 equivalent results include T300, T350, T400, and T600 cases where
multiple detailed Excel rows share the same comparable projection. Their full
rows remain visible in `detailed_candidates`, but they no longer create false
business ambiguity.

The four no-match results are the grey MH90180 records described above.

One ambiguity remains intentionally:

- `3402510MH40078 Proforma Invoice for Okura 20251020.xlsx`, business line 3.
  The source provides T300 and 100% cotton but no decisive category/weave
  evidence. Both `贡缎/T300/100C` and `缎条/T300/100C` remain supported by
  dictionary rows, so no candidate is forced.

## 6. Style Status Before And After

| Status | Before | After |
|---|---:|---:|
| exact_match | 0 | 0 |
| equivalent_match | 0 | 26 |
| dictionary_more_specific | 0 | 0 |
| partial_match | 0 | 4 |
| ambiguous | 7 | 0 |
| conflict | 0 | 0 |
| dictionary_no_match | 42 | 10 |
| source_not_provided | 0 | 9 |

All 49 style comparison records remain present.

The original seven style ambiguities all became `equivalent_match`. They were
caused by broad matching against rows with unrelated flange counts, generic
no-pocket rows, or duplicate names for the same structure.

## 7. Original 42 Style No-Match Results

| Gate 3A-C.1 root cause | New status | Count |
|---|---|---:|
| shadow_parser_wrong | equivalent_match | 12 |
| dictionary_missing_rule | equivalent_match | 7 |
| dictionary_missing_rule | dictionary_no_match | 10 |
| source_information_insufficient | partial_match | 4 |
| source_information_insufficient | source_not_provided | 9 |

All 12 records previously classified as `shadow_parser_wrong` were rechecked
and now match through controlled aliases and components.

Seven records previously classified as missing dictionary rules were found to
be representable by existing structured rows once source components were
correctly extracted. No dictionary content was changed.

The remaining ten no-match records are:

- 1 Okura record with `bottom opening, no flap, hand holes`;
- 9 MAK records with `open on bottom, no flap, hand holes`.

These are explicit, sufficiently described combinations, but the current style
dictionary does not contain a matching canonical row. They remain
`dictionary_no_match`; the matcher does not substitute the official Python
value.

The 13 source-insufficient records were safely reclassified as required:

- 4 records contain only partial craft evidence and are `partial_match`;
- 9 records contain no supported style structure and are
  `source_not_provided`.

## 8. Test Coverage

Added focused tests cover:

- 4 mm sateen stripe category priority;
- ordinary sateen projection;
- same projection with multiple detailed rows;
- genuinely different projections remaining ambiguous;
- explicit composition conflict;
- absent source yarn not eliminating candidates;
- combined density, composition, and yarn filtering;
- `no falnge` and `no flange` negation;
- bag style plus hand holes;
- `no flap` versus positive flap;
- envelope style;
- insufficient style evidence;
- genuine multi-style ambiguity;
- official JSON non-modification.

Full result:

```text
120 passed
```

## 9. Non-Target Field Protection

The final 49-record shadow report was compared with the Gate 3A-C.2 baseline.
The complete status distributions are unchanged for:

- `币种`
- `物料名称`
- `规格`
- `颜色`
- `面料-涤棉成分`
- `尺寸类型`
- `行备注`
- `是否绣花`

The size distribution remains exactly:

```text
equivalent_match=40
partial_match=6
conflict=0
dictionary_no_match=3
```

## 10. Data And Environment Protection

- Official business JSON SHA-256 values: unchanged.
- Gate 2D parse report SHA-256 values: unchanged.
- Original PI Excel SHA-256 values: unchanged.
- `PI单提取规则.xlsx` SHA-256:
  `8d527595f671b63762a15b1f5aa89004df4e773f68e776c824c37d57dece3c7c`.
- `款式表_structured.xlsx` SHA-256:
  `75faab06a151ee8f9d6d9dcb28ca4679414f4008fb86ae5d88acf5d0ee60660c`.
- The generated shadow report remains under ignored
  `data/output/gate3a_c_shadow/`.
- No LLM or external API was called.
- Dependencies were not changed.
- Day01 remains at
  `b6206bf28a9ce5499e317cee324b16ea98bf569d` with a clean worktree.

## 11. Production Integration Assessment

The project can proceed to a read-only evaluation of formal dictionary
integration. This is not approval to connect the dictionaries to production.

Before production integration, the evaluation must explicitly address:

- the one remaining fabric ambiguity;
- the 16 fabric dictionary coverage gaps;
- the 10 style dictionary coverage gaps;
- failure and fallback behavior when a dictionary row cannot be selected;
- preservation of Gate 2D as the only official result until a later gate
  approves a controlled cutover.

## 12. Conclusion

Gate 3A-C.3 meets its calibration goals:

- fabric conflict: 2 to 0;
- fabric ambiguous: 29 to 1;
- style dictionary no-match: 42 to 10;
- style ambiguous: 7 to 0;
- all non-target fields unchanged;
- official data and dictionaries unchanged.

This gate changes shadow diagnostics only. It does not modify any official
business result or production parsing rule.

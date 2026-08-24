# Gate 3A-D Dictionary Integration Impact Preview Report

## 1. Scope And Baseline

Gate 3A-D simulates decisions that a future dictionary integration could make.
It does not write any decision into the official 20-field JSON and does not
connect dictionaries to the Gate 2D production parser.

Baseline:

- Repository HEAD: `653d267352a1005f3fe39e28fb5caef8dc31fea4`
- Baseline commit: `fix: calibrate fabric and style shadow matching`
- Baseline tests: `120 passed`
- Corpus: 12 PI workbooks, 49 records
- Evaluated fields per record: 10
- Total field observations: 490
- Input shadow report SHA-256:
  `a952d37d2fcedbc091ebf6d8c46ea6330c36641a7d2b32732d18f30adf3b8746`

The simulator consumes the existing Gate 3A-C shadow report only. It does not
rerun Gate 2D, open either Excel dictionary, or derive candidates by looking up
the current Python value.

## 2. Decision Contract

- Nonempty Python value plus `exact_match` or `equivalent_match`:
  `keep_python`.
- Empty or `unrecognized` Python value plus one source-backed candidate:
  `propose_fill`.
- Python `defaulted` plus one source-backed candidate:
  `propose_replace_default`.
- Python `defaulted` without explicit source evidence: `keep_default`.
- `dictionary_more_specific` may become `propose_enrich` only when the
  source-projected candidate is unique, matched components are explicit, and
  no component is missing or conflicting.
- `ambiguous` and `conflict`: `manual_review`.
- `partial_match`, `dictionary_no_match`, and `source_not_provided`: no
  override.
- `detailed_candidates` are retained for diagnosis but are never used as the
  proposed value. Dictionary-row details absent from the PI cannot enrich an
  official result.

The implementation validates that every record has exactly the ten contracted
shadow fields. The real run produced 12 files, 49 records, and 490 decisions;
the action total and per-field observation totals independently reconcile to
490.

## 3. Action Results

| Action | Count | Effect on official JSON |
|---|---:|---|
| `keep_python` | 408 | None |
| `keep_default` | 77 | None |
| `propose_fill` | 0 | None |
| `propose_replace_default` | 0 | None |
| `propose_enrich` | 0 | None |
| `manual_review` | 5 | None |
| `not_applicable` | 0 | None |
| **Total** | **490** | **None** |

Actual proposed field changes: **0**.

No observation satisfied all of these requirements at once: a Python value
eligible for change, one dictionary candidate, an allowed shadow status, and
explicit PI evidence supporting the candidate. This result is intentionally
reported as zero; no change was manufactured to demonstrate dictionary value.

## 4. Field Assessments

| Field | Verified | Partial | Ambiguous | No match | Source missing | Simulated action | Risk |
|---|---:|---:|---:|---:|---:|---|---|
| 币种 | 36/49 | 0 | 0 | 7 | 6 | 49 keep Python | `medium_risk` |
| 物料名称 | 46/49 | 0 | 0 | 3 | 0 | 49 keep Python | `low_risk` |
| 规格 | 40/49 | 6 | 0 | 3 | 0 | 49 keep Python | `medium_risk` |
| 颜色 | 45/49 | 0 | 4 | 0 | 0 | 45 keep Python, 4 review | `medium_risk` |
| 面料 | 32/49 | 0 | 1 | 16 | 0 | 48 keep Python, 1 review | `high_risk` |
| 面料-涤棉成分 | 39/49 | 0 | 0 | 10 | 0 | 49 keep Python | `high_risk` |
| 款式 | 26/49 | 4 | 0 | 10 | 9 | 49 keep Python | `not_ready` |
| 尺寸类型 | 12/49 | 0 | 0 | 2 | 35 | 14 keep Python, 35 keep default | `not_ready` |
| 行备注 | 16/49 | 8 | 0 | 25 | 0 | 49 keep Python | `not_ready` |
| 是否绣花 | 7/49 | 0 | 0 | 0 | 42 | 7 keep Python, 42 keep default | `not_ready` |

`Verified` is `exact_match + equivalent_match`. Every row in this table uses
49 observations. No field produced `dictionary_more_specific` or `conflict`.

### Risk interpretation

- `low_risk`: `物料名称` has 46 verified records, no ambiguity, no partial
  match, no missing source evidence, and only three safe Python fallbacks.
- `medium_risk`: `币种` has 13 unsupported or missing-source observations;
  `规格` has six partial and three no-match observations; `颜色` has four
  ambiguities. These fields are safe only while unresolved cases keep Python
  or enter review.
- `high_risk`: `面料` has one ambiguity and 16 coverage gaps.
  `面料-涤棉成分` has ten coverage gaps. Neither dictionary is ready to be
  authoritative for these fields.
- `not_ready`: `款式`, `尺寸类型`, `行备注`, and `是否绣花` have fewer than
  60% verified observations or extensive missing-source/default behavior.

## 5. Proposed Changes

### `propose_fill`

None.

### `propose_replace_default`

None. The 35 defaulted `尺寸类型` observations and 42 defaulted
`是否绣花` observations have no source-backed unique candidate, so all 77
defaults are preserved.

### `propose_enrich`

None. The source report contains no `dictionary_more_specific` observation.
Detailed fabric dictionary rows are diagnostic evidence only and cannot add
parameters absent from the PI.

Every proposed-change category therefore has zero entries. There is no
proposed value whose reliability needs to be ranked against Python.

## 6. Manual Reviews

All five manual reviews are existing `ambiguous` observations. The simulator
does not select either candidate.

| Source PI | Business line | Field | Source cells | Python | Candidates |
|---|---:|---|---|---|---|
| `20251231 被套 Proforma Invoice（11行）.xlsx` | 7 | 颜色 | A19:E19 | 浅灰色 | 灰色 / 蓝色 |
| `3402510MH40078  Proforma Invoice for Okura 20251020.xlsx` | 3 | 颜色 | A12:E12 | 漂白色 | 漂白色 / 蓝色 |
| `3402510MH40078  Proforma Invoice for Okura 20251020.xlsx` | 3 | 面料 | D12 | T300/100C | 贡缎/T300/100C / 缎条/T300/100C |
| `3402510MH40078  Proforma Invoice for Okura 20251020.xlsx` | 6 | 颜色 | A15:E15 | 浅灰色 | 灰色 / 蓝色 |
| `3402510MH40090 Proforma Invoice【Ease Hotel】- Canasin 20251023.xlsx` | 2 | 颜色 | A10:E10 | 漂白色 | 漂白色 / 蓝色 |

The four color reviews contain multiple color terms in the source evidence.
The fabric review lacks evidence that distinguishes sateen from sateen stripe.
These are review signals, not permission to modify Python.

## 7. Integration Answers

1. **How many fields would change now?** Zero.
2. **How many are `propose_fill`?** Zero.
3. **How many are `propose_replace_default`?** Zero.
4. **How many are `propose_enrich`?** Zero.
5. **Does every proposed change have explicit PI evidence?** There are no
   proposed changes. The simulator would reject a proposal without explicit
   source text, source cells, and one source-projected candidate.
6. **Which fields can enter low-risk formal integration?** Only
   `物料名称`, and initially as validation with Python fallback rather than as
   an overwrite authority.
7. **Which fields must remain shadow-only?** `面料`, `面料-涤棉成分`,
   `款式`, `尺寸类型`, `行备注`, and `是否绣花`. `币种`, `规格`, and `颜色`
   may continue controlled validation but are not approved for automatic
   overwrite.
8. **Would dictionary integration improve the current 49 results?** It adds
   independent validation for 299 observations and identifies five review
   cases, but it produces no safer field value and therefore does not improve
   the official JSON content in this corpus.
9. **Is a zero-change result acceptable?** Yes. It is the only result
   consistent with the source-evidence and no-overwrite contract.

## 8. Recommended Next Integration Boundary

The first formal step should be validation-only integration for `物料名称`,
with Gate 2D remaining authoritative and all unmatched cases falling back to
Python. `币种`, `规格`, and `颜色` can remain read-only validation candidates
while their missing, partial, and ambiguous cases are resolved.

No field is approved in this gate for automatic filling, default replacement,
enrichment, or production overwrite. The high-risk and not-ready fields must
remain in shadow mode.

## 9. Tests And Protection

Implemented tests cover:

- exact/equivalent retention;
- source-backed fill and default-replacement proposals;
- default retention without source evidence;
- ambiguous/conflict review;
- no override for partial, no-match, or source-missing observations;
- rejection of dictionary-only enrichment detail;
- all 12 files, 49 records, and 490 observations;
- fail-closed field-contract validation;
- atomic preview writing and official JSON non-modification.

Final test result: `137 passed`.

Protection results:

- Official Gate 2D business JSON SHA-256 values: unchanged.
- Gate 2D parse report SHA-256 values: unchanged.
- Original 12 PI workbook SHA-256 values: unchanged.
- `PI单提取规则.xlsx` SHA-256:
  `8d527595f671b63762a15b1f5aa89004df4e773f68e776c824c37d57dece3c7c`,
  unchanged.
- `款式表_structured.xlsx` SHA-256:
  `75faab06a151ee8f9d6d9dcb28ca4679414f4008fb86ae5d88acf5d0ee60660c`,
  unchanged.
- Gate 3A-C shadow report SHA-256: unchanged.
- Local preview remains ignored under
  `data/output/gate3a_d_integration_preview/`.
- Gate 2D production parser: unchanged.
- Dependencies: unchanged.
- LLM/external API calls: none.
- Day01: unchanged and clean.

## 10. Deliverables And Conclusion

Local ignored output:

`data/output/gate3a_d_integration_preview/dictionary_integration_preview.json`

The simulation proves that the current dictionaries are useful as an
independent verification and review layer, but not as an automatic source of
better values for the current 49-record corpus. The official 20-field JSON
remains untouched, and Gate 2D remains the sole production result.

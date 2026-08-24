# Gate 3A-E Product Dictionary Validation Integration Report

## 1. Gate Goal

Gate 3A-E adds one optional validation-only sidecar to the existing `parse`
command. The dictionary validates only whether the product category represented
inside the official `物料名称` is `被套`.

The dictionary does not extract, fill, normalize, enrich, or overwrite any
official field. The customer prefix in `物料名称` is not compared. No other
field is validated in this gate.

Initial baseline:

- Repository: `D:\AI-Learning\Projects\bedding-order-parser`
- Branch: `master`
- Initial HEAD: `9caa138b559fc5688ad40f43e062c3dfbaa95620`
- Initial commit: `feat: add dictionary integration impact preview`
- Initial worktree: clean
- Initial tests: `137 passed`
- Git author: `小艾 <1746762028@qq.com>`
- Day01 HEAD: `b6206bf28a9ce5499e317cee324b16ea98bf569d`
- Day01 worktree: clean

## 2. Implementation

### CLI

The existing command now accepts:

```powershell
uv run python -m bedding_order_parser parse "<PI.xlsx>" `
  --output "<result.json>" `
  --dictionary-validate
```

The flag is optional and defaults to false.

Without `--dictionary-validate`:

- the existing parser performs the same Gate 2D workflow;
- no dictionary file is loaded;
- only the official business JSON and parse report are generated;
- no dictionary validation report is created.

With `--dictionary-validate`:

1. the existing Python parser completes;
2. the official business JSON and parse report are atomically written;
3. the approved read-only dictionary loader validates both dictionary SHA-256
   values;
4. the validation layer reopens the PI read-only;
5. the existing parse-report source coordinates are used to read independent
   product evidence;
6. the existing shadow product-category comparison evaluates that evidence;
7. a third atomic JSON report is written beside the official pair.

The validation report default name is:

```text
<result stem>_dictionary_validation.json
```

### Modules

- [`src/bedding_order_parser/cli.py`](../../src/bedding_order_parser/cli.py):
  exposes the optional flag and prints the third report path and status.
- [`src/bedding_order_parser/pipeline/order_parser.py`](../../src/bedding_order_parser/pipeline/order_parser.py):
  invokes validation only after the official pair succeeds.
- [`src/bedding_order_parser/dictionaries/product_validation.py`](../../src/bedding_order_parser/dictionaries/product_validation.py):
  builds and atomically writes the product-only validation report.
- [`tests/dictionaries/test_product_validation.py`](../../tests/dictionaries/test_product_validation.py):
  covers the CLI contract, source independence, failure isolation, output
  encoding, and official-output protection.

Absolute module root:

`D:\AI-Learning\Projects\bedding-order-parser`

## 3. Evidence And Status Contract

Each validation record retains:

- `source_file`
- `sheet`
- `source_cells`
- `source_text`
- `python_value`
- `detected_category`
- `dictionary_candidates`
- `validation_status`
- `action`
- `reason`

The source text is reread from the original PI cells recorded by the
`物料名称` parse diagnostic. The dictionary candidate is generated before the
Python value is compared. The validation layer never searches the dictionary
using the `被套` text already present in the Python result.

Allowed statuses:

- `equivalent_match`
- `dictionary_no_match`
- `source_not_provided`
- `conflict`

Allowed actions:

- `keep_python`
- `manual_review`

`conflict` is the only status that produces `manual_review`. Every other status
keeps the Python result. No action can write into the official record.

The validation module rejects any dictionary candidate other than `被套`.
The approved `Dubet cover` spelling variant is normalized only in the
validation evidence passed to the existing product comparison; the report
preserves the original source text.

## 4. No-Flag Real Regression

All 12 approved PI workbooks were parsed without the new flag.

| Check | Result |
|---|---:|
| PI files | 12 |
| Official business JSON files | 12 |
| Parse reports | 12 |
| Dictionary validation reports | 0 |
| Dictionary load attempts | 0 by contract and automated test |

The no-flag code path retains the previous default arguments and never invokes
the validation builder.

## 5. Validation-Enabled Real Regression

The same 12 PI workbooks were then parsed to the same output paths with
`--dictionary-validate --overwrite`.

| Result | Count |
|---|---:|
| PI files | 12 |
| Validation reports | 12 |
| Validation records | 49 |
| `equivalent_match` | 49 |
| `dictionary_no_match` | 0 |
| `source_not_provided` | 0 |
| `conflict` | 0 |
| `keep_python` | 49 |
| `manual_review` | 0 |

Every validation report completed successfully. All 49 records contain only
the `物料名称` field and all have nonempty source-cell evidence.

### Why The Result Is 49 Rather Than The Earlier Approximate 46/3

The three previous product-category no-match observations are all from:

`3402510MG10094 Canasin Proforma Invoice-Blooming_Caption by Hyatt KABUTOCHO-Oct.26.2025 V2.xlsx`

Their original product texts are the approved spelling variant:

- `Dubet cover TWIN`
- `Dubet cover Queen`
- `Dubet cover King`

Gate 3A-E explicitly requires this existing approved spelling variant to be
handled. These three records therefore validate as `equivalent_match`.
No status was forced to preserve the earlier approximate count.

## 6. Official Output Protection

Protection checks:

- The 12 validation-disabled business JSON SHA-256 values were recorded.
- Validation-enabled parsing rewrote the same official paths.
- All 12 business JSON SHA-256 values remained identical.
- All 12 parse report SHA-256 values remained identical.
- The 12 generated business JSON files also match the existing Gate 2D
  business JSON files byte-for-byte.
- The fixed 20-field schema file is unchanged.
- Existing Gate 2D business JSON and parse report files are unchanged.
- The two source dictionaries are unchanged.
- The original 12 PI workbooks are unchanged.
- `pyproject.toml`, `uv.lock`, and `.python-version` are unchanged.
- Day01 is unchanged.

The parse report model and business JSON model do not reference or consume the
dictionary validation report. The third report is an independent local output
under the Git-ignored `data/output/` tree.

## 7. Dictionary Failure And Fallback

Automated tests cover both expected dictionary-load failure and unexpected
validation-side failure.

When validation is enabled and a dictionary is missing, has the wrong SHA, or
cannot be loaded:

- the official business JSON already exists;
- the official parse report already exists;
- neither official file is deleted or rolled back;
- the third report has `status: "failed"`;
- `failure_reason` records the validation-side reason;
- no official field is changed.

If writing the third report itself fails, the CLI returns an explicit project
error while the already successful official pair remains in place.

When validation is disabled, dictionary availability has no effect on parsing.

## 8. Tests

New tests cover:

1. the CLI flag is optional;
2. `Duvet Cover` produces `equivalent_match`;
3. Chinese `被套` produces `equivalent_match`;
4. approved `Dubet cover` produces `equivalent_match`;
5. Python text containing `被套` cannot validate itself without source
   evidence;
6. dictionary no-match keeps Python;
7. dictionary conflict requires manual review;
8. UTF-8 Chinese JSON and atomic writing;
9. no-flag parsing does not invoke validation or create a third report;
10. enabled validation creates a third report;
11. enabled validation leaves the official JSON and parse report byte-identical;
12. missing dictionaries leave official outputs intact;
13. unexpected validation failure is isolated after official output success;
14. PI workbook SHA-256 remains unchanged.

Final command:

```powershell
uv run pytest
```

Final result:

```text
150 passed
```

## 9. Extension Readiness

This gate establishes reusable infrastructure for future validation-only
fields:

- an opt-in CLI mode;
- post-parse sidecar orchestration;
- independent source-cell evidence;
- approved SHA-checked dictionary loading;
- closed validation statuses and actions;
- atomic third-report writing;
- failure isolation from official outputs.

This is a technical foundation for later discussion of currency, size, and
color validation. It is not approval to implement those fields now. Their
evidence selection, status contracts, ambiguity handling, and real-data risk
must be approved in separate gates.

## 10. Explicit Non-Changes

- No official 20-field value was changed.
- No product field was filled, normalized, enriched, or overwritten by a
  dictionary.
- No field other than the product category inside `物料名称` was validated.
- No item-extraction core rule was changed.
- No field normalizer, metadata extractor, or party extractor was changed.
- No dependency was added or modified.
- No LLM, API, embedding, FAISS, or `material_info.csv` was used.
- No README, AGENTS, handoff, schema, dictionary, PI, or Day01 file was
  modified.

## 11. Deliverables

Committed report:

- Relative path:
  `docs/reports/GATE_3A_E_PRODUCT_VALIDATION_INTEGRATION_REPORT.md`
- Absolute path:
  `D:\AI-Learning\Projects\bedding-order-parser\docs\reports\GATE_3A_E_PRODUCT_VALIDATION_INTEGRATION_REPORT.md`

Local ignored validation reports:

`data/output/gate3a_e_product_validation/*_dictionary_validation.json`

Gate 3A-E is complete when the final protection checks, commit, and post-commit
test run pass.

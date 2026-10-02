# Laghubitta Pilot Demo: Contract Addendum v1.1

Status: ADDITIVE addendum to `docs/laghubitta_contract.md` (v1, frozen and
unchanged). Everything in v1 still holds unless a ruling below replaces it.
All data is synthetic. Thresholds, bands and rates are illustrative,
placeholders pending calibration. No compliance or approval claim.

## 1. Contract-owner rulings

- **R1. Tolerance.** Ratios: absolute `1e-9`. NPR amounts: relative `1e-9`.
  This replaces the v1 absolute `1e-9` on amounts, which is below float
  resolution for NPR sums of this size.
- **R2. Audit hashing.** Before hashing any output, round every float to 10
  significant digits, recursively. Stored JSON figures stay unrounded. Params
  are hashed as given.
- **R3. Byte-exact artefacts.** `.gitattributes` at the repo root marks the
  demo CSV, JSON and HTML (and the template CSV and JS engine) `-text`, so every
  checkout has identical bytes and the input sha256 check is byte-exact.

## 2. Data (section 2 additions)

- Each CSV row is a **centre-level pooled account (group loans aggregated per
  centre)** at one month-end. The column name `loan_id` is kept and holds the
  centre account id.
- `disbursed_npr` is the cumulative principal disbursed to that centre account
  up to and including the month. New loan cycles to the members of a centre
  add to both `disbursed_npr` and `outstanding_npr`.
- Caps: at most 2,000 distinct `loan_id`, about 60 branches, 24 month-ends.
- All NPR amounts are at institution scale (gross in the NPR 1,000 to 2,000
  crore range for the synthetic book).

## 3. Classification view (new, additive)

The five-bucket structure of v1 section 3 is unchanged. A separate,
configurable five-band classification is added.

```python
# cbsrm/mfi/classification.py
DEFAULT_CLASSIFICATION: dict = {"bands": [
    {"key": "pass",        "label": "Pass",        "min_dpd": 0,   "max_dpd": 30,   "provision_rate": 0.01},
    {"key": "watchlist",   "label": "Watchlist",   "min_dpd": 31,  "max_dpd": 90,   "provision_rate": 0.05},
    {"key": "substandard", "label": "Substandard", "min_dpd": 91,  "max_dpd": 180,  "provision_rate": 0.25},
    {"key": "doubtful",    "label": "Doubtful",    "min_dpd": 181, "max_dpd": 365,  "provision_rate": 0.50},
    {"key": "loss",        "label": "Loss",        "min_dpd": 366, "max_dpd": None, "provision_rate": 1.00},
]}   # placeholders pending calibration

def validate_classification(config: dict) -> list[str]: ...   # plain-language problems, [] if valid
def assign_class(days_past_due: pd.Series, config: dict | None = None) -> pd.Series: ...
def classification_table(loans, as_of: str, config: dict | None = None) -> pd.DataFrame: ...
```

- Bands are ordered and contiguous: the first starts at 0, each `min_dpd`
  equals the previous `max_dpd + 1`, and only the last may have
  `max_dpd = None` (no upper limit).
- A live row (`written_off = 0`) belongs to the band with
  `min_dpd <= days_past_due <= max_dpd`.
- `classification_table` returns one row per band, in band order, with
  columns `[key, label, min_dpd, max_dpd, n_loans, balance_npr, share,
  provision_rate, provision_npr]`. Here `balance_npr` is the sum of
  `outstanding_npr` over live rows in the band. `share = balance_npr / gross_npr`,
  or NaN when gross is 0. `provision_npr = balance_npr * provision_rate`.
- Every display of this table carries the exact label: "Configurable
  five-band classification. Bands and rates are placeholders pending
  calibration to the current NRB directive for D-class institutions."

JSON addition (section 6):
`"classification": {"as_of", "config": {...}, "rows": [...table rows...],
"total_balance_npr", "total_provision_npr"}`, computed at the latest `as_of`.

## 4. Branch findings (new, additive)

JSON addition: `"findings": [...]`, with one entry per branch that has at least
one alert at the latest `as_of`. Entries are sorted by `branch_id` and have these
fields:

```
{branch_id, branch_name, district, province, as_of, prev_as_of,
 gross_npr, par30, par30_prev, collection_efficiency, collection_efficiency_prev,
 rules: [{rule, value, threshold, severity}],            # that branch's alerts, rule order
 top_product, top_product_share, top_sector, top_sector_share}
```

- `top_product` is the product with the largest share of the branch's PAR30
  balance (live rows with `days_past_due > 30`) at the latest `as_of`.
  `top_product_share` is that product's share of the branch's PAR30 balance.
  The sector fields work the same way.
- When a branch has no PAR30 balance, these four fields are null.
- Ties go to the alphabetically first key.

The paragraph shown to users is a fixed template filled from these fields. No
generated text from any model is used.

## 5. Column mapping file (app)

The mapping that the app downloads and loads has this format:

```json
{"format": "cbsrm-laghubitta-mapping", "version": 1,
 "columns": {"as_of": "<column name in the user's file>", "...": "..."}}
```

Every section 2 field must map to a distinct source column. Mapping happens in
the browser and nothing is uploaded.

## 6. Audit chain

After `alerts`, the chain gains two records, `classification` and `findings`,
before the scenario records. Their params are
`{"as_of", "config": <classification config>}` and
`{"as_of", "prev_as_of", "config": <alerts config>}`. Ruling R2 applies.
`meta.contract_version` stays `1`, and `meta.contract_addendum = "1.1"` is
added.

## 7. Presentation

- All amounts use NPR. Where a full rupee number is shown, it uses South Asian
  digit grouping (for example 12,34,56,789). Crore figures are shown with two
  decimals.
- All three laghubitta pages share the header navigation Product, App and
  Sample dashboard. They are `noindex, nofollow` and carry the synthetic-data
  banner on the first screen.
- The "Verified against the open-source reference library" badge appears only
  for the bundled sample data, and only when the browser engine reproduces the
  reference JSON under R1.

# Laghubitta Pilot Demo: Frozen Contract v1

Status: FROZEN. Base ref: `main` at `bc897dfa32f5af84aa1454d2fb3cfb0e9b614a9c`.
Repo path once committed: `docs/laghubitta_contract.md`.
All data is synthetic. Institution label: "Sample Laghubitta (synthetic data)".
All thresholds, buckets and provisioning rates are illustrative and must be
calibrated to current NRB directives before any real use. No compliance claim.

## 1. File ownership

| Owner | Branch | Files |
|---|---|---|
| Orchestrator (Claude Code) | `feat/laghubitta-pilot-demo` | `tools/build_laghubitta_demo.py`, `site/laghubitta.html`, `site/laghubitta_demo.json`, `site/laghubitta_loans.csv`, `docs/laghubitta_contract.md`, `tests/test_laghubitta_parity.py` |
| Library (Codex) | `feat/laghubitta-mfi-lib` | `cbsrm/mfi/**`, `tests/test_mfi_*.py` |

Neither agent edits the other's files, `pyproject.toml`, README, CI, or versions.
Library dependencies: `pandas`, `numpy`, stdlib only.

## 2. Input: `laghubitta_loans.csv`

One row per loan per month-end. UTF-8, comma separated, header row.

| Column | Type | Rule |
|---|---|---|
| `as_of` | str `YYYY-MM-DD` | month-end date |
| `loan_id` | str | stable across months |
| `branch_id` | str | e.g. `BR001` |
| `branch_name` | str | |
| `district` | str | real Nepal district name |
| `province` | str | one of the 7 provinces |
| `product` | str | loan product |
| `sector` | str | economic sector |
| `disbursed_npr` | float | original principal |
| `outstanding_npr` | float | principal outstanding; `0` when `written_off = 1` |
| `days_past_due` | int | `>= 0` |
| `restructured` | int | `0` or `1` |
| `written_off` | int | `0` or `1` |
| `writeoff_npr` | float | amount written off in that month only, else `0` |
| `due_npr` | float | amount due in that month |
| `collected_npr` | float | amount collected in that month |

Generator caps: about 60 branches, at most 2,000 loans, 24 month-ends, fixed seed.

## 3. Buckets

Ordered, by `days_past_due`, for rows with `written_off = 0`:

| Key | Range |
|---|---|
| `current` | 0 |
| `b1_30` | 1 to 30 |
| `b31_90` | 31 to 90 |
| `b91_180` | 91 to 180 |
| `b180p` | above 180 |

`BUCKETS = ["current", "b1_30", "b31_90", "b91_180", "b180p"]`

## 4. Formulas

For a set of rows at one `as_of`. "Live" means `written_off = 0`.

- `gross_npr` = sum of `outstanding_npr` over live rows
- `par30` = sum of `outstanding_npr` over live rows with `days_past_due > 30`, divided by `gross_npr`
- `par90` = same with `days_past_due > 90`
- `npl_ratio` = same with `days_past_due > config["npl_dpd_threshold"]` (default 90)
- `restructured_ratio` = sum of `outstanding_npr` over live rows with `restructured = 1`, divided by `gross_npr`
- `writeoff_ratio` = `W / (gross_npr + W)` where `W` = sum of `writeoff_npr` over all rows
- `collection_efficiency` = sum of `collected_npr` / sum of `due_npr` over all rows
- `n_loans` = count of live rows

Any ratio with a zero denominator is `NaN` in Python and `null` in JSON.
JSON stores unrounded floats. Parity tolerance: absolute `1e-9`.

## 5. Library API (`cbsrm.mfi`)

`loans` is always a DataFrame with the section 2 schema. `as_of` values are strings.

```python
# cbsrm/mfi/config.py
DEFAULT_CONFIG: dict = {
    "npl_dpd_threshold": 90,
    "provision_rates": {"current": 0.01, "b1_30": 0.05, "b31_90": 0.25,
                        "b91_180": 0.50, "b180p": 1.00},   # illustrative
    "alerts": {"par30_level": 0.10, "par30_jump": 0.02,
               "roll_rate": 0.05, "collection_drop": 0.05},
}
BUCKETS: list[str]
def assign_bucket(days_past_due: pd.Series) -> pd.Series: ...

# cbsrm/mfi/portfolio.py
def portfolio_metrics(loans, as_of: str, by: Sequence[str] = (),
                      config: dict | None = None) -> pd.DataFrame:
    """Columns: [*by, gross_npr, par30, par90, npl_ratio, restructured_ratio,
    writeoff_ratio, collection_efficiency, n_loans]. by=() gives one row.
    Sorted ascending by the `by` columns."""

def bucket_balances(loans, as_of: str, by: Sequence[str] = ()) -> pd.DataFrame:
    """Columns: [*by, current, b1_30, b31_90, b91_180, b180p] in NPR, live rows."""

# cbsrm/mfi/migration.py
STATES = BUCKETS + ["written_off", "closed"]
def migration_matrix(loans, from_as_of: str, to_as_of: str,
                     weight: str = "outstanding") -> pd.DataFrame:
    """Index: BUCKETS (state at from_as_of, live rows only). Columns: STATES.
    Weight is outstanding_npr at from_as_of, or 1 if weight == "count".
    A loan absent at to_as_of is "closed". Rows sum to 1; a zero-weight row is NaN."""

def roll_rates(matrix: pd.DataFrame) -> pd.Series:
    """Per from-bucket share moving to any worse bucket or written_off.
    'closed' is not worse. b180p roll rate counts written_off only."""

# cbsrm/mfi/concentration.py
def hhi(loans, as_of: str, by: str) -> float:
    """Sum of squared shares of gross_npr across `by`. Range (0, 1]."""
def top_n_share(loans, as_of: str, by: str, n: int = 5) -> float: ...

# cbsrm/mfi/early_warning.py
def branch_alerts(loans, as_of: str, prev_as_of: str,
                  config: dict | None = None) -> pd.DataFrame:
    """Columns: [branch_id, rule, value, threshold, severity].
    Rules, per branch:
      PAR30_LEVEL      value = par30(as_of);                 fires if value >= par30_level
      PAR30_JUMP       value = par30(as_of) - par30(prev);   fires if value >= par30_jump
      ROLL_RATE        value = roll rate of 'current' bucket prev -> as_of;
                                                             fires if value >= roll_rate
      COLLECTION_DROP  value = coll_eff(prev) - coll_eff(as_of);
                                                             fires if value >= collection_drop
    NaN values never fire. severity = "high" if value >= 2 * threshold else "medium".
    Sorted by branch_id, then rule."""

# cbsrm/mfi/stress.py
def apply_scenario(segments: pd.DataFrame, balance_sheet: dict, scenario: dict,
                   config: dict | None = None) -> dict: ...

# cbsrm/mfi/audit.py
def record(name: str, input_sha256: str, params: dict, output: dict,
           prev_hash: str | None = None) -> dict: ...
```

### 5.1 Stress engine

`segments`: columns `[sector, province, current, b1_30, b31_90, b91_180, b180p]` (NPR).

`balance_sheet` keys: `capital_npr`, `rwa_npr`, `liquid_assets_npr`,
`inflows_90d_npr`, `outflows_90d_npr`, `borrowings_npr`.

`scenario` keys (all optional except `id`):

| Key | Default | Meaning |
|---|---|---|
| `id`, `label` | | identifiers |
| `base_shift` | 0.0 | share of each bucket moving one bucket worse |
| `sector_mult` | `{}` | multiplier by sector, default 1 |
| `province_mult` | `{}` | multiplier by province, default 1 |
| `funding_cost_bps` | 0 | parallel rise in funding cost |
| `inflow_haircut` | 0.0 | share of 90 day inflows lost |
| `outflow_mult` | 1.0 | multiplier on 90 day outflows |

Per segment row: `s = min(1, base_shift * sector_mult * province_mult)`.
Using pre-shock balances simultaneously:

```
current'  = (1 - s) * current
b1_30'    = (1 - s) * b1_30   + s * current
b31_90'   = (1 - s) * b31_90  + s * b1_30
b91_180'  = (1 - s) * b91_180 + s * b31_90
b180p'    =           b180p   + s * b91_180
```

Then, over summed stressed buckets `T[b]` and `gross = sum(T)`:

- `par30 = (T[b31_90] + T[b91_180] + T[b180p]) / gross`
- `par90 = (T[b91_180] + T[b180p]) / gross`
- `provisions_npr = sum(T[b] * provision_rates[b])`
- `delta_provisions_npr = provisions_npr - provisions on unstressed buckets`
- `nii_hit_npr = borrowings_npr * funding_cost_bps / 10000`
- `capital_npr = capital_npr_base - delta_provisions_npr - nii_hit_npr`
- `car = capital_npr / rwa_npr`
- `liquidity_gap_90d_npr = liquid_assets_npr + inflows_90d_npr * (1 - inflow_haircut) - outflows_90d_npr * outflow_mult`

Return dict keys: `scenario_id, buckets (dict by bucket), gross_npr, par30, par90,
provisions_npr, delta_provisions_npr, nii_hit_npr, capital_npr, car,
liquidity_gap_90d_npr`.

### 5.2 Audit record

`canon(x) = json.dumps(x, sort_keys=True, separators=(",", ":"))`

`record` returns `{name, input_sha256, params_sha256, output_sha256, prev_hash, hash}` where
`params_sha256 = sha256(canon(params))`, `output_sha256 = sha256(canon(output))`,
`hash = sha256(canon([prev_hash or "", name, input_sha256, params_sha256, output_sha256]))`.
Hex digests. No timestamps inside hashes. Using `cbsrm.audit.AuditChain` in
addition is optional.

## 6. Output: `site/laghubitta_demo.json`

```
{
  "meta":   {"institution", "synthetic": true, "seed", "generated_at",
             "contract_version": 1, "currency": "NPR"},
  "config": DEFAULT_CONFIG,
  "as_of_dates": [24 strings, ascending],
  "institution": [{"as_of", ...section 4 metrics}],            # 24 rows
  "branches": [{"branch_id", "branch_name", "district", "province",
                "series": [{"as_of", ...section 4 metrics}]}],
  "by_district" | "by_product" | "by_sector": [{key, ...section 4 metrics}],  # latest as_of
  "segments": [{"sector", "province", ...5 bucket balances}],   # latest as_of
  "migration": {"from_as_of", "to_as_of", "states", "matrix", "roll_rates"},
  "concentration": {"district": {"hhi", "top5_share"}, "sector": {...}, "product": {...}},
  "alerts": [{"branch_id", "rule", "value", "threshold", "severity"}],
  "balance_sheet": {...section 5.1 keys},
  "scenarios": [{...section 5.1 scenario}],
    # ids: base, rate_up_200bp, agri_income_shock, monsoon_seasonal,
    #      regional_disaster, funding_squeeze
  "audit": {"input_sha256", "chain": [record...], "head_hash"}
}
```

`audit.input_sha256` is the sha256 of the CSV file bytes.

## 7. Parity test (orchestrator)

`tests/test_laghubitta_parity.py` loads the CSV, calls `cbsrm.mfi`, and asserts
equality within `1e-9` against `institution`, `branches`, `migration`,
`concentration`, `alerts`, and `apply_scenario` for every entry in `scenarios`.
The generator does not import `cbsrm.mfi`.

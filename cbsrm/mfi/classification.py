"""Configurable five-band loan classification (contract addendum v1.1, section 3).

The bands, day cut-offs and provision rates in DEFAULT_CLASSIFICATION are
placeholders pending calibration. They are NOT NRB values and make no
compliance claim. Every display of the table must carry the label:
"Configurable five-band classification. Bands and rates are placeholders
pending calibration to the current NRB directive for D-class institutions."

A config is ``{"bands": [band, ...]}`` where each band has ``key``, ``label``,
``min_dpd``, ``max_dpd`` and ``provision_rate``. Bands are ordered and
contiguous: the first starts at 0, each ``min_dpd`` is the previous
``max_dpd + 1``, and only the last band has ``max_dpd = None`` (no upper
limit), which it must. Day limits are whole numbers up to 2**53 - 1, the
largest whole number JavaScript holds exactly. A missing or blank ``label``
falls back to the ``key``.

The site engine (site/laghubitta-engine.js) mirrors this module: the same
problem messages, the same band for every value and the same table rows.

The v1 five-bucket structure (``cbsrm.mfi.config.BUCKETS``) is unchanged.
"""
from __future__ import annotations

import math
import numbers

import numpy as np
import pandas as pd

DEFAULT_CLASSIFICATION: dict = {"bands": [
    {"key": "pass", "label": "Pass", "min_dpd": 0, "max_dpd": 30,
     "provision_rate": 0.01},
    {"key": "watchlist", "label": "Watchlist", "min_dpd": 31, "max_dpd": 90,
     "provision_rate": 0.05},
    {"key": "substandard", "label": "Substandard", "min_dpd": 91, "max_dpd": 180,
     "provision_rate": 0.25},
    {"key": "doubtful", "label": "Doubtful", "min_dpd": 181, "max_dpd": 365,
     "provision_rate": 0.50},
    {"key": "loss", "label": "Loss", "min_dpd": 366, "max_dpd": None,
     "provision_rate": 1.00},
]}  # placeholders pending calibration; not NRB values

TABLE_COLUMNS = [
    "key", "label", "min_dpd", "max_dpd", "n_loans", "balance_npr", "share",
    "provision_rate", "provision_npr",
]

# Largest whole number a JavaScript number holds exactly (Number.MAX_SAFE_INTEGER).
_MAX_DAYS = 2**53 - 1
# The characters JavaScript's String.prototype.trim() removes, so that a blank
# key or label is judged the same way here and in the site engine.
_BLANK = (
    " \t\n\v\f\r\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def _is_real(value: object) -> bool:
    """A real number, NaN and infinity included; booleans are not numbers here (as in JS)."""
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    """Finite real number."""
    return _is_real(value) and (isinstance(value, numbers.Integral) or math.isfinite(value))


def _as_float(value: numbers.Real) -> float:
    """float(value), with a whole number too large for a float becoming +/- infinity."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _is_days(value: object) -> bool:
    """Whole number of days from 0 to _MAX_DAYS (31.0 counts: JSON cannot tell them apart)."""
    if not _is_number(value):
        return False
    whole = isinstance(value, numbers.Integral) or float(value).is_integer()
    return whole and 0 <= value <= _MAX_DAYS


def _is_text(value: object) -> bool:
    """A string with something other than blanks in it."""
    return isinstance(value, str) and value.strip(_BLANK) != ""


def _band_name(position: int, band: object) -> str:
    key = band.get("key") if isinstance(band, dict) else None
    if _is_text(key):
        return f'Band {position} ("{key}")'
    return f"Band {position}"


def validate_classification(config: dict) -> list[str]:
    """Return plain-language problems with a classification config, [] if valid.

    The site engine (site/laghubitta-engine.js) returns the same messages.
    """
    if not isinstance(config, dict):
        return ['The classification settings must be an object with a "bands" list.']
    bands = config.get("bands")
    if not isinstance(bands, (list, tuple)):
        return ['The classification settings need a "bands" list.']
    if not bands:
        return ["At least one band is needed."]
    problems: list[str] = []
    seen: dict[str, int] = {}
    prev_end: int | None = None  # previous band's max_dpd, when known and finite
    last = len(bands)
    for position, band in enumerate(bands, start=1):
        if not isinstance(band, dict):
            problems.append(
                f"Band {position} must be an object with key, label, min_dpd, max_dpd "
                "and provision_rate."
            )
            prev_end = None
            continue
        name = _band_name(position, band)
        key = band.get("key")
        if not _is_text(key):
            problems.append(f'Band {position} needs a key, a short name such as "pass".')
        elif key in seen:
            problems.append(
                f"{name} uses the same key as band {seen[key]}. Each band needs a different key."
            )
        else:
            seen[key] = position
        low, high = band.get("min_dpd"), band.get("max_dpd")
        low_ok = _is_days(low)
        if not low_ok:
            problems.append(f"{name}: min_dpd must be a whole number of days, 0 or more.")
        elif position == 1 and low != 0:
            problems.append(f"{name} must start at 0 days past due, but its min_dpd is {int(low)}.")
        elif position > 1 and prev_end is not None and low != prev_end + 1:
            problems.append(
                f"{name} must start at {prev_end + 1} days past due, one day after band "
                f"{position - 1} ends, but its min_dpd is {int(low)}."
            )
        prev_end = None
        if high is None:
            if position < last:
                problems.append(
                    f"{name} has no upper limit (empty max_dpd), but only the last band "
                    "may be open-ended."
                )
        elif not _is_days(high):
            problems.append(
                f"{name}: max_dpd must be a whole number of days, 0 or more, or empty for "
                "no upper limit."
            )
        else:
            prev_end = int(high)
            if position == last:
                problems.append(
                    f"{name} is the last band, so its max_dpd must be empty (no upper limit) "
                    "so that every loan falls in a band."
                )
            if low_ok and high < low:
                problems.append(
                    f"{name} ends at {int(high)} days past due, before it starts at "
                    f"{int(low)}. max_dpd must be at least min_dpd."
                )
        rate = band.get("provision_rate")
        if not _is_number(rate) or not 0 <= rate <= 1:
            problems.append(
                f"{name}: provision_rate must be a number from 0 to 1 "
                "(for example 0.25 for 25%)."
            )
    return problems


def _checked_bands(config: dict | None) -> list[dict]:
    config = DEFAULT_CLASSIFICATION if config is None else config
    problems = validate_classification(config)
    if problems:
        raise ValueError("Invalid classification config: " + " ".join(problems))
    return list(config["bands"])


def _days_values(days_past_due: pd.Series) -> np.ndarray:
    """Days as floats; NaN for a value that is not a number (missing, text, True/False).

    Text is not converted, so "31" is in no band, as in the site engine.
    """
    if (pd.api.types.is_numeric_dtype(days_past_due)
            and not pd.api.types.is_bool_dtype(days_past_due)):
        return days_past_due.to_numpy(dtype=float, na_value=np.nan)
    return np.array([
        _as_float(value) if _is_real(value) else np.nan for value in days_past_due
    ], dtype=float)


def _band_codes(days_past_due: pd.Series, bands: list[dict]) -> np.ndarray:
    """Band position per value; -1 where no band has min_dpd <= value <= max_dpd."""
    values = _days_values(days_past_due)
    codes = np.full(len(values), -1, dtype=np.int64)
    for position, band in enumerate(bands):
        inside = values >= band["min_dpd"]
        if band.get("max_dpd") is not None:
            inside &= values <= band["max_dpd"]
        codes[inside & (codes == -1)] = position
    return codes


def assign_class(days_past_due: pd.Series, config: dict | None = None) -> pd.Series:
    """Return each value's band key as an ordered categorical in band order.

    Keeps the input index and name. A value in no band is NaN: negative,
    missing, not a number (text such as "31", True/False), or a fraction falling
    between two bands such as 30.5. Raises ValueError listing the problems
    when the config is invalid; ``None`` means DEFAULT_CLASSIFICATION.
    """
    bands = _checked_bands(config)
    categories = [band["key"] for band in bands]
    codes = _band_codes(days_past_due, bands)
    return pd.Series(
        pd.Categorical.from_codes(codes, categories=categories, ordered=True),
        index=days_past_due.index, name=days_past_due.name,
    )


def classification_table(
    loans: pd.DataFrame, as_of: str, config: dict | None = None,
) -> pd.DataFrame:
    """Return one row per band, in band order, over live rows at ``as_of``.

    Columns: [key, label, min_dpd, max_dpd, n_loans, balance_npr, share,
    provision_rate, provision_npr]. ``balance_npr`` sums ``outstanding_npr``
    of live rows (``written_off == 0``) in the band; ``share`` divides it by
    gross (all live rows) and is NaN when gross is 0; ``provision_npr`` is
    ``balance_npr * provision_rate``. Bands with no rows are kept, with zeros.
    ``max_dpd`` is an object column holding ints, and None (never NaN) for the
    open-ended last band, so it serialises to JSON null. ``label`` falls back to
    ``key`` when missing or blank. A live row whose days fit no band counts
    towards gross but not towards any band. Raises ValueError when the config
    is invalid; ``None`` means DEFAULT_CLASSIFICATION.
    """
    bands = _checked_bands(config)
    frame = loans.loc[(loans["as_of"] == as_of) & (loans["written_off"] == 0)]
    outstanding = frame["outstanding_npr"].to_numpy(dtype=float)
    codes = _band_codes(frame["days_past_due"], bands)
    gross = float(outstanding.sum())
    counts, balances = [], []
    for position in range(len(bands)):
        inside = codes == position
        counts.append(int(inside.sum()))
        balances.append(float(outstanding[inside].sum()))
    rates = [float(band["provision_rate"]) for band in bands]
    balance = pd.Series(balances, dtype=float)
    return pd.DataFrame({
        "key": [band["key"] for band in bands],
        "label": [band["label"] if _is_text(band.get("label")) else band["key"] for band in bands],
        "min_dpd": pd.Series([int(band["min_dpd"]) for band in bands], dtype="int64"),
        "max_dpd": pd.Series(
            [None if band.get("max_dpd") is None else int(band["max_dpd"]) for band in bands],
            dtype=object,
        ),
        "n_loans": pd.Series(counts, dtype="int64"),
        "balance_npr": balance,
        "share": balance / gross if gross != 0 else pd.Series(np.nan, index=balance.index),
        "provision_rate": pd.Series(rates, dtype=float),
        "provision_npr": balance * pd.Series(rates, dtype=float),
    }, columns=TABLE_COLUMNS)

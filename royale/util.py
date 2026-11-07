"""Small numeric helpers used everywhere."""
import numpy as np
import pandas as pd


def cents_to_usd(x):
    """Integer cents -> dollars (float). Works on scalars, Series and arrays. Convert once, early."""
    if isinstance(x, pd.Series):
        return x.astype("float64") / 100.0
    return np.asarray(x, dtype="float64") / 100.0 if np.ndim(x) else float(x) / 100.0


def safe_ratio(num, den):
    """num / den, but NaN where den is 0 or missing (e.g. observed hold on a machine with no coin-in).

    Use it on *sums* (ratio of sums), never to average daily ratios.
    """
    if isinstance(num, pd.Series) or isinstance(den, pd.Series):
        if isinstance(den, pd.Series):
            den = den.astype("float64")
            den = den.where(den != 0)
        elif den == 0 or pd.isna(den):
            den = np.nan
        return (num / den).astype("float64")
    num_a = np.asarray(num, dtype="float64")
    den_a = np.asarray(den, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where((den_a == 0) | np.isnan(den_a), np.nan, num_a / den_a)
    return float(out) if out.ndim == 0 else out

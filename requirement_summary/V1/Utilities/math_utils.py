# V1/Utilities/math_utils.py
# ---------------------------------------------------------------------------
# SHARED MATHEMATICAL & PARSING UTILITIES
# ---------------------------------------------------------------------------

import pandas as pd
import numpy as np

def minmax_normalize(series: pd.Series, fallback: float = 0.0) -> pd.Series:
    """
    Min-max normalize a Series to [0, 1].
    Formula: (x - min) / (max - min)
    
    Args:
        series: The pandas Series to normalize.
        fallback: The value to return if max == min (avoids division by zero).
                  - Stage 1 automated scoring uses 0.0 as the fallback.
                  - Stage 2/3 manual scoring uses 1.0 as the fallback.
    """
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(fallback, index=series.index)
    return (series - mn) / (mx - mn)


def extract_rim_size(sku_series: pd.Series) -> pd.Series:
    """
    Extract rim size from SKUCode (positions 8:10 = 9th and 10th characters).
    Converts to numeric and handles invalid values, matching the original 
    demand_processor.py logic perfectly.
    """
    return pd.to_numeric(sku_series.str[8:10], errors='coerce').fillna(0).astype('Int64')
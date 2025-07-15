# app/utils.py

import pandas as pd

def _is_zero_volume(sub_df: pd.DataFrame, idx: int = -1) -> bool:
    """
    주어진 sub‑dataframe(단일 티커)을 받아
    원하는 행(idx)의 Volume 이 0·NaN 이면 True.
    """
    return (
        "Volume" not in sub_df.columns
        or pd.isna(sub_df["Volume"].iloc[idx])
        or sub_df["Volume"].iloc[idx] == 0
    )
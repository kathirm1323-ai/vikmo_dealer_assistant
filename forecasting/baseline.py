"""
Baseline Forecasting Models for Demand Prediction.

Implements two simple baselines:
1. Last Value — forecast = last observed value
2. Moving Average — forecast = mean of last N observations

These serve as benchmarks to compare against Prophet.
"""

import os
import sys
import pandas as pd
import numpy as np

# Reconfigure stdout to use UTF-8 to prevent charmap errors on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sales_history.csv")


def load_sales_data() -> pd.DataFrame:
    """Load and prepare the sales history dataset."""
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    df = df.sort_values(["sku", "date"]).reset_index(drop=True)
    return df


def train_test_split(df: pd.DataFrame, test_periods: int = 12) -> tuple:
    """
    Split data into train/test per SKU.
    Holds out the last `test_periods` months as the test set.

    Returns:
        (train_df, test_df)
    """
    train_dfs = []
    test_dfs = []

    for sku in df["sku"].unique():
        sku_data = df[df["sku"] == sku].sort_values("date")
        n = len(sku_data)

        if n <= test_periods:
            train_dfs.append(sku_data)
            continue

        train_dfs.append(sku_data.iloc[:-test_periods])
        test_dfs.append(sku_data.iloc[-test_periods:])

    train = pd.concat(train_dfs, ignore_index=True) if train_dfs else pd.DataFrame()
    test = pd.concat(test_dfs, ignore_index=True) if test_dfs else pd.DataFrame()

    return train, test


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Error."""
    return np.mean(np.abs(actual - predicted))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Percentage Error (handles zeros)."""
    mask = actual != 0
    if mask.sum() == 0:
        return 0.0
    return np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100


# ---------------------------------------------------------------------------
# Baseline Models
# ---------------------------------------------------------------------------

def last_value_forecast(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """
    Last Value Baseline: predict the last training value for all test periods.

    For each SKU, the forecast is simply the last observed sales value.
    """
    results = []

    for sku in test["sku"].unique():
        sku_train = train[train["sku"] == sku].sort_values("date")
        sku_test = test[test["sku"] == sku].sort_values("date")

        if sku_train.empty:
            continue

        last_val = sku_train["units_sold"].iloc[-1]

        for _, row in sku_test.iterrows():
            results.append({
                "date": row["date"],
                "sku": row["sku"],
                "actual": row["units_sold"],
                "predicted": last_val,
                "model": "Last Value",
            })

    return pd.DataFrame(results)


def moving_average_forecast(
    train: pd.DataFrame, test: pd.DataFrame, window: int = 3
) -> pd.DataFrame:
    """
    Moving Average Baseline: predict the mean of the last `window` training values.

    For each SKU, the forecast is the average of the last 3 months.
    """
    results = []

    for sku in test["sku"].unique():
        sku_train = train[train["sku"] == sku].sort_values("date")
        sku_test = test[test["sku"] == sku].sort_values("date")

        if len(sku_train) < window:
            avg_val = sku_train["units_sold"].mean()
        else:
            avg_val = sku_train["units_sold"].iloc[-window:].mean()

        for _, row in sku_test.iterrows():
            results.append({
                "date": row["date"],
                "sku": row["sku"],
                "actual": row["units_sold"],
                "predicted": round(avg_val, 1),
                "model": "Moving Average (3m)",
            })

    return pd.DataFrame(results)


def evaluate_baselines() -> dict:
    """
    Run both baseline models and return metrics.

    Returns:
        Dict with MAE and MAPE for each baseline model.
    """
    df = load_sales_data()
    train, test = train_test_split(df, test_periods=12)

    if test.empty:
        return {"error": "Not enough data for evaluation"}

    # Run baselines
    lv_results = last_value_forecast(train, test)
    ma_results = moving_average_forecast(train, test)

    metrics = {
        "last_value": {
            "mae": round(mae(lv_results["actual"].values, lv_results["predicted"].values), 2),
            "mape": round(mape(lv_results["actual"].values, lv_results["predicted"].values), 2),
        },
        "moving_average": {
            "mae": round(mae(ma_results["actual"].values, ma_results["predicted"].values), 2),
            "mape": round(mape(ma_results["actual"].values, ma_results["predicted"].values), 2),
        },
    }

    return metrics


if __name__ == "__main__":
    print("\n📊 Running Baseline Forecasts...")
    metrics = evaluate_baselines()

    print("\n" + "=" * 50)
    print("  BASELINE RESULTS")
    print("=" * 50)

    for model, m in metrics.items():
        print(f"\n  {model.replace('_', ' ').title()}:")
        print(f"    MAE:  {m['mae']}")
        print(f"    MAPE: {m['mape']}%")

    print("\n" + "=" * 50)

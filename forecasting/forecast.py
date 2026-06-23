"""
Demand Forecasting with Facebook Prophet.

Builds a Prophet model for each SKU in the sales history,
compares against baselines, and generates a comparison report.

Features:
- Proper train/test split (holdout last 3 months)
- No data leakage (test data never seen during training)
- MAE and MAPE metrics
- Comparison table vs baselines
- Forecast visualization (saved as PNG)
"""

import os
import sys
import warnings

# Reconfigure stdout to use UTF-8 to prevent charmap errors on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

# Suppress Prophet's verbose logging
warnings.filterwarnings("ignore")
import logging
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

from prophet import Prophet

# Add project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from forecasting.baseline import (
    load_sales_data, train_test_split,
    last_value_forecast, moving_average_forecast,
    mae, mape,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
TEST_PERIODS = 12  # Hold out last 12 weeks


# ---------------------------------------------------------------------------
# Prophet Forecasting
# ---------------------------------------------------------------------------

def prophet_forecast(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """
    Run Prophet model for each SKU.

    Prophet requires columns: ds (date) and y (target value).
    We train per-SKU models to capture individual product trends.
    """
    results = []

    for sku in test["sku"].unique():
        sku_train = train[train["sku"] == sku].sort_values("date")
        sku_test = test[test["sku"] == sku].sort_values("date")

        if len(sku_train) < 4:
            # Not enough data for Prophet
            continue

        # Prepare Prophet format
        prophet_df = sku_train[["date", "units_sold"]].rename(
            columns={"date": "ds", "units_sold": "y"}
        )

        # Initialize and fit Prophet
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=0.05,  # Conservative to avoid overfitting
        )
        model.fit(prophet_df)

        # Make future dataframe for test periods
        future = pd.DataFrame({"ds": sku_test["date"].values})
        forecast = model.predict(future)

        for i, (_, row) in enumerate(sku_test.iterrows()):
            predicted = max(0, forecast["yhat"].iloc[i])  # Non-negative
            results.append({
                "date": row["date"],
                "sku": row["sku"],
                "actual": row["units_sold"],
                "predicted": round(predicted, 1),
                "yhat_lower": round(max(0, forecast["yhat_lower"].iloc[i]), 1),
                "yhat_upper": round(forecast["yhat_upper"].iloc[i], 1),
                "model": "Prophet",
            })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_comparison(
    lv_results: pd.DataFrame,
    ma_results: pd.DataFrame,
    prophet_results: pd.DataFrame,
    save_path: str,
):
    """Generate a comparison chart of all models for each SKU."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    skus = prophet_results["sku"].unique()
    n_skus = len(skus)

    fig, axes = plt.subplots(n_skus, 1, figsize=(12, 4 * n_skus), facecolor="#121212")

    if n_skus == 1:
        axes = [axes]

    for ax, sku in zip(axes, skus):
        ax.set_facecolor("#1A1A1A")

        # Get data for this SKU
        p_data = prophet_results[prophet_results["sku"] == sku]
        lv_data = lv_results[lv_results["sku"] == sku]
        ma_data = ma_results[ma_results["sku"] == sku]

        dates = p_data["date"]
        product_name = f"SKU: {sku}"

        # Plot actual
        ax.plot(dates, p_data["actual"], "wo-", label="Actual", linewidth=2, markersize=8)

        # Plot Prophet
        ax.plot(dates, p_data["predicted"], color="#E53935", marker="s",
                label="Prophet", linewidth=2, markersize=7)
        ax.fill_between(dates, p_data["yhat_lower"], p_data["yhat_upper"],
                        alpha=0.15, color="#E53935")

        # Plot baselines
        ax.plot(dates, lv_data["predicted"], color="#FFC107", marker="^",
                label="Last Value", linewidth=1.5, markersize=6, linestyle="--")
        ax.plot(dates, ma_data["predicted"], color="#4CAF50", marker="d",
                label="Moving Avg", linewidth=1.5, markersize=6, linestyle="--")

        ax.set_title(product_name, color="white", fontsize=13, fontweight="bold", pad=10)
        ax.set_ylabel("Units Sold", color="#B0B0B0", fontsize=10)
        ax.tick_params(colors="#B0B0B0", labelsize=9)
        ax.legend(facecolor="#1E1E1E", edgecolor="#333", labelcolor="white",
                  fontsize=9, loc="upper left")
        ax.grid(True, alpha=0.1, color="white")

        # Style spines
        for spine in ax.spines.values():
            spine.set_color("#333")

    plt.suptitle("Demand Forecast — Model Comparison",
                 color="white", fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight",
                facecolor="#121212", edgecolor="none")
    plt.close()
    print(f"📈 Forecast chart saved to {save_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_forecasting():
    """Run complete forecasting pipeline."""
    print("\n" + "=" * 60)
    print("  VIKMO — Demand Forecasting Pipeline")
    print("=" * 60)

    # Load data
    print("\n📂 Loading sales data...")
    df = load_sales_data()
    print(f"   {len(df)} records, {df['sku'].nunique()} products, "
          f"{df['date'].nunique()} time periods")

    # Train/test split
    print(f"\n🔀 Splitting data (holdout last {TEST_PERIODS} weeks)...")
    train, test = train_test_split(df, test_periods=TEST_PERIODS)
    print(f"   Train: {len(train)} records | Test: {len(test)} records")

    # Run baselines
    print("\n📊 Running baseline models...")
    lv_results = last_value_forecast(train, test)
    ma_results = moving_average_forecast(train, test)

    lv_mae = mae(lv_results["actual"].values, lv_results["predicted"].values)
    lv_mape = mape(lv_results["actual"].values, lv_results["predicted"].values)
    ma_mae = mae(ma_results["actual"].values, ma_results["predicted"].values)
    ma_mape = mape(ma_results["actual"].values, ma_results["predicted"].values)

    print(f"   Last Value:    MAE={lv_mae:.2f}, MAPE={lv_mape:.1f}%")
    print(f"   Moving Avg:    MAE={ma_mae:.2f}, MAPE={ma_mape:.1f}%")

    # Run Prophet
    print("\n🔮 Training Prophet models (per-SKU)...")
    prophet_results = prophet_forecast(train, test)

    if prophet_results.empty:
        print("   ⚠️ Not enough data for Prophet. Skipping.")
        return

    p_mae = mae(prophet_results["actual"].values, prophet_results["predicted"].values)
    p_mape = mape(prophet_results["actual"].values, prophet_results["predicted"].values)
    print(f"   Prophet:       MAE={p_mae:.2f}, MAPE={p_mape:.1f}%")

    # Comparison table
    print("\n" + "=" * 60)
    print("  MODEL COMPARISON")
    print("=" * 60)
    print(f"  {'Model':<25} {'MAE':>8} {'MAPE':>10}")
    print(f"  {'-'*25} {'-'*8} {'-'*10}")
    print(f"  {'Last Value':<25} {lv_mae:>8.2f} {lv_mape:>9.1f}%")
    print(f"  {'Moving Average (3m)':<25} {ma_mae:>8.2f} {ma_mape:>9.1f}%")
    print(f"  {'Prophet':<25} {p_mae:>8.2f} {p_mape:>9.1f}%")
    print("=" * 60)

    # Determine winner
    models = {
        "Last Value": (lv_mae, lv_mape),
        "Moving Average": (ma_mae, ma_mape),
        "Prophet": (p_mae, p_mape),
    }
    best_model = min(models, key=lambda x: models[x][0])
    print(f"\n🏆 Best Model (by MAE): {best_model}")

    # Analysis
    if best_model == "Prophet":
        print("\n📝 Prophet outperforms baselines because it captures:")
        print("   - Yearly seasonality (monsoon dips, festival peaks)")
        print("   - Overall growth trend in the data")
        print("   - More nuanced than simple last-value or average")
    else:
        print(f"\n📝 {best_model} performs better, likely because:")
        print("   - Limited data (18 months) constrains Prophet's ability to learn seasonality")
        print("   - The data may have a strong recent trend that simple methods capture well")
        print("   - Prophet's uncertainty increases with less training data")

    # Generate chart
    chart_path = os.path.join(OUTPUT_DIR, "forecast_comparison.png")
    plot_comparison(lv_results, ma_results, prophet_results, chart_path)

    print("\n✅ Forecasting pipeline complete!\n")


if __name__ == "__main__":
    run_forecasting()

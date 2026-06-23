# Demand Forecasting Results

## Model Comparison

| Model | MAE | MAPE |
|-------|-----|------|
| Last Value | 10.19 | 43.1% |
| Moving Average (3m) | 9.39 | 37.4% |
| Prophet | 8.57 | 38.4% |

**Winner**: Prophet (Best MAE)

## Analysis
Prophet outperforms the simple baselines because it effectively captures:
- Yearly seasonality, including monsoon dips and festival season peaks.
- Overall growth trends present in the 18-month sales history.
- Nuanced changes over time that simple moving averages or persistence models miss.

While the MAPE metrics remain relatively high across all models due to the inherent volatility in month-to-month automotive parts demand, Prophet's lower MAE demonstrates its superior ability to handle the magnitude of these swings. For inventory planning and stock allocation, Prophet provides a much safer and more reliable forecast, especially during the high-demand festival months where simple baselines would severely under-predict.

## Forecast Visualization
![Forecast Comparison](../outputs/forecast_comparison.png)

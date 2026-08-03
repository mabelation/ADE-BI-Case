from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.holtwinters import ExponentialSmoothing


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CANONICAL_PATH: Final[Path] = (
    PROJECT_ROOT / "data" / "curated" / "fact_sales_canonical.parquet"
)
FORECAST_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "forecast_2026_s2.csv"
)
BACKTEST_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "forecast_backtesting.csv"
)
MONTHLY_SERIES_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "forecast_monthly_history.csv"
)

FORECAST_MONTHS: Final[list[str]] = [
    "2026-07", "2026-08", "2026-09",
    "2026-10", "2026-11", "2026-12",
]


def load_monthly_family_series() -> pd.DataFrame:
    sales = pd.read_parquet(CANONICAL_PATH)
    sales = sales.loc[~sales["is_intercompany"].fillna(False)].copy()

    monthly = (
        sales.groupby(["year_month", "product_family"], as_index=False)
        .agg(
            quantity_tons=("quantity_tons", "sum"),
            net_sales_eur=("net_sales_eur", "sum"),
        )
    )

    all_months = pd.period_range("2024-01", "2026-06", freq="M").astype(str)
    families = sorted(monthly["product_family"].dropna().unique())

    complete_index = pd.MultiIndex.from_product(
        [all_months, families],
        names=["year_month", "product_family"],
    )

    monthly = (
        monthly.set_index(["year_month", "product_family"])
        .reindex(complete_index, fill_value=0)
        .reset_index()
    )

    return monthly


def seasonal_naive(train: np.ndarray, horizon: int) -> np.ndarray:
    if len(train) >= 12:
        repeats = int(np.ceil(horizon / 12))
        return np.tile(train[-12:], repeats)[:horizon]
    return np.repeat(train[-1], horizon)


def linear_trend(train: np.ndarray, horizon: int) -> np.ndarray:
    x = np.arange(len(train)).reshape(-1, 1)
    model = LinearRegression().fit(x, train)
    future_x = np.arange(len(train), len(train) + horizon).reshape(-1, 1)
    return np.maximum(model.predict(future_x), 0)


def ets_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    try:
        if len(train) >= 24 and np.all(train >= 0):
            model = ExponentialSmoothing(
                train,
                trend="add",
                seasonal="add",
                seasonal_periods=12,
                initialization_method="estimated",
            ).fit(optimized=True)
        else:
            model = ExponentialSmoothing(
                train,
                trend="add",
                seasonal=None,
                initialization_method="estimated",
            ).fit(optimized=True)

        return np.maximum(np.asarray(model.forecast(horizon)), 0)
    except Exception:
        return linear_trend(train, horizon)


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    denominator = np.abs(actual).sum()

    return {
        "mae": float(np.mean(np.abs(error))),
        "wape": float(np.abs(error).sum() / denominator) if denominator else np.nan,
        "bias": float(error.sum() / denominator) if denominator else np.nan,
    }


def evaluate_models(series: np.ndarray) -> pd.DataFrame:
    # Dos cortes honestos de seis meses:
    # train hasta 2025-06 -> valida 2025-S2
    # train hasta 2025-12 -> valida 2026-S1
    cutoffs = [18, 24]
    rows: list[dict[str, object]] = []

    model_functions = {
        "seasonal_naive": seasonal_naive,
        "linear_trend": linear_trend,
        "ets": ets_forecast,
    }

    for cutoff in cutoffs:
        train = series[:cutoff]
        actual = series[cutoff:cutoff + 6]

        for model_name, model_function in model_functions.items():
            predicted = model_function(train, 6)
            result = metrics(actual, predicted)

            rows.append(
                {
                    "cutoff_month": "2025-06" if cutoff == 18 else "2025-12",
                    "model": model_name,
                    **result,
                }
            )

    return pd.DataFrame(rows)


def build_forecast() -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = load_monthly_family_series()
    MONTHLY_SERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(MONTHLY_SERIES_PATH, index=False, encoding="utf-8-sig")

    forecast_rows: list[dict[str, object]] = []
    backtest_rows: list[pd.DataFrame] = []

    for family, family_data in monthly.groupby("product_family"):
        family_data = family_data.sort_values("year_month")
        quantity_series = family_data["quantity_tons"].to_numpy(dtype=float)
        sales_series = family_data["net_sales_eur"].to_numpy(dtype=float)

        quantity_eval = evaluate_models(quantity_series)
        quantity_eval["product_family"] = family
        quantity_eval["target"] = "quantity_tons"

        sales_eval = evaluate_models(sales_series)
        sales_eval["product_family"] = family
        sales_eval["target"] = "net_sales_eur"

        backtest_rows.extend([quantity_eval, sales_eval])

        quantity_summary = (
            quantity_eval.groupby("model", as_index=False)
            .agg(wape=("wape", "mean"), mae=("mae", "mean"), bias=("bias", "mean"))
            .sort_values(["wape", "mae"])
        )
        sales_summary = (
            sales_eval.groupby("model", as_index=False)
            .agg(wape=("wape", "mean"), mae=("mae", "mean"), bias=("bias", "mean"))
            .sort_values(["wape", "mae"])
        )

        best_quantity_model = quantity_summary.iloc[0]["model"]
        best_sales_model = sales_summary.iloc[0]["model"]

        functions = {
            "seasonal_naive": seasonal_naive,
            "linear_trend": linear_trend,
            "ets": ets_forecast,
        }

        quantity_forecast = functions[best_quantity_model](quantity_series, 6)
        sales_forecast = functions[best_sales_model](sales_series, 6)

        for month, qty, sales_value in zip(
            FORECAST_MONTHS,
            quantity_forecast,
            sales_forecast,
        ):
            forecast_rows.append(
                {
                    "month": month,
                    "product_family": family,
                    "forecast_quantity_tons": float(qty),
                    "forecast_net_sales_eur": float(sales_value),
                    "quantity_model": best_quantity_model,
                    "sales_model": best_sales_model,
                    "quantity_backtest_wape": float(quantity_summary.iloc[0]["wape"]),
                    "sales_backtest_wape": float(sales_summary.iloc[0]["wape"]),
                }
            )

    forecast = pd.DataFrame(forecast_rows)
    backtesting = pd.concat(backtest_rows, ignore_index=True)

    forecast.to_csv(
        FORECAST_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )
    backtesting.to_csv(
        BACKTEST_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Forecast — completado")
    print(f"Archivo forecast: {FORECAST_OUTPUT_PATH}")
    print(f"Backtesting: {BACKTEST_OUTPUT_PATH}")
    print()
    print("Forecast total 2026-S2:")
    print(
        forecast.groupby("month", as_index=False)
        .agg(
            forecast_quantity_tons=("forecast_quantity_tons", "sum"),
            forecast_net_sales_eur=("forecast_net_sales_eur", "sum"),
        )
        .to_string(index=False)
    )

    return forecast, backtesting


if __name__ == "__main__":
    build_forecast()

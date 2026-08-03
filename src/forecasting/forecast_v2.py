from __future__ import annotations

from pathlib import Path
from typing import Callable, Final

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.holtwinters import ExponentialSmoothing


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

CANONICAL_PATH: Final[Path] = (
    PROJECT_ROOT / "data" / "curated" / "fact_sales_canonical.parquet"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "forecast_v2_2026_s2.csv"
)

BACKTEST_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "forecast_v2_backtesting.csv"
)

SUMMARY_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "forecast_v2_summary.csv"
)

FORECAST_MONTHS: Final[list[str]] = [
    "2026-07",
    "2026-08",
    "2026-09",
    "2026-10",
    "2026-11",
    "2026-12",
]

ModelFunction = Callable[[np.ndarray, int], np.ndarray]


def seasonal_naive(train: np.ndarray, horizon: int) -> np.ndarray:
    """Repite los valores de los mismos meses del año anterior."""

    if len(train) >= 12:
        return np.asarray(
            [train[len(train) - 12 + index] for index in range(horizon)],
            dtype=float,
        )

    return np.repeat(train[-1], horizon).astype(float)


def linear_trend(train: np.ndarray, horizon: int) -> np.ndarray:
    """Proyecta una tendencia lineal no negativa."""

    x_train = np.arange(len(train)).reshape(-1, 1)
    x_future = np.arange(
        len(train),
        len(train) + horizon,
    ).reshape(-1, 1)

    model = LinearRegression()
    model.fit(x_train, train)

    return np.maximum(
        model.predict(x_future),
        0,
    )


def ets_forecast(train: np.ndarray, horizon: int) -> np.ndarray:
    """Ajusta ETS con estacionalidad cuando existe historia suficiente."""

    try:
        if len(train) >= 24:
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

        return np.maximum(
            np.asarray(model.forecast(horizon)),
            0,
        )

    except Exception:
        return linear_trend(train, horizon)


MODEL_FUNCTIONS: Final[dict[str, ModelFunction]] = {
    "seasonal_naive": seasonal_naive,
    "linear_trend": linear_trend,
    "ets": ets_forecast,
}


def calculate_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> dict[str, float]:
    """Calcula WAPE, MAE, RMSE y bias."""

    error = predicted - actual
    denominator = np.abs(actual).sum()

    return {
        "wape": (
            float(np.abs(error).sum() / denominator)
            if denominator > 0
            else np.nan
        ),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": (
            float(error.sum() / denominator)
            if denominator > 0
            else np.nan
        ),
    }


def forecast_interval(
    point_forecast: np.ndarray,
    residuals: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Construye intervalo aproximado del 95% con residuos de backtesting.

    No se interpreta como intervalo probabilístico exacto; representa
    incertidumbre empírica basada en errores fuera de muestra.
    """

    residual_std = float(np.nanstd(residuals, ddof=1))

    if not np.isfinite(residual_std):
        residual_std = 0.0

    lower = np.maximum(
        point_forecast - 1.96 * residual_std,
        0,
    )
    upper = point_forecast + 1.96 * residual_std

    return lower, upper


def load_monthly_family_data() -> pd.DataFrame:
    """Construye volumen, venta y precio medio mensual por familia."""

    sales = pd.read_parquet(CANONICAL_PATH)

    sales = sales.loc[
        ~sales["is_intercompany"].fillna(False)
    ].copy()

    monthly = (
        sales.groupby(
            [
                "year_month",
                "product_family",
            ],
            as_index=False,
        )
        .agg(
            quantity_tons=("quantity_tons", "sum"),
            net_sales_eur=("net_sales_eur", "sum"),
        )
    )

    monthly["average_price_eur_per_ton"] = np.where(
        monthly["quantity_tons"] > 0,
        monthly["net_sales_eur"] / monthly["quantity_tons"],
        np.nan,
    )

    all_months = pd.period_range(
        "2024-01",
        "2026-06",
        freq="M",
    ).astype(str)

    families = sorted(
        monthly["product_family"]
        .dropna()
        .unique()
        .tolist()
    )

    complete_index = pd.MultiIndex.from_product(
        [
            all_months,
            families,
        ],
        names=[
            "year_month",
            "product_family",
        ],
    )

    monthly = (
        monthly.set_index(
            [
                "year_month",
                "product_family",
            ]
        )
        .reindex(complete_index)
        .reset_index()
    )

    monthly["quantity_tons"] = (
        monthly["quantity_tons"]
        .fillna(0)
    )

    monthly["net_sales_eur"] = (
        monthly["net_sales_eur"]
        .fillna(0)
    )

    monthly["average_price_eur_per_ton"] = (
        monthly.groupby(
            "product_family",
            group_keys=False,
        )["average_price_eur_per_ton"]
        .transform(
            lambda series: (
                series.interpolate(
                    method="linear",
                    limit_direction="both",
                )
                .ffill()
                .bfill()
            )
        )
    )

    return monthly


def evaluate_models(
    series: np.ndarray,
    target_name: str,
    product_family: str,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Ejecuta dos ventanas de backtesting de seis meses."""

    rows: list[dict[str, object]] = []
    residuals_by_model: dict[str, list[float]] = {
        name: []
        for name in MODEL_FUNCTIONS
    }

    cutoffs = {
        "2025-S2": 18,
        "2026-S1": 24,
    }

    for validation_period, cutoff in cutoffs.items():
        train = series[:cutoff]
        actual = series[cutoff:cutoff + 6]

        for model_name, model_function in MODEL_FUNCTIONS.items():
            predicted = model_function(
                train,
                6,
            )

            model_metrics = calculate_metrics(
                actual,
                predicted,
            )

            residuals_by_model[model_name].extend(
                (actual - predicted).tolist()
            )

            rows.append(
                {
                    "product_family": product_family,
                    "target": target_name,
                    "validation_period": validation_period,
                    "model": model_name,
                    **model_metrics,
                }
            )

    residual_arrays = {
        name: np.asarray(values, dtype=float)
        for name, values in residuals_by_model.items()
    }

    return pd.DataFrame(rows), residual_arrays


def select_best_model(
    evaluation: pd.DataFrame,
) -> str:
    """Elige el modelo por WAPE, usando MAE como desempate."""

    summary = (
        evaluation.groupby(
            "model",
            as_index=False,
        )
        .agg(
            average_wape=("wape", "mean"),
            average_mae=("mae", "mean"),
            average_bias=("bias", "mean"),
        )
        .sort_values(
            [
                "average_wape",
                "average_mae",
                "average_bias",
            ],
            key=lambda series: (
                series.abs()
                if series.name == "average_bias"
                else series
            ),
        )
    )

    return str(summary.iloc[0]["model"])


def build_forecast_v2() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Pronostica volumen y precio por separado.

    Revenue V2 = forecast toneladas × forecast precio medio EUR/t.
    """

    monthly = load_monthly_family_data()

    forecast_rows: list[dict[str, object]] = []
    backtest_frames: list[pd.DataFrame] = []

    for product_family, family_data in monthly.groupby(
        "product_family"
    ):
        family_data = family_data.sort_values(
            "year_month"
        )

        volume_series = family_data[
            "quantity_tons"
        ].to_numpy(dtype=float)

        price_series = family_data[
            "average_price_eur_per_ton"
        ].to_numpy(dtype=float)

        volume_eval, volume_residuals = evaluate_models(
            volume_series,
            "quantity_tons",
            str(product_family),
        )

        price_eval, price_residuals = evaluate_models(
            price_series,
            "average_price_eur_per_ton",
            str(product_family),
        )

        backtest_frames.extend(
            [
                volume_eval,
                price_eval,
            ]
        )

        best_volume_model = select_best_model(
            volume_eval
        )
        best_price_model = select_best_model(
            price_eval
        )

        volume_forecast = MODEL_FUNCTIONS[
            best_volume_model
        ](
            volume_series,
            6,
        )

        price_forecast = MODEL_FUNCTIONS[
            best_price_model
        ](
            price_series,
            6,
        )

        volume_lower, volume_upper = forecast_interval(
            volume_forecast,
            volume_residuals[best_volume_model],
        )

        price_lower, price_upper = forecast_interval(
            price_forecast,
            price_residuals[best_price_model],
        )

        revenue_forecast = (
            volume_forecast
            * price_forecast
        )

        revenue_lower = (
            volume_lower
            * price_lower
        )

        revenue_upper = (
            volume_upper
            * price_upper
        )

        volume_wape = float(
            volume_eval.loc[
                volume_eval["model"] == best_volume_model,
                "wape",
            ].mean()
        )

        price_wape = float(
            price_eval.loc[
                price_eval["model"] == best_price_model,
                "wape",
            ].mean()
        )

        for index, month in enumerate(
            FORECAST_MONTHS
        ):
            forecast_rows.append(
                {
                    "month": month,
                    "product_family": product_family,
                    "forecast_quantity_tons": volume_forecast[index],
                    "quantity_lower_95": volume_lower[index],
                    "quantity_upper_95": volume_upper[index],
                    "forecast_price_eur_per_ton": price_forecast[index],
                    "price_lower_95": price_lower[index],
                    "price_upper_95": price_upper[index],
                    "forecast_revenue_eur": revenue_forecast[index],
                    "revenue_lower_95": revenue_lower[index],
                    "revenue_upper_95": revenue_upper[index],
                    "quantity_model": best_volume_model,
                    "price_model": best_price_model,
                    "quantity_backtest_wape": volume_wape,
                    "price_backtest_wape": price_wape,
                }
            )

    forecast = pd.DataFrame(
        forecast_rows
    )

    backtesting = pd.concat(
        backtest_frames,
        ignore_index=True,
    )

    monthly_total = (
        forecast.groupby(
            "month",
            as_index=False,
        )
        .agg(
            forecast_quantity_tons=(
                "forecast_quantity_tons",
                "sum",
            ),
            quantity_lower_95=(
                "quantity_lower_95",
                "sum",
            ),
            quantity_upper_95=(
                "quantity_upper_95",
                "sum",
            ),
            forecast_revenue_eur=(
                "forecast_revenue_eur",
                "sum",
            ),
            revenue_lower_95=(
                "revenue_lower_95",
                "sum",
            ),
            revenue_upper_95=(
                "revenue_upper_95",
                "sum",
            ),
        )
    )

    monthly_total[
        "forecast_price_eur_per_ton"
    ] = (
        monthly_total["forecast_revenue_eur"]
        / monthly_total["forecast_quantity_tons"]
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    forecast.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    backtesting.to_csv(
        BACKTEST_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    monthly_total.to_csv(
        SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Forecast V2 — completado")
    print(f"Detalle: {OUTPUT_PATH}")
    print(f"Backtesting: {BACKTEST_PATH}")
    print(f"Resumen mensual: {SUMMARY_PATH}")
    print()
    print("Forecast descompuesto 2026-S2:")
    print(
        monthly_total.to_string(
            index=False
        )
    )

    print()
    print(
        "Totales H2 — "
        f"Volumen: {monthly_total['forecast_quantity_tons'].sum():,.2f} t | "
        f"Revenue: €{monthly_total['forecast_revenue_eur'].sum():,.2f}"
    )

    return forecast, backtesting


if __name__ == "__main__":
    build_forecast_v2()

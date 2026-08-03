from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

FORECAST_V2_SUMMARY_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "forecast_v2_summary.csv"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "forecast_v3_scenarios.csv"
)

SUMMARY_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "forecast_v3_scenario_summary.csv"
)


# Escenarios comerciales sencillos y defendibles.
#
# Pesimista:
# - Volumen 5% por debajo del escenario base.
# - Precio medio 2% por debajo del escenario base.
#
# Optimista:
# - Volumen 5% por encima del escenario base.
# - Precio medio 2% por encima del escenario base.
#
# La sensibilidad mantiene separados los dos motores del revenue:
# demanda física y precio medio.
SCENARIO_ASSUMPTIONS: Final[dict[str, dict[str, float]]] = {
    "PESSIMISTIC": {
        "volume_factor": 0.95,
        "price_factor": 0.98,
    },
    "BASE": {
        "volume_factor": 1.00,
        "price_factor": 1.00,
    },
    "OPTIMISTIC": {
        "volume_factor": 1.05,
        "price_factor": 1.02,
    },
}


def load_forecast_v2_summary() -> pd.DataFrame:
    """Carga y valida el resumen mensual del Forecast V2."""

    if not FORECAST_V2_SUMMARY_PATH.exists():
        raise FileNotFoundError(
            "No existe el resumen de Forecast V2: "
            f"{FORECAST_V2_SUMMARY_PATH}"
        )

    forecast = pd.read_csv(
        FORECAST_V2_SUMMARY_PATH
    )

    required_columns = {
        "month",
        "forecast_quantity_tons",
        "forecast_revenue_eur",
        "forecast_price_eur_per_ton",
        "quantity_lower_95",
        "quantity_upper_95",
        "revenue_lower_95",
        "revenue_upper_95",
    }

    missing_columns = (
        required_columns
        - set(forecast.columns)
    )

    if missing_columns:
        raise ValueError(
            "Forecast V2 no contiene las columnas requeridas: "
            f"{sorted(missing_columns)}"
        )

    return forecast


def build_scenario_rows(
    base_forecast: pd.DataFrame,
) -> pd.DataFrame:
    """
    Crea escenario pesimista, base y optimista.

    Revenue se recalcula siempre como:
    toneladas del escenario × precio medio del escenario.
    """

    scenario_frames: list[pd.DataFrame] = []

    for scenario_name, assumptions in (
        SCENARIO_ASSUMPTIONS.items()
    ):
        scenario = base_forecast.copy()

        scenario["scenario"] = (
            scenario_name
        )

        scenario["volume_factor"] = (
            assumptions["volume_factor"]
        )

        scenario["price_factor"] = (
            assumptions["price_factor"]
        )

        scenario[
            "scenario_quantity_tons"
        ] = (
            scenario["forecast_quantity_tons"]
            * scenario["volume_factor"]
        )

        scenario[
            "scenario_price_eur_per_ton"
        ] = (
            scenario[
                "forecast_price_eur_per_ton"
            ]
            * scenario["price_factor"]
        )

        scenario[
            "scenario_revenue_eur"
        ] = (
            scenario[
                "scenario_quantity_tons"
            ]
            * scenario[
                "scenario_price_eur_per_ton"
            ]
        )

        scenario[
            "revenue_change_vs_base_eur"
        ] = (
            scenario[
                "scenario_revenue_eur"
            ]
            - scenario[
                "forecast_revenue_eur"
            ]
        )

        scenario[
            "revenue_change_vs_base_pct"
        ] = (
            scenario[
                "scenario_revenue_eur"
            ]
            / scenario[
                "forecast_revenue_eur"
            ]
            - 1
        )

        scenario_frames.append(
            scenario
        )

    return pd.concat(
        scenario_frames,
        ignore_index=True,
    )


def create_scenario_summary(
    scenarios: pd.DataFrame,
) -> pd.DataFrame:
    """Resume volumen, precio medio y revenue por escenario."""

    summary = (
        scenarios.groupby(
            "scenario",
            as_index=False,
        )
        .agg(
            h2_quantity_tons=(
                "scenario_quantity_tons",
                "sum",
            ),
            h2_revenue_eur=(
                "scenario_revenue_eur",
                "sum",
            ),
            revenue_change_vs_base_eur=(
                "revenue_change_vs_base_eur",
                "sum",
            ),
        )
    )

    summary[
        "weighted_average_price_eur_per_ton"
    ] = (
        summary["h2_revenue_eur"]
        / summary["h2_quantity_tons"]
    )

    base_revenue = float(
        summary.loc[
            summary["scenario"] == "BASE",
            "h2_revenue_eur",
        ].iloc[0]
    )

    summary[
        "revenue_change_vs_base_pct"
    ] = (
        summary["h2_revenue_eur"]
        / base_revenue
        - 1
    )

    scenario_order = pd.CategoricalDtype(
        categories=[
            "PESSIMISTIC",
            "BASE",
            "OPTIMISTIC",
        ],
        ordered=True,
    )

    summary["scenario"] = (
        summary["scenario"]
        .astype(scenario_order)
    )

    return summary.sort_values(
        "scenario"
    ).reset_index(drop=True)


def build_forecast_v3_scenarios() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """Genera y guarda los escenarios del Forecast V3."""

    base_forecast = (
        load_forecast_v2_summary()
    )

    scenarios = build_scenario_rows(
        base_forecast
    )

    summary = create_scenario_summary(
        scenarios
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    scenarios.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    summary.to_csv(
        SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        "Forecast V3 / Scenario Planning — completado"
    )
    print(
        f"Detalle mensual: {OUTPUT_PATH}"
    )
    print(
        f"Resumen escenarios: {SUMMARY_PATH}"
    )
    print()
    print(
        "Supuestos:"
    )
    print(
        "PESSIMISTIC = volumen -5%, precio -2%"
    )
    print(
        "BASE        = Forecast V2"
    )
    print(
        "OPTIMISTIC  = volumen +5%, precio +2%"
    )
    print()
    print(
        "Resumen 2026-S2:"
    )
    print(
        summary.to_string(
            index=False
        )
    )

    return scenarios, summary


if __name__ == "__main__":
    build_forecast_v3_scenarios()

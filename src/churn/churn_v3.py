from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

CUSTOMER_HEALTH_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "customer_health_index.csv"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "customer_recovery_priority.csv"
)

SUMMARY_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "customer_recovery_priority_summary.csv"
)


def min_max_score(series: pd.Series) -> pd.Series:
    """Normaliza una variable a una escala de 0 a 100."""

    minimum = float(series.min())
    maximum = float(series.max())

    if maximum == minimum:
        return pd.Series(
            np.repeat(50.0, len(series)),
            index=series.index,
        )

    return (
        (series - minimum)
        / (maximum - minimum)
        * 100
    )


def load_customer_health() -> pd.DataFrame:
    """Carga y valida la salida de Customer Health V2."""

    if not CUSTOMER_HEALTH_PATH.exists():
        raise FileNotFoundError(
            "No existe Customer Health V2: "
            f"{CUSTOMER_HEALTH_PATH}"
        )

    customers = pd.read_csv(
        CUSTOMER_HEALTH_PATH
    )

    required_columns = {
        "customer_global_id",
        "customer_name",
        "customer_country",
        "customer_segment",
        "customer_health_index",
        "health_status",
        "churn_risk_score",
        "value_at_risk_eur",
        "sales_12m_eur",
        "margin_12m_eur",
        "margin_pct_12m",
        "recency_days",
        "health_drivers",
        "recommended_action",
    }

    missing_columns = (
        required_columns
        - set(customers.columns)
    )

    if missing_columns:
        raise ValueError(
            "Customer Health V2 no contiene las columnas requeridas: "
            f"{sorted(missing_columns)}"
        )

    return customers


def calculate_recovery_priority(
    customers: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calcula prioridad de recuperación.

    La prioridad combina:
    - 45% valor económico en riesgo
    - 35% riesgo de churn
    - 20% margen absoluto recuperable

    Se usa margen absoluto positivo para priorizar cuentas que,
    además de vender, aportan valor económico recuperable.
    """

    customers = customers.copy()

    customers["positive_margin_eur"] = (
        customers["margin_12m_eur"]
        .clip(lower=0)
    )

    customers["value_risk_component"] = min_max_score(
        customers["value_at_risk_eur"]
    )

    customers["churn_risk_component"] = (
        customers["churn_risk_score"]
        .clip(lower=0, upper=100)
    )

    customers["margin_component"] = min_max_score(
        customers["positive_margin_eur"]
    )

    customers["recovery_priority_score"] = (
        0.45 * customers["value_risk_component"]
        + 0.35 * customers["churn_risk_component"]
        + 0.20 * customers["margin_component"]
    ).round(1)

    customers["recovery_priority_level"] = pd.cut(
        customers["recovery_priority_score"],
        bins=[
            -np.inf,
            50,
            70,
            85,
            np.inf,
        ],
        labels=[
            "MONITOR",
            "MEDIUM",
            "HIGH",
            "IMMEDIATE",
        ],
    )

    customers["recommended_timing"] = (
        customers["recovery_priority_level"]
        .astype("string")
        .map(
            {
                "IMMEDIATE": "Contact within 24-48 hours",
                "HIGH": "Commercial visit this week",
                "MEDIUM": "Account review this month",
                "MONITOR": "Monthly monitoring",
            }
        )
    )

    customers["commercial_owner_action"] = np.select(
        [
            customers["recovery_priority_level"]
            .astype("string")
            .eq("IMMEDIATE"),
            customers["recovery_priority_level"]
            .astype("string")
            .eq("HIGH"),
            customers["recovery_priority_level"]
            .astype("string")
            .eq("MEDIUM"),
        ],
        [
            (
                "Assign senior account owner, confirm recovery plan, "
                "pricing conditions and next-order commitment"
            ),
            (
                "Schedule commercial visit, diagnose decline drivers "
                "and define 30-day recovery actions"
            ),
            (
                "Review account performance, discounts and purchase frequency"
            ),
        ],
        default=(
            "Keep automated monthly monitoring and cross-sell review"
        ),
    )

    return customers


def build_customer_recovery_priority() -> pd.DataFrame:
    """Genera ranking económico de recuperación comercial."""

    customers = load_customer_health()

    prioritized = calculate_recovery_priority(
        customers
    )

    status_order = pd.CategoricalDtype(
        categories=[
            "IMMEDIATE",
            "HIGH",
            "MEDIUM",
            "MONITOR",
        ],
        ordered=True,
    )

    prioritized["recovery_priority_level"] = (
        prioritized["recovery_priority_level"]
        .astype("string")
        .astype(status_order)
    )

    prioritized = prioritized.sort_values(
        [
            "recovery_priority_level",
            "recovery_priority_score",
            "value_at_risk_eur",
        ],
        ascending=[
            True,
            False,
            False,
        ],
    ).reset_index(drop=True)

    prioritized["recovery_rank"] = (
        np.arange(len(prioritized))
        + 1
    )

    output_columns = [
        "recovery_rank",
        "customer_global_id",
        "customer_name",
        "customer_country",
        "customer_segment",
        "customer_health_index",
        "health_status",
        "churn_risk_score",
        "value_at_risk_eur",
        "sales_12m_eur",
        "margin_12m_eur",
        "margin_pct_12m",
        "recovery_priority_score",
        "recovery_priority_level",
        "recommended_timing",
        "recency_days",
        "health_drivers",
        "recommended_action",
        "commercial_owner_action",
    ]

    prioritized[output_columns].to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    summary = (
        prioritized.groupby(
            "recovery_priority_level",
            observed=True,
            as_index=False,
        )
        .agg(
            customers=("customer_global_id", "nunique"),
            sales_12m_eur=("sales_12m_eur", "sum"),
            value_at_risk_eur=("value_at_risk_eur", "sum"),
            margin_12m_eur=("margin_12m_eur", "sum"),
            average_priority_score=(
                "recovery_priority_score",
                "mean",
            ),
        )
    )

    summary.to_csv(
        SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Customer Health V3 / Recovery Priority — completado")
    print(f"Ranking: {OUTPUT_PATH}")
    print(f"Resumen: {SUMMARY_PATH}")
    print()
    print("Resumen de prioridad:")
    print(
        summary.to_string(
            index=False
        )
    )
    print()
    print("Top 10 cuentas a recuperar:")
    print(
        prioritized[
            output_columns
        ]
        .head(10)
        .to_string(index=False)
    )

    return prioritized[output_columns]


if __name__ == "__main__":
    build_customer_recovery_priority()

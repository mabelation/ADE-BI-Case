from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

CANONICAL_PATH: Final[Path] = (
    PROJECT_ROOT / "data" / "curated" / "fact_sales_canonical.parquet"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "customer_health_index.csv"
)

SUMMARY_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "customer_health_summary.csv"
)

ACTIONS_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "customer_health_actions.csv"
)

REFERENCE_DATE: Final[pd.Timestamp] = pd.Timestamp("2026-06-30")


def safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    """Divide evitando infinitos y divisiones entre cero."""

    result = np.where(
        denominator != 0,
        numerator / denominator,
        0.0,
    )

    return pd.Series(
        result,
        index=numerator.index,
        dtype="float64",
    )


def percentile_health(
    series: pd.Series,
    higher_is_better: bool,
) -> pd.Series:
    """
    Convierte una variable a puntuación de salud entre 0 y 100.

    Usa percentiles para mantener comparabilidad entre indicadores.
    """

    rank = series.rank(
        pct=True,
        method="average",
    )

    health = (
        rank
        if higher_is_better
        else 1 - rank
    )

    return health * 100


def load_customer_data() -> pd.DataFrame:
    """Carga ventas finales y construye métricas por cliente."""

    sales = pd.read_parquet(
        CANONICAL_PATH
    )

    sales = sales.loc[
        ~sales["is_intercompany"].fillna(False)
    ].copy()

    sales["invoice_date"] = pd.to_datetime(
        sales["invoice_date"],
        errors="coerce",
    )

    recent_12m = sales.loc[
        (sales["invoice_date"] >= "2025-07-01")
        & (sales["invoice_date"] <= REFERENCE_DATE)
    ].copy()

    previous_12m = sales.loc[
        (sales["invoice_date"] >= "2024-07-01")
        & (sales["invoice_date"] <= "2025-06-30")
    ].copy()

    recent = (
        recent_12m.groupby(
            [
                "customer_global_id",
                "customer_name",
                "customer_country",
                "customer_segment",
            ],
            as_index=False,
        )
        .agg(
            last_purchase_date=("invoice_date", "max"),
            sales_12m_eur=("net_sales_eur", "sum"),
            margin_12m_eur=("gross_margin_eur", "sum"),
            tons_12m=("quantity_tons", "sum"),
            invoices_12m=("invoice_id", "nunique"),
            active_months_12m=("year_month", "nunique"),
            product_families_12m=("product_family", "nunique"),
        )
    )

    previous = (
        previous_12m.groupby(
            "customer_global_id",
            as_index=False,
        )
        .agg(
            previous_sales_12m_eur=("net_sales_eur", "sum"),
            previous_margin_12m_eur=("gross_margin_eur", "sum"),
            previous_invoices_12m=("invoice_id", "nunique"),
            previous_active_months_12m=("year_month", "nunique"),
            previous_product_families_12m=("product_family", "nunique"),
        )
    )

    customers = recent.merge(
        previous,
        on="customer_global_id",
        how="left",
    )

    numeric_fill_zero = [
        "previous_sales_12m_eur",
        "previous_margin_12m_eur",
        "previous_invoices_12m",
        "previous_active_months_12m",
        "previous_product_families_12m",
    ]

    customers[numeric_fill_zero] = (
        customers[numeric_fill_zero]
        .fillna(0)
    )

    customers["recency_days"] = (
        REFERENCE_DATE
        - customers["last_purchase_date"]
    ).dt.days

    customers["sales_change_pct"] = safe_divide(
        customers["sales_12m_eur"]
        - customers["previous_sales_12m_eur"],
        customers["previous_sales_12m_eur"],
    )

    customers["frequency_change_pct"] = safe_divide(
        customers["invoices_12m"]
        - customers["previous_invoices_12m"],
        customers["previous_invoices_12m"],
    )

    customers["margin_pct_12m"] = safe_divide(
        customers["margin_12m_eur"],
        customers["sales_12m_eur"],
    )

    previous_margin_pct = safe_divide(
        customers["previous_margin_12m_eur"],
        customers["previous_sales_12m_eur"],
    )

    customers["margin_change_pp"] = (
        customers["margin_pct_12m"]
        - previous_margin_pct
    ) * 100

    customers["portfolio_change"] = (
        customers["product_families_12m"]
        - customers["previous_product_families_12m"]
    )

    return customers


def calculate_health_components(
    customers: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula los cinco componentes del Customer Health Index."""

    customers = customers.copy()

    customers["recency_health"] = percentile_health(
        customers["recency_days"],
        higher_is_better=False,
    )

    customers["sales_trend_health"] = percentile_health(
        customers["sales_change_pct"],
        higher_is_better=True,
    )

    customers["frequency_health"] = percentile_health(
        customers["frequency_change_pct"],
        higher_is_better=True,
    )

    customers["margin_health"] = percentile_health(
        customers["margin_change_pp"],
        higher_is_better=True,
    )

    customers["portfolio_health"] = percentile_health(
        customers["portfolio_change"],
        higher_is_better=True,
    )

    customers["customer_health_index"] = (
        0.30 * customers["recency_health"]
        + 0.25 * customers["sales_trend_health"]
        + 0.20 * customers["frequency_health"]
        + 0.15 * customers["margin_health"]
        + 0.10 * customers["portfolio_health"]
    ).round(1)

    customers["health_status"] = pd.cut(
        customers["customer_health_index"],
        bins=[
            -np.inf,
            25,
            45,
            65,
            np.inf,
        ],
        labels=[
            "CRITICAL",
            "HIGH_RISK",
            "WATCH",
            "HEALTHY",
        ],
    )

    customers["churn_risk_score"] = (
        100
        - customers["customer_health_index"]
    ).round(1)

    customers["value_at_risk_eur"] = (
        customers["sales_12m_eur"]
        * customers["churn_risk_score"]
        / 100
    )

    return customers


def create_recommendations(
    customers: pd.DataFrame,
) -> pd.DataFrame:
    """Asigna razones principales y una acción comercial concreta."""

    customers = customers.copy()

    def build_reasons(row: pd.Series) -> str:
        reasons: list[str] = []

        if row["recency_days"] >= 120:
            reasons.append(
                f"{int(row['recency_days'])} days without purchase"
            )

        if row["sales_change_pct"] <= -0.25:
            reasons.append(
                f"sales down {abs(row['sales_change_pct']):.0%}"
            )

        if row["frequency_change_pct"] <= -0.25:
            reasons.append(
                f"frequency down {abs(row['frequency_change_pct']):.0%}"
            )

        if row["margin_change_pp"] <= -2:
            reasons.append(
                f"margin down {abs(row['margin_change_pp']):.1f} pp"
            )

        if row["portfolio_change"] < 0:
            reasons.append(
                f"portfolio reduced by {abs(int(row['portfolio_change']))} families"
            )

        return (
            "; ".join(reasons)
            if reasons
            else "moderate deterioration across indicators"
        )

    def recommend_action(row: pd.Series) -> str:
        if row["health_status"] == "CRITICAL":
            if row["sales_change_pct"] <= -0.50:
                return (
                    "Immediate commercial visit; identify lost volume, "
                    "review competitor activity and present recovery offer"
                )

            if row["recency_days"] >= 180:
                return (
                    "Reactivation campaign within 7 days; confirm account "
                    "status and purchasing plan"
                )

            return (
                "Assign recovery owner; review pricing, service issues "
                "and next-order commitment"
            )

        if row["health_status"] == "HIGH_RISK":
            if row["margin_change_pp"] <= -2:
                return (
                    "Review discounts and product mix; protect margin "
                    "while rebuilding frequency"
                )

            return (
                "Schedule account review; recover purchase frequency "
                "and monitor monthly"
            )

        if row["health_status"] == "WATCH":
            return (
                "Monitor monthly; trigger alert if sales or frequency "
                "declines again"
            )

        return (
            "Maintain relationship and identify cross-sell opportunities"
        )

    customers["health_drivers"] = customers.apply(
        build_reasons,
        axis=1,
    )

    customers["recommended_action"] = customers.apply(
        recommend_action,
        axis=1,
    )

    return customers


def build_customer_health_index() -> pd.DataFrame:
    """Genera Customer Health Index, resumen y plan de acción."""

    customers = load_customer_data()

    customers = calculate_health_components(
        customers
    )

    customers = create_recommendations(
        customers
    )

    status_order = pd.CategoricalDtype(
        categories=[
            "CRITICAL",
            "HIGH_RISK",
            "WATCH",
            "HEALTHY",
        ],
        ordered=True,
    )

    customers["health_status"] = (
        customers["health_status"]
        .astype("string")
        .astype(status_order)
    )

    customers = customers.sort_values(
        [
            "health_status",
            "value_at_risk_eur",
        ],
        ascending=[
            True,
            False,
        ],
    )

    output_columns = [
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
        "sales_change_pct",
        "frequency_change_pct",
        "margin_change_pp",
        "active_months_12m",
        "product_families_12m",
        "portfolio_change",
        "recency_health",
        "sales_trend_health",
        "frequency_health",
        "margin_health",
        "portfolio_health",
        "health_drivers",
        "recommended_action",
    ]

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    customers[output_columns].to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    summary = (
        customers.groupby(
            "health_status",
            observed=True,
            as_index=False,
        )
        .agg(
            customers=("customer_global_id", "nunique"),
            sales_12m_eur=("sales_12m_eur", "sum"),
            value_at_risk_eur=("value_at_risk_eur", "sum"),
            margin_12m_eur=("margin_12m_eur", "sum"),
            average_health_index=(
                "customer_health_index",
                "mean",
            ),
        )
    )

    summary.to_csv(
        SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    action_plan = customers.loc[
        customers["health_status"].isin(
            [
                "CRITICAL",
                "HIGH_RISK",
            ]
        ),
        [
            "customer_global_id",
            "customer_name",
            "customer_country",
            "customer_segment",
            "health_status",
            "customer_health_index",
            "value_at_risk_eur",
            "sales_12m_eur",
            "recency_days",
            "health_drivers",
            "recommended_action",
        ],
    ].copy()

    action_plan.to_csv(
        ACTIONS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Churn V2 / Customer Health — completado")
    print(f"Customer Health Index: {OUTPUT_PATH}")
    print(f"Resumen: {SUMMARY_PATH}")
    print(f"Plan de acción: {ACTIONS_PATH}")
    print()
    print("Resumen Customer Health:")
    print(
        summary.to_string(
            index=False
        )
    )
    print()
    print("Top 10 acciones prioritarias:")
    print(
        action_plan.head(10).to_string(
            index=False
        )
    )

    return customers[output_columns]


if __name__ == "__main__":
    build_customer_health_index()

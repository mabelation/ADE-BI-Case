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
    PROJECT_ROOT / "outputs" / "churn_prioritized.csv"
)
SUMMARY_PATH: Final[Path] = (
    PROJECT_ROOT / "outputs" / "churn_summary.csv"
)

REFERENCE_DATE: Final[pd.Timestamp] = pd.Timestamp("2026-06-30")


def percentile_score(series: pd.Series, higher_is_risk: bool = True) -> pd.Series:
    ranks = series.rank(pct=True, method="average")
    return ranks if higher_is_risk else 1 - ranks


def build_churn_risk() -> pd.DataFrame:
    sales = pd.read_parquet(CANONICAL_PATH)
    sales = sales.loc[~sales["is_intercompany"].fillna(False)].copy()
    sales["invoice_date"] = pd.to_datetime(sales["invoice_date"])

    last_12m = sales.loc[
        (sales["invoice_date"] >= "2025-07-01")
        & (sales["invoice_date"] <= REFERENCE_DATE)
    ].copy()

    previous_12m = sales.loc[
        (sales["invoice_date"] >= "2024-07-01")
        & (sales["invoice_date"] <= "2025-06-30")
    ].copy()

    customer_current = (
        last_12m.groupby(
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

    customer_previous = (
        previous_12m.groupby("customer_global_id", as_index=False)
        .agg(
            previous_sales_12m_eur=("net_sales_eur", "sum"),
            previous_tons_12m=("quantity_tons", "sum"),
            previous_invoices_12m=("invoice_id", "nunique"),
        )
    )

    customers = customer_current.merge(
        customer_previous,
        on="customer_global_id",
        how="left",
    )

    fill_zero = [
        "previous_sales_12m_eur",
        "previous_tons_12m",
        "previous_invoices_12m",
    ]
    customers[fill_zero] = customers[fill_zero].fillna(0)

    customers["recency_days"] = (
        REFERENCE_DATE - customers["last_purchase_date"]
    ).dt.days

    customers["sales_change_pct"] = np.where(
        customers["previous_sales_12m_eur"] > 0,
        (
            customers["sales_12m_eur"]
            - customers["previous_sales_12m_eur"]
        )
        / customers["previous_sales_12m_eur"],
        0,
    )

    customers["frequency_change_pct"] = np.where(
        customers["previous_invoices_12m"] > 0,
        (
            customers["invoices_12m"]
            - customers["previous_invoices_12m"]
        )
        / customers["previous_invoices_12m"],
        0,
    )

    # Score interpretable 0-100:
    # 35% recencia, 30% caída de venta, 20% baja frecuencia,
    # 15% poca actividad mensual.
    recency_risk = percentile_score(
        customers["recency_days"],
        higher_is_risk=True,
    )
    decline_risk = percentile_score(
        customers["sales_change_pct"],
        higher_is_risk=False,
    )
    frequency_risk = percentile_score(
        customers["frequency_change_pct"],
        higher_is_risk=False,
    )
    activity_risk = percentile_score(
        customers["active_months_12m"],
        higher_is_risk=False,
    )

    customers["churn_risk_score"] = (
        100
        * (
            0.35 * recency_risk
            + 0.30 * decline_risk
            + 0.20 * frequency_risk
            + 0.15 * activity_risk
        )
    ).round(1)

    customers["risk_level"] = pd.cut(
        customers["churn_risk_score"],
        bins=[-np.inf, 50, 70, 85, np.inf],
        labels=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    )

    customers["value_at_risk_eur"] = (
        customers["sales_12m_eur"]
        * customers["churn_risk_score"]
        / 100
    )

    customers["priority_score"] = (
        customers["value_at_risk_eur"]
        * (1 + customers["margin_12m_eur"].clip(lower=0) / customers["sales_12m_eur"].replace(0, np.nan))
    ).fillna(customers["value_at_risk_eur"])

    def reason(row: pd.Series) -> str:
        reasons: list[str] = []

        if row["recency_days"] >= 90:
            reasons.append(f"{int(row['recency_days'])} days since last purchase")
        if row["sales_change_pct"] <= -0.25:
            reasons.append(f"sales down {abs(row['sales_change_pct']):.0%}")
        if row["frequency_change_pct"] <= -0.25:
            reasons.append(f"invoice frequency down {abs(row['frequency_change_pct']):.0%}")
        if row["active_months_12m"] <= 4:
            reasons.append(f"active only {int(row['active_months_12m'])} months")

        return "; ".join(reasons) if reasons else "moderate deterioration across indicators"

    customers["risk_reasons"] = customers.apply(reason, axis=1)

    customers = customers.sort_values(
        ["risk_level", "priority_score"],
        ascending=[False, False],
    )

    output_columns = [
        "customer_global_id",
        "customer_name",
        "customer_country",
        "customer_segment",
        "risk_level",
        "churn_risk_score",
        "value_at_risk_eur",
        "sales_12m_eur",
        "margin_12m_eur",
        "recency_days",
        "sales_change_pct",
        "frequency_change_pct",
        "active_months_12m",
        "product_families_12m",
        "risk_reasons",
    ]

    customers[output_columns].to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    summary = (
        customers.groupby("risk_level", observed=True, as_index=False)
        .agg(
            customers=("customer_global_id", "nunique"),
            sales_12m_eur=("sales_12m_eur", "sum"),
            value_at_risk_eur=("value_at_risk_eur", "sum"),
            margin_12m_eur=("margin_12m_eur", "sum"),
        )
    )

    summary.to_csv(
        SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Churn — completado")
    print(f"Ranking: {OUTPUT_PATH}")
    print(f"Resumen: {SUMMARY_PATH}")
    print()
    print("Resumen de riesgo:")
    print(summary.to_string(index=False))
    print()
    print("Top 10 prioridades:")
    print(
        customers[output_columns]
        .head(10)
        .to_string(index=False)
    )

    return customers[output_columns]


if __name__ == "__main__":
    build_churn_risk()

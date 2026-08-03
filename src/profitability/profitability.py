from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

CANONICAL_PATH: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "fact_sales_canonical.parquet"
)

FORECAST_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "forecast_2026_s2.csv"
)

SCENARIOS_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "profitability_scenarios.csv"
)

BASELINE_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "profitability_baseline_2026_s2.csv"
)

FAMILY_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "profitability_by_family.csv"
)

CUSTOMER_OPPORTUNITIES_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "profitability_customer_opportunities.csv"
)

TARGET_MARGIN_UPLIFT_PP: Final[float] = 2.0


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga ventas canónicas y forecast final."""

    if not CANONICAL_PATH.exists():
        raise FileNotFoundError(
            f"No existe la tabla canónica: {CANONICAL_PATH}"
        )

    if not FORECAST_PATH.exists():
        raise FileNotFoundError(
            f"No existe el forecast: {FORECAST_PATH}"
        )

    sales = pd.read_parquet(CANONICAL_PATH)
    forecast = pd.read_csv(FORECAST_PATH)

    sales["invoice_date"] = pd.to_datetime(
        sales["invoice_date"],
        errors="coerce",
    )

    sales = sales.loc[
        ~sales["is_intercompany"].fillna(False)
    ].copy()

    return sales, forecast


def build_family_baseline(
    sales: pd.DataFrame,
    forecast: pd.DataFrame,
) -> pd.DataFrame:
    """
    Proyecta el margen base de 2026-S2 por familia.

    La tasa de margen se estima con los últimos 12 meses disponibles
    (julio 2025 a junio 2026), para reflejar la economía más reciente.
    """

    recent = sales.loc[
        (sales["invoice_date"] >= "2025-07-01")
        & (sales["invoice_date"] <= "2026-06-30")
    ].copy()

    family_history = (
        recent.groupby(
            "product_family",
            as_index=False,
        )
        .agg(
            historical_sales_eur=("net_sales_eur", "sum"),
            historical_margin_eur=("gross_margin_eur", "sum"),
            historical_tons=("quantity_tons", "sum"),
        )
    )

    family_history["historical_margin_pct"] = np.where(
        family_history["historical_sales_eur"] != 0,
        (
            family_history["historical_margin_eur"]
            / family_history["historical_sales_eur"]
        ),
        np.nan,
    )

    forecast_family = (
        forecast.groupby(
            "product_family",
            as_index=False,
        )
        .agg(
            forecast_sales_eur=("forecast_net_sales_eur", "sum"),
            forecast_tons=("forecast_quantity_tons", "sum"),
        )
    )

    baseline = forecast_family.merge(
        family_history,
        on="product_family",
        how="left",
        validate="one_to_one",
    )

    overall_margin_pct = (
        recent["gross_margin_eur"].sum()
        / recent["net_sales_eur"].sum()
    )

    baseline["historical_margin_pct"] = (
        baseline["historical_margin_pct"]
        .fillna(overall_margin_pct)
    )

    baseline["forecast_margin_eur"] = (
        baseline["forecast_sales_eur"]
        * baseline["historical_margin_pct"]
    )

    baseline["forecast_margin_pct"] = (
        baseline["forecast_margin_eur"]
        / baseline["forecast_sales_eur"]
    )

    return baseline


def build_customer_opportunities(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Identifica clientes con margen bajo, negativo o deterioro reciente."""

    recent = sales.loc[
        (sales["invoice_date"] >= "2025-07-01")
        & (sales["invoice_date"] <= "2026-06-30")
    ].copy()

    customer = (
        recent.groupby(
            [
                "customer_global_id",
                "customer_name",
                "customer_country",
                "customer_segment",
            ],
            as_index=False,
        )
        .agg(
            sales_12m_eur=("net_sales_eur", "sum"),
            margin_12m_eur=("gross_margin_eur", "sum"),
            tons_12m=("quantity_tons", "sum"),
            invoices_12m=("invoice_id", "nunique"),
            product_families=("product_family", "nunique"),
        )
    )

    customer["margin_pct"] = np.where(
        customer["sales_12m_eur"] != 0,
        customer["margin_12m_eur"]
        / customer["sales_12m_eur"],
        np.nan,
    )

    customer["opportunity_type"] = np.select(
        [
            customer["margin_pct"] < 0,
            customer["margin_pct"] < 0.06,
            customer["margin_pct"] < 0.10,
        ],
        [
            "NEGATIVE_MARGIN",
            "VERY_LOW_MARGIN",
            "LOW_MARGIN",
        ],
        default="HEALTHY_MARGIN",
    )

    customer["recoverable_margin_eur"] = np.select(
        [
            customer["margin_pct"] < 0,
            customer["margin_pct"] < 0.06,
            customer["margin_pct"] < 0.10,
        ],
        [
            (-customer["margin_12m_eur"]).clip(lower=0) * 0.50,
            customer["sales_12m_eur"] * 0.02,
            customer["sales_12m_eur"] * 0.01,
        ],
        default=0.0,
    )

    customer = customer.sort_values(
        [
            "recoverable_margin_eur",
            "sales_12m_eur",
        ],
        ascending=False,
    )

    return customer


def calculate_scenarios(
    sales: pd.DataFrame,
    baseline: pd.DataFrame,
    customer_opportunities: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cuantifica cuatro palancas de margen.

    Las palancas se calculan sobre el volumen futuro o se escalan a un
    horizonte de seis meses, evitando aplicar el impacto directamente
    sobre todo el histórico.
    """

    baseline_sales = baseline["forecast_sales_eur"].sum()
    baseline_margin = baseline["forecast_margin_eur"].sum()
    baseline_margin_pct = baseline_margin / baseline_sales

    recent = sales.loc[
        (sales["invoice_date"] >= "2025-07-01")
        & (sales["invoice_date"] <= "2026-06-30")
    ].copy()

    # Palanca 1: precio selectivo
    # Universo: clientes con margen positivo pero inferior a 10%.
    # Supuesto: +1.5% de precio con retención de 98% del volumen.
    eligible_pricing = customer_opportunities.loc[
        (customer_opportunities["margin_pct"] >= 0)
        & (customer_opportunities["margin_pct"] < 0.10)
    ]

    eligible_share = (
        eligible_pricing["sales_12m_eur"].sum()
        / recent["net_sales_eur"].sum()
    )

    pricing_base_forecast = baseline_sales * eligible_share
    pricing_impact = pricing_base_forecast * 0.015 * 0.98

    # Palanca 2: recuperación de pérdidas o margen insuficiente.
    # Se anualiza la oportunidad de clientes y se lleva a seis meses.
    customer_recovery_impact = (
        customer_opportunities["recoverable_margin_eur"].sum()
        * 0.50
    )

    # Palanca 3: reducción de notas de crédito.
    # Se usa la venta absoluta de documentos negativos de los últimos 12m
    # y se proyecta a 6 meses. Supuesto: reducir 25% del impacto.
    credit_notes = recent.loc[
        recent["document_sign"] < 0
    ]

    credit_note_12m = abs(
        credit_notes["net_sales_eur"].sum()
    )

    credit_note_impact = credit_note_12m * 0.50 * 0.25

    # Palanca 4: mejora de mezcla.
    # Se mueve 5% de la venta futura de las familias del cuartil inferior
    # hacia el cuartil superior. El impacto es la diferencia de margen.
    family_ranked = baseline.sort_values(
        "historical_margin_pct"
    ).copy()

    low_threshold = family_ranked[
        "historical_margin_pct"
    ].quantile(0.25)

    high_threshold = family_ranked[
        "historical_margin_pct"
    ].quantile(0.75)

    low_families = family_ranked.loc[
        family_ranked["historical_margin_pct"] <= low_threshold
    ]

    high_families = family_ranked.loc[
        family_ranked["historical_margin_pct"] >= high_threshold
    ]

    low_margin_pct = (
        low_families["forecast_margin_eur"].sum()
        / low_families["forecast_sales_eur"].sum()
    )

    high_margin_pct = (
        high_families["forecast_margin_eur"].sum()
        / high_families["forecast_sales_eur"].sum()
    )

    shifted_sales = (
        low_families["forecast_sales_eur"].sum()
        * 0.05
    )

    mix_impact = shifted_sales * max(
        high_margin_pct - low_margin_pct,
        0,
    )

    scenarios = pd.DataFrame(
        [
            {
                "lever": "Selective pricing",
                "affected_base_eur": pricing_base_forecast,
                "assumption": (
                    "Increase price 1.5% for positive-margin customers "
                    "below 10% margin; retain 98% of volume"
                ),
                "incremental_margin_eur": pricing_impact,
                "implementation_risk": "MEDIUM",
            },
            {
                "lever": "Recover low/negative-margin accounts",
                "affected_base_eur": eligible_pricing["sales_12m_eur"].sum(),
                "assumption": (
                    "Recover 50% of quantified six-month opportunity "
                    "through price floors, discount control and order conditions"
                ),
                "incremental_margin_eur": customer_recovery_impact,
                "implementation_risk": "MEDIUM",
            },
            {
                "lever": "Reduce credit notes",
                "affected_base_eur": credit_note_12m * 0.50,
                "assumption": (
                    "Reduce 25% of projected 2026-S2 credit-note impact "
                    "through root-cause actions"
                ),
                "incremental_margin_eur": credit_note_impact,
                "implementation_risk": "LOW",
            },
            {
                "lever": "Improve product mix",
                "affected_base_eur": shifted_sales,
                "assumption": (
                    "Shift 5% of forecast sales from bottom-quartile "
                    "families to top-quartile margin families"
                ),
                "incremental_margin_eur": mix_impact,
                "implementation_risk": "MEDIUM",
            },
        ]
    )

    scenarios["margin_uplift_pp"] = (
        scenarios["incremental_margin_eur"]
        / baseline_sales
        * 100
    )

    scenarios["baseline_sales_eur"] = baseline_sales
    scenarios["baseline_margin_eur"] = baseline_margin
    scenarios["baseline_margin_pct"] = baseline_margin_pct

    total_incremental_margin = scenarios[
        "incremental_margin_eur"
    ].sum()

    total_uplift_pp = (
        total_incremental_margin
        / baseline_sales
        * 100
    )

    total_row = pd.DataFrame(
        [
            {
                "lever": "TOTAL",
                "affected_base_eur": np.nan,
                "assumption": (
                    f"Combined scenario; target is "
                    f"{TARGET_MARGIN_UPLIFT_PP:.1f} pp"
                ),
                "incremental_margin_eur": total_incremental_margin,
                "implementation_risk": "PORTFOLIO",
                "margin_uplift_pp": total_uplift_pp,
                "baseline_sales_eur": baseline_sales,
                "baseline_margin_eur": baseline_margin,
                "baseline_margin_pct": baseline_margin_pct,
            }
        ]
    )

    return pd.concat(
        [
            scenarios,
            total_row,
        ],
        ignore_index=True,
    )


def run_profitability_analysis() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ejecuta baseline futuro y escenarios de rentabilidad."""

    sales, forecast = load_inputs()

    baseline = build_family_baseline(
        sales,
        forecast,
    )

    customer_opportunities = build_customer_opportunities(
        sales
    )

    scenarios = calculate_scenarios(
        sales,
        baseline,
        customer_opportunities,
    )

    SCENARIOS_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    baseline.to_csv(
        BASELINE_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    baseline.to_csv(
        FAMILY_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    customer_opportunities.to_csv(
        CUSTOMER_OPPORTUNITIES_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    scenarios.to_csv(
        SCENARIOS_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Rentabilidad — completada")
    print(f"Baseline: {BASELINE_OUTPUT_PATH}")
    print(f"Escenarios: {SCENARIOS_OUTPUT_PATH}")
    print(f"Oportunidades cliente: {CUSTOMER_OPPORTUNITIES_PATH}")
    print()
    print("Escenarios de margen:")
    print(
        scenarios[
            [
                "lever",
                "incremental_margin_eur",
                "margin_uplift_pp",
                "implementation_risk",
            ]
        ].to_string(index=False)
    )

    return baseline, scenarios


if __name__ == "__main__":
    run_profitability_analysis()

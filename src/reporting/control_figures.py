from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

CANONICAL_PATH: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "fact_sales_canonical.parquet"
)

CONTROL_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "cifras-control.csv"
)

EXECUTIVE_METRICS_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "executive_metrics.csv"
)

TOP_COUNTRIES_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "top_countries_2025.csv"
)

INTERCOMPANY_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "intercompany_summary.csv"
)


def load_sales() -> pd.DataFrame:
    """Carga la tabla canónica y valida las columnas mínimas."""

    if not CANONICAL_PATH.exists():
        raise FileNotFoundError(
            f"No existe la tabla canónica: {CANONICAL_PATH}"
        )

    sales = pd.read_parquet(CANONICAL_PATH)

    required_columns = {
        "sale_key",
        "invoice_id",
        "invoice_date",
        "year_month",
        "year",
        "subsidiary",
        "customer_global_id",
        "customer_country",
        "is_intercompany",
        "quantity_tons",
        "net_sales_eur",
        "gross_margin_eur",
    }

    missing_columns = required_columns - set(sales.columns)

    if missing_columns:
        raise ValueError(
            "La tabla canónica no contiene las columnas requeridas: "
            f"{sorted(missing_columns)}"
        )

    sales["invoice_date"] = pd.to_datetime(
        sales["invoice_date"],
        errors="coerce",
    )

    sales["year"] = pd.to_numeric(
        sales["year"],
        errors="coerce",
    ).astype("Int64")

    sales["is_intercompany"] = (
        sales["is_intercompany"]
        .astype("boolean")
    )

    return sales


def create_control_figures(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Genera cifras de control mensuales para cliente final.

    Número de facturas:
    cuenta documentos únicos por filial + invoice_id,
    evitando mezclar facturas con el mismo número entre filiales.
    """

    final_sales = sales.loc[
        ~sales["is_intercompany"].fillna(False)
    ].copy()

    final_sales["invoice_key"] = (
        final_sales["subsidiary"].astype("string")
        + "|"
        + final_sales["invoice_id"].astype("string")
    )

    monthly = (
        final_sales.groupby(
            "year_month",
            as_index=False,
        )
        .agg(
            toneladas=("quantity_tons", "sum"),
            venta_neta_eur_cliente_final=(
                "net_sales_eur",
                "sum",
            ),
            margen_bruto_eur=(
                "gross_margin_eur",
                "sum",
            ),
            numero_facturas=(
                "invoice_key",
                "nunique",
            ),
        )
        .sort_values("year_month")
    )

    monthly["margen_bruto_pct"] = (
        monthly["margen_bruto_eur"]
        / monthly["venta_neta_eur_cliente_final"]
    )

    output = monthly[
        [
            "year_month",
            "toneladas",
            "venta_neta_eur_cliente_final",
            "margen_bruto_pct",
            "numero_facturas",
        ]
    ].rename(
        columns={
            "year_month": "mes",
        }
    )

    return output


def create_executive_metrics(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Genera las métricas obligatorias del resumen ejecutivo."""

    final_sales = sales.loc[
        ~sales["is_intercompany"].fillna(False)
    ].copy()

    intercompany = sales.loc[
        sales["is_intercompany"].fillna(False)
    ].copy()

    final_2025 = final_sales.loc[
        final_sales["year"] == 2025
    ]

    final_2026_s1 = final_sales.loc[
        (final_sales["invoice_date"] >= "2026-01-01")
        & (final_sales["invoice_date"] <= "2026-06-30")
    ]

    inter_2025 = intercompany.loc[
        intercompany["year"] == 2025
    ]

    inter_2026_s1 = intercompany.loc[
        (intercompany["invoice_date"] >= "2026-01-01")
        & (intercompany["invoice_date"] <= "2026-06-30")
    ]

    active_customers_2026_s1 = final_2026_s1[
        "customer_global_id"
    ].nunique()

    metrics = pd.DataFrame(
        {
            "metric": [
                "venta_neta_cliente_final_2025_eur",
                "venta_neta_cliente_final_2025_m_eur",
                "toneladas_cliente_final_2025",
                "toneladas_cliente_final_2025_kt",
                "margen_bruto_2025_eur",
                "margen_bruto_2025_pct",
                "venta_neta_cliente_final_2026_s1_eur",
                "venta_neta_cliente_final_2026_s1_m_eur",
                "toneladas_cliente_final_2026_s1",
                "toneladas_cliente_final_2026_s1_kt",
                "intercompany_2025_eur",
                "intercompany_2025_m_eur",
                "intercompany_2025_ton",
                "intercompany_2025_kt",
                "intercompany_2026_s1_eur",
                "intercompany_2026_s1_m_eur",
                "intercompany_2026_s1_ton",
                "intercompany_2026_s1_kt",
                "clientes_activos_2026_s1",
            ],
            "value": [
                final_2025["net_sales_eur"].sum(),
                final_2025["net_sales_eur"].sum() / 1_000_000,
                final_2025["quantity_tons"].sum(),
                final_2025["quantity_tons"].sum() / 1_000,
                final_2025["gross_margin_eur"].sum(),
                (
                    final_2025["gross_margin_eur"].sum()
                    / final_2025["net_sales_eur"].sum()
                ),
                final_2026_s1["net_sales_eur"].sum(),
                final_2026_s1["net_sales_eur"].sum() / 1_000_000,
                final_2026_s1["quantity_tons"].sum(),
                final_2026_s1["quantity_tons"].sum() / 1_000,
                inter_2025["net_sales_eur"].sum(),
                inter_2025["net_sales_eur"].sum() / 1_000_000,
                inter_2025["quantity_tons"].sum(),
                inter_2025["quantity_tons"].sum() / 1_000,
                inter_2026_s1["net_sales_eur"].sum(),
                inter_2026_s1["net_sales_eur"].sum() / 1_000_000,
                inter_2026_s1["quantity_tons"].sum(),
                inter_2026_s1["quantity_tons"].sum() / 1_000,
                active_customers_2026_s1,
            ],
        }
    )

    return metrics


def create_top_countries_2025(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula los tres países con mayor venta a cliente final en 2025."""

    final_2025 = sales.loc[
        (~sales["is_intercompany"].fillna(False))
        & (sales["year"] == 2025)
    ].copy()

    result = (
        final_2025.groupby(
            "customer_country",
            as_index=False,
        )
        .agg(
            venta_neta_eur=("net_sales_eur", "sum"),
            toneladas=("quantity_tons", "sum"),
            margen_bruto_eur=("gross_margin_eur", "sum"),
            clientes=("customer_global_id", "nunique"),
        )
        .sort_values(
            "venta_neta_eur",
            ascending=False,
        )
        .head(3)
    )

    result["venta_neta_m_eur"] = (
        result["venta_neta_eur"] / 1_000_000
    )

    result["margen_bruto_pct"] = (
        result["margen_bruto_eur"]
        / result["venta_neta_eur"]
    )

    return result


def create_intercompany_summary(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resume flujos intercompañía por filial destino y periodo.

    La filial asociada a la factura se usa como filial de destino operativa,
    conforme al modelo disponible.
    """

    intercompany = sales.loc[
        sales["is_intercompany"].fillna(False)
    ].copy()

    intercompany["period"] = "OTHER"

    intercompany.loc[
        intercompany["year"] == 2025,
        "period",
    ] = "2025"

    intercompany.loc[
        (
            (intercompany["invoice_date"] >= "2026-01-01")
            & (intercompany["invoice_date"] <= "2026-06-30")
        ),
        "period",
    ] = "2026_S1"

    result = (
        intercompany.loc[
            intercompany["period"].isin(
                ["2025", "2026_S1"]
            )
        ]
        .groupby(
            [
                "period",
                "subsidiary",
            ],
            as_index=False,
        )
        .agg(
            venta_neta_eur=("net_sales_eur", "sum"),
            toneladas=("quantity_tons", "sum"),
            documentos=("invoice_id", "nunique"),
        )
        .sort_values(
            [
                "period",
                "subsidiary",
            ]
        )
    )

    result["venta_neta_m_eur"] = (
        result["venta_neta_eur"] / 1_000_000
    )

    result["toneladas_kt"] = (
        result["toneladas"] / 1_000
    )

    return result


def save_control_outputs() -> None:
    """Genera todos los outputs de control y resumen ejecutivo."""

    sales = load_sales()

    CONTROL_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    control_figures = create_control_figures(sales)
    executive_metrics = create_executive_metrics(sales)
    top_countries = create_top_countries_2025(sales)
    intercompany_summary = create_intercompany_summary(sales)

    control_figures.to_csv(
        CONTROL_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    executive_metrics.to_csv(
        EXECUTIVE_METRICS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    top_countries.to_csv(
        TOP_COUNTRIES_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    intercompany_summary.to_csv(
        INTERCOMPANY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Reportes de control — completados")
    print(f"Cifras de control: {CONTROL_OUTPUT_PATH}")
    print(f"Métricas ejecutivas: {EXECUTIVE_METRICS_PATH}")
    print(f"Top países 2025: {TOP_COUNTRIES_PATH}")
    print(f"Intercompañía: {INTERCOMPANY_PATH}")
    print()
    print("Métricas ejecutivas:")
    print(executive_metrics.to_string(index=False))


if __name__ == "__main__":
    save_control_outputs()

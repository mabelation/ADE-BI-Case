from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

STAGING_DIRECTORY: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "staging"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "fact_sales_canonical.parquet"
)

QUALITY_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "quality_canonical_sales.csv"
)

UNMATCHED_CUSTOMERS_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "unmatched_customers.csv"
)

UNMATCHED_PRODUCTS_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "unmatched_products.csv"
)

MISSING_FX_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "missing_fx_rates.csv"
)

MISSING_COSTS_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "missing_standard_costs.csv"
)


CRM_PATH: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "maestros"
    / "crm-clientes.csv"
)

PRODUCT_MASTER_PATH: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "maestros"
    / "productos.xlsx"
)

FX_PATH: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "maestros"
    / "tipos-cambio.csv"
)

COST_PATH: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "maestros"
    / "costos-estandar.xlsx"
)


PLANT_MAPPING: Final[dict[str, str]] = {
    "INDABEL": "Deinze (BE)",
    "EUROLAM": "Zawiercie (PL)",
    "TURIO": "Valencia (ES)",
}


CANONICAL_COLUMNS: Final[list[str]] = [
    "sale_key",
    "record_key",
    "subsidiary",
    "plant",
    "source_system",
    "source_file",
    "invoice_id",
    "invoice_line",
    "invoice_date",
    "year_month",
    "year",
    "customer_erp_id",
    "customer_global_id",
    "customer_name",
    "customer_country",
    "customer_segment",
    "customer_status",
    "is_intercompany",
    "product_erp_id",
    "product_global_id",
    "product_name",
    "product_family",
    "quantity_tons",
    "currency",
    "exchange_rate_units_per_eur",
    "net_sales_local",
    "net_sales_eur",
    "standard_cost_eur_per_ton",
    "standard_cost_eur",
    "gross_margin_eur",
    "gross_margin_pct",
    "document_type",
    "document_sign",
    "order_id",
]


def load_staging_file(file_name: str) -> pd.DataFrame:
    """Lee un archivo staging requerido."""

    file_path = STAGING_DIRECTORY / file_name

    if not file_path.exists():
        raise FileNotFoundError(
            f"No existe el archivo staging requerido: {file_path}"
        )

    return pd.read_parquet(file_path)


def clean_string_series(series: pd.Series) -> pd.Series:
    """Normaliza texto sin convertir valores nulos en la palabra 'nan'."""

    return (
        series
        .astype("string")
        .str.strip()
    )


def prepare_indabel() -> pd.DataFrame:
    """Convierte Indabel al contrato canónico intermedio."""

    df = load_staging_file(
        "stg_indabel_sales.parquet"
    ).copy()

    result = pd.DataFrame(
        {
            "record_key": df["record_key"],
            "subsidiary": "INDABEL",
            "plant": PLANT_MAPPING["INDABEL"],
            "source_system": df["source_system"],
            "source_file": df["source_file"],
            "invoice_id": df["invoice_id"],
            "invoice_line": df["invoice_line"],
            "invoice_date": df["invoice_date"],
            "customer_erp_id": (
                df["customer_erp_id"]
                .astype("string")
                .str.replace(
                    r"^0+",
                    "",
                    regex=True,
                    )
                    ),
            "customer_name_source": df["customer_name"],
            "customer_country_source": df["country"],
            "product_erp_id": df["product_erp_id"],
            "product_global_id": (
                df["product_erp_id"]
                .astype("string")
                .str.replace(
                    r"^0+",
                    "",
                    regex=True,
                    )
                    ),
            "product_name_source": df["product_name"],
            "quantity_tons": df["quantity_tons_signed"],
            "currency": df["currency"],
            "net_sales_local": df["net_amount_local_signed"],
            "document_type": df["document_type"],
            "document_sign": df["document_sign"],
            "order_id": df["order_id"],
        }
    )

    return result


def prepare_eurolam() -> pd.DataFrame:
    """
    Convierte Eurolam al contrato canónico intermedio.

    El exportador puede reprocesar lotes. Se eliminan únicamente filas
    completamente idénticas. Después se valida que factura-línea sea única.
    """

    df = load_staging_file(
        "stg_eurolam_sales.parquet"
    ).copy()

    rows_before = len(df)

    # Los extractos anuales de StalexERP contienen transacciones
    # históricas reprocesadas. En los casos analizados, la única
    # diferencia entre copias es el archivo de origen.
    #
    # Por ello, la deduplicación compara todos los campos de negocio,
    # excluyendo únicamente record_key y source_file.
    business_columns = [
        column
        for column in df.columns
        if column not in {
            "record_key",
            "source_file",
        }
    ]

    df = (
        df.drop_duplicates(
            subset=business_columns,
            keep="first",
        )
        .copy()
    )

    rows_removed = rows_before - len(df)

    print(
        "Eurolam — duplicados por reprocesamiento eliminados: "
        f"{rows_removed:,}"
    )

    remaining_duplicate_mask = df["record_key"].duplicated(
        keep=False
    )

    if remaining_duplicate_mask.any():
        conflicting = (
            df.loc[remaining_duplicate_mask]
            .sort_values("record_key")
        )

        conflict_path = (
            PROJECT_ROOT
            / "outputs"
            / "eurolam_conflicting_duplicates.csv"
        )

        conflicting.to_csv(
            conflict_path,
            index=False,
            encoding="utf-8-sig",
        )

        raise ValueError(
            "Persisten llaves factura-línea con diferencias de negocio "
            "después de excluir source_file. "
            f"Revisar: {conflict_path}"
        )

    document_sign = (
        df["document_type"]
        .map(
            {
                "FAKTURA": 1,
                "KOREKTA": -1,
            }
        )
    )

    if document_sign.isna().any():
        unknown_types = sorted(
            df.loc[
                document_sign.isna(),
                "document_type",
            ]
            .dropna()
            .unique()
            .tolist()
        )

        raise ValueError(
            "Eurolam contiene tipos de documento sin regla: "
            f"{unknown_types}"
        )

    result = pd.DataFrame(
        {
            "record_key": df["record_key"],
            "subsidiary": "EUROLAM",
            "plant": PLANT_MAPPING["EUROLAM"],
            "source_system": df["source_system"],
            "source_file": df["source_file"],
            "invoice_id": df["invoice_id"],
            "invoice_line": df["invoice_line"],
            "invoice_date": df["invoice_date"],
            "customer_erp_id": df["customer_erp_id"],
            "customer_name_source": df["customer_name"],
            "customer_country_source": df["country"],
            "product_erp_id": df["product_erp_id"],
            "product_global_id": df["product_erp_id"],
            "product_name_source": df["product_name"],
            "quantity_tons": (
                df["quantity_tons"]
                * document_sign
            ),
            "currency": df["currency"],
            "net_sales_local": (
                df["net_amount_local"]
                * document_sign
            ),
            "document_type": df["document_type"],
            "document_sign": document_sign,
            "order_id": df["order_id"],
        }
    )

    return result


def prepare_turio() -> pd.DataFrame:
    """Convierte Turio al contrato canónico intermedio."""

    df = load_staging_file(
        "stg_turio_sales.parquet"
    ).copy()

    result = pd.DataFrame(
        {
            "record_key": df["record_key"],
            "subsidiary": "TURIO",
            "plant": PLANT_MAPPING["TURIO"],
            "source_system": df["source_system"],
            "source_file": df["source_file"],
            "invoice_id": df["invoice_id"],
            "invoice_line": df["invoice_line"],
            "invoice_date": df["invoice_date"],
            "customer_erp_id": df["customer_erp_id"],
            "customer_name_source": df["customer_name"],
            "customer_country_source": df["country"],
            "product_erp_id": df["product_erp_id"],
            "product_global_id": df["product_global_id"],
            "product_name_source": df["product_name"],
            "quantity_tons": df["quantity_tons_signed"],
            "currency": df["currency"],
            "net_sales_local": df["net_amount_local_signed"],
            "document_type": df["document_type"],
            "document_sign": df["document_sign"],
            "order_id": df["order_id"],
        }
    )

    return result


def load_crm() -> pd.DataFrame:
    """Carga y valida el maestro corporativo de clientes."""

    crm = pd.read_csv(
        CRM_PATH,
        dtype="string",
    )

    crm.columns = [
        str(column).strip().lower()
        for column in crm.columns
    ]

    required_columns = {
        "cliente_global_id",
        "nombre",
        "pais",
        "segmento",
        "filial",
        "id_erp",
        "vat",
        "estatus",
        "fecha_baja",
    }

    missing_columns = required_columns - set(crm.columns)

    if missing_columns:
        raise ValueError(
            "CRM sin columnas requeridas: "
            f"{sorted(missing_columns)}"
        )

    for column in crm.columns:
        crm[column] = clean_string_series(
            crm[column]
        )

    crm["filial"] = crm["filial"].str.upper()

    if crm.duplicated(
        subset=["filial", "id_erp"]
    ).any():
        raise ValueError(
            "El CRM contiene claves filial + id_erp duplicadas."
        )

    return crm


def enrich_customers(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Homologa clientes con el CRM.

    Los clientes que no aparecen en CRM se conservan para auditoría y se
    clasifican provisionalmente como intercompañía. Este supuesto se basa
    en que el CRM contiene el universo documentado de clientes externos.
    """

    crm = load_crm()

    crm_for_join = crm.rename(
        columns={
            "filial": "subsidiary",
            "id_erp": "customer_erp_id",
            "cliente_global_id": "customer_global_id",
            "nombre": "customer_name_master",
            "pais": "customer_country_master",
            "segmento": "customer_segment",
            "estatus": "customer_status",
            "fecha_baja": "customer_end_date",
            "vat": "customer_vat",
        }
    )

    enriched = sales.merge(
        crm_for_join[
            [
                "subsidiary",
                "customer_erp_id",
                "customer_global_id",
                "customer_name_master",
                "customer_country_master",
                "customer_segment",
                "customer_status",
                "customer_end_date",
                "customer_vat",
            ]
        ],
        on=[
            "subsidiary",
            "customer_erp_id",
        ],
        how="left",
        validate="many_to_one",
    )

    unmatched_mask = enriched[
        "customer_global_id"
    ].isna()

    unmatched = (
        enriched.loc[
            unmatched_mask,
            [
                "subsidiary",
                "customer_erp_id",
                "customer_name_source",
                "customer_country_source",
            ],
        ]
        .drop_duplicates()
        .sort_values(
            [
                "subsidiary",
                "customer_erp_id",
            ]
        )
    )

    unmatched.to_csv(
        UNMATCHED_CUSTOMERS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    enriched["is_intercompany"] = unmatched_mask

    enriched["customer_global_id"] = (
        enriched["customer_global_id"]
        .fillna(
            "INTERCOMPANY|"
            + enriched["subsidiary"]
            + "|"
            + enriched["customer_erp_id"]
        )
    )

    enriched["customer_name"] = (
        enriched["customer_name_master"]
        .fillna(
            enriched["customer_name_source"]
        )
    )

    enriched["customer_country"] = (
        enriched["customer_country_master"]
        .fillna(
            enriched["customer_country_source"]
        )
    )

    enriched["customer_segment"] = (
        enriched["customer_segment"]
        .fillna("INTERCOMPANY")
    )

    enriched["customer_status"] = (
        enriched["customer_status"]
        .fillna("INTERNAL")
    )

    return enriched


def load_products() -> pd.DataFrame:
    """Carga el maestro corporativo de productos."""

    products = pd.read_excel(
        PRODUCT_MASTER_PATH,
        sheet_name="productos",
    )

    products.columns = [
        str(column).strip().lower()
        for column in products.columns
    ]

    required_columns = {
        "sku",
        "nombre",
        "familia",
        "kg_por_unidad",
        "unidad_venta",
    }

    missing_columns = required_columns - set(products.columns)

    if missing_columns:
        raise ValueError(
            "Maestro de productos sin columnas requeridas: "
            f"{sorted(missing_columns)}"
        )

    products["sku"] = clean_string_series(
        products["sku"]
    )

    products["nombre"] = clean_string_series(
        products["nombre"]
    )

    products["familia"] = clean_string_series(
        products["familia"]
    )

    if products["sku"].duplicated().any():
        raise ValueError(
            "El maestro de productos contiene SKU duplicados."
        )

    return products


def enrich_products(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Homologa productos con el maestro corporativo."""

    products = load_products().rename(
        columns={
            "sku": "product_global_id",
            "nombre": "product_name_master",
            "familia": "product_family",
        }
    )

    enriched = sales.merge(
        products[
            [
                "product_global_id",
                "product_name_master",
                "product_family",
            ]
        ],
        on="product_global_id",
        how="left",
        validate="many_to_one",
    )

    unmatched_mask = enriched[
        "product_family"
    ].isna()

    unmatched = (
        enriched.loc[
            unmatched_mask,
            [
                "subsidiary",
                "product_erp_id",
                "product_global_id",
                "product_name_source",
            ],
        ]
        .drop_duplicates()
        .sort_values(
            [
                "subsidiary",
                "product_erp_id",
            ]
        )
    )

    unmatched.to_csv(
        UNMATCHED_PRODUCTS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    if unmatched_mask.any():
        raise ValueError(
            "Existen productos sin homologación corporativa. "
            f"Revisar: {UNMATCHED_PRODUCTS_PATH}"
        )

    enriched["product_name"] = (
        enriched["product_name_master"]
        .fillna(
            enriched["product_name_source"]
        )
    )

    return enriched


def load_exchange_rates() -> pd.DataFrame:
    """Carga tipos de cambio y agrega EUR = 1."""

    fx = pd.read_csv(
        FX_PATH,
        dtype={
            "anio_mes": "string",
            "moneda": "string",
        },
    )

    fx.columns = [
        str(column).strip().lower()
        for column in fx.columns
    ]

    fx["anio_mes"] = clean_string_series(
        fx["anio_mes"]
    )

    fx["moneda"] = (
        clean_string_series(
            fx["moneda"]
        )
        .str.upper()
    )

    fx["unidades_por_eur"] = pd.to_numeric(
        fx["unidades_por_eur"],
        errors="coerce",
    )

    eur_months = pd.DataFrame(
        {
            "anio_mes": pd.period_range(
                "2024-01",
                "2026-06",
                freq="M",
            ).astype(str),
            "moneda": "EUR",
            "unidades_por_eur": 1.0,
        }
    )

    fx = pd.concat(
        [
            fx,
            eur_months,
        ],
        ignore_index=True,
    )

    return fx.drop_duplicates(
        subset=[
            "anio_mes",
            "moneda",
        ],
        keep="last",
    )


def fill_missing_fx_rates(
    sales: pd.DataFrame,
    fx: pd.DataFrame,
) -> pd.DataFrame:
    """
    Completa huecos puntuales de FX con interpolación temporal.

    El maestro tiene huecos aislados para PLN. Se interpola entre el mes
    anterior y posterior dentro de la misma moneda. El dato imputado queda
    marcado para trazabilidad.
    """

    required = (
        sales[
            [
                "year_month",
                "currency",
            ]
        ]
        .drop_duplicates()
        .rename(
            columns={
                "year_month": "anio_mes",
                "currency": "moneda",
            }
        )
    )

    complete = required.merge(
        fx,
        on=[
            "anio_mes",
            "moneda",
        ],
        how="left",
    )

    complete["fx_was_imputed"] = (
        complete["unidades_por_eur"]
        .isna()
    )

    complete["month_date"] = pd.to_datetime(
        complete["anio_mes"] + "-01",
        errors="coerce",
    )

    complete = complete.sort_values(
        [
            "moneda",
            "month_date",
        ]
    )

    complete["unidades_por_eur"] = (
        complete.groupby(
            "moneda",
            group_keys=False,
        )["unidades_por_eur"]
        .transform(
            lambda series: series.interpolate(
                method="linear",
                limit_direction="both",
            )
        )
    )

    still_missing = complete[
        complete["unidades_por_eur"].isna()
    ]

    still_missing.to_csv(
        MISSING_FX_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    if not still_missing.empty:
        raise ValueError(
            "No fue posible resolver todos los tipos de cambio. "
            f"Revisar: {MISSING_FX_PATH}"
        )

    return complete[
        [
            "anio_mes",
            "moneda",
            "unidades_por_eur",
            "fx_was_imputed",
        ]
    ]


def convert_to_eur(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Convierte importes locales a EUR."""

    fx = load_exchange_rates()
    fx_complete = fill_missing_fx_rates(
        sales,
        fx,
    )

    enriched = sales.merge(
        fx_complete,
        left_on=[
            "year_month",
            "currency",
        ],
        right_on=[
            "anio_mes",
            "moneda",
        ],
        how="left",
        validate="many_to_one",
    )

    enriched["exchange_rate_units_per_eur"] = (
        enriched["unidades_por_eur"]
    )

    enriched["net_sales_eur"] = (
        enriched["net_sales_local"]
        / enriched["exchange_rate_units_per_eur"]
    )

    return enriched


def load_standard_costs() -> pd.DataFrame:
    """Carga costos estándar por producto, planta y año."""

    costs = pd.read_excel(
        COST_PATH
    )

    costs.columns = [
        str(column).strip().lower()
        for column in costs.columns
    ]

    costs["sku"] = clean_string_series(
        costs["sku"]
    )

    costs["planta"] = clean_string_series(
        costs["planta"]
    )

    costs["anio"] = pd.to_numeric(
        costs["anio"],
        errors="coerce",
    ).astype("Int64")

    costs["costo_eur_ton"] = pd.to_numeric(
        costs["costo_eur_ton"],
        errors="coerce",
    )

    if costs.duplicated(
        subset=[
            "sku",
            "planta",
            "anio",
        ]
    ).any():
        raise ValueError(
            "El maestro de costos contiene claves duplicadas."
        )

    return costs


def calculate_profitability(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega costo estándar y margen bruto."""

    costs = load_standard_costs().rename(
        columns={
            "sku": "product_global_id",
            "planta": "plant",
            "anio": "year",
            "costo_eur_ton": "standard_cost_eur_per_ton",
        }
    )

    enriched = sales.merge(
        costs,
        on=[
            "product_global_id",
            "plant",
            "year",
        ],
        how="left",
        validate="many_to_one",
    )

    missing_mask = enriched[
        "standard_cost_eur_per_ton"
    ].isna()

    missing = (
        enriched.loc[
            missing_mask,
            [
                "subsidiary",
                "plant",
                "year",
                "product_global_id",
            ],
        ]
        .drop_duplicates()
        .sort_values(
            [
                "plant",
                "year",
                "product_global_id",
            ]
        )
    )

    missing.to_csv(
        MISSING_COSTS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    if missing_mask.any():
        raise ValueError(
            "Existen ventas sin costo estándar. "
            f"Revisar: {MISSING_COSTS_PATH}"
        )

    enriched["standard_cost_eur"] = (
        enriched["quantity_tons"]
        * enriched["standard_cost_eur_per_ton"]
    )

    enriched["gross_margin_eur"] = (
        enriched["net_sales_eur"]
        - enriched["standard_cost_eur"]
    )

    enriched["gross_margin_pct"] = np.where(
        enriched["net_sales_eur"] != 0,
        enriched["gross_margin_eur"]
        / enriched["net_sales_eur"],
        np.nan,
    )

    return enriched


def create_quality_summary(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Crea controles consolidados del modelo canónico."""

    final_customer_sales = sales.loc[
        ~sales["is_intercompany"]
    ]

    intercompany_sales = sales.loc[
        sales["is_intercompany"]
    ]

    return pd.DataFrame(
        {
            "control": [
                "total_rows",
                "unique_sale_keys",
                "duplicated_sale_keys",
                "minimum_invoice_date",
                "maximum_invoice_date",
                "unique_customers_global",
                "unique_products_global",
                "intercompany_rows",
                "intercompany_customers",
                "final_customer_quantity_tons",
                "final_customer_net_sales_eur",
                "final_customer_gross_margin_eur",
                "final_customer_gross_margin_pct",
                "intercompany_quantity_tons",
                "intercompany_net_sales_eur",
                "fx_imputed_rows",
                "null_net_sales_eur",
                "null_standard_cost",
                "null_customer_global_id",
                "null_product_global_id",
            ],
            "value": [
                len(sales),
                sales["sale_key"].nunique(),
                int(
                    sales["sale_key"]
                    .duplicated()
                    .sum()
                ),
                sales["invoice_date"].min(),
                sales["invoice_date"].max(),
                sales["customer_global_id"].nunique(),
                sales["product_global_id"].nunique(),
                len(intercompany_sales),
                intercompany_sales[
                    "customer_global_id"
                ].nunique(),
                final_customer_sales[
                    "quantity_tons"
                ].sum(),
                final_customer_sales[
                    "net_sales_eur"
                ].sum(),
                final_customer_sales[
                    "gross_margin_eur"
                ].sum(),
                (
                    final_customer_sales[
                        "gross_margin_eur"
                    ].sum()
                    / final_customer_sales[
                        "net_sales_eur"
                    ].sum()
                ),
                intercompany_sales[
                    "quantity_tons"
                ].sum(),
                intercompany_sales[
                    "net_sales_eur"
                ].sum(),
                int(
                    sales["fx_was_imputed"]
                    .sum()
                ),
                int(
                    sales["net_sales_eur"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["standard_cost_eur_per_ton"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["customer_global_id"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["product_global_id"]
                    .isna()
                    .sum()
                ),
            ],
        }
    )


def build_canonical_sales() -> pd.DataFrame:
    """Construye y guarda la tabla canónica consolidada."""

    print()
    print("Construyendo modelo canónico...")

    source_frames = [
        prepare_indabel(),
        prepare_eurolam(),
        prepare_turio(),
    ]

    sales = pd.concat(
        source_frames,
        ignore_index=True,
    )

    sales["invoice_date"] = pd.to_datetime(
        sales["invoice_date"],
        errors="coerce",
    )

    sales["year_month"] = (
        sales["invoice_date"]
        .dt.to_period("M")
        .astype("string")
    )

    sales["year"] = (
        sales["invoice_date"]
        .dt.year
        .astype("Int64")
    )

    sales["currency"] = (
        clean_string_series(
            sales["currency"]
        )
        .str.upper()
    )

    sales["sale_key"] = (
        sales["subsidiary"]
        + "|"
        + sales["invoice_id"].astype("string")
        + "|"
        + sales["invoice_line"].astype("string")
    )

    if sales["sale_key"].duplicated().any():
        duplicate_path = (
            PROJECT_ROOT
            / "outputs"
            / "canonical_duplicate_sale_keys.csv"
        )

        sales.loc[
            sales["sale_key"].duplicated(
                keep=False
            )
        ].to_csv(
            duplicate_path,
            index=False,
            encoding="utf-8-sig",
        )

        raise ValueError(
            "El modelo canónico contiene llaves repetidas. "
            f"Revisar: {duplicate_path}"
        )

    sales = enrich_customers(sales)
    sales = enrich_products(sales)
    sales = convert_to_eur(sales)
    sales = calculate_profitability(sales)

    sales = sales.sort_values(
        [
            "invoice_date",
            "subsidiary",
            "invoice_id",
            "invoice_line",
        ]
    ).reset_index(drop=True)

    for column in CANONICAL_COLUMNS:
        if column not in sales.columns:
            sales[column] = pd.NA

    final_sales = sales[
        CANONICAL_COLUMNS
        + [
            "fx_was_imputed",
            "customer_vat",
            "customer_end_date",
        ]
    ].copy()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    QUALITY_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    final_sales.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    quality_summary = create_quality_summary(
        final_sales
    )

    quality_summary.to_csv(
        QUALITY_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Modelo canónico — completado")
    print(f"Filas: {len(final_sales):,}")
    print(
        "Toneladas cliente final: "
        f"{final_sales.loc[~final_sales['is_intercompany'], 'quantity_tons'].sum():,.4f}"
    )
    print(
        "Venta cliente final EUR: "
        f"{final_sales.loc[~final_sales['is_intercompany'], 'net_sales_eur'].sum():,.2f}"
    )
    print(
        "Margen bruto cliente final: "
        f"{final_sales.loc[~final_sales['is_intercompany'], 'gross_margin_eur'].sum():,.2f}"
    )
    print(f"Archivo: {OUTPUT_PATH}")
    print(f"Controles: {QUALITY_OUTPUT_PATH}")

    return final_sales


if __name__ == "__main__":
    build_canonical_sales()
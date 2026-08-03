from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

SOURCE_DIRECTORY: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "erp-indabel-belgica"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "staging"
    / "stg_indabel_sales.parquet"
)

QUALITY_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "quality_indabel.csv"
)

DOCUMENT_SUMMARY_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "indabel_document_indicator_summary.csv"
)

SOURCE_FILES: Final[list[str]] = [
    "indabel_vbrp_2024.parquet",
    "indabel_vbrp_2025.parquet",
    "indabel_vbrp_2026_S1.parquet",
]

COLUMN_MAPPING: Final[dict[str, str]] = {
    "VBELN": "invoice_id",
    "POSNR": "invoice_line",
    "FKART": "document_type",
    "FKDAT": "invoice_date",
    "KUNNR": "customer_erp_id",
    "NAME1": "customer_name",
    "LAND1": "country",
    "MATNR": "product_erp_id",
    "ARKTX": "product_name",
    "MENGE": "quantity_source",
    "MEINS": "unit_of_measure",
    "WAERK": "currency",
    "NETWR": "net_amount_local",
    "SHKZG": "debit_credit_indicator",
    "BSTNK": "order_id",
    "VGBEL": "reference_document_id",
}

DOCUMENT_SIGN_MAPPING: Final[dict[str, int]] = {
    "ZF2": 1,
    "ZG2": -1,
}


def normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia espacios y normaliza columnas de texto."""

    text_columns = [
        "invoice_id",
        "document_type",
        "customer_erp_id",
        "customer_name",
        "country",
        "product_erp_id",
        "product_name",
        "unit_of_measure",
        "currency",
        "debit_credit_indicator",
        "order_id",
        "reference_document_id",
    ]

    for column in text_columns:
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
        )

    df["country"] = df["country"].str.upper()
    df["currency"] = df["currency"].str.upper()
    df["document_type"] = df["document_type"].str.upper()
    df["unit_of_measure"] = df["unit_of_measure"].str.upper()
    df["debit_credit_indicator"] = (
        df["debit_credit_indicator"]
        .str.upper()
    )

    return df


def convert_data_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte fechas, líneas, cantidades e importes."""

    df["invoice_line"] = pd.to_numeric(
        df["invoice_line"],
        errors="coerce",
    ).astype("Int64")

    # SAP entrega FKDAT como YYYYMMDD, por ejemplo 20240101.
    df["invoice_date"] = pd.to_datetime(
        df["invoice_date"]
        .astype("string")
        .str.replace(r"\.0$", "", regex=True),
        format="%Y%m%d",
        errors="coerce",
    )

    df["quantity_source"] = pd.to_numeric(
        df["quantity_source"],
        errors="coerce",
    )

    df["net_amount_local"] = pd.to_numeric(
        df["net_amount_local"],
        errors="coerce",
    )

    # SAP reporta la cantidad en kilogramos.
    # El modelo canónico trabajará en toneladas.
    df["quantity_tons"] = (
        df["quantity_source"]
        / 1000
    )

    return df


def apply_document_sign(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica el signo de negocio según el tipo de documento.

    ZF2 = factura, signo positivo.
    ZG2 = nota de crédito, signo negativo.

    Los importes originales se conservan y se crean columnas firmadas.
    """

    df["document_sign"] = (
        df["document_type"]
        .map(DOCUMENT_SIGN_MAPPING)
        .astype("Int64")
    )

    unknown_mask = df["document_sign"].isna()

    if unknown_mask.any():
        unknown_types = sorted(
            df.loc[
                unknown_mask,
                "document_type",
            ]
            .dropna()
            .unique()
            .tolist()
        )

        raise ValueError(
            "Se encontraron tipos de documento sin regla de signo: "
            f"{unknown_types}"
        )

    df["quantity_tons_signed"] = (
        df["quantity_tons"]
        * df["document_sign"]
    )

    df["net_amount_local_signed"] = (
        df["net_amount_local"]
        * df["document_sign"]
    )

    return df


def validate_document_indicator(
    df: pd.DataFrame,
) -> None:
    """
    Valida la consistencia observada entre FKART y SHKZG.

    En los datos analizados:
    - ZF2 tiene indicador vacío.
    - ZG2 tiene indicador X.
    """

    invalid_zf2 = df[
        (df["document_type"] == "ZF2")
        & (
            df["debit_credit_indicator"]
            .fillna("")
            .ne("")
        )
    ]

    invalid_zg2 = df[
        (df["document_type"] == "ZG2")
        & (
            df["debit_credit_indicator"]
            .fillna("")
            .ne("X")
        )
    ]

    if not invalid_zf2.empty or not invalid_zg2.empty:
        raise ValueError(
            "Se detectaron combinaciones inesperadas entre "
            "document_type y debit_credit_indicator."
        )


def read_indabel_file(
    file_path: Path,
) -> pd.DataFrame:
    """Lee y estandariza un extracto SAP de Indabel."""

    df = pd.read_parquet(file_path)

    missing_columns = (
        set(COLUMN_MAPPING)
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"El archivo {file_path.name} no contiene las columnas "
            f"esperadas: {sorted(missing_columns)}"
        )

    df = df.rename(
        columns=COLUMN_MAPPING
    )

    df = normalize_text_columns(df)
    df = convert_data_types(df)
    df = apply_document_sign(df)

    validate_document_indicator(df)

    df["source_file"] = file_path.name
    df["source_system"] = "SAP"
    df["subsidiary"] = "INDABEL"
    df["plant"] = "DEINZE"

    df["record_key"] = (
        df["subsidiary"]
        + "|"
        + df["invoice_id"]
        + "|"
        + df["invoice_line"].astype("string")
    )

    return df


def load_indabel_sales() -> pd.DataFrame:
    """Consolida los extractos de 2024, 2025 y 2026 S1."""

    frames: list[pd.DataFrame] = []

    for file_name in SOURCE_FILES:
        file_path = (
            SOURCE_DIRECTORY
            / file_name
        )

        if not file_path.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo requerido: {file_path}"
            )

        print(
            f"Leyendo Indabel: {file_name}"
        )

        frames.append(
            read_indabel_file(
                file_path
            )
        )

    sales = pd.concat(
        frames,
        ignore_index=True,
    )

    return sales


def create_document_indicator_summary(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Resume las combinaciones de documento e indicador SAP."""

    summary = (
        sales.groupby(
            [
                "document_type",
                "debit_credit_indicator",
            ],
            dropna=False,
        )
        .agg(
            rows=("record_key", "size"),
            quantity_tons=(
                "quantity_tons",
                "sum",
            ),
            quantity_tons_signed=(
                "quantity_tons_signed",
                "sum",
            ),
            net_amount_local=(
                "net_amount_local",
                "sum",
            ),
            net_amount_local_signed=(
                "net_amount_local_signed",
                "sum",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "document_type",
                "debit_credit_indicator",
            ]
        )
    )

    return summary


def create_indabel_quality_summary(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Genera controles de calidad para Indabel."""

    document_types = ", ".join(
        sorted(
            sales["document_type"]
            .dropna()
            .unique()
            .tolist()
        )
    )

    currencies = ", ".join(
        sorted(
            sales["currency"]
            .dropna()
            .unique()
            .tolist()
        )
    )

    units = ", ".join(
        sorted(
            sales["unit_of_measure"]
            .dropna()
            .unique()
            .tolist()
        )
    )

    summary = pd.DataFrame(
        {
            "control": [
                "total_rows",
                "unique_record_keys",
                "duplicated_record_keys",
                "null_invoice_dates",
                "null_invoice_lines",
                "null_quantity_source",
                "null_quantity_tons",
                "null_net_amount_local",
                "null_document_sign",
                "unique_customers",
                "unique_products",
                "minimum_invoice_date",
                "maximum_invoice_date",
                "document_types",
                "currencies",
                "units_of_measure",
                "gross_quantity_tons",
                "net_quantity_tons",
                "gross_net_amount_local",
                "net_amount_local_signed",
            ],
            "value": [
                len(sales),
                sales["record_key"].nunique(),
                int(
                    sales["record_key"]
                    .duplicated()
                    .sum()
                ),
                int(
                    sales["invoice_date"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["invoice_line"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["quantity_source"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["quantity_tons"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["net_amount_local"]
                    .isna()
                    .sum()
                ),
                int(
                    sales["document_sign"]
                    .isna()
                    .sum()
                ),
                sales[
                    "customer_erp_id"
                ].nunique(),
                sales[
                    "product_erp_id"
                ].nunique(),
                sales[
                    "invoice_date"
                ].min(),
                sales[
                    "invoice_date"
                ].max(),
                document_types,
                currencies,
                units,
                sales[
                    "quantity_tons"
                ].sum(),
                sales[
                    "quantity_tons_signed"
                ].sum(),
                sales[
                    "net_amount_local"
                ].sum(),
                sales[
                    "net_amount_local_signed"
                ].sum(),
            ],
        }
    )

    return summary


def save_indabel_staging() -> pd.DataFrame:
    """Ejecuta la ingesta y guarda staging de Indabel."""

    sales = load_indabel_sales()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    QUALITY_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    sales.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    quality_summary = (
        create_indabel_quality_summary(
            sales
        )
    )

    document_summary = (
        create_document_indicator_summary(
            sales
        )
    )

    quality_summary.to_csv(
        QUALITY_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    document_summary.to_csv(
        DOCUMENT_SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        "Indabel — Ingesta completada"
    )
    print(
        f"Filas leídas: {len(sales):,}"
    )
    print(
        f"Archivo staging: {OUTPUT_PATH}"
    )
    print(
        f"Controles: {QUALITY_OUTPUT_PATH}"
    )
    print(
        "Resumen documento/indicador: "
        f"{DOCUMENT_SUMMARY_PATH}"
    )

    print()
    print(
        "Combinaciones documento / indicador:"
    )
    print(
        document_summary.to_string(
            index=False
        )
    )

    return sales


if __name__ == "__main__":
    save_indabel_staging()
from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

SOURCE_DIRECTORY: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "erp-eurolam-polonia"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "staging"
    / "stg_eurolam_sales.parquet"
)

SOURCE_FILES: Final[list[str]] = [
    "faktury_2024.csv",
    "faktury_2025.csv",
    "faktury_2026_S1.csv",
]

COLUMN_MAPPING: Final[dict[str, str]] = {
    "NR_FAKTURY": "invoice_id",
    "POZYCJA": "invoice_line",
    "DATA_FAKTURY": "invoice_date",
    "KOD_KLIENTA": "customer_erp_id",
    "NAZWA_KLIENTA": "customer_name",
    "KRAJ": "country",
    "INDEKS": "product_erp_id",
    "NAZWA_TOWARU": "product_name",
    "ILOSC_TON": "quantity_tons",
    "CENA_NETTO_T": "net_price_per_ton",
    "WARTOSC_NETTO": "net_amount_local",
    "WALUTA": "currency",
    "RODZAJ": "document_type",
    "NR_ZAMOWIENIA": "order_id",
}


def normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia espacios y normaliza columnas de texto sin alterar el contenido."""

    text_columns = [
        "invoice_id",
        "customer_erp_id",
        "customer_name",
        "country",
        "product_erp_id",
        "product_name",
        "currency",
        "document_type",
        "order_id",
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

    return df


def convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte los campos numéricos del formato europeo a valores numéricos."""

    numeric_columns = [
        "quantity_tons",
        "net_price_per_ton",
        "net_amount_local",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column]
            .astype("string")
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce",
        )

    df["invoice_line"] = pd.to_numeric(
        df["invoice_line"],
        errors="coerce",
    ).astype("Int64")

    return df


def read_eurolam_file(file_path: Path) -> pd.DataFrame:
    """Lee y estandariza un extracto de facturas de StalexERP."""

    df = pd.read_csv(
        file_path,
        sep=";",
        skiprows=2,
        encoding="cp1250",
        dtype="string",
    )

    missing_columns = set(COLUMN_MAPPING) - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"El archivo {file_path.name} no contiene las columnas "
            f"esperadas: {sorted(missing_columns)}"
        )

    df = df.rename(columns=COLUMN_MAPPING)

    df = normalize_text_columns(df)
    df = convert_numeric_columns(df)

    df["invoice_date"] = pd.to_datetime(
        df["invoice_date"],
        format="%d.%m.%Y",
        errors="coerce",
    )

    df["source_file"] = file_path.name
    df["source_system"] = "STALEXERP"
    df["subsidiary"] = "EUROLAM"
    df["plant"] = "ZAWIERCIE"

    return df


def load_eurolam_sales() -> pd.DataFrame:
    """Consolida los extractos de 2024, 2025 y 2026 S1."""

    frames: list[pd.DataFrame] = []

    for file_name in SOURCE_FILES:
        file_path = SOURCE_DIRECTORY / file_name

        if not file_path.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo requerido: {file_path}"
            )

        print(f"Leyendo Eurolam: {file_name}")

        frames.append(
            read_eurolam_file(file_path)
        )

    sales = pd.concat(
        frames,
        ignore_index=True,
    )

    sales["record_key"] = (
        sales["subsidiary"]
        + "|"
        + sales["invoice_id"]
        + "|"
        + sales["invoice_line"].astype("string")
    )

    return sales


def create_eurolam_quality_summary(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Genera controles básicos sin modificar aún los registros."""

    summary = pd.DataFrame(
        {
            "control": [
                "total_rows",
                "unique_record_keys",
                "duplicated_record_keys",
                "null_invoice_dates",
                "null_quantity_tons",
                "null_net_amount_local",
                "unique_customers",
                "unique_products",
                "minimum_invoice_date",
                "maximum_invoice_date",
            ],
            "value": [
                len(sales),
                sales["record_key"].nunique(),
                int(sales["record_key"].duplicated().sum()),
                int(sales["invoice_date"].isna().sum()),
                int(sales["quantity_tons"].isna().sum()),
                int(sales["net_amount_local"].isna().sum()),
                sales["customer_erp_id"].nunique(),
                sales["product_erp_id"].nunique(),
                sales["invoice_date"].min(),
                sales["invoice_date"].max(),
            ],
        }
    )

    return summary


def save_eurolam_staging() -> pd.DataFrame:
    """Ejecuta la ingesta y guarda la capa staging en Parquet."""

    sales = load_eurolam_sales()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    sales.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    quality_path = (
        PROJECT_ROOT
        / "outputs"
        / "quality_eurolam.csv"
    )

    quality_summary = create_eurolam_quality_summary(
        sales
    )

    quality_summary.to_csv(
        quality_path,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Eurolam — Ingesta completada")
    print(f"Filas leídas: {len(sales):,}")
    print(f"Archivo staging: {OUTPUT_PATH}")
    print(f"Controles: {quality_path}")

    return sales


if __name__ == "__main__":
    save_eurolam_staging()
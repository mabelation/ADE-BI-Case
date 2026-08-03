from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

SOURCE_DIRECTORY: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "erp-turio-espana"
)

PRODUCT_MASTER_PATH: Final[Path] = (
    PROJECT_ROOT
    / "datos"
    / "maestros"
    / "productos.xlsx"
)

OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "staging"
    / "stg_turio_sales.parquet"
)

QUALITY_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "quality_turio.csv"
)

DUPLICATES_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "turio_duplicate_resolution.csv"
)

SCHEMA_OUTPUT_PATH: Final[Path] = (
    PROJECT_ROOT
    / "outputs"
    / "turio_schema_by_file.csv"
)


COLUMN_MAPPING: Final[dict[str, str]] = {
    "Nº Factura": "invoice_id",
    "Línea": "invoice_line",
    "Fecha": "invoice_date",
    "Cód. Cliente": "customer_erp_id",
    "Cliente": "customer_name",
    "Cód. Artículo": "product_erp_id",
    "Descripción": "product_name",
    "Cantidad (uds)": "quantity_units",
    "Importe Base (€)": "net_amount_eur_reported",
    "Importe Total (€)": "gross_amount_eur",
    "Nº Pedido": "order_id",
}


REQUIRED_SOURCE_COLUMNS: Final[set[str]] = {
    "Nº Factura",
    "Línea",
    "Fecha",
    "Cód. Cliente",
    "Cliente",
    "Cód. Artículo",
    "Descripción",
    "Cantidad (uds)",
    "Importe Total (€)",
    "Nº Pedido",
}


TEXT_COLUMNS: Final[list[str]] = [
    "invoice_id",
    "customer_erp_id",
    "customer_name",
    "product_erp_id",
    "product_name",
    "order_id",
]


def list_sales_files() -> list[Path]:
    """Obtiene únicamente los informes mensuales de ventas."""

    files = sorted(
        file_path
        for file_path in SOURCE_DIRECTORY.glob("*.xlsx")
        if file_path.name.lower() != "clientes-turio.xlsx"
        and not file_path.name.startswith("~$")
    )

    if not files:
        raise FileNotFoundError(
            f"No se encontraron informes de Turio en {SOURCE_DIRECTORY}"
        )

    return files


def find_sales_sheet(file_path: Path) -> str:
    """
    Identifica la hoja que contiene el informe mensual.

    El nombre de la hoja cambia entre archivos, por lo que no se fija
    como 'Ventas', 'VENTAS' o 'Hoja1'. Se identifica por sus columnas.
    """

    workbook = pd.ExcelFile(file_path)
    candidate_sheets: list[str] = []

    for sheet_name in workbook.sheet_names:
        preview = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            header=2,
            nrows=5,
        )

        if REQUIRED_SOURCE_COLUMNS.issubset(set(preview.columns)):
            candidate_sheets.append(sheet_name)

    if len(candidate_sheets) != 1:
        raise ValueError(
            f"El archivo {file_path.name} debería contener exactamente "
            f"una hoja de ventas. Hojas candidatas: {candidate_sheets}"
        )

    return candidate_sheets[0]


def ensure_optional_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea columnas opcionales ausentes.

    En algunos meses de 2025 no existe Importe Base (€), pero sí existe
    Importe Total (€).
    """

    for source_column in COLUMN_MAPPING:
        if source_column not in df.columns:
            df[source_column] = pd.NA

    return df


def keep_detail_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Conserva únicamente líneas de facturación reales.

    Cada Excel contiene una fila final de TOTAL que no debe integrarse
    como una factura.
    """

    invoice_values = df["Nº Factura"].astype("string").str.strip()

    detail_mask = invoice_values.str.match(
        r"^V\d{2}-\d+$",
        na=False,
    )

    return df.loc[detail_mask].copy()


def normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia espacios en columnas de texto."""

    for column in TEXT_COLUMNS:
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
        )

    return df


def convert_data_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte líneas, fechas, cantidades e importes."""

    df["invoice_line"] = pd.to_numeric(
        df["invoice_line"],
        errors="coerce",
    ).astype("Int64")

    # Las fechas vienen mezcladas entre DD/MM/YYYY y valores Excel datetime.
    df["invoice_date"] = pd.to_datetime(
        df["invoice_date"],
        dayfirst=True,
        errors="coerce",
    )

    numeric_columns = [
        "quantity_units",
        "net_amount_eur_reported",
        "gross_amount_eur",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    return df


def reconstruct_net_amount(df: pd.DataFrame) -> pd.DataFrame:
    """
    Define el importe neto de venta en EUR.

    Cuando Importe Base (€) está disponible, se utiliza directamente.

    Cuando está ausente por el cambio temporal de configuración de
    GestionMax, se reconstruye como Importe Total (€) / 1.21.

    Supuesto documentado:
    Importe Total (€) incluye IVA de 21%.
    """

    df["net_amount_reconstructed"] = (
        df["net_amount_eur_reported"].isna()
    )

    df["net_amount_eur"] = (
        df["net_amount_eur_reported"]
        .fillna(
            df["gross_amount_eur"] / 1.21
        )
    )

    return df


def read_turio_file(file_path: Path) -> pd.DataFrame:
    """Lee y estandariza un informe mensual de GestionMax."""

    sheet_name = find_sales_sheet(file_path)

    source_df = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=2,
    )

    missing_required = (
        REQUIRED_SOURCE_COLUMNS
        - set(source_df.columns)
    )

    if missing_required:
        raise ValueError(
            f"El archivo {file_path.name} no contiene las columnas "
            f"requeridas: {sorted(missing_required)}"
        )

    source_df = keep_detail_rows(source_df)
    source_df = ensure_optional_columns(source_df)

    df = (
        source_df[list(COLUMN_MAPPING)]
        .rename(columns=COLUMN_MAPPING)
    )

    df = normalize_text_columns(df)
    df = convert_data_types(df)
    df = reconstruct_net_amount(df)

    df["source_file"] = file_path.name
    df["source_sheet"] = sheet_name
    df["source_system"] = "GESTIONMAX"
    df["subsidiary"] = "TURIO"
    df["plant"] = "VALENCIA"
    df["country"] = "ES"
    df["currency"] = "EUR"
    df["document_type"] = "INVOICE"
    df["document_sign"] = 1

    df["record_key"] = (
        df["subsidiary"]
        + "|"
        + df["invoice_id"]
        + "|"
        + df["invoice_line"].astype("string")
    )

    return df


def load_turio_raw_sales() -> pd.DataFrame:
    """Consolida los 30 informes mensuales de Turio."""

    frames: list[pd.DataFrame] = []

    for file_path in list_sales_files():
        print(f"Leyendo Turio: {file_path.name}")
        frames.append(
            read_turio_file(file_path)
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )


def validate_duplicate_groups(
    duplicate_rows: pd.DataFrame,
) -> None:
    """
    Verifica que las llaves repetidas difieran únicamente en cantidad.

    En los diez casos observados, todas las variables comerciales son
    iguales y una de las dos filas tiene cantidad cero.
    """

    stable_columns = [
        "invoice_date",
        "customer_erp_id",
        "customer_name",
        "product_erp_id",
        "product_name",
        "net_amount_eur",
        "gross_amount_eur",
        "order_id",
        "source_file",
    ]

    conflicting_keys: list[str] = []

    for record_key, group in duplicate_rows.groupby("record_key"):
        has_conflict = any(
            group[column].nunique(dropna=False) > 1
            for column in stable_columns
        )

        if has_conflict:
            conflicting_keys.append(record_key)

    if conflicting_keys:
        raise ValueError(
            "Existen llaves repetidas con diferencias comerciales "
            f"no explicadas: {conflicting_keys}"
        )


def resolve_duplicate_record_keys(
    sales: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Resuelve las llaves factura-línea repetidas de Turio.

    Regla:
    - Se valida que cliente, producto, fecha, pedido e importes coincidan.
    - Se conserva la fila con mayor cantidad.
    - Se descarta la fila duplicada cuya cantidad es cero.

    No se aplica drop_duplicates sin una regla de negocio explícita.
    """

    duplicate_mask = sales.duplicated(
        subset=["record_key"],
        keep=False,
    )

    duplicate_rows = sales.loc[
        duplicate_mask
    ].copy()

    if duplicate_rows.empty:
        resolution_report = pd.DataFrame(
            columns=[
                "record_key",
                "invoice_id",
                "invoice_line",
                "quantity_units",
                "resolution",
                "source_file",
            ]
        )

        return sales.copy(), resolution_report

    validate_duplicate_groups(duplicate_rows)

    ranked_duplicates = duplicate_rows.sort_values(
        by=[
            "record_key",
            "quantity_units",
        ],
        ascending=[
            True,
            False,
        ],
        na_position="last",
    ).copy()

    ranked_duplicates["duplicate_rank"] = (
        ranked_duplicates
        .groupby("record_key")
        .cumcount()
        + 1
    )

    ranked_duplicates["resolution"] = ranked_duplicates[
        "duplicate_rank"
    ].map(
        {
            1: "KEPT_NON_ZERO_OR_HIGHEST_QUANTITY",
            2: "REMOVED_ZERO_OR_LOWER_QUANTITY",
        }
    )

    rows_to_keep = (
        sales.sort_values(
            by=[
                "record_key",
                "quantity_units",
            ],
            ascending=[
                True,
                False,
            ],
            na_position="last",
        )
        .drop_duplicates(
            subset=["record_key"],
            keep="first",
        )
        .copy()
    )

    resolution_report = ranked_duplicates[
        [
            "record_key",
            "invoice_id",
            "invoice_line",
            "invoice_date",
            "customer_erp_id",
            "product_erp_id",
            "quantity_units",
            "net_amount_eur",
            "order_id",
            "resolution",
            "source_file",
        ]
    ].copy()

    return rows_to_keep, resolution_report


def load_product_mapping() -> pd.DataFrame:
    """
    Construye el mapeo GestionMax → SKU corporativo.

    Combina:
    - hoja equivalencias-turio
    - hoja productos
    """

    products = pd.read_excel(
        PRODUCT_MASTER_PATH,
        sheet_name="productos",
    )

    equivalences = pd.read_excel(
        PRODUCT_MASTER_PATH,
        sheet_name="equivalencias-turio",
    )

    products.columns = [
        str(column).strip().lower()
        for column in products.columns
    ]

    equivalences.columns = [
        str(column).strip().lower()
        for column in equivalences.columns
    ]

    required_product_columns = {
        "sku",
        "nombre",
        "familia",
        "kg_por_unidad",
        "unidad_venta",
    }

    required_equivalence_columns = {
        "sku",
        "codigo_gm",
    }

    if not required_product_columns.issubset(products.columns):
        raise ValueError(
            "La hoja productos no contiene todas las columnas requeridas."
        )

    if not required_equivalence_columns.issubset(
        equivalences.columns
    ):
        raise ValueError(
            "La hoja equivalencias-turio no contiene todas las "
            "columnas requeridas."
        )

    products["sku"] = (
        products["sku"]
        .astype("string")
        .str.strip()
    )

    equivalences["sku"] = (
        equivalences["sku"]
        .astype("string")
        .str.strip()
    )

    equivalences["codigo_gm"] = (
        equivalences["codigo_gm"]
        .astype("string")
        .str.strip()
    )

    products["kg_por_unidad"] = pd.to_numeric(
        products["kg_por_unidad"],
        errors="coerce",
    )

    mapping = equivalences.merge(
        products,
        on="sku",
        how="left",
        validate="many_to_one",
    )

    if mapping["kg_por_unidad"].isna().any():
        missing_skus = sorted(
            mapping.loc[
                mapping["kg_por_unidad"].isna(),
                "sku",
            ]
            .dropna()
            .unique()
            .tolist()
        )

        raise ValueError(
            "Existen equivalencias sin kg_por_unidad: "
            f"{missing_skus}"
        )

    return mapping


def enrich_products_and_quantities(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """Homologa productos y convierte unidades de venta a toneladas."""

    product_mapping = load_product_mapping()

    mapping_columns = [
        "codigo_gm",
        "sku",
        "nombre",
        "familia",
        "kg_por_unidad",
        "unidad_venta",
    ]

    enriched = sales.merge(
        product_mapping[mapping_columns],
        left_on="product_erp_id",
        right_on="codigo_gm",
        how="left",
        validate="many_to_one",
    )

    enriched = enriched.rename(
        columns={
            "sku": "product_global_id",
            "nombre": "product_master_name",
            "familia": "product_family",
            "unidad_venta": "sales_unit",
        }
    )

    missing_mapping_mask = enriched[
        "product_global_id"
    ].isna()

    if missing_mapping_mask.any():
        missing_codes = sorted(
            enriched.loc[
                missing_mapping_mask,
                "product_erp_id",
            ]
            .dropna()
            .unique()
            .tolist()
        )

        raise ValueError(
            "Existen códigos GestionMax sin equivalencia corporativa: "
            f"{missing_codes}"
        )

    enriched["quantity_tons"] = (
        enriched["quantity_units"]
        * enriched["kg_por_unidad"]
        / 1000
    )

    enriched["quantity_tons_signed"] = (
        enriched["quantity_tons"]
        * enriched["document_sign"]
    )

    # Turio ya reporta EUR.
    enriched["net_amount_local"] = enriched[
        "net_amount_eur"
    ]

    enriched["net_amount_local_signed"] = (
        enriched["net_amount_local"]
        * enriched["document_sign"]
    )

    return enriched


def create_schema_report() -> pd.DataFrame:
    """Genera un reporte del esquema observado en cada Excel."""

    records: list[dict[str, object]] = []

    for file_path in list_sales_files():
        sheet_name = find_sales_sheet(file_path)

        preview = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            header=2,
            nrows=1,
        )

        records.append(
            {
                "source_file": file_path.name,
                "source_sheet": sheet_name,
                "column_count": len(preview.columns),
                "has_net_amount_base": (
                    "Importe Base (€)" in preview.columns
                ),
                "columns": " | ".join(
                    map(str, preview.columns)
                ),
            }
        )

    return pd.DataFrame(records)


def create_quality_summary(
    raw_sales: pd.DataFrame,
    clean_sales: pd.DataFrame,
    duplicate_report: pd.DataFrame,
) -> pd.DataFrame:
    """Genera controles de calidad y trazabilidad para Turio."""

    return pd.DataFrame(
        {
            "control": [
                "raw_detail_rows",
                "clean_rows",
                "unique_record_keys",
                "duplicate_occurrences_removed",
                "duplicate_record_key_groups",
                "null_invoice_dates",
                "null_invoice_lines",
                "null_quantity_units",
                "null_net_amount_eur",
                "unmapped_products",
                "missing_kg_per_unit",
                "unique_customers",
                "unique_products_erp",
                "unique_products_global",
                "minimum_invoice_date",
                "maximum_invoice_date",
                "files_processed",
                "rows_with_reported_net_amount",
                "rows_with_reconstructed_net_amount",
                "gross_quantity_units",
                "net_quantity_tons",
                "net_sales_eur",
            ],
            "value": [
                len(raw_sales),
                len(clean_sales),
                clean_sales["record_key"].nunique(),
                len(raw_sales) - len(clean_sales),
                (
                    duplicate_report["record_key"].nunique()
                    if not duplicate_report.empty
                    else 0
                ),
                int(
                    clean_sales["invoice_date"]
                    .isna()
                    .sum()
                ),
                int(
                    clean_sales["invoice_line"]
                    .isna()
                    .sum()
                ),
                int(
                    clean_sales["quantity_units"]
                    .isna()
                    .sum()
                ),
                int(
                    clean_sales["net_amount_eur"]
                    .isna()
                    .sum()
                ),
                int(
                    clean_sales["product_global_id"]
                    .isna()
                    .sum()
                ),
                int(
                    clean_sales["kg_por_unidad"]
                    .isna()
                    .sum()
                ),
                clean_sales["customer_erp_id"].nunique(),
                clean_sales["product_erp_id"].nunique(),
                clean_sales["product_global_id"].nunique(),
                clean_sales["invoice_date"].min(),
                clean_sales["invoice_date"].max(),
                clean_sales["source_file"].nunique(),
                int(
                    (~clean_sales["net_amount_reconstructed"])
                    .sum()
                ),
                int(
                    clean_sales["net_amount_reconstructed"]
                    .sum()
                ),
                clean_sales["quantity_units"].sum(),
                clean_sales["quantity_tons_signed"].sum(),
                clean_sales["net_amount_local_signed"].sum(),
            ],
        }
    )


def save_turio_staging() -> pd.DataFrame:
    """Ejecuta la ingesta completa de Turio y guarda staging."""

    raw_sales = load_turio_raw_sales()

    clean_sales, duplicate_report = (
        resolve_duplicate_record_keys(raw_sales)
    )

    clean_sales = enrich_products_and_quantities(
        clean_sales
    )

    clean_sales = clean_sales.sort_values(
        by=[
            "invoice_date",
            "invoice_id",
            "invoice_line",
        ]
    ).reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    QUALITY_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    clean_sales.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    duplicate_report.to_csv(
        DUPLICATES_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    schema_report = create_schema_report()

    schema_report.to_csv(
        SCHEMA_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    quality_summary = create_quality_summary(
        raw_sales=raw_sales,
        clean_sales=clean_sales,
        duplicate_report=duplicate_report,
    )

    quality_summary.to_csv(
        QUALITY_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("Turio — Ingesta completada")
    print(f"Filas originales: {len(raw_sales):,}")
    print(f"Filas limpias: {len(clean_sales):,}")
    print(
        "Duplicados removidos: "
        f"{len(raw_sales) - len(clean_sales):,}"
    )
    print(
        "Toneladas netas: "
        f"{clean_sales['quantity_tons_signed'].sum():,.4f}"
    )
    print(
        "Venta neta EUR: "
        f"{clean_sales['net_amount_local_signed'].sum():,.2f}"
    )
    print(f"Archivo staging: {OUTPUT_PATH}")
    print(f"Controles: {QUALITY_OUTPUT_PATH}")
    print(f"Resolución de duplicados: {DUPLICATES_OUTPUT_PATH}")
    print(f"Reporte de esquemas: {SCHEMA_OUTPUT_PATH}")

    return clean_sales


if __name__ == "__main__":
    save_turio_staging()
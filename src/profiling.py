from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "datos"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "profiling_summary.csv"


def profile_dataframe(
    df: pd.DataFrame,
    file_path: Path,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Genera métricas básicas de calidad para un DataFrame."""

    total_cells = df.shape[0] * df.shape[1]
    null_cells = int(df.isna().sum().sum())

    return {
        "file": str(file_path.relative_to(PROJECT_ROOT)),
        "sheet": sheet_name or "",
        "rows": len(df),
        "columns": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "null_cells": null_cells,
        "null_percentage": round(
            (null_cells / total_cells) * 100,
            4,
        )
        if total_cells > 0
        else 0.0,
        "column_names": " | ".join(map(str, df.columns)),
        "status": "OK",
        "error": "",
    }


def read_csv_file(file_path: Path) -> pd.DataFrame:
    """Lee CSV probando configuraciones habituales del caso."""

    encodings = ["utf-8", "utf-8-sig", "cp1250", "latin1"]
    separators = [",", ";", "\t"]

    last_error: Exception | None = None

    for encoding in encodings:
        for separator in separators:
            for skip_rows in [0, 1, 2]:
                try:
                    df = pd.read_csv(
                        file_path,
                        encoding=encoding,
                        sep=separator,
                        skiprows=skip_rows,
                        engine="python",
                    )

                    if len(df.columns) > 1:
                        return df

                except Exception as exc:
                    last_error = exc

    raise ValueError(
        f"No fue posible leer el CSV. Último error: {last_error}"
    )


def profile_csv(file_path: Path) -> list[dict[str, Any]]:
    df = read_csv_file(file_path)
    return [profile_dataframe(df, file_path)]


def profile_parquet(file_path: Path) -> list[dict[str, Any]]:
    df = pd.read_parquet(file_path)
    return [profile_dataframe(df, file_path)]


def profile_excel(file_path: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    workbook = pd.ExcelFile(file_path)

    for sheet_name in workbook.sheet_names:
        df = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
        )

        results.append(
            profile_dataframe(
                df=df,
                file_path=file_path,
                sheet_name=sheet_name,
            )
        )

    return results


def profile_file(file_path: Path) -> list[dict[str, Any]]:
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".csv":
            return profile_csv(file_path)

        if suffix == ".parquet":
            return profile_parquet(file_path)

        if suffix in {".xlsx", ".xls"}:
            return profile_excel(file_path)

        return []

    except Exception as exc:
        return [
            {
                "file": str(file_path.relative_to(PROJECT_ROOT)),
                "sheet": "",
                "rows": None,
                "columns": None,
                "duplicate_rows": None,
                "null_cells": None,
                "null_percentage": None,
                "column_names": "",
                "status": "ERROR",
                "error": str(exc),
            }
        ]


def run_profiling() -> pd.DataFrame:
    """Recorre todos los archivos soportados y genera el reporte."""

    supported_extensions = {".csv", ".parquet", ".xlsx", ".xls"}

    files = sorted(
        path
        for path in DATA_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in supported_extensions
    )

    if not files:
        raise FileNotFoundError(
            f"No se encontraron archivos de datos en: {DATA_ROOT}"
        )

    results: list[dict[str, Any]] = []

    for file_path in files:
        print(f"Analizando: {file_path.relative_to(PROJECT_ROOT)}")
        results.extend(profile_file(file_path))

    summary = pd.DataFrame(results)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(f"Archivos analizados: {len(files)}")
    print(f"Registros del reporte: {len(summary)}")
    print(f"Reporte generado en: {OUTPUT_PATH}")

    return summary


if __name__ == "__main__":
    run_profiling()

def preview_raw_files() -> None:
    """Genera una vista cruda de las primeras filas de CSV y Excel."""

    preview_output = PROJECT_ROOT / "outputs" / "raw_previews.txt"

    supported_extensions = {".csv", ".xlsx", ".xls"}

    files = sorted(
        path
        for path in DATA_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in supported_extensions
    )

    preview_output.parent.mkdir(parents=True, exist_ok=True)

    with preview_output.open("w", encoding="utf-8") as output_file:
        for file_path in files:
            relative_path = file_path.relative_to(PROJECT_ROOT)

            output_file.write("\n")
            output_file.write("=" * 100 + "\n")
            output_file.write(f"ARCHIVO: {relative_path}\n")
            output_file.write("=" * 100 + "\n")

            try:
                if file_path.suffix.lower() == ".csv":
                    preview = pd.read_csv(
                        file_path,
                        header=None,
                        nrows=15,
                        sep=None,
                        engine="python",
                        encoding="cp1250",
                    )

                    output_file.write(
                        preview.to_string(
                            index=True,
                            header=False,
                        )
                    )
                    output_file.write("\n")

                else:
                    workbook = pd.ExcelFile(file_path)

                    for sheet_name in workbook.sheet_names:
                        output_file.write(
                            f"\nHOJA: {sheet_name}\n"
                        )

                        preview = pd.read_excel(
                            file_path,
                            sheet_name=sheet_name,
                            header=None,
                            nrows=15,
                        )

                        output_file.write(
                            preview.to_string(
                                index=True,
                                header=False,
                            )
                        )
                        output_file.write("\n")

            except Exception as exc:
                output_file.write(
                    f"ERROR AL LEER ARCHIVO: {exc}\n"
                )

    print(f"Vista cruda generada en: {preview_output}")
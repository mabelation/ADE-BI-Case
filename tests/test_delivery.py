from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_required_delivery_files_exist():
    required_files = [
        ROOT / "main.py",
        ROOT / "README.md",
        ROOT / "requirements.txt",
        ROOT / "resumen-ejecutivo.md",
        ROOT / "outputs" / "cifras-control.csv",
    ]

    missing = [str(path) for path in required_files if not path.exists()]
    assert not missing, f"Faltan archivos obligatorios: {missing}"


def test_final_presentation_exists():
    presentations = [
        path
        for path in ROOT.glob("*.pptx")
        if not path.name.startswith("~$")
        and "plantilla" not in path.name.lower()
    ]

    assert presentations, "No se encontró la presentación final."


def test_control_figures_are_not_empty():
    path = ROOT / "outputs" / "cifras-control.csv"
    df = pd.read_csv(path)

    assert not df.empty, "cifras-control.csv está vacío."
    assert len(df.columns) >= 5, (
        "cifras-control.csv debe contener al menos mes, toneladas, "
        "venta neta, margen bruto y número de facturas."
    )


def test_no_notebooks_in_delivery():
    notebooks = [
        path
        for path in ROOT.rglob("*.ipynb")
        if ".venv" not in path.parts
    ]

    assert not notebooks, f"No se permiten notebooks: {notebooks}"


def test_readme_documents_assumptions_and_limitations():
    content = (ROOT / "README.md").read_text(
        encoding="utf-8"
    ).lower()

    assert "supuestos" in content
    assert "limitaciones" in content
    assert "main.py" in content

import ast
from pathlib import Path

from demand_ingestion import data_sources

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }


def test_external_data_sources_do_not_export_historical_dataset_tools():
    assert set(data_sources.__all__) == {"RegionMasterEntry", "load_region_master"}
    assert not hasattr(data_sources, "discover_dataset")
    assert not (
        PACKAGE_ROOT
        / "src"
        / "demand_ingestion"
        / "data_sources"
        / "historical_demand"
        / "__init__.py"
    ).exists()


def test_weather_dag_uses_only_weather_ingestion_path():
    dag_imports = _module_imports(PACKAGE_ROOT / "dags" / "weather_ingestion_dag.py")
    pipeline_imports = _module_imports(
        PACKAGE_ROOT / "src" / "demand_ingestion" / "ingestion" / "weather_ingestion.py"
    )

    assert "demand_ingestion.ingestion.weather_ingestion" in dag_imports
    assert "demand_ingestion.open_meteo_client" in pipeline_imports
    assert "demand_ingestion.historical_demand.importer" not in pipeline_imports
    assert "demand_ingestion.ingestion.festival_ingestion" not in dag_imports


def test_festival_dag_uses_only_festival_ingestion_path():
    dag_imports = _module_imports(PACKAGE_ROOT / "dags" / "festival_ingestion_dag.py")
    pipeline_imports = _module_imports(
        PACKAGE_ROOT / "src" / "demand_ingestion" / "ingestion" / "festival_ingestion.py"
    )

    assert "demand_ingestion.ingestion.festival_ingestion" in dag_imports
    assert "demand_ingestion.calendarific_client" in pipeline_imports
    assert "demand_ingestion.historical_demand.importer" not in pipeline_imports
    assert "demand_ingestion.ingestion.weather_ingestion" not in dag_imports

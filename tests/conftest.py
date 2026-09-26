from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def raw_records_path(project_root: Path) -> Path:
    return project_root / "data" / "raw" / "crossref_records.json"


@pytest.fixture
def isolated_settings(tmp_path: Path):
    """Settings whose quality/freshness outputs land in tmp_path, not data/quality/.

    Without this, running the test suite would overwrite the real observability
    artifacts that the reports and dashboard cite as evidence.
    """
    from core.config import load_settings

    settings = load_settings()
    quality_dir = tmp_path / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    paths = replace(
        settings.paths,
        quality_dir=quality_dir,
        freshness_report=quality_dir / "freshness_report.json",
    )
    return replace(settings, paths=paths)

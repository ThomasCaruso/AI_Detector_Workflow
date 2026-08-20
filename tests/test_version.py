from pathlib import Path
import tomllib

import authorship_shift


def test_runtime_version_matches_project_metadata():
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert authorship_shift.__version__ == project["version"]

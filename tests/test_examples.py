from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqltoolkit.connection.config import load_config_from_env, load_config_from_file


ROOT = Path(__file__).resolve().parents[1]
CONFIG_EXAMPLES = ROOT / "examples" / "configs"
ENV_EXAMPLES = ROOT / "examples" / "env-sample"


def _load_env_example(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    sorted(CONFIG_EXAMPLES.glob("*.json")),
    ids=lambda path: path.name,
)
def test_json_examples_are_valid_json(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "databases" in data


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "access_mode"),
    [
        (path, access_mode)
        for path in sorted(CONFIG_EXAMPLES.glob("*.ini"))
        for access_mode in ("primary", "replica")
    ],
    ids=lambda item: item.name if isinstance(item, Path) else item,
)
def test_ini_examples_load_for_both_aliases(path: Path, access_mode: str) -> None:
    dialect = path.name.split(".", 1)[0]
    config = load_config_from_file(
        dialect=dialect,
        tenant="default",
        access_mode=access_mode,
        async_mode=False,
        config_path=path,
    )
    assert config.url


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "access_mode"),
    [
        (path, access_mode)
        for path in sorted(ENV_EXAMPLES.iterdir())
        if path.is_file() and path.suffix == ".env"
        for access_mode in ("primary", "replica")
    ],
)
def test_env_examples_load_for_both_aliases(path: Path, access_mode: str) -> None:
    dialect = path.name.split(".", 1)[0]
    config = load_config_from_env(
        dialect=dialect,
        tenant="default",
        access_mode=access_mode,
        async_mode=False,
        env=_load_env_example(path),
    )
    assert config.url


@pytest.mark.unit
def test_env_aliases_match_file_aliases() -> None:
    env = {
        "SQLTOOLKIT__POSTGRESQL__DEFAULT__READWRITE__URL": (
            "postgresql+psycopg://user:password@localhost:5432/app"
        ),
        "SQLTOOLKIT__POSTGRESQL__DEFAULT__READWRITE__DATABASE_OPTIONS": (
            '{"application_name":"sqltoolkit"}'
        ),
        "SQLTOOLKIT__POSTGRESQL__DEFAULT__READWRITE__OPTIONS": (
            '{"pool_use_lifo": true, "pool_recycle": 1800}'
        ),
        "SQLTOOLKIT__POSTGRESQL__DEFAULT__READWRITE__SESSION_SETTINGS": (
            '{"search_path":"app, public"}'
        ),
    }

    config = load_config_from_env(
        dialect="postgresql",
        tenant="default",
        access_mode="readwrite",
        async_mode=False,
        env=env,
    )

    assert config.url.endswith("?application_name=sqltoolkit")
    assert config.engine_kwargs["pool_use_lifo"] is True
    assert config.engine_kwargs["pool_recycle"] == 1800
    assert config.on_connect_statements == (
        "SELECT pg_catalog.set_config('search_path', 'app, public', false)",
    )

import markdown_gost


def test_package_imports():
    assert markdown_gost is not None


def test_version_attribute_is_string():
    assert isinstance(markdown_gost.__version__, str)


def test_version_matches_pyproject():
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert markdown_gost.__version__ == version

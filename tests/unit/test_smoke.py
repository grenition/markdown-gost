import markdown_gost


def test_package_imports():
    assert markdown_gost is not None


def test_version_attribute_is_string():
    assert isinstance(markdown_gost.__version__, str)


def test_version_matches_pyproject():
    assert markdown_gost.__version__ == "0.1.0"

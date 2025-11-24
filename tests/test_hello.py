import pytest

from eps_spine_shared.hello import hello


@pytest.mark.parametrize(
    "name,expected",
    [
        ("World", "Hello, World!"),
        ("", "Hello, !"),
    ],
)
def test_hello(name, expected):
    assert hello(name) == expected


def test_hello_default():
    assert hello() == "Hello, World!"

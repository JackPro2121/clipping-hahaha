import pytest
from chocodata import parse_views, parse_length


def test_parse_views():
    assert parse_views(1000) == 1000
    assert parse_views("1,234") == 1234
    assert parse_views("1.5K") == 1500
    assert parse_views("2.4M") == 2400000
    assert parse_views("1B") == 1000000000
    assert parse_views(None) == 0
    assert parse_views("invalid") == 0


def test_parse_length():
    assert parse_length(120) == 120
    assert parse_length("0:45") == 45
    assert parse_length("1:30") == 90
    assert parse_length("01:23:45") == 5025
    assert parse_length("invalid") is None

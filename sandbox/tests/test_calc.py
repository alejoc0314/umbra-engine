from sandbox.calc import add


def test_add():
    assert add(2, 3) == 5


def test_power():
    from sandbox.calc import power

    assert power(2, 3) == 8
    assert power(5, 0) == 1


def test_power_rejects_negative_exponent():
    import pytest

    from sandbox.calc import power

    with pytest.raises(ValueError):
        power(2, -1)


def test_mean():
    from sandbox.calc import mean

    assert mean([1, 2, 3]) == 2


def test_mean_rejects_empty():
    import pytest

    from sandbox.calc import mean

    with pytest.raises(ValueError):
        mean([])

import pytest

from umbra.unified.explain import spend_text


@pytest.mark.parametrize("cost, tokens, esperado", [
    (0.42, 60000, "$0.42 + 60k tokens"),
    (0, 60, "60 tokens"),
    (0.42, 0, "$0.42"),
    (0, 1_500_000, "1.5M tokens"),
])
def test_spend_text(cost, tokens, esperado):
    out = spend_text(cost, tokens)
    assert out == esperado
    assert "sin precio" not in out

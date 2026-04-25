import pytest
import requests

import main


def _converter_up():
    try:
        requests.get(main.CONVERT_URL, timeout=1)
        return True
    except requests.RequestException:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _converter_up(), reason=f"converter not reachable at {main.CONVERT_URL}"),
]


def test_convert_markdown_returns_yjs_bytes():
    out = main.convert_markdown("# hello\n\nworld")
    assert isinstance(out, bytes)
    assert len(out) > 0

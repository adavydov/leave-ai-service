import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_main_import_smoke():
    from app.main import app

    assert app is not None
    paths = {route.path for route in app.routes}
    assert '/api/health' in paths

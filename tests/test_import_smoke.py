import importlib
import sys
from pathlib import Path

from fastapi import FastAPI

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_app_main_import_smoke_and_health_route_present():
    module = importlib.import_module("app.main")
    app = getattr(module, "app", None)

    assert app is not None
    assert isinstance(app, FastAPI)
    assert any(route.path == "/api/health" for route in app.routes)

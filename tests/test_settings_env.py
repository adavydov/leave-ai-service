import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.settings import get_settings


def test_settings_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('APP_ENV=dev\nLOG_LEVEL=DEBUG\nMAX_UPLOAD_MB=12\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('MAX_UPLOAD_MB', raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert s.MAX_UPLOAD_MB == 12

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    APP_ENV: str = 'dev'
    LOG_LEVEL: str = 'INFO'
    DEBUG_STEPS: bool = False

    ANTHROPIC_API_KEY: str = ''
    ANTHROPIC_MODEL: str = 'claude-sonnet-4-6'
    ANTHROPIC_VISION_MODEL: str = 'claude-sonnet-4-6'
    ANTHROPIC_STRUCTURED_MODEL: str = 'claude-sonnet-4-6'
    ANTHROPIC_HTTP_TIMEOUT_S: int = 60
    ANTHROPIC_MAX_RETRIES: int = 0

    ANTHROPIC_VISION_TIMEOUT_S: int = 90
    ANTHROPIC_STRUCTURED_PARSE_TIMEOUT_S: int = 15
    ANTHROPIC_STRUCTURED_FALLBACK_TIMEOUT_S: int = 90

    MAX_UPLOAD_MB: int = 15
    PDF_MAX_PAGES: int = 2
    PDF_TARGET_LONG_EDGE: int = 1568
    PDF_COLOR_MODE: str = 'gray'
    MAX_IMAGE_B64_CHARS: int = 4_000_000
    ANTHROPIC_STRUCTURED_DRAFT_MAX_CHARS: int = 12000

    @property
    def MAX_PDF_BYTES(self) -> int:
        return int(self.MAX_UPLOAD_MB) * 1024 * 1024


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == '':
        return default
    try:
        return int(v)
    except ValueError:
        return default


@lru_cache
def get_settings() -> Settings:
    load_dotenv(dotenv_path='.env')
    data = {
        'APP_ENV': os.getenv('APP_ENV', 'dev'),
        'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
        'DEBUG_STEPS': _env_bool('DEBUG_STEPS', False),
        'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY', ''),
        'ANTHROPIC_MODEL': os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
        'ANTHROPIC_VISION_MODEL': os.getenv('ANTHROPIC_VISION_MODEL', os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6')),
        'ANTHROPIC_STRUCTURED_MODEL': os.getenv('ANTHROPIC_STRUCTURED_MODEL', os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6')),
        'ANTHROPIC_HTTP_TIMEOUT_S': _env_int('ANTHROPIC_HTTP_TIMEOUT_S', 60),
        'ANTHROPIC_MAX_RETRIES': _env_int('ANTHROPIC_MAX_RETRIES', 0),
        'ANTHROPIC_VISION_TIMEOUT_S': _env_int('ANTHROPIC_VISION_TIMEOUT_S', 90),
        'ANTHROPIC_STRUCTURED_PARSE_TIMEOUT_S': _env_int('ANTHROPIC_STRUCTURED_PARSE_TIMEOUT_S', 15),
        'ANTHROPIC_STRUCTURED_FALLBACK_TIMEOUT_S': _env_int('ANTHROPIC_STRUCTURED_FALLBACK_TIMEOUT_S', 90),
        'MAX_UPLOAD_MB': _env_int('MAX_UPLOAD_MB', 15),
        'PDF_MAX_PAGES': _env_int('PDF_MAX_PAGES', 2),
        'PDF_TARGET_LONG_EDGE': _env_int('PDF_TARGET_LONG_EDGE', 1568),
        'PDF_COLOR_MODE': os.getenv('PDF_COLOR_MODE', 'gray'),
        'MAX_IMAGE_B64_CHARS': _env_int('MAX_IMAGE_B64_CHARS', 4_000_000),
        'ANTHROPIC_STRUCTURED_DRAFT_MAX_CHARS': _env_int('ANTHROPIC_STRUCTURED_DRAFT_MAX_CHARS', 12000),
    }
    settings = Settings(**data)
    if settings.APP_ENV != 'dev' and not settings.ANTHROPIC_API_KEY:
        raise RuntimeError('ANTHROPIC_API_KEY is required outside dev mode')
    return settings

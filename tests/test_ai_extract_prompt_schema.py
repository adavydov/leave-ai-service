import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import _parse_prompt_ru_json_only


def test_parse_prompt_mentions_extended_leave_schema_fields():
    prompt = _parse_prompt_ru_json_only('черновик')
    assert 'reason_text' in prompt
    assert 'is_part_of_annual_leave' in prompt
    assert 'schedule_reference' in prompt

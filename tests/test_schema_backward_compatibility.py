import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas import LeaveRequestExtract


def test_schema_accepts_old_payload_without_new_leave_fields():
    payload = {
        'employer_name': 'ООО Ромашка',
        'employee': {'full_name': 'Иванов И.И.'},
        'manager': {'full_name': 'Петров П.П.'},
        'request_date': '2026-02-01',
        'leave': {
            'leave_type': 'annual_paid',
            'start_date': '2026-02-10',
            'end_date': '2026-02-16',
            'days_count': 7,
        },
    }
    ex = LeaveRequestExtract.model_validate(payload)
    assert ex.leave.reason_text is None
    assert ex.leave.is_part_of_annual_leave is None
    assert ex.leave.schedule_reference is None

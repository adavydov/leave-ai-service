from pydantic import BaseModel, Field
from typing import Optional, Literal, List

LeaveType = Literal["annual_paid", "unpaid", "other", "unknown"]

class Employee(BaseModel):
    full_name: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    personnel_number: Optional[str] = None

class LeaveInfo(BaseModel):
    leave_type: LeaveType = "unknown"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days_count: Optional[int] = None

class LeaveRequestExtract(BaseModel):
    employee: Employee
    leave: LeaveInfo
    signature_present: Optional[bool] = None
    confidence: float = Field(..., ge=0, le=1)

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List, Literal


LeaveType = Literal[
    "annual_paid",   # ежегодный оплачиваемый
    "unpaid",        # без сохранения
    "study",         # учебный
    "maternity",     # отпуск по беременности и родам
    "childcare",     # по уходу за ребёнком
    "other",
    "unknown",
]


class Employee(BaseModel):
    full_name: Optional[str] = Field(None, description="ФИО сотрудника")
    position: Optional[str] = Field(None, description="Должность")
    department: Optional[str] = Field(None, description="Подразделение")
    personnel_number: Optional[str] = Field(None, description="Табельный номер (если указан)")


class Manager(BaseModel):
    full_name: Optional[str] = Field(None, description="ФИО адресата/руководителя")
    position: Optional[str] = Field(None, description="Должность адресата (если указана)")


class LeaveInfo(BaseModel):
    leave_type: LeaveType = Field("unknown", description="Тип отпуска по смыслу заявления")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    days_count: Optional[int] = Field(None, description="Количество календарных дней")
    comment: Optional[str] = Field(None, description="Примечание/основание/период и т.п.")


class Quality(BaseModel):
    overall_confidence: float = Field(0.0, ge=0, le=1, description="Уверенность 0..1")
    missing_fields: List[str] = Field(default_factory=list, description="Каких важных полей не хватает")
    notes: List[str] = Field(default_factory=list, description="Короткие замечания")


class LeaveRequestExtract(BaseModel):
    schema_version: str = Field("1.0", description="Версия схемы")
    employer_name: Optional[str] = Field(None, description="Организация (если указана)")
    employee: Employee = Field(default_factory=Employee)
    manager: Manager = Field(default_factory=Manager)

    request_date: Optional[str] = Field(None, description="Дата заявления YYYY-MM-DD")
    leave: LeaveInfo = Field(default_factory=LeaveInfo)

    signature_present: Optional[bool] = Field(None, description="Есть ли подпись")
    signature_confidence: Optional[float] = Field(None, ge=0, le=1, description="Уверенность подписи 0..1")

    raw_text: Optional[str] = Field(None, description="Короткая выжимка/фрагменты, подтверждающие поля")
    quality: Quality = Field(default_factory=Quality)


class ValidationIssue(BaseModel):
    level: Literal["error", "warn", "info"] = "info"
    code: str
    message: str


class ApiResponse(BaseModel):
    extract: LeaveRequestExtract
    validation: List[ValidationIssue]

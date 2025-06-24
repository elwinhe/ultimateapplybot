# app/models/email.py
# • Pydantic model for email messages
# • Exposes `EmailMessage` model
# • Uses `pydantic` for data validation
# • Uses `typing` for type hints

from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

class EmailAttachment(BaseModel):
    id: str
    name: str
    content_type: str = Field(..., alias="contentType")
    size: int

class Email(BaseModel):
    id: str
    subject: str
    body: str
    from_address: EmailStr = Field(..., alias="from")
    to_addresses: List[EmailStr] = Field(..., alias="to")
    cc_addresses: List[EmailStr] = Field(default=[], alias="cc")
    bcc_addresses: List[EmailStr] = Field(default=[], alias="bcc")
    received_date: _dt.datetime
    attachments: Optional[List[EmailAttachment]] = None

    model_config = {
        "populate_by_name": True,
        "str_strip_whitespace": True,
        "frozen": True,
    }
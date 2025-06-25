"""
app/models/email.py

Pydantic v2 models for parsing and validating email messages from the Microsoft Graph API.

This module defines the data contract for email objects, ensuring type safety,
validation, and a clean interface for the rest of the application.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Nested Helper Models
class EmailAddress(BaseModel):
    """Represents the 'emailAddress' object within a 'from', 'to', etc. field."""
    name: Optional[str] = None
    address: EmailStr

class Body(BaseModel):
    """Represents the 'body' object, containing content and its type."""
    content_type: Literal["text", "html"] = Field(..., alias="contentType")
    content: str

class EmailAttachment(BaseModel):
    """Pydantic model for a single email attachment."""
    id: str
    name: str
    content_type: str = Field(..., alias="contentType")
    size: int


# Primary Email Model
class Email(BaseModel):
    """
    Represents a single email message, adapted from the Microsoft Graph API response.
    """
    # Core Fields
    id: str
    subject: str
    received_date_time: datetime = Field(..., alias="receivedDateTime")

    body: Body
    from_address: EmailAddress = Field(..., alias="from")
    to_addresses: List[EmailAddress] = Field(..., alias="toRecipients", min_length=1)
    cc_addresses: List[EmailAddress] = Field(default=[], alias="ccRecipients")
    bcc_addresses: List[EmailAddress] = Field(default=[], alias="bccRecipients")

    has_attachments: bool = Field(..., alias="hasAttachments")
    attachments: Optional[List[EmailAttachment]] = None

    model_config = {
        "populate_by_name": True,
        "frozen": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "AAMkAGE1M2_...",
                    "receivedDateTime": "2025-06-24T12:00:00Z",
                    "subject": "Project Update",
                    "hasAttachments": True,
                    "from": {
                        "emailAddress": {
                            "name": "Alice Johnson",
                            "address": "alice@contoso.com"
                        }
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "name": "Bob Smith",
                                "address": "bob@contoso.com"
                            }
                        }
                    ],
                    "body": {
                        "contentType": "html",
                        "content": "<html><body><p>See attached.</p></body></html>"
                    }
                }
            ]
        }
    }

    @model_validator(mode="before")
    @classmethod
    def flatten_graph_api_addresses(cls, values):
        # Helper to extract EmailAddress from Graph API style dict
        def extract_email_address(obj):
            if isinstance(obj, dict) and "emailAddress" in obj:
                return obj["emailAddress"]
            return obj

        if "from" in values and isinstance(values["from"], dict):
            values["from"] = extract_email_address(values["from"])

        for field in ["toRecipients", "ccRecipients", "bccRecipients"]:
            if field in values and isinstance(values[field], list):
                values[field] = [extract_email_address(item) for item in values[field]]

        return values

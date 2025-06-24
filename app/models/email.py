"""
app/models/email.py

Pydantic v2 models for parsing and validating email messages from the Microsoft Graph API.

This module defines the data contract for email objects, ensuring type safety,
validation, and a clean interface for the rest of the application.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

# --- Nested Helper Models ---
# These models represent the nested JSON objects returned by the Graph API.
# This approach is more robust and explicit than direct field mapping.

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

    # Refined Body and Address Fields
    body: Body # Use the nested Body model for robustness
    from_address: EmailAddress = Field(..., alias="from")
    to_addresses: List[EmailAddress] = Field(..., alias="toRecipients")
    cc_addresses: List[EmailAddress] = Field(default=[], alias="ccRecipients")
    bcc_addresses: List[EmailAddress] = Field(default=[], alias="bccRecipients")

    # Attachment Fields
    has_attachments: bool = Field(..., alias="hasAttachments")
    attachments: Optional[List[EmailAttachment]] = None

    # Pydantic v2 Configuration
    model_config = {
        # Allows populating fields by either their name or alias.
        "populate_by_name": True,
        # Enforces immutability after creation, compliant with pure-first design.
        "frozen": True,
        # Provides an example for auto-generated documentation.
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

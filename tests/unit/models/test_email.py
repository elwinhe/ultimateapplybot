# tests/models/test_email.py

import pytest
from copy import deepcopy
from datetime import datetime, timezone
from pydantic import ValidationError
from app.models.email import Email, EmailAddress, Body, EmailAttachment


class TestEmailModel:
    """Test suite for the Email model."""

    # Test data constants
    VALID_PAYLOAD = {
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

    HTML_PAYLOAD = {
        **VALID_PAYLOAD,
        "body": {
            "contentType": "html",
            "content": "<html><body><h1>Hello</h1><p>This is HTML content.</p></body></html>"
        }
    }

    TEXT_PAYLOAD = {
        **VALID_PAYLOAD,
        "body": {
            "contentType": "text",
            "content": "This is plain text content."
        }
    }

    WITH_ATTACHMENTS_PAYLOAD = {
        **VALID_PAYLOAD,
        "attachments": [
            {
                "id": "attachment-1",
                "name": "document.pdf",
                "contentType": "application/pdf",
                "size": 1024000
            },
            {
                "id": "attachment-2", 
                "name": "image.jpg",
                "contentType": "image/jpeg",
                "size": 512000
            }
        ]
    }

    WITH_CC_BCC_PAYLOAD = {
        **VALID_PAYLOAD,
        "ccRecipients": [
            {
                "emailAddress": {
                    "name": "Carol Manager",
                    "address": "carol@contoso.com"
                }
            }
        ],
        "bccRecipients": [
            {
                "emailAddress": {
                    "address": "dave@contoso.com"
                }
            }
        ]
    }

    class TestValidData:
        """Tests for valid data scenarios."""

        def test_email_model_parses_valid_data(self):
            """Tests that the Email model correctly parses a valid API response."""
            email = Email.model_validate(deepcopy(TestEmailModel.VALID_PAYLOAD))

            assert email.id == "AAMkAGE1M2_..."
            assert email.subject == "Project Update"
            assert email.has_attachments is True
            assert email.received_date_time == datetime(2025, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
            
            # Test from address
            assert isinstance(email.from_address, EmailAddress)
            assert email.from_address.name == "Alice Johnson"
            assert email.from_address.address == "alice@contoso.com"
            
            # Test to addresses
            assert len(email.to_addresses) == 1
            assert email.to_addresses[0].name == "Bob Smith"
            assert email.to_addresses[0].address == "bob@contoso.com"
            
            # Test body
            assert isinstance(email.body, Body)
            assert email.body.content_type == "html"
            assert "<html><body><p>See attached.</p></body></html>" in email.body.content

        def test_email_with_html_content(self):
            """Tests email with HTML content type."""
            email = Email.model_validate(deepcopy(TestEmailModel.HTML_PAYLOAD))
            assert email.body.content_type == "html"
            assert "<h1>Hello</h1>" in email.body.content

        def test_email_with_text_content(self):
            """Tests email with text content type."""
            email = Email.model_validate(deepcopy(TestEmailModel.TEXT_PAYLOAD))
            assert email.body.content_type == "text"
            assert email.body.content == "This is plain text content."

        def test_email_with_attachments(self):
            """Tests email with attachment data."""
            email = Email.model_validate(deepcopy(TestEmailModel.WITH_ATTACHMENTS_PAYLOAD))
            
            assert len(email.attachments) == 2
            assert email.attachments[0].id == "attachment-1"
            assert email.attachments[0].name == "document.pdf"
            assert email.attachments[0].content_type == "application/pdf"
            assert email.attachments[0].size == 1024000
            
            assert email.attachments[1].id == "attachment-2"
            assert email.attachments[1].name == "image.jpg"
            assert email.attachments[1].content_type == "image/jpeg"
            assert email.attachments[1].size == 512000

        def test_email_with_cc_bcc_recipients(self):
            """Tests email with CC and BCC recipients."""
            email = Email.model_validate(deepcopy(TestEmailModel.WITH_CC_BCC_PAYLOAD))
            
            # Test CC recipients
            assert len(email.cc_addresses) == 1
            assert email.cc_addresses[0].name == "Carol Manager"
            assert email.cc_addresses[0].address == "carol@contoso.com"
            
            # Test BCC recipients
            assert len(email.bcc_addresses) == 1
            assert email.bcc_addresses[0].name is None  # No name provided
            assert email.bcc_addresses[0].address == "dave@contoso.com"

        def test_email_with_empty_optional_fields(self):
            """Tests email with empty optional fields."""
            payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            payload["ccRecipients"] = []
            payload["bccRecipients"] = []
            payload["attachments"] = None
            
            email = Email.model_validate(payload)
            assert email.cc_addresses == []
            assert email.bcc_addresses == []
            assert email.attachments is None

    class TestInvalidData:
        """Tests for invalid data scenarios."""

        def test_email_model_raises_error_on_missing_required_field(self):
            """Tests that a ValidationError is raised if a required field is missing."""
            invalid_payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            del invalid_payload["subject"]  # Remove a required field

            with pytest.raises(ValidationError):
                Email.model_validate(invalid_payload)

        def test_email_model_raises_error_on_invalid_email_format(self):
            """Tests that EmailStr correctly validates email formats."""
            invalid_payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            invalid_payload["from"]["emailAddress"]["address"] = "not-an-email"
            with pytest.raises(ValidationError, match="value is not a valid email address"):
                Email.model_validate(invalid_payload)

        def test_email_model_raises_error_on_invalid_datetime(self):
            """Tests that invalid datetime format raises ValidationError."""
            invalid_payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            invalid_payload["receivedDateTime"] = "invalid-datetime"

            with pytest.raises(ValidationError):
                Email.model_validate(invalid_payload)

        def test_email_model_raises_error_on_invalid_content_type(self):
            """Tests that invalid content type raises ValidationError."""
            invalid_payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            invalid_payload["body"]["contentType"] = "invalid"

            with pytest.raises(ValidationError):
                Email.model_validate(invalid_payload)

        def test_email_model_raises_error_on_missing_from_address(self):
            """Tests that missing from address raises ValidationError."""
            invalid_payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            del invalid_payload["from"]

            with pytest.raises(ValidationError):
                Email.model_validate(invalid_payload)

        def test_email_model_raises_error_on_empty_to_recipients(self):
            """Tests that empty to recipients raises ValidationError."""
            invalid_payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            invalid_payload["toRecipients"] = []
            with pytest.raises(ValidationError):
                Email.model_validate(invalid_payload)

    class TestEdgeCases:
        """Tests for edge cases and boundary conditions."""

        def test_email_with_special_characters_in_subject(self):
            """Tests email with special characters in subject."""
            payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            payload["subject"] = "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?"
            payload["body"]["contentType"] = "html"  # Ensure valid contentType
            email = Email.model_validate(payload)
            assert email.subject == "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?"

        def test_email_with_very_long_content(self):
            """Tests email with very long content."""
            payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            payload["body"]["content"] = "x" * 10000  # 10k character content
            payload["body"]["contentType"] = "html"  # Ensure valid contentType
            email = Email.model_validate(payload)
            assert len(email.body.content) == 10000

        def test_email_with_unicode_characters(self):
            """Tests email with unicode characters."""
            payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            payload["subject"] = "Unicode: asdf"
            payload["from"]["emailAddress"]["name"] = "José María"
            payload["body"]["contentType"] = "html"  # Ensure valid contentType
            email = Email.model_validate(payload)
            assert email.subject == "Unicode: asdf"
            assert email.from_address.name == "José María"

        def test_email_with_different_datetime_formats(self):
            """Tests email with different datetime formats."""
            # Test with timezone info
            payload = deepcopy(TestEmailModel.VALID_PAYLOAD)
            payload["receivedDateTime"] = "2025-06-24T12:00:00.123Z"
            payload["body"]["contentType"] = "html"  # Ensure valid contentType
            email = Email.model_validate(payload)
            assert email.received_date_time == datetime(2025, 6, 24, 12, 0, 0, 123000, tzinfo=timezone.utc)

    class TestModelConfiguration:
        """Tests for model configuration and behavior."""

        def test_model_is_frozen(self):
            """Tests that the model is immutable."""
            email = Email.model_validate(deepcopy(TestEmailModel.VALID_PAYLOAD))
            with pytest.raises(ValidationError, match="Instance is frozen"):
                email.subject = "New Subject"

        def test_field_aliases_work_correctly(self):
            """Tests that field aliases work correctly."""
            email = Email.model_validate(deepcopy(TestEmailModel.VALID_PAYLOAD))
            
            # Test that aliased fields are accessible
            assert hasattr(email, 'received_date_time')
            assert hasattr(email, 'from_address')
            assert hasattr(email, 'to_addresses')
            assert hasattr(email, 'cc_addresses')
            assert hasattr(email, 'bcc_addresses')
            assert hasattr(email, 'has_attachments')

        def test_model_serialization(self):
            """Tests that the model can be serialized to dict."""
            email = Email.model_validate(deepcopy(TestEmailModel.VALID_PAYLOAD))
            email_dict = email.model_dump()
            
            assert email_dict["id"] == "AAMkAGE1M2_..."
            assert email_dict["subject"] == "Project Update"
            assert email_dict["has_attachments"] is True

        def test_model_json_serialization(self):
            """Tests that the model can be serialized to JSON."""
            email = Email.model_validate(deepcopy(TestEmailModel.VALID_PAYLOAD))
            email_json = email.model_dump_json()
            assert '"id":"AAMkAGE1M2_..."' in email_json
            assert '"subject":"Project Update"' in email_json


class TestEmailAddress:
    """Test suite for the EmailAddress model."""

    def test_email_address_with_name(self):
        """Tests EmailAddress with name and address."""
        address = EmailAddress(name="John Doe", address="john@example.com")
        assert address.name == "John Doe"
        assert address.address == "john@example.com"

    def test_email_address_without_name(self):
        """Tests EmailAddress with only address."""
        address = EmailAddress(address="jane@example.com")
        assert address.name is None
        assert address.address == "jane@example.com"

    def test_email_address_invalid_email(self):
        """Tests that invalid email raises ValidationError."""
        with pytest.raises(ValidationError):
            EmailAddress(address="invalid-email")


class TestBody:
    """Test suite for the Body model."""

    def test_body_html_content(self):
        """Tests Body with HTML content."""
        body = Body(contentType="html", content="<p>Hello</p>")
        assert body.content_type == "html"
        assert body.content == "<p>Hello</p>"

    def test_body_text_content(self):
        """Tests Body with text content."""
        body = Body(contentType="text", content="Hello world")
        assert body.content_type == "text"
        assert body.content == "Hello world"

    def test_body_invalid_content_type(self):
        """Tests that invalid content type raises ValidationError."""
        with pytest.raises(ValidationError):
            Body(contentType="invalid", content="test")


class TestEmailAttachment:
    """Test suite for the EmailAttachment model."""

    def test_attachment_valid_data(self):
        """Tests EmailAttachment with valid data."""
        attachment = EmailAttachment(
            id="att-1",
            name="document.pdf",
            contentType="application/pdf",
            size=1024000
        )
        assert attachment.id == "att-1"
        assert attachment.name == "document.pdf"
        assert attachment.content_type == "application/pdf"
        assert attachment.size == 1024000

    def test_attachment_field_aliases(self):
        """Tests that field aliases work correctly."""
        attachment = EmailAttachment(
            id="att-1",
            name="document.pdf",
            contentType="application/pdf",
            size=1024000
        )
        assert hasattr(attachment, 'content_type')
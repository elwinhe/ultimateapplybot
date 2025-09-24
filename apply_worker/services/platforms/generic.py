import logging
import os
import shutil
from playwright.sync_api import Playwright, Page, Frame, expect
import re
import config
from services.openai import OpenAIService
from services.platforms.base import BasePlatform
import time

logger = logging.getLogger(__name__)

class GenericPlatform(BasePlatform):
    def __init__(self, page: Page, applicant_details_context: str, openai_service: OpenAIService):
        super().__init__(page, applicant_details_context, openai_service)
        self.handled_question_patterns = [
            r"\b((full|legal|first|last)\s?)?name\b|\bfirst and last name\b",
            r"\bemail\b",
            # ... (rest of the patterns)
        ]

    def apply(self, url: str) -> tuple[bool, dict]:
        # ... (implementation of the apply method)
        return True, {}

    # ... (all the _handle methods will be moved here) 
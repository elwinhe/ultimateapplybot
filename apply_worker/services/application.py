import logging
import os
import time
from playwright.sync_api import Playwright, expect

import config
from services.openai import OpenAIService

logger = logging.getLogger(__name__)

class ApplicationService:
    def __init__(self, playwright: Playwright):
        self.browser = playwright.chromium.launch_persistent_context(
            user_data_dir=config.USER_DATA_DIR,
            headless=False,
            slow_mo=50
        )
        self.context = self.browser
        # Ensure all required applicant info is present
        if not all([config.APPLICANT_FIRST_NAME, config.APPLICANT_LAST_NAME, config.APPLICANT_EMAIL, config.APPLICANT_RESUME_PATH, config.APPLICANT_DETAILS_PATH]):
             raise ValueError("Applicant first name, last name, email, resume path, and details path must be configured in .env")
        if not os.path.exists(config.APPLICANT_RESUME_PATH):
            raise FileNotFoundError(f"Resume file not found at: {config.APPLICANT_RESUME_PATH}")
        if not os.path.exists(config.APPLICANT_DETAILS_PATH):
            raise FileNotFoundError(f"Applicant details file not found at: {config.APPLICANT_DETAILS_PATH}")
        
        with open(config.APPLICANT_DETAILS_PATH, 'r') as f:
            self.applicant_details_context = f.read()

        self.openai_service = OpenAIService()

    def _apply_to_greenhouse(self, page, url: str) -> tuple[bool, dict]:
        logger.info("Detected Greenhouse job posting. Starting application process...")
        page.goto(url, wait_until="domcontentloaded")

        # 1. Scrape job description for categorization
        job_description_text = page.locator("#content").inner_text()
        job_details = self.openai_service.categorize_job_description(job_description_text)
        
        # Check for Greenhouse login credentials and attempt autofill
        try:
            logger.info("Attempting to autofill with existing Greenhouse session...")
            autofill_button = page.locator("button", has_text="Autofill with Greenhouse")
            if autofill_button.is_visible():
                autofill_button.click()
                logger.info("Clicked 'Autofill with Greenhouse' button. Please complete any required login steps in the browser.")
                # Add a generous timeout for the user to manually log in and for autofill to complete
                page.wait_for_timeout(15000) # 15 seconds for manual login
                logger.info("Continuing with application after autofill attempt.")
            else:
                logger.info("'Autofill with Greenhouse' button not found. Proceeding with manual fill.")
                self._manually_fill_greenhouse_form(page, job_description_text, self.applicant_details_context)

        except Exception as e:
            logger.warning(f"An error occurred during the autofill process: {e}. Falling back to manual fill.")
            self._manually_fill_greenhouse_form(page, job_description_text, self.applicant_details_context)

        # Before submitting, check for any remaining required fields that might not have been autofilled
        self._manually_fill_greenhouse_form(page, job_description_text, self.applicant_details_context)
        
        # 7. Submit the application
        page.locator("#submit_app").click()

        # 8. Confirmation
        expect(page.locator("#application_confirmation")).to_be_visible(timeout=15000)
        logger.info("Application submitted successfully! Confirmation page detected.")
        return True, job_details
        
    def _manually_fill_greenhouse_form(self, page, job_description_text, applicant_details_context):
        """Helper function to manually fill the Greenhouse application form."""
        # 2. Fill in standard fields
        page.locator("#first_name").fill(config.APPLICANT_FIRST_NAME)
        page.locator("#last_name").fill(config.APPLICANT_LAST_NAME)
        page.locator("#email").fill(config.APPLICANT_EMAIL)
        if config.APPLICANT_PHONE:
            page.locator("#phone").fill(config.APPLICANT_PHONE)
        
        # 3. Handle resume upload
        page.locator("button[aria-describedby='resume-allowable-file-types']").click()
        page.locator("input[data-source='attach']").set_input_files(config.APPLICANT_RESUME_PATH)
        expect(page.locator(".link-container a")).to_be_visible(timeout=10000)
        logger.info("Resume uploaded successfully.")

        # 4. Fill optional, common fields if they exist
        if config.APPLICANT_LINKEDIN_URL:
            page.locator('label:has-text("LinkedIn") + input').fill(config.APPLICANT_LINKEDIN_URL)
        if config.APPLICANT_GITHUB_URL:
            page.locator('label:has-text("GitHub") + input').fill(config.APPLICANT_GITHUB_URL)

        # 5. Handle "Legally authorized to work" question robustly
        auth_question_locator = page.locator('label:text-matches("authorized to work", "i")')
        if auth_question_locator.is_visible():
            # Find the associated select dropdown and choose "Yes"
            select_id = auth_question_locator.get_attribute("for")
            page.locator(f"#{select_id}").select_option(label="Yes")
            logger.info("Answered 'Yes' to work authorization question.")

        # 6. Handle custom required questions
        custom_question_selector = (
            'label:has-text("*")'
            ':not(:text-matches("first name", "i"))'
            ':not(:text-matches("last name", "i"))'
            ':not(:text-matches("email", "i"))'
            ':not(:text-matches("phone", "i"))'
            ':not(:text-matches("resume", "i"))'
            ':not(:text-matches("cv", "i"))'
            ':not(:text-matches("cover letter", "i"))'
            ':not(:text-matches("linkedin", "i"))'
            ':not(:text-matches("github", "i"))'
            ':not(:text-matches("website", "i"))'
            ':not(:text-matches("portfolio", "i"))'
            ':not(:text-matches("authorized to work", "i"))'
        )
        custom_questions = page.locator(custom_question_selector).all()
        for question_label in custom_questions:
            question_text = question_label.inner_text()
            # Find the associated input/textarea
            input_id = question_label.get_attribute("for")
            input_field = page.locator(f"#{input_id}")
            
            # Check if it's a textarea or text input (and not already filled)
            if input_field.tag_name() in ["textarea", "input"] and not input_field.input_value():
                answer = self.openai_service.generate_custom_answer(
                    question=question_text, 
                    job_description=job_description_text,
                    applicant_details=applicant_details_context
                )
                if answer:
                    input_field.fill(answer)
                    time.sleep(1) # Brief pause to mimic human typing speed
        
        logger.info("Completed manual form fill process.")

    def apply_to_job(self, url: str) -> tuple[bool, dict]:
        """
        Navigates to a job URL, categorizes it, and attempts to apply.
        Returns a tuple of (success_boolean, job_details_dict).
        """
        page = self.context.new_page()
        try:
            if "boards.greenhouse.io" in url:
                return self._apply_to_greenhouse(page, url)
            # Add other platforms here with 'elif "boards.lever.co" in url:' etc.
            else:
                logger.warning(f"No specific application logic for URL: {url}")
                return False, {}
        except Exception as e:
            logger.error(f"Failed to apply to {url}: {e}", exc_info=True)
            return False, {}
        finally:
            page.close()

    def close(self):
        self.browser.close() 
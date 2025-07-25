import logging
import os
import time
import re
import shutil
from playwright.sync_api import Playwright, expect

import config
from services.openai import OpenAIService

logger = logging.getLogger(__name__)

class ApplicationService:
    def __init__(self, playwright: Playwright):
        # Clear the cache by deleting the user data directory on startup
        if os.path.exists(config.USER_DATA_DIR):
            logger.info(f"Clearing browser cache by deleting directory: {config.USER_DATA_DIR}")
            shutil.rmtree(config.USER_DATA_DIR)
            logger.info("Cache directory deleted successfully.")

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

        # A centralized list of regex patterns for questions handled by other methods or to be ignored.
        self.handled_question_patterns = [
            # Standard fields (name, contact info)
            r"\b((full|legal|first|last)\s?)?name\b",
            r"\bemail\b",
            r"\bphone\b",
            r"\blinkedin\b",
            r"\bgithub\b",
            r"\btwitter\b",
            r"\b(website|portfolio)\b",
            r"\bhear about\b",
            r"\bearliest start date\b",
            # Education
            r"\bschool\b",
            r"\bdegree\b",
            r"\bdiscipline\b",
            r"\buniversity\b",
            r"\bmajor\b",
            r"\bfield of study\b",
            r"\bgraduation\b",
            r"\bend date\b",
            r"\bmonth\b",
            r"\byear\b",

            # Resume/CV upload
            r"r[eé]sum[eé]|cv|cover letter",

            # Common screening questions
            r"authorized (to|to)? work",
            r"sponsorship",
            r"former|previously employed",
            r"consider(ed)?",
            r"receive text messages",
            r"read|accept|understand",
            r"conditions of employment",
            r"work onsite",
            r"bay area",
            r"san francisco",

            # Explicitly ignored questions (demographics, etc.)
            r"disability",
            r"veteran",
            r"gender",
            r"race",
            r"hispanic|latino",
        ]

    def _get_locator(self, page, selectors):
        """Iterates through a list of selectors and returns the first visible one."""
        for selector in selectors:
            locator = page.locator(selector).first
            if locator.is_visible():
                logger.info(f"Found visible element with selector: '{selector}'")
                return locator
        return None

    def _get_input_by_label(self, page, label_regex):
        """Finds an input field associated with a given label using regex."""
        try:
            label = page.locator(f'label:text-matches("{label_regex}", "i")').first
            if label.is_visible():
                input_id = label.get_attribute("for")
                if input_id:
                    # Use an attribute selector to handle IDs that might start with numbers
                    return page.locator(f'[id="{input_id}"]')
                # Fallback for labels that wrap inputs
                return label.locator("..").locator("input, textarea, select").first
        except Exception as e:
            logger.debug(f"Could not find input for label regex '{label_regex}': {e}")
        return None

    def _fill_standard_fields(self, page):
        """Fills in common, standard text fields on an application form."""
        logger.info("Filling standard fields...")

        # Handle "Full Name" and "Legal Name" edge cases first
        full_name_input = self._get_input_by_label(page, r"^((full|legal)\s)?name$")
        name_handled = False
        if full_name_input and full_name_input.is_visible() and not full_name_input.input_value():
            full_name = f"{config.APPLICANT_FIRST_NAME} {config.APPLICANT_LAST_NAME}"
            full_name_input.fill(full_name)
            logger.info("Filled 'full/legal name'.")
            name_handled = True

        # Dictionary of other standard fields
        fields_to_fill = {
            "email": config.APPLICANT_EMAIL,
            "phone": config.APPLICANT_PHONE,
            "linkedin": config.APPLICANT_LINKEDIN_URL,
            "github": config.APPLICANT_GITHUB_URL,
            "twitter": config.APPLICANT_TWITTER_URL,
            "earliest start date": "ASAP",
            "school": "Case Western Reserve University",
            "university": "Case Western Reserve University", 
            "degree": "Bachelor's",
            "graduation year": "2024",
            "end date year": "2024",
        }

        # Add first/last name to the dict only if we haven't already handled the full name
        if not name_handled:
            fields_to_fill["first name"] = config.APPLICANT_FIRST_NAME
            fields_to_fill["last name"] = config.APPLICANT_LAST_NAME

        for label, value in fields_to_fill.items():
            if value:
                input_field = self._get_input_by_label(page, label)
                if input_field and input_field.is_visible() and input_field.is_editable() and not input_field.input_value():
                    input_field.fill(value)
                    logger.info(f"Filled '{label}'.")
                elif input_field:
                    logger.debug(f"Input for '{label}' was found but was not visible, not editable, or already had a value.")

        # Handle education fields specifically
        self._handle_education_fields(page)

    def _handle_education_fields(self, page):
        """Handles education-related fields like university selection and graduation date."""
        logger.info("Handling education fields...")

        # --- DEBUGGING: Log all labels and select elements ---
        try:
            all_labels = page.locator("label").all()
            all_label_texts = [label.inner_text().strip() for label in all_labels if label.is_visible()]
            logger.info(f"Visible labels on page for education context: {all_label_texts}")

            all_selects = page.locator("select").all()
            logger.info(f"Found {len(all_selects)} total select elements on page for education.")
            for i, select_elem in enumerate(all_selects):
                name_attr = select_elem.get_attribute("name") or ""
                id_attr = select_elem.get_attribute("id") or ""
                logger.info(f"Education select {i+1}: name='{name_attr}', id='{id_attr}'")
        except Exception as debug_err:
            logger.warning(f"Error during education field debug logging: {debug_err}")
        # --- END DEBUGGING ---
        
        # Handle university/school dropdown
        university_selectors = [
            "select[name*='school' i]",
            "select[name*='university' i]",
            "select[id*='school' i]",
            "select[id*='university' i]",
        ]
        
        university_selected = False # Flag to track if university was selected via dropdown
        for selector in university_selectors:
            university_select = page.locator(selector).first
            if university_select.is_visible():
                try:
                    # Try to find Case Western Reserve University
                    university_select.select_option(label=re.compile(r".*case western.*", re.IGNORECASE))
                    logger.info("Selected Case Western Reserve University")
                    university_selected = True
                    break
                except:
                    try:
                        # Fallback to partial match
                        university_select.select_option(label=re.compile(r".*western.*", re.IGNORECASE))
                        logger.info("Selected university with 'western' in name")
                        university_selected = True
                        break
                    except Exception as e:
                        logger.debug(f"Could not select university: {e}")

        # --- Autocomplete / free-text fallback for university -----------------------
        if not university_selected:
            try:
                uni_label = page.locator("label:text-matches('school|university', 'i')").first
                auto_uni_input = uni_label.locator("xpath=following::input[@role='combobox'][1]").first
                if auto_uni_input.is_visible() and auto_uni_input.is_editable():
                    auto_uni_input.fill("Case Western Reserve University")
                    page.wait_for_timeout(600)
                    suggestion = page.locator("div[role='option'], li[role='option']").first
                    if suggestion.is_visible():
                        suggestion.click()
                        logger.info("Selected university via autocomplete suggestion")
                    else:
                        auto_uni_input.press("ArrowDown")
                        page.wait_for_timeout(300)
                        auto_uni_input.press("Enter")
                        logger.info("Confirmed university entry with ArrowDown + Enter")
            except Exception as uni_auto_err:
                logger.debug(f"Autocomplete university fallback failed: {uni_auto_err}")
        
        # Handle degree dropdown
        degree_selectors = [
            "select[name*='degree' i]",
            "select[id*='degree' i]",
        ]
        
        degree_selected = False
        for selector in degree_selectors:
            degree_select = page.locator(selector).first
            if degree_select.is_visible():
                try:
                    # Try bachelor's variants
                    degree_patterns = [r".*bachelor.*", r".*b\.?s\.?.*", r".*ba.*", r".*bs.*"]
                    for pattern in degree_patterns:
                        try:
                            degree_select.select_option(label=re.compile(pattern, re.IGNORECASE))
                            logger.info(f"Selected degree with pattern: {pattern}")
                            degree_selected = True
                            break
                        except:
                            continue
                    if degree_selected:
                        break
                except Exception as e:
                    logger.debug(f"Could not select degree: {e}")

        # --- Autocomplete / free-text fallback for degree -----------------------
        if not degree_selected:
            try:
                degree_label = page.locator("label:text-matches('degree', 'i')").first
                auto_degree_input = degree_label.locator("xpath=following::input[@role='combobox'][1]").first
                if auto_degree_input.is_visible() and auto_degree_input.is_editable():
                    auto_degree_input.fill("Bachelor's")
                    page.wait_for_timeout(800)
                    suggestion = page.locator("div[role='option'], li[role='option']").first
                    if suggestion.is_visible():
                        suggestion.click()
                        logger.info("Selected degree via autocomplete suggestion")
                    else:
                        auto_degree_input.press("ArrowDown")
                        page.wait_for_timeout(300)
                        auto_degree_input.press("Enter")
                        logger.info("Confirmed degree entry with ArrowDown + Enter")
            except Exception as degree_auto_err:
                logger.debug(f"Autocomplete degree fallback failed: {degree_auto_err}")
        
        # Handle graduation month dropdown  
        month_selectors = [
            "select[name*='month' i]",
            "select[id*='month' i]",
            "select[name*='graduation' i][name*='month' i]",
        ]
        
        month_selected = False
        for selector in month_selectors:
            month_select = page.locator(selector).first
            if month_select.is_visible():
                try:
                    # Try to select May (common graduation month)
                    month_select.select_option(label=re.compile(r".*may.*", re.IGNORECASE))
                    logger.info("Selected May for graduation month")
                    month_selected = True
                    break
                except:
                    try:
                        # Fallback to June
                        month_select.select_option(label=re.compile(r".*june.*", re.IGNORECASE))
                        logger.info("Selected June for graduation month")
                        month_selected = True
                        break
                    except Exception as e:
                        logger.debug(f"Could not select graduation month: {e}")
        
        # --- Autocomplete / free-text fallback for month -----------------------
        if not month_selected:
            try:
                month_label = page.locator("label:text-matches('month', 'i')").first
                auto_month_input = month_label.locator("xpath=following::input[@role='combobox'][1]").first
                if auto_month_input.is_visible() and auto_month_input.is_editable():
                    auto_month_input.fill("May")
                    page.wait_for_timeout(800)
                    suggestion = page.locator("div[role='option']:has-text('May'), li[role='option']:has-text('May')").first
                    if suggestion.is_visible():
                        suggestion.click()
                        logger.info("Selected 'May' via autocomplete suggestion")
                    else:
                        auto_month_input.press("ArrowDown")
                        page.wait_for_timeout(300)
                        auto_month_input.press("Enter")
                        logger.info("Confirmed month entry with ArrowDown + Enter")
            except Exception as month_auto_err:
                logger.debug(f"Autocomplete month fallback failed: {month_auto_err}")

    def _handle_resume_upload(self, form_context, main_page=None):
        """Finds and fills the resume upload field, handling various UI patterns."""
        logger.info("Handling resume upload...")

        # A list of selectors for elements that, when clicked, should trigger a file chooser.
        upload_selectors = [
            'button:has-text("Attach")',  # Greenhouse specific "Attach" button
            'button:text-matches("upload file", "i")', # Ashby-specific
            'button:text-matches("upload resume", "i")',
            'button:text-matches("upload cv", "i")',
            'button[data-automation-id*="resume"]',  # Common on modern ATS
            '[aria-label*="resume" i]',             # Catches "Upload resume", "Attach Resume", etc.
            'input[type="file"]'                    # The actual file input itself
        ]

        # Handle FrameLocator vs Page differently for file chooser
        from playwright.sync_api import FrameLocator, Frame, Page
        
        # Treat both FrameLocator and Frame (already-switched context) as an iframe path
        if isinstance(form_context, (FrameLocator, Frame)):
            logger.info("Working within iframe context for file upload")
            
            for selector in upload_selectors:
                target = form_context.locator(selector).first
                
                if target.is_visible():
                    logger.info(f"Found potential resume upload element with selector: '{selector}' in iframe")
                    try:
                        # For iframe file inputs, try direct interaction
                        if selector == 'input[type="file"]':
                            target.set_input_files(config.APPLICANT_RESUME_PATH)
                            logger.info("Successfully set files directly on file input in iframe.")
                        else:
                            # For buttons in iframe, use the main page for file chooser
                            if main_page:
                                logger.info("Clicking attach button and expecting file chooser on main page...")
                                with main_page.expect_file_chooser(timeout=5000) as fc_info:
                                    target.click(force=True)
                                
                                file_chooser = fc_info.value
                                file_chooser.set_files(config.APPLICANT_RESUME_PATH)
                                logger.info("Successfully uploaded file via file chooser from iframe button.")
                            else:
                                target.click(force=True)
                                logger.info("Clicked attach button without file chooser handler.")
                        
                        # Check for confirmation
                        resume_filename = os.path.basename(config.APPLICANT_RESUME_PATH)
                        confirmation_locator = form_context.locator(
                            f"*:text-matches('{re.escape(resume_filename)}|{re.escape(resume_filename.split('.')[0])}', 'i')"
                        ).first
                        
                        expect(confirmation_locator).to_be_visible(timeout=10000)
                        logger.info("Resume upload confirmed by text visibility in iframe.")
                        return
                        
                    except Exception as e:
                        logger.warning(f"Iframe interaction with selector '{selector}' failed. Error: {e}")
                        continue
                        
        else:
            # ========== main-page logic ==========
            logger.info("Working on main page for file upload")

            for selector in upload_selectors:
                target = form_context.locator(selector).first
                if not target.is_visible():
                    continue

                logger.info(f"Found potential resume upload element with selector: '{selector}'")

                try:
                    # 1) direct set when we already have the <input type=file>
                    if selector == 'input[type="file"]':
                        target.set_input_files(config.APPLICANT_RESUME_PATH)
                        logger.info("Uploaded via direct set_input_files on file input.")
                    else:
                        # 2) click the button; if filechooser fires – great
                        with form_context.expect_file_chooser(timeout=3000) as fc_info:
                            target.click(force=True)
                        fc_info.value.set_files(config.APPLICANT_RESUME_PATH)
                        logger.info("Uploaded via file chooser after clicking button.")
                except TimeoutError:
                    # 3) No file-chooser fired – find hidden file input and set directly
                    hidden_input = form_context.locator('input[type="file"]').first
                    if hidden_input.count() and hidden_input.is_enabled():
                        hidden_input.set_input_files(config.APPLICANT_RESUME_PATH)
                        logger.info("Uploaded by setting files on hidden file input fallback.")
                    else:
                        logger.warning("File chooser did not appear and no file input found; trying next selector.")
                        continue  # try next selector

                # confirmation text …
                resume_filename = os.path.basename(config.APPLICANT_RESUME_PATH)
                confirmation = form_context.locator(
                    f"*:text-matches('{resume_filename}|{resume_filename.split('.')[0]}','i')"
                ).first
                expect(confirmation).to_be_visible(timeout=10000)
                logger.info("Resume upload confirmed.")
                return
        
        # If the loop completes without returning, no method worked.
        logger.warning("Could not find and interact with any known resume upload element.")

        # Fallback check for confirmation text, in case the upload succeeded without us detecting it.
        resume_filename = os.path.basename(config.APPLICANT_RESUME_PATH)
        confirmation_locator = form_context.locator(f"text='{resume_filename}', text='{resume_filename.split('.')[0]}'").first
        
        try:
            expect(confirmation_locator).to_be_visible(timeout=5000)
            logger.info("Resume upload confirmed via fallback check.")
        except Exception:
            logger.warning("Could not find resume confirmation text. The upload may have still been successful. Continuing application...")

    def _handle_demographic_questions(self, page):
        """Handles common demographic questions with a neutral/decline answer."""
        logger.info("Handling common demographic questions...")
        
        # A mapping of question keywords to the desired answer label pattern.
        questions_to_answer = {
            r"veteran": r"decline|not a veteran|prefer not to say",
            r"disability": r"decline|prefer not to say|no",
            r"race|ethnicity": r"Asian",
            r"gender": r"Male",
            r"pronouns?": r"he/him",
            r"sexual orientation": r"Straight",
            r"hispanic|latino": r"No",
            r"hear about": r"Website",
        }

        for keyword, answer_pattern in questions_to_answer.items():
            try:
                # Find the label or legend for the question
                question_element = page.locator(f"*:text-matches('{keyword}', 'i')").first
                if question_element.is_visible():
                    # Find the container that holds both the question and answers
                    container = question_element.locator("xpath=ancestor::*[self::div or self::fieldset][1]")
                    if not container.is_visible():
                        container = page # Fallback to page

                    # Attempt to answer via SELECT dropdown
                    select_input = container.locator("select").first
                    if select_input.is_visible() and select_input.is_editable():
                        # Use a regex to find the answer option
                        select_input.select_option(label=re.compile(answer_pattern, re.IGNORECASE))
                        logger.info(f"Selected an answer option for '{keyword}' question.")
                        continue

                    # Attempt to answer via radio button
                    radio_label = container.locator(f"label:text-matches('{answer_pattern}', 'i')").first
                    if radio_label.is_visible():
                        radio_label.click()
                        logger.info(f"Clicked an answer option for '{keyword}' question.")

            except Exception as e:
                logger.debug(f"Could not find or answer demographic question for keyword: '{keyword}'. Error: {e}")

    def _handle_screening_questions(self, page):
        """Handles common yes/no screening questions like work authorization and sponsorship."""
        logger.info("Handling common screening questions...")
        
        # First, let's see what text content is available on the page
        try:
            page_text = page.locator("body").inner_text()
            logger.info(f"Page contains text about work authorization: {'authorized to work' in page_text.lower()}")
            logger.info(f"Page contains text about sponsorship: {'sponsorship' in page_text.lower()}")
            logger.info(f"Page contains text about hear about: {'hear about' in page_text.lower()}")
            logger.info(f"Page contains text about location: {'location' in page_text.lower()}")
        except Exception as e:
            logger.warning(f"Could not analyze page text: {e}")
        
        # A mapping of question keywords to the desired answer label for dropdowns/radios.
        questions_to_answer = {
            # Work authorization
            r"authorized.*work|work.*authorized|legally.*authorized": "Yes",
            
            # Visa sponsorship (now including free text patterns)
            r"sponsorship|visa.*sponsor|sponsor.*visa|require.*sponsorship|sponsorship.*require|future.*sponsorship": "No",
            
            # Employment history
            r"former|previously.*employed|worked for.*before": "No",
            
            # General consideration questions
            r"consider(ed)?|willing.*consider": "Yes",
            
            # Communication preferences
            r"receive.*text|text.*message|sms": "Yes",
            
            # How did you hear about this job
            r"hear.*about|how.*hear|source": "Website",
            
            # Onsite work requirements
            r"work.*onsite|onsite.*work|in.*person": "Yes",
            
            # Geographic questions
            r"bay area|san francisco.*area|currently.*living.*bay|living.*san francisco": "Yes",
            r"from where do you intend to work": "San Francisco, CA",
            r"willing.*to.*relocate": "Yes",

            # --- Merged Demographic Questions ---
            r"gender": r"Male",
            r"race|ethnicity": r"Asian",
            r"veteran": r"Not a veteran",
            r"disability": r"No",
            r"hispanic|latino": r"No",
        }

        for keyword, answer_label in questions_to_answer.items():
            try:
                # --- Sponsorship Free-Text Special Handling ---
                if "sponsorship" in keyword:
                    try:
                        # Try to find and fill a text input first for sponsorship questions
                        sponsorship_label = page.locator(f"label:text-matches('{keyword}', 'i')").first
                        if sponsorship_label.is_visible():
                            # Find a container, same as below, to scope the search
                            container = sponsorship_label.locator("xpath=ancestor::*[self::div or self::fieldset][1]").first
                            if not container.is_visible():
                                container = page
                            
                            text_input = container.locator("input[type='text'], textarea").first
                            if text_input.is_visible() and text_input.is_editable() and not text_input.input_value():
                                text_input.fill(answer_label)
                                # Pressing Enter as user suggested might help submit the value
                                text_input.press("Enter")
                                logger.info(f"Filled sponsorship free-text field with '{answer_label}' and pressed Enter.")
                                # If we successfully filled the text field, we can skip other checks for this keyword
                                continue
                    except Exception:
                        # This is not a critical failure, just a different type of form element
                        logger.debug("Sponsorship free-text handling failed, proceeding to standard checks.")
                # --- End Special Handling ---

                logger.info(f"Looking for question matching pattern: '{keyword}'")
                
                # Try multiple approaches to find the question
                question_selectors = [
                    f"*:text-matches('{keyword}', 'i')",
                    f"label:text-matches('{keyword}', 'i')",
                    f"legend:text-matches('{keyword}', 'i')",
                    f"h1:text-matches('{keyword}', 'i'), h2:text-matches('{keyword}', 'i'), h3:text-matches('{keyword}', 'i')",
                    f"div:text-matches('{keyword}', 'i')",
                    f"span:text-matches('{keyword}', 'i')"
                ]
                
                question_element = None
                for selector in question_selectors:
                    potential_elements = page.locator(selector).all()
                    logger.debug(f"Selector '{selector}' found {len(potential_elements)} elements")
                    if len(potential_elements) > 0:
                        question_element = potential_elements[0]
                        logger.info(f"Found question element using selector: '{selector}'")
                        break
                
                if question_element and question_element.is_visible():
                    # Find the container that holds both the question and answers
                    container_selectors = [
                        "xpath=ancestor::*[self::div or self::fieldset or self::form][1]",
                        "xpath=ancestor::*[self::div][1]",
                        "xpath=parent::*"
                    ]
                    
                    container = None
                    for container_selector in container_selectors:
                        try:
                            potential_container = question_element.locator(container_selector)
                            if potential_container.count() > 0:
                                container = potential_container.first
                                break
                        except:
                            continue
                    
                    if not container:
                        container = page  # Fallback to page if no clear container is found
                        logger.info(f"Using page as container for '{keyword}' question")

                    # Attempt to answer via SELECT dropdown
                    select_inputs = container.locator("select").all()
                    logger.debug(f"Found {len(select_inputs)} select elements in container")
                    
                    answered = False
                    for select_input in select_inputs:
                        if select_input.is_visible() and select_input.is_editable():
                            try:
                                # Get all available options first
                                options = select_input.locator("option").all()
                                option_texts = [opt.inner_text() for opt in options if opt.inner_text().strip()]
                                logger.debug(f"Available options: {option_texts}")
                                
                                # Try exact match first
                                select_input.select_option(label=answer_label)
                                logger.info(f"Selected '{answer_label}' for '{keyword}' question via select dropdown.")
                                answered = True
                                break
                            except:
                                try:
                                    # Try regex match
                                    select_input.select_option(label=re.compile(f".*{re.escape(answer_label)}.*", re.IGNORECASE))
                                    logger.info(f"Selected '{answer_label}' (regex) for '{keyword}' question via select dropdown.")
                                    answered = True
                                    break
                                except Exception as select_error:
                                    logger.debug(f"Could not select option in dropdown: {select_error}")

                    # Attempt to answer via radio button by clicking its label
                    if not answered:
                        radio_labels = container.locator(f"label:text-matches('{re.escape(answer_label)}', 'i')").all()
                        logger.debug(f"Found {len(radio_labels)} radio label elements matching '{answer_label}'")
                        
                        for radio_label in radio_labels:
                            if radio_label.is_visible():
                                try:
                                    radio_label.click()
                                    logger.info(f"Clicked '{answer_label}' radio for '{keyword}' question.")
                                    answered = True
                                    break
                                except Exception as radio_error:
                                    logger.debug(f"Could not click radio label: {radio_error}")
                    
                    if not answered:
                        logger.warning(f"Could not answer question '{keyword}' with standard select/radio, trying custom dropdown...")
                        
                        try:
                            # This handles custom dropdowns common in Greenhouse (divs acting as selects)
                            # The clickable element is often a div that contains an input with role="combobox"
                            # 1. Find the button that opens the dropdown menu.
                            dropdown_button = container.locator("button[aria-haspopup='listbox'], div:has(input[role='combobox'])").first
                            if dropdown_button.is_visible():
                                logger.info(f"Found custom dropdown button for '{keyword}'. Clicking to open.")
                                # Add a small delay
                                page.wait_for_timeout(1500)
                                dropdown_button.click()
                                page.wait_for_timeout(1500)
                                
                                # 2. The options panel is often at the root of the page, not inside the container.
                                options_panel = page.locator("div[role='listbox']").last
                                expect(options_panel).to_be_visible(timeout=3000)
                                first_option = options_panel.locator("*[role='option']").first
                                first_option.click()
                                
                                # 3. Click the option within the now-visible panel.
                                option_to_click = options_panel.locator(f"*[role='option']:text-matches('^{re.escape(answer_label)}$', 'i')").first
                                if option_to_click.is_visible():
                                    option_to_click.click()
                                    page.wait_for_timeout(1500)
                                    logger.info(f"Selected '{answer_label}' from custom dropdown for '{keyword}'.")
                                    answered = True
                                else:
                                    # Try a more flexible match (starts with)
                                    flexible_option_to_click = options_panel.locator(f"*[role='option']:text-matches('^{re.escape(answer_label)}.*', 'i')").first
                                    if flexible_option_to_click.is_visible():
                                        flexible_option_to_click.click()
                                        page.wait_for_timeout(1500)
                                        logger.info(f"Selected '{answer_label}' (flexible match) from custom dropdown for '{keyword}'.")
                                        answered = True
                                    else:
                                        logger.warning(f"Custom dropdown opened, but could not find option starting with '{answer_label}'.")
                                        # Click away to close the dropdown
                                        page.locator("body").click(position={'x': 0, 'y': 0})
                        except Exception as custom_dropdown_error:
                            logger.debug(f"Failed to handle '{keyword}' as a custom dropdown: {custom_dropdown_error}")

                    # --- Free-text fallback ----------------------------------------------------
                    if not answered:
                        try:
                            text_input = container.locator("input[type='text'], textarea").first
                            if text_input.is_visible() and text_input.is_editable():
                                text_input.fill(answer_label)
                                page.wait_for_timeout(300)
                                text_input.press("ArrowDown")
                                page.wait_for_timeout(400)
                                text_input.press("Enter")
                                logger.info(f"Typed '{answer_label}' and confirmed selection for '{keyword}'.")
                                answered = True
                        except Exception as text_err:
                            logger.debug(f"Free-text fallback failed for '{keyword}': {text_err}")

                    if not answered:
                        logger.warning(f"Failed to answer question matching '{keyword}' pattern")
                else:
                    logger.debug(f"No visible question element found for pattern: '{keyword}'")

            except Exception as e:
                logger.warning(f"Error processing question for keyword '{keyword}': {e}")
        
        # Handle location selection specifically with more debugging
        logger.info("Looking for location fields...")
        try:
            location_found = False
            # First, check for custom dropdowns for location
            # A more robust selector: find a label with 'Location' and get the nearby combobox input's container div
            location_label = page.locator("label:text-matches('location(\\s*\\(city\\))?', 'i')").first
            if location_label.is_visible():
                location_dropdown_button = page.locator("div[role='combobox']", has=location_label.locator("+ *")).first
                
                if location_dropdown_button.is_visible():
                    logger.info("Found custom location dropdown. Clicking to open.")
                    # Add a small delay
                    page.wait_for_timeout(300)
                    location_dropdown_button.click()
                    page.wait_for_timeout(300)
                    
                    options_panel = page.locator("div[role='listbox']").last
                    expect(options_panel).to_be_visible(timeout=5000)
                    
                    # Log all available options for debugging
                    all_options = options_panel.locator("*[role='option']").all()
                    all_option_texts = [opt.inner_text() for opt in all_options]
                    logger.info(f"Available location options: {all_option_texts}")

                    # Prioritize Los Altos > California > United States
                    option_patterns = [
                        r"Los Altos.*California|California.*Los Altos",
                        r"California",
                        r"United States|USA|US"
                    ]
                    
                    for pattern in option_patterns:
                        for option in all_options:
                            option_text = option.inner_text()
                            if re.search(pattern, option_text, re.IGNORECASE):
                                option.click()
                                page.wait_for_timeout(1500)
                                logger.info(f"Selected location '{option_text}' from custom dropdown.")
                                location_found = True
                                break
                        if location_found:
                            break
                    
                    if not location_found:
                        logger.warning("Opened custom location dropdown but couldn't find a suitable option.")
                        page.locator("body").click(position={'x': 0, 'y': 0}) # Click away

            # --- Autocomplete text-combo fallback -------------------------------------
            if not location_found and location_label.is_visible():
                try:
                    auto_input = location_label.locator("xpath=following::input[@role='combobox'][1]").first
                    if auto_input.is_visible() and auto_input.is_editable():
                        logger.info("Using autocomplete text field for location.")
                        auto_input.fill("Los Altos")
                        page.wait_for_timeout(600)
                        suggestion = page.locator("div[role='option']").first
                        if suggestion.is_visible():
                            suggestion.click()
                            logger.info("Clicked first autocomplete suggestion for location.")
                            location_found = True
                        else:
                            auto_input.press("ArrowDown")
                            page.wait_for_timeout(300)
                            auto_input.press("ArrowUp")
                            page.wait_for_timeout(300)
                            auto_input.press("Enter")
                            logger.info("Confirmed location entry with ArrowDown + Enter.")
                            location_found = True
                except Exception as ac_err:
                    logger.debug(f"Autocomplete location fallback failed: {ac_err}")

            # If custom dropdown fails or doesn't exist, try standard methods
            if not location_found:
                location_selectors = [
                    "select[name*='location' i]",
                    "select[name*='current' i][name*='location' i]",
                    "input[name*='location' i]",
                    "input[placeholder*='location' i]",
                    "select:has(option:text-matches('california|los altos', 'i'))",
                    "select[name*='address' i]",
                    "select[id*='address' i]",
                    "select[name*='city' i]",
                    "select[id*='city' i]",
                    "select[name*='state' i]",
                    "select[id*='state' i]",
                    "*:text-matches('location|current.*location', 'i') ~ select",
                    "*:text-matches('where.*located', 'i') ~ select",
                    "label:text-matches('location|current.*location', 'i') select"
                ]
                
                # First, let's see what select elements exist on the page
                all_selects = page.locator("select").all()
                logger.info(f"Found {len(all_selects)} total select elements on page")
                
                for i, select_elem in enumerate(all_selects):
                    try:
                        name_attr = select_elem.get_attribute("name") or ""
                        id_attr = select_elem.get_attribute("id") or ""
                        options = select_elem.locator("option").all()
                        option_count = len(options)
                        first_few_options = [opt.inner_text().strip() for opt in options[:3] if opt.inner_text().strip()]
                        
                        logger.debug(f"Select {i+1}: name='{name_attr}', id='{id_attr}', {option_count} options, first few: {first_few_options}")
                        
                        # Check if this might be a location-related select
                        if any(keyword in (name_attr + id_attr).lower() for keyword in ['location', 'address', 'city', 'state', 'country']):
                            logger.info(f"Potential location select found: name='{name_attr}', id='{id_attr}'")
                    except Exception as e:
                            logger.debug(f"Error analyzing select {i+1}: {e}")
            
                location_found = False
                # If custom dropdown fails or doesn't exist, try standard methods
                if not location_found:
                    for selector in location_selectors:
                        location_fields = page.locator(selector).all()
                        logger.debug(f"Location selector '{selector}' found {len(location_fields)} elements")
                        
                        for location_field in location_fields:
                            if location_field.is_visible():
                                logger.info(f"Found location field with selector: '{selector}'")
                                field_type = location_field.evaluate('element => element.tagName.toLowerCase()')
                                
                                if field_type == 'select':
                                    # Get all options and log them
                                    try:
                                        options = location_field.locator("option").all()
                                        option_texts = [opt.inner_text().strip() for opt in options if opt.inner_text().strip()]
                                        logger.info(f"Location select options: {option_texts}")
                                        
                                        # Try to find an option with California or Los Altos
                                        for option_text in option_texts:
                                            if re.search(r"los altos", option_text, re.IGNORECASE):
                                                location_field.select_option(label=option_text)
                                                logger.info(f"Selected Los Altos, California location: '{option_text}'")
                                                location_found = True
                                                break
                                            elif re.search(r"california", option_text, re.IGNORECASE):
                                                location_field.select_option(label=option_text)
                                                logger.info(f"Selected California location: '{option_text}'")
                                                location_found = True
                                                break
                                            elif re.search(r"united states|usa|us", option_text, re.IGNORECASE):
                                                # Save this as a fallback but keep looking for California
                                                fallback_option = option_text
                                        
                                        # If no California found, use US fallback
                                        if not location_found and 'fallback_option' in locals() and fallback_option:
                                            location_field.select_option(label=fallback_option)
                                            logger.info(f"Selected United States location as fallback: '{fallback_option}'")
                                            location_found = True
                                        
                                    except Exception as select_error:
                                        logger.debug(f"Error processing location select: {select_error}")
                                        
                                elif field_type == 'input':
                                    location_field.fill("Los Altos, California, United States")
                                    logger.info("Filled location text field.")
                                    location_found = True
                                    break
                                
                                if location_found:
                                    break
                                    
                            if location_found:
                                break
                            
                    if not location_found:
                        logger.warning("No location field found or filled")
                                
        except Exception as e:
            logger.warning(f"Error handling location field: {e}")
        
        # A list of keywords for statements that require a checkbox to be ticked.
        checkbox_statements = [
            r"i have read|i accept|i understand",
            r"conditions of employment",
        ]

        for statement in checkbox_statements:
            try:
                # Find the text associated with the checkbox
                statement_element = page.locator(f"*:text-matches('{statement}', 'i')").first
                if statement_element.is_visible():
                    # Find a nearby checkbox and check it if it's not already checked
                    container = statement_element.locator("xpath=ancestor::*[self::div or self::label or self::p][1]")
                    checkbox = container.locator("input[type='checkbox']").first
                    if checkbox.is_visible() and not checkbox.is_checked():
                        checkbox.check()
                        logger.info(f"Ticked checkbox related to: '{statement}'")
            except Exception:
                logger.debug(f"Could not find or tick checkbox for statement: '{statement}'.")


    def _fill_custom_questions(self, page, job_description_text):
        """Finds all unanswered text/select fields and uses an LLM to answer them."""
        logger.info("Answering custom questions by discovering empty fields...")

        # Find all potential input fields that might need an answer
        all_inputs = page.locator("input[type='text'], input[type='email'], input[type='tel'], textarea, select").all()
        
        for i, input_locator in enumerate(all_inputs):
            try:
                # Use a try-except block for each field to make it resilient
                if not input_locator.is_visible() or not input_locator.is_editable():
                    continue
                
                is_select = 'select' in input_locator.evaluate('element => element.tagName.toLowerCase()')

                # Check if it's already filled
                if not is_select and input_locator.input_value():
                    logger.debug(f"Input at index {i} is already filled. Skipping.")
                    continue

                question_text = ""
                input_id = input_locator.get_attribute("id")
                
                # 1. Try to find a label by 'for' attribute (most reliable)
                if input_id:
                    label = page.locator(f"label[for='{input_id}']").first
                    if label.is_visible():
                        question_text = label.inner_text()
                
                # 2. If no label, check for a label wrapping the input
                if not question_text:
                    label = input_locator.locator("xpath=ancestor::label").first
                    if label.is_visible():
                        question_text = label.inner_text()
                
                # 3. If still no label, check for a preceding sibling or a legend in a fieldset
                if not question_text:
                    # Check for common heading tags or p tags that act as labels
                    label = input_locator.locator("xpath=preceding-sibling::*[self::label or self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6 or self::p or self::legend]").last
                    if label.is_visible():
                        question_text = label.inner_text()

                if not question_text:
                    # 4. Fallback to placeholder or aria-label as the question
                    aria_label = input_locator.get_attribute("aria-label")
                    placeholder = input_locator.get_attribute("placeholder")
                    question_text = aria_label or placeholder

                if not question_text:
                    logger.debug(f"Could not determine question for a visible, empty input field (index {i}). Skipping.")
                    continue

                # 5. Check if this is a question we should ignore using the master pattern list
                question_lower = question_text.lower().strip()
                if any(re.search(pattern, question_lower, re.IGNORECASE) for pattern in self.handled_question_patterns):
                    logger.debug(f"Skipping already-handled/ignored question: '{question_text}'")
                    continue

                # 6. If we have a valid question, get an answer and fill it
                logger.info(f"Found custom question by discovery: '{question_text}'")
                answer = self.openai_service.generate_custom_answer(
                    question=question_text, 
                    job_description=job_description_text,
                    applicant_details=self.applicant_details_context
                )
                if answer:
                    if is_select:
                        # For select, try to find an option that partially matches the answer
                        # Use a flexible regex to catch variations
                        input_locator.select_option(label=re.compile(f".*{re.escape(answer)}.*", re.IGNORECASE))
                    else:
                        input_locator.fill(answer)
                    logger.info(f"Answered custom question: '{question_text[:50]}...'")
                    time.sleep(1) # Add a small delay to mimic human behavior and avoid rate-limiting

            except Exception as e:
                logger.warning(f"Could not process a potential custom question field (index {i}): {e}")


    def _submit_application(self, page):
        """
        Finds and clicks the submit button, then waits for confirmation.
        """
        logger.info("Looking for a submit button to finalize application.")
        submit_selectors = [
            "button.ashby-application-form-submit-button", # Ashby-specific
            "button[type='submit']",
            "button:text-matches('^(submit|apply|finish|complete)','i')",
            "button[data-automation-id='submitButton']",  # Workday
            "button[data-testid='SubmitButton']"
        ]

        for selector in submit_selectors:
            # Use .first because some pages might have multiple matches (e.g., in hidden forms)
            submit_button = page.locator(selector).first
            if submit_button.count() > 0 and submit_button.is_visible():
                try:
                    logger.info(f"Attempting to click submit button with selector: {selector}")
                    submit_button.click(force=True, timeout=5000)
                    logger.info("Submit button clicked successfully.")
                    return  # Exit after successful click
                except Exception as e:
                    logger.warning(f"Standard click failed for selector {selector}: {e}. Trying JavaScript click.")
                    try:
                        submit_button.dispatch_event('click')
                        logger.info("Submit button clicked successfully via JavaScript.")
                        return  # Exit after successful click
                    except Exception as e2:
                        logger.error(f"JavaScript click also failed for selector {selector}: {e2}")

        logger.warning("Could not find or click a submit button on the final page.")

    def apply_to_job(self, url: str) -> tuple[bool, dict]:
        """
        Navigates to a job URL, determines the platform, and fills out the application.
        """
        page = self.context.new_page()
        trace_path = None # Initialize trace_path
        tracing_started = False # Flag to track tracing status
        try:
            # --- Start Tracing ---
            # Create a unique filename for the trace
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            sanitized_url = re.sub(r'[^a-zA-Z0-9]', '_', url)
            trace_filename = f"trace_{timestamp}_{sanitized_url[:50]}.zip"
            trace_path = os.path.join("output", trace_filename)
            self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            tracing_started = True
            logger.info(f"Tracing started. Trace file will be saved to: {trace_path}")

            logger.info(f"Navigating to job page: {url}")
            page.goto(url, wait_until="domcontentloaded")
            
            # Add a generous static wait for complex pages to finish loading all scripts
            logger.info("Waiting for 5 seconds for page to settle...")
            page.wait_for_timeout(5000)

            # --- Pre-Application Crawling Step ---
            # Handle embedded iframes (common with Greenhouse on company career pages)
            # Wait longer for iframes to load
            logger.info("Waiting for page to fully load including iframes...")
            page.wait_for_timeout(5000)
            
            # 1️⃣  First, see if the form is already in the top-level DOM
            if (page.locator("#application-form, #application, #form, .ashby-application-form-container").count() > 0) or "/application" in page.url:
                logger.info("Found application form in main page – no iframe switch needed")
                form_page = page                # work on the main page
            else:
                logger.info("Form not in main page, searching iframes...")
                form_page = None
                # iterate through all frames Playwright knows about
                for fr in page.frames:
                    try:
                        if fr.locator("#application-form, #application, #form, .ashby-application-form-container").count() > 0:
                            form_page = fr
                            logger.info(f"Found application form inside frame {fr.url[:80]}")
                            break
                    except Exception:
                        # cross-origin frames raise if we touch their DOM; just skip them
                        continue

                if not form_page:
                    logger.warning("Could not locate application form in any frame. Attempting to click an 'Apply' button if available.")

            # ------------- if no form yet, try clicking "Apply" (Ashby, Greenhouse, etc.) -----------------
            if form_page is None:
                apply_button = page.locator(
                    ",".join([
                        "a:text-matches('apply to( this)? job', 'i')",
                        "button:text-matches('apply to( this)? job', 'i')",
                        "a:text-matches('apply for( this)? job', 'i')",
                        "button:text-matches('apply for( this)? job', 'i')",
                        "a:text-matches('^apply( now)?$', 'i')",
                        "button:text-matches('^apply( now)?$', 'i')",
                        "a[href*='apply']",
                        "button[data-testid='applyButton']"
                    ])
                ).first
                if apply_button.is_visible():
                    logger.info("Clicking top-level Apply button (capturing possible new page)")

                    new_page = None
                    try:
                        # Some boards open the form in a new tab/window
                        with self.context.expect_page(timeout=10000) as page_event:
                            apply_button.click()
                        new_page = page_event.value
                        logger.info("Detected new page after clicking Apply button.")
                    except Exception:
                        # No new page event – assume same tab navigation
                        logger.debug("No new page event; staying on same tab.")
                        apply_button.click()

                    target_page = new_page if new_page else page

                    # Wait for the target page to finish loading
                    try:
                        target_page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        logger.debug("Load state wait timed out but proceeding.")

                    if (target_page.locator('#application-form, #application, #form, .ashby-application-form-container').count() > 0) or "/application" in target_page.url:
                        form_page = target_page
                        logger.info("Form found after clicking Apply button.")
                    else:
                        logger.warning("Form not found after clicking Apply button. Continuing without form.")

            # ------------------------------------------------------------------
            # Retry form detection after clicking the Apply button. Some boards
            # (e.g. Ashby) render the form inside a modal that appears a few
            # moments later and does **not** use the classic #application-form
            # ids. Give the page a little extra time and try again using broader
            # heuristics before giving up.
            # ------------------------------------------------------------------
            if form_page is None:
                logger.info("Waiting a bit longer for application form/modal to appear…")
                page.wait_for_timeout(5000)  # allow JS to mount modal components

                # Look again on the top-level page using wider selectors
                alt_form_selectors = [
                    "#application-form", "#application", "#form", ".ashby-application-form-container",
                    "form[action*='apply']",
                    "form[action*='application']",
                    "div[role='dialog'] form",
                    "form[data-test*='PostingApplicationForm']"
                ]
                alt_locator = page.locator(", ".join(alt_form_selectors)).first
                if alt_locator.is_visible():
                    form_page = page
                    logger.info("Found application form after waiting (top-level page).")

                # If not on main page, search through iframes again
                if form_page is None:
                    for fr in page.frames:
                        try:
                            if fr.locator(", ".join(alt_form_selectors)).count() > 0:
                                form_page = fr
                                logger.info(f"Found application form inside frame {fr.url[:80]} after retry.")
                                break
                        except Exception:
                            continue

                # As a last resort, if we can see *any* editable input on the
                #     page or in its frames, treat that context as the form.
                if form_page is None:
                    try:
                        page.wait_for_selector("input, textarea, select", timeout=3000)
                        logger.warning("No explicit form container found, but inputs are present – proceeding with main page as form context.")
                        form_page = page
                    except Exception:
                        logger.error("Still could not locate an application form after retries.")
                        return False, {}

            # If we still don't have a form, give up gracefully
            if form_page is None:
                logger.error("Could not locate application form even after attempting to click an 'Apply' button.")
                return False, {}

            # --- Platform-Specific Optimizations ---
            # Note: The form_page variable might be a FrameLocator, which doesn't have a `url` attribute.
            # We still check the top-level page URL for this.
            if "greenhouse.io" in page.url or page.locator("iframe[src*='greenhouse.io']").first:
                # Skip Greenhouse autofill as it may prevent manual field completion.
                logger.info("Greenhouse detected, but skipping autofill to allow manual field completion.")
                # autofill_button = form_page.locator("button", has_text="Autofill with Greenhouse").first
                # if autofill_button.is_visible():
                #     logger.info("Greenhouse detected, attempting autofill.")
                #     autofill_button.click()
                #     page.wait_for_timeout(3000) # Wait for autofill
                # else:
                #     logger.info("No Greenhouse autofill button found.")
            
            # --- General Application Logic ---
            logger.info("Starting general form filling process...")
            if form_page is page:
                form_page.locator("body").wait_for(timeout=5000)
            
            # Limit the job description text to avoid exceeding token limits
            full_job_description = form_page.locator("body").inner_text()
            max_words = 400
            job_description_words = full_job_description.split()
            truncated_job_description = " ".join(job_description_words[:max_words])
            
            job_details = {}
            # if truncated_job_description:
            #     logger.info(f"Truncated job description to {len(truncated_job_description)} characters to avoid token limit.")
            #     job_details = self.openai_service.categorize_job_description(truncated_job_description)
            # else:
            #     logger.warning("Could not extract job description from the page.")
            
            # Loop through multi-page applications
            MAX_PAGES = 10
            for page_num in range(MAX_PAGES):
                logger.info(f"Processing application page {page_num + 1}...")

                # Fill all visible fields on the current page using the correct context (form_page)
                self._fill_standard_fields(form_page)
                self._handle_resume_upload(form_page, page) # Pass the main page to _handle_resume_upload
                self._handle_screening_questions(form_page)
                self._fill_custom_questions(form_page, truncated_job_description)

                # Look for a "Next" or "Continue" button within the form context
                next_selectors = [
                    "button:text-matches('^(next|continue)$', 'i')",
                    "a:text-matches('^(next|continue)$', 'i')",
                ]
                next_button = form_page.locator(", ".join(next_selectors)).first

                if next_button.is_visible():
                    logger.info("Found 'Next/Continue' button, proceeding to next page.")
                    next_button.click()
                    # After clicking, we might need to wait for the frame/page to reload
                    form_page.wait_for_load_state("domcontentloaded", timeout=10000)
                else:
                    logger.info("No 'Next/Continue' button found. Assuming this is the final page.")
                    break  # Exit the loop to proceed to submission

            self._submit_application(form_page)

            # --- Confirmation ---
            # Use a more specific selector for the confirmation message to avoid matching nav links.
            # Check within a specific container or for a heading tag.
            confirmation_selector = "div[id*='content'] h1, div[class*='content'] h1, h1, h2"
            confirmation_text_locator = page.locator(confirmation_selector).filter(
                has_text=re.compile("thank you|application submitted|successfully submitted", re.IGNORECASE)
            )
            
            expect(confirmation_text_locator.first).to_be_visible(timeout=20000)
            logger.info("Application submitted successfully! Confirmation detected.")
            
            # Stop tracing on success
            if tracing_started:
                self.context.tracing.stop(path=trace_path)
                logger.info(f"Application successful. Trace file saved to {trace_path}")
            
            return True, job_details

        except Exception as e:
            logger.error(f"Failed to apply to {url}: {e}", exc_info=True)
            
            # --- Save trace and screenshot on failure ---
            if page:
                # Create a unique filename for the screenshot
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                sanitized_url = re.sub(r'[^a-zA-Z0-9]', '_', url)
                screenshot_filename = f"failure_{timestamp}_{sanitized_url[:50]}.png"
                screenshot_path = os.path.join("output", screenshot_filename)
                try:
                    page.screenshot(path=screenshot_path)
                    logger.info(f"Screenshot saved to {screenshot_path}")
                except Exception as screenshot_error:
                    logger.error(f"Failed to save screenshot: {screenshot_error}")

            if tracing_started:
                if trace_path:
                    try:
                        self.context.tracing.stop(path=trace_path)
                        logger.info(f"Trace file for failed application saved to: {trace_path}")
                    except Exception as trace_error:
                        logger.error(f"Failed to stop tracing: {trace_error}")
                else:
                    # If trace_path wasn't set, create a default one
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    default_trace_path = os.path.join("output", f"failure_trace_{timestamp}.zip")
                    try:
                        self.context.tracing.stop(path=default_trace_path)
                        logger.info(f"Trace file for failed application saved to: {default_trace_path}")
                    except Exception as trace_error:
                        logger.error(f"Failed to stop tracing with default path: {trace_error}")

            return False, {}
        finally:
            if page:
                page.close()

    def close(self):
        self.browser.close() 
import boto3
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from botocore.exceptions import ClientError
from playwright.sync_api import sync_playwright, Playwright, expect
import time

import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GoogleSheetsService:
    def __init__(self):
        # ... (Same as sqs_consumer)
        creds_json = json.loads(config.GOOGLE_SERVICE_ACCOUNT_CREDS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open(config.GOOGLE_SHEET_NAME).sheet1

    def update_status(self, row: int, status: str):
        """Updates the status in a specific row."""
        try:
            self.sheet.update_cell(row, 5, status) # Column E for status
            logger.info(f"Updated status to '{status}' for row {row}")
        except Exception as e:
            logger.error(f"Failed to update status for row {row}: {e}")


class ApplicationService:
    def __init__(self, playwright: Playwright):
        self.browser = playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context()

    def apply_to_job(self, url: str) -> bool:
        """
        Navigates to a job URL and attempts to apply.
        This is a placeholder for the complex application logic.
        """
        page = self.context.new_page()
        try:
            logger.info(f"Navigating to {url}...")
            page.goto(url, wait_until="domcontentloaded")
            
            # --- Placeholder Logic ---
            # In a real scenario, you would have complex logic here to detect the platform
            # (e.g., Greenhouse, Lever) and fill out the form fields.
            # For now, we'll just simulate a process that takes time.
            time.sleep(5) 
            
            # Simulate success for now
            logger.info(f"Successfully simulated applying to {url}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply to {url}: {e}", exc_info=True)
            return False
        finally:
            page.close()

    def close(self):
        self.browser.close()


class ApplyWorker:
    def __init__(self, playwright: Playwright):
        self.sqs_client = boto3.client("sqs", region_name=config.AWS_REGION)
        self.sheets_service = GoogleSheetsService()
        self.application_service = ApplicationService(playwright)

    def process_message(self, message: dict):
        body_str = message['Body']
        body = json.loads(body_str)
        url = body.get('url')
        sheet_row = body.get('sheet_row')

        if not all([url, sheet_row]):
            logger.warning(f"Received message without a URL or sheet_row: {body_str}")
            # We should still delete the malformed message to avoid a loop
            self.sqs_client.delete_message(
                QueueUrl=config.SQS_APPLY_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            return

        # 1. Attempt to apply
        success = self.application_service.apply_to_job(url)

        # 2. Update the status in the exact row
        status = "APPLIED" if success else "FAILED"
        self.sheets_service.update_status(sheet_row, status)

        # 3. Delete the message from the apply queue
        self.sqs_client.delete_message(
            QueueUrl=config.SQS_APPLY_QUEUE_URL,
            ReceiptHandle=message['ReceiptHandle']
        )
        logger.info(f"Deleted message from apply queue: {message['MessageId']}")


    def start(self):
        logger.info("Starting Apply Worker...")
        while True:
            try:
                response = self.sqs_client.receive_message(
                    QueueUrl=config.SQS_APPLY_QUEUE_URL,
                    MaxNumberOfMessages=1, # Process one at a time due to browser automation
                    WaitTimeSeconds=20,
                    VisibilityTimeout=120 # Give enough time for playwright
                )
                messages = response.get('Messages', [])
                if messages:
                    logger.info(f"Received {len(messages)} new application message(s).")
                    for message in messages:
                        self.process_message(message)
                else:
                    logger.info("No new application messages. Waiting...")
            except KeyboardInterrupt:
                logger.info("Worker stopped by user.")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred in the worker loop: {e}", exc_info=True)
        
        self.application_service.close() 
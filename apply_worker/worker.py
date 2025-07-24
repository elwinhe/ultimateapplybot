import boto3
import json
import logging
from botocore.exceptions import ClientError
from playwright.sync_api import sync_playwright, Playwright
import os
import time

import config
from services.google_sheets import GoogleSheetsService
from services.application import ApplicationService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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

        # 1. Attempt to apply and categorize the job
        success, job_details = self.application_service.apply_to_job(url)

        # 2. Update the sheet with job details from AI
        if job_details:
            self.sheets_service.update_job_details(
                row=sheet_row,
                job_title=job_details.get("job_title", "N/A"),
                seniority=job_details.get("seniority", "N/A"),
                technologies=job_details.get("technologies", "N/A"),
            )

        # 3. Update the status in the exact row
        status = "APPLIED" if success else "FAILED"
        self.sheets_service.update_status(sheet_row, status)

        # 4. Delete the message from the apply queue
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
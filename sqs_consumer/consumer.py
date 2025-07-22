import boto3
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import config

logger = logging.getLogger(__name__)

class GoogleSheetsService:
    """A service for interacting with the Google Sheets API."""

    def __init__(self):
        if not all([config.GOOGLE_SHEET_NAME, config.GOOGLE_SERVICE_ACCOUNT_CREDS]):
            raise ValueError("Google Sheet name and service account credentials must be configured.")
        
        try:
            creds_json = json.loads(config.GOOGLE_SERVICE_ACCOUNT_CREDS)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open(config.GOOGLE_SHEET_NAME).sheet1
            logger.info("Successfully connected to Google Sheet: %s", config.GOOGLE_SHEET_NAME)
            self._initialize_sheet()
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}", exc_info=True)
            raise

    def _initialize_sheet(self):
        """Writes the header row if the sheet is empty."""
        if not self.sheet.get_all_values():
            self.sheet.append_row(["url", "source_message_id", "timestamp"])
            logger.info("Wrote header row to empty sheet.")

    def append_row(self, data: list):
        """Appends a new row to the sheet."""
        self.sheet.append_row(data)
        logger.info("Appended new row to Google Sheet.")


class SQSConsumer:
    """A consumer for processing messages from an SQS queue."""

    def __init__(self):
        if not all([config.AWS_ACCESS_KEY_ID, config.AWS_SECRET_ACCESS_KEY, config.SQS_QUEUE_URL]):
            raise ValueError("AWS credentials and SQS_QUEUE_URL must be configured.")
            
        try:
            self.sqs_client = boto3.client("sqs", region_name=config.AWS_REGION)
            logger.info("Successfully connected to SQS queue: %s", config.SQS_QUEUE_URL)
        except (NoCredentialsError, PartialCredentialsError, ClientError) as e:
            logger.error(f"Failed to connect to SQS: {e}")
            raise

        self.sheets_service = GoogleSheetsService()

    def _process_message(self, message: dict):
        """Parses a message and appends its data to the Google Sheet."""
        try:
            body = json.loads(message['Body'])
            url = body.get('url')
            source_id = body.get('source_message_id')
            timestamp = body.get('timestamp')

            self.sheets_service.append_row([url, source_id, timestamp])
            logger.info(f"Successfully processed and saved URL: {url}")

            # Delete the message from the queue
            self.sqs_client.delete_message(
                QueueUrl=config.SQS_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            logger.info("Deleted message from queue.")

        except Exception as e:
            logger.error(f"An error occurred while processing message: {e}", exc_info=True)

    def start_consuming(self):
        """Starts an infinite loop to poll for and process messages."""
        logger.info("Starting SQS consumer...")
        while True:
            try:
                response = self.sqs_client.receive_message(
                    QueueUrl=config.SQS_QUEUE_URL,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=20
                )
                messages = response.get('Messages', [])
                if messages:
                    logger.info(f"Received {len(messages)} new messages.")
                    for message in messages:
                        self._process_message(message)
                else:
                    logger.info("No new messages. Waiting...")
            except KeyboardInterrupt:
                logger.info("Consumer stopped by user.")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred in the consumer loop: {e}", exc_info=True) 
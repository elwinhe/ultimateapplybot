import boto3
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from gspread.exceptions import APIError
import time
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

    def get_all_urls(self) -> set:
        """Fetches all URLs from the first column of the sheet to check for duplicates."""
        logger.info("Fetching existing URLs from sheet for deduplication...")
        # Assumes URLs are in the first column (A)
        urls = self.sheet.col_values(1)
        # Skip header row
        return set(urls[1:])

    def _initialize_sheet(self):
        """Writes the header row if the sheet is empty."""
        if not self.sheet.get_all_values():
            self.sheet.append_row(["url", "source_message_id", "to_address", "timestamp", "status"])
            logger.info("Wrote header row to empty sheet.")

    def append_rows(self, data: list) -> int:
        """Appends multiple rows and returns the starting row number of the appended data."""
        update_result = self.sheet.append_rows(data, value_input_option='USER_ENTERED')
        # Response gives a range like 'Sheet1!A58:D67'. We need the starting row, 58.
        updated_range = update_result['updates']['updatedRange']
        # 'Sheet1!A58:D67' -> 'A58'
        start_cell = updated_range.split('!')[1].split(':')[0]
        # 'A58' -> 58
        start_row = int("".join(filter(str.isdigit, start_cell)))
        logger.info(f"Appended {len(data)} new rows starting at row {start_row} to Google Sheet.")
        return start_row


class SQSConsumer:
    """A consumer for processing messages from an SQS queue."""

    def __init__(self):
        if not all([
            config.AWS_ACCESS_KEY_ID, 
            config.AWS_SECRET_ACCESS_KEY, 
            config.SQS_QUEUE_URL,
            config.SQS_APPLY_QUEUE_URL
        ]):
            raise ValueError("AWS credentials, SQS_QUEUE_URL, and SQS_APPLY_QUEUE_URL must be configured.")
            
        try:
            self.sqs_client = boto3.client("sqs", region_name=config.AWS_REGION)
            # Validate connection to the primary queue
            self.sqs_client.get_queue_attributes(QueueUrl=config.SQS_QUEUE_URL, AttributeNames=['All'])
            logger.info("Successfully connected to SQS queue: %s", config.SQS_QUEUE_URL)
            # Validate connection to the apply queue
            self.sqs_client.get_queue_attributes(QueueUrl=config.SQS_APPLY_QUEUE_URL, AttributeNames=['All'])
            logger.info("Successfully connected to SQS apply queue: %s", config.SQS_APPLY_QUEUE_URL)
        except (NoCredentialsError, PartialCredentialsError, ClientError) as e:
            logger.error(f"Failed to connect to SQS: {e}")
            raise

        self.sheets_service = GoogleSheetsService()
        self.auto_apply_platforms = ["lever.co", "greenhouse.io", "ashbyhq.com", "linkedin.com"]

    def _is_auto_appliable(self, url: str) -> bool:
        """Checks if a URL is from a platform we can automatically apply to."""
        return any(platform in url for platform in self.auto_apply_platforms)

    def start_consuming(self):
        """Starts an infinite loop to poll for and process messages in batches."""
        logger.info("Starting SQS consumer...")
        while True:
            try:
                response = self.sqs_client.receive_message(
                    QueueUrl=config.SQS_QUEUE_URL,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=20
                )
                messages = response.get('Messages', [])
                if not messages:
                    logger.info("No new messages. Waiting...")
                    continue
                
                logger.info(f"Received {len(messages)} new messages.")
                
                # 1. Fetch existing URLs to prevent duplicates
                existing_urls = self.sheets_service.get_all_urls()
                
                rows_to_append = []
                messages_to_process = []
                messages_to_delete_immediately = [] # For duplicates found in this batch

                for message in messages:
                    try:
                        url = json.loads(message['Body']).get('url')
                        if url in existing_urls:
                            # This URL is already in the sheet, mark for deletion
                            messages_to_delete_immediately.append({
                                'Id': message['MessageId'], 
                                'ReceiptHandle': message['ReceiptHandle']
                            })
                            existing_urls.add(url) # Also add to set to handle in-batch duplicates
                        else:
                            # This is a new URL
                            messages_to_process.append(message)
                            existing_urls.add(url)
                    except (json.JSONDecodeError, TypeError):
                        logger.error(f"Malformed message body, skipping: {message.get('Body')}")

                # Prepare new rows for sheets from valid, new messages
                for message in messages_to_process:
                    body = json.loads(message['Body'])
                    rows_to_append.append([
                        body.get('url'),
                        body.get('source_message_id'),
                        body.get('to_address'),
                        body.get('timestamp'),
                        "PENDING"
                    ])

                # 2. Batch append to Google Sheets if there are new rows
                if rows_to_append:
                    try:
                        start_row = self.sheets_service.append_rows(rows_to_append)
                        
                        # 3. Forward to apply queue where applicable
                        for i, message in enumerate(messages_to_process):
                            body = json.loads(message['Body'])
                            if self._is_auto_appliable(body['url']):
                                sheet_row = start_row + i
                                body['sheet_row'] = sheet_row
                                self.sqs_client.send_message(
                                    QueueUrl=config.SQS_APPLY_QUEUE_URL,
                                    MessageBody=json.dumps(body)
                                )
                    except APIError as e:
                        logger.error(f"Failed to write batch to Google Sheets. Messages will be reprocessed. Error: {e}")
                        # Don't delete, let them be reprocessed after timeout
                        time.sleep(60) 
                        continue # Skip deletion for this batch

                # 4. Batch delete all processed messages (newly added and duplicates)
                all_messages_to_delete = messages_to_delete_immediately + [
                    {'Id': msg['MessageId'], 'ReceiptHandle': msg['ReceiptHandle']} 
                    for msg in messages_to_process
                ]

                if all_messages_to_delete:
                    self.sqs_client.delete_message_batch(
                        QueueUrl=config.SQS_QUEUE_URL,
                        Entries=all_messages_to_delete
                    )
                    logger.info(f"Successfully processed and deleted batch of {len(all_messages_to_delete)} messages.")

            except KeyboardInterrupt:
                logger.info("Consumer stopped by user.")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred in the consumer loop: {e}", exc_info=True) 
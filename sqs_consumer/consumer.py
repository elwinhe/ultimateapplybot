import boto3
import json
import logging
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from gspread.exceptions import APIError
import time
import config
from services.google_sheets import GoogleSheetsService

logger = logging.getLogger(__name__)


class SQSConsumer:
    """A consumer for processing messages from an SQS queue."""
    BUFFER_MAX_SIZE = 100
    WRITE_INTERVAL_SECONDS = 30

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
        self.auto_apply_platforms = ["lever.co", "greenhouse.io", "ashbyhq.com"]
        
        # Initialize an in-memory cache for URLs to prevent rate limiting
        logger.info("Initializing local URL cache from Google Sheet...")
        self.existing_urls = self.sheets_service.get_all_urls()
        logger.info(f"Successfully initialized cache with {len(self.existing_urls)} URLs.")
        
        # Initialize write buffer and tracking for batched writes
        self.write_buffer = []
        self.buffered_messages_for_delete = []
        self.last_write_time = time.time()


    def _is_auto_appliable(self, url: str) -> bool:
        """Checks if a URL is from a platform we can automatically apply to."""
        return any(platform in url for platform in self.auto_apply_platforms)

    def _flush_write_buffer(self):
        """Writes the current buffer to Google Sheets and clears it."""
        if not self.write_buffer:
            return

        logger.info(f"Flushing buffer with {len(self.write_buffer)} rows to Google Sheets.")
        try:
            start_row = self.sheets_service.append_rows(self.write_buffer)
            
            # Forward appliable URLs to the next queue
            for i, row_data in enumerate(self.write_buffer):
                url = row_data[0] # URL is the first item
                if self._is_auto_appliable(url):
                    sheet_row_num = start_row + i
                    # Find the original message to enrich and forward
                    original_message_body = json.loads(self.buffered_messages_for_delete[i]['Body'])
                    original_message_body['sheet_row'] = sheet_row_num
                    self.sqs_client.send_message(
                        QueueUrl=config.SQS_APPLY_QUEUE_URL,
                        MessageBody=json.dumps(original_message_body)
                    )
            
            # Batch delete messages from the primary queue, respecting the 10-message limit
            all_entries_to_delete = [
                {'Id': msg['MessageId'], 'ReceiptHandle': msg['ReceiptHandle']}
                for msg in self.buffered_messages_for_delete
            ]
            
            if all_entries_to_delete:
                logger.info(f"Preparing to delete {len(all_entries_to_delete)} messages in batches of 10.")
                for i in range(0, len(all_entries_to_delete), 10):
                    batch = all_entries_to_delete[i:i + 10]
                    self.sqs_client.delete_message_batch(
                        QueueUrl=config.SQS_QUEUE_URL,
                        Entries=batch
                    )
                    logger.info(f"Deleted a batch of {len(batch)} messages.")
                logger.info("Finished deleting all message batches.")

            # Clear buffers and reset timer on success
            self.write_buffer.clear()
            self.buffered_messages_for_delete.clear()
            self.last_write_time = time.time()

        except APIError as e:
            logger.error(f"Failed to write buffer to Google Sheets. Will retry. Error: {e}")
            # Do not clear buffers, allow for retry on the next cycle.
            # Add a small delay to avoid hammering the API on retries.
            time.sleep(60)
        except Exception as e:
            logger.error(f"An unexpected error occurred during buffer flush: {e}", exc_info=True)


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
                
                if messages:
                    logger.info(f"Received {len(messages)} new messages.")
                    
                    # Process messages and add them to the buffer
                    for message in messages:
                        try:
                            url = json.loads(message['Body']).get('url')
                            if url in self.existing_urls:
                                # If URL is a duplicate, delete immediately without buffering
                                self.sqs_client.delete_message(
                                    QueueUrl=config.SQS_QUEUE_URL,
                                    ReceiptHandle=message['ReceiptHandle']
                                )
                            else:
                                # It's a new URL, add to cache and buffer
                                self.existing_urls.add(url)
                                body = json.loads(message['Body'])
                                self.write_buffer.append([
                                    body.get('url'),
                                    body.get('subject'),
                                    body.get('user_id'),
                                    body.get('received_date_time'),
                                    "PENDING" # Initial status
                                ])
                                self.buffered_messages_for_delete.append(message)
                        except (json.JSONDecodeError, TypeError):
                            logger.error(f"Malformed message body, skipping: {message.get('Body')}")
                
                # Check if it's time to flush the buffer
                time_since_last_write = time.time() - self.last_write_time
                if (len(self.write_buffer) >= self.BUFFER_MAX_SIZE) or \
                   (self.write_buffer and time_since_last_write >= self.WRITE_INTERVAL_SECONDS):
                    self._flush_write_buffer()

            except KeyboardInterrupt:
                logger.info("Consumer stopping. Flushing final buffer...")
                self._flush_write_buffer()
                logger.info("Consumer stopped by user.")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred in the consumer loop: {e}", exc_info=True)
                # Pause briefly to prevent rapid-fire errors
                time.sleep(10) 
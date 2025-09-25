import boto3
import json
import logging
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import time
import asyncio
from datetime import datetime
from uuid import uuid4
import asyncpg
import config

logger = logging.getLogger(__name__)


class SQLSQSConsumer:
    """A consumer for processing messages from SQS queue and storing in PostgreSQL."""
    BUFFER_MAX_SIZE = 100
    WRITE_INTERVAL_SECONDS = 30

    def __init__(self):
        if not all([
            config.AWS_ACCESS_KEY_ID, 
            config.AWS_SECRET_ACCESS_KEY, 
            config.SQS_QUEUE_URL,
            config.SQS_APPLY_QUEUE_URL
        ]):
            raise ValueError("AWS credentials and SQS URLs must be configured.")
            
        try:
            self.sqs_client = boto3.client("sqs", region_name=config.AWS_REGION)
            self.sqs_client.get_queue_attributes(QueueUrl=config.SQS_QUEUE_URL, AttributeNames=['All'])
            logger.info("Successfully connected to SQS queue: %s", config.SQS_QUEUE_URL)
            self.sqs_client.get_queue_attributes(QueueUrl=config.SQS_APPLY_QUEUE_URL, AttributeNames=['All'])
            logger.info("Successfully connected to SQS apply queue: %s", config.SQS_APPLY_QUEUE_URL)
        except (NoCredentialsError, PartialCredentialsError, ClientError) as e:
            logger.error(f"Failed to connect to SQS: {e}")
            raise

        # Initialize write buffer for batch processing
        self.write_buffer = []
        self.buffered_messages_for_delete = []
        self.last_write_time = time.time()
        
        # PostgreSQL connection will be created in async context
        self.db_pool = None

    async def initialize_db(self):
        """Initialize PostgreSQL connection pool."""
        self.db_pool = await asyncpg.create_pool(
            config.POSTGRES_URL,
            min_size=1,
            max_size=10
        )
        logger.info("Successfully connected to PostgreSQL")

    async def close(self):
        """Close database connections."""
        if self.db_pool:
            await self.db_pool.close()

    async def get_existing_urls(self, user_id: str) -> set:
        """Fetch existing URLs for a user to check for duplicates."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT url FROM jobs WHERE user_id = $1",
                user_id
            )
            return {row['url'] for row in rows}

    async def _flush_write_buffer(self):
        """Write buffered jobs to PostgreSQL and forward to apply queue."""
        if not self.write_buffer:
            return

        logger.info(f"Attempting to flush buffer with {len(self.write_buffer)} jobs to PostgreSQL.")
        
        async with self.db_pool.acquire() as conn:
            try:
                # Start a transaction
                async with conn.transaction():
                    inserted_jobs = []
                    
                    # Insert all jobs and collect their IDs
                    for job_data in self.write_buffer:
                        job_id = str(uuid4())
                        
                        # Insert job
                        await conn.execute("""
                            INSERT INTO jobs (id, url, title, user_id, status, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, 'pending', NOW(), NOW())
                        """, job_id, job_data['url'], job_data.get('subject', ''), job_data['user_id'])
                        
                        inserted_jobs.append({
                            'job_id': job_id,
                            'message_data': job_data,
                            'original_message': self.buffered_messages_for_delete[len(inserted_jobs)]
                        })
                        
                        # Log activity
                        await conn.execute("""
                            INSERT INTO activity_events (user_id, type, title, metadata, created_at)
                            VALUES ($1, 'job_added', $2, $3, NOW())
                        """, job_data['user_id'], f"Job added: {job_data.get('subject', job_data['url'])}", 
                            json.dumps({'url': job_data['url'], 'source': 'email'}))
                    
                    logger.info(f"Successfully inserted {len(inserted_jobs)} jobs to PostgreSQL.")
                
                # Forward messages to apply queue if needed
                messages_to_forward = []
                for job_info in inserted_jobs:
                    # Check if job should be auto-applied (you can add logic here)
                    if self._should_auto_apply(job_info['message_data']):
                        messages_to_forward.append({
                            'Id': job_info['original_message']['MessageId'],
                            'MessageBody': json.dumps({
                                'job_id': job_info['job_id'],
                                'url': job_info['message_data']['url'],
                                'user_id': job_info['message_data']['user_id']
                            })
                        })
                
                if messages_to_forward:
                    logger.info(f"Forwarding {len(messages_to_forward)} messages to apply queue...")
                    for i in range(0, len(messages_to_forward), 10):
                        batch = messages_to_forward[i:i+10]
                        self.sqs_client.send_message_batch(
                            QueueUrl=config.SQS_APPLY_QUEUE_URL,
                            Entries=batch
                        )
                    logger.info("Successfully forwarded messages to apply queue.")
                
            except Exception as e:
                logger.error(f"Failed to write jobs to PostgreSQL: {e}", exc_info=True)
                raise
        
        # Delete processed messages from source queue
        try:
            all_entries_to_delete = [
                {'Id': msg['MessageId'], 'ReceiptHandle': msg['ReceiptHandle']}
                for msg in self.buffered_messages_for_delete
            ]
            if all_entries_to_delete:
                logger.info(f"Deleting {len(all_entries_to_delete)} messages from source queue...")
                for i in range(0, len(all_entries_to_delete), 10):
                    batch = all_entries_to_delete[i:i + 10]
                    response = self.sqs_client.delete_message_batch(
                        QueueUrl=config.SQS_QUEUE_URL,
                        Entries=batch
                    )
                    if response.get('Failed'):
                        logger.error(f"Failed to delete some messages from SQS: {response['Failed']}")
                logger.info("Finished deleting messages from source queue.")
        except Exception as e:
            logger.error(f"Error deleting messages from source queue: {e}", exc_info=True)

        # Clear buffers
        self.write_buffer.clear()
        self.buffered_messages_for_delete.clear()
        self.last_write_time = time.time()
        logger.info("Cleared local buffers.")

    def _should_auto_apply(self, job_data: dict) -> bool:
        """Determine if a job should be auto-applied."""
        # Add your logic here - for now, return True for all jobs
        # You might want to check keywords, companies, etc.
        return True

    async def start_consuming(self):
        """Start consuming messages from SQS queue."""
        logger.info("Starting SQL-based SQS consumer...")
        
        # Initialize database connection
        await self.initialize_db()
        
        try:
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
                        
                        # Process messages
                        for message in messages:
                            try:
                                body = json.loads(message['Body'])
                                url = body.get('url')
                                user_id = body.get('user_id')
                                
                                if not url or not user_id:
                                    logger.error(f"Invalid message format: {message['Body']}")
                                    # Delete invalid message
                                    self.sqs_client.delete_message(
                                        QueueUrl=config.SQS_QUEUE_URL,
                                        ReceiptHandle=message['ReceiptHandle']
                                    )
                                    continue
                                
                                # Check for duplicates
                                existing_urls = await self.get_existing_urls(user_id)
                                if url in existing_urls:
                                    logger.info(f"Duplicate URL {url} for user {user_id}, skipping")
                                    self.sqs_client.delete_message(
                                        QueueUrl=config.SQS_QUEUE_URL,
                                        ReceiptHandle=message['ReceiptHandle']
                                    )
                                else:
                                    # Add to buffer
                                    self.write_buffer.append(body)
                                    self.buffered_messages_for_delete.append(message)
                                    
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.error(f"Malformed message body: {message.get('Body')}, error: {e}")
                                # Delete malformed message
                                self.sqs_client.delete_message(
                                    QueueUrl=config.SQS_QUEUE_URL,
                                    ReceiptHandle=message['ReceiptHandle']
                                )
                    
                    # Check if it's time to flush the buffer
                    time_since_last_write = time.time() - self.last_write_time
                    if (len(self.write_buffer) >= self.BUFFER_MAX_SIZE) or \
                       (self.write_buffer and time_since_last_write >= self.WRITE_INTERVAL_SECONDS):
                        await self._flush_write_buffer()

                except KeyboardInterrupt:
                    logger.info("Consumer stopping. Flushing final buffer...")
                    await self._flush_write_buffer()
                    logger.info("Consumer stopped by user.")
                    break
                except Exception as e:
                    logger.error(f"Error in consumer loop: {e}", exc_info=True)
                    await asyncio.sleep(10)
                    
        finally:
            await self.close()


def run_consumer():
    """Entry point to run the consumer."""
    consumer = SQLSQSConsumer()
    asyncio.run(consumer.start_consuming())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    run_consumer()

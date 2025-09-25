import boto3
import json
import logging
from botocore.exceptions import ClientError
from playwright.sync_api import sync_playwright, Playwright
import os
import time
import asyncpg
import asyncio
from datetime import datetime

import config
from services.application import ApplicationService
from services.postgres_service import PostgresService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SQLApplyWorker:
    def __init__(self, playwright: Playwright):
        self.sqs_client = boto3.client("sqs", region_name=config.AWS_REGION)
        self.postgres_service = PostgresService()
        self.application_service = ApplicationService(playwright)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    async def process_message_async(self, message: dict):
        """Async message processing logic."""
        body_str = message['Body']
        body = json.loads(body_str)
        job_id = body.get('job_id')
        url = body.get('url')
        user_id = body.get('user_id')

        if not all([job_id, url, user_id]):
            logger.warning(f"Received message without required fields: {body_str}")
            # Delete malformed message
            self.sqs_client.delete_message(
                QueueUrl=config.SQS_APPLY_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            return

        try:
            # Update job status to 'processing'
            await self.postgres_service.update_job_status(job_id, 'processing')
            
            # Log activity
            await self.postgres_service.log_activity(
                user_id=user_id,
                activity_type='auto_apply_started',
                title=f"Started auto-apply for job",
                metadata={'job_id': job_id, 'url': url}
            )

            # Attempt to apply
            success, job_details = self.application_service.apply_to_job(url)

            if success:
                # Update job with details and status
                await self.postgres_service.update_job_applied(
                    job_id=job_id,
                    job_title=job_details.get("job_title"),
                    company=job_details.get("company"),
                    location=job_details.get("location"),
                    technologies=job_details.get("technologies"),
                    seniority=job_details.get("seniority")
                )
                
                # Log success activity
                await self.postgres_service.log_activity(
                    user_id=user_id,
                    activity_type='job_applied',
                    title=f"Successfully applied to {job_details.get('job_title', 'job')}",
                    metadata={'job_id': job_id, 'job_details': job_details}
                )
                
                logger.info(f"Successfully applied to job {job_id}")
            else:
                # Update status to failed
                await self.postgres_service.update_job_status(job_id, 'failed')
                
                # Log failure activity
                await self.postgres_service.log_activity(
                    user_id=user_id,
                    activity_type='application_failed',
                    title=f"Failed to apply to job",
                    metadata={'job_id': job_id, 'url': url, 'error': 'Application process failed'}
                )
                
                logger.error(f"Failed to apply to job {job_id}")

        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
            # Update status to failed
            await self.postgres_service.update_job_status(job_id, 'failed')
            
            # Log error activity
            await self.postgres_service.log_activity(
                user_id=user_id,
                activity_type='application_failed',
                title=f"Error applying to job",
                metadata={'job_id': job_id, 'error': str(e)}
            )
        
        finally:
            # Delete the message from queue
            self.sqs_client.delete_message(
                QueueUrl=config.SQS_APPLY_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            logger.info(f"Deleted message from apply queue: {message['MessageId']}")

    def process_message(self, message: dict):
        """Synchronous wrapper for async message processing."""
        self.loop.run_until_complete(self.process_message_async(message))

    def start(self):
        logger.info("Starting SQL-based Apply Worker...")
        
        # Initialize PostgreSQL connection
        self.loop.run_until_complete(self.postgres_service.initialize())
        
        try:
            while True:
                try:
                    response = self.sqs_client.receive_message(
                        QueueUrl=config.SQS_APPLY_QUEUE_URL,
                        MaxNumberOfMessages=1,  # Process one at a time due to browser automation
                        WaitTimeSeconds=20,
                        VisibilityTimeout=120  # Give enough time for playwright
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
                    logger.error(f"Error in worker loop: {e}", exc_info=True)
                    time.sleep(10)
        finally:
            self.application_service.close()
            self.loop.run_until_complete(self.postgres_service.close())
            self.loop.close()


def main():
    with sync_playwright() as playwright:
        worker = SQLApplyWorker(playwright)
        worker.start()


if __name__ == "__main__":
    main()

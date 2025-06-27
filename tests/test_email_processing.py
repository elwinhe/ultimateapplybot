#!/usr/bin/env python3
"""
Test script for email processing functionality.
This script properly initializes all dependencies and runs the email processing task.
"""
import asyncio
import logging

from app.services.postgres_client import postgres_client
from app.tasks.email_tasks import pull_and_process_emails_logic

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Main function to test email processing."""
    try:
        # Initialize PostgreSQL client
        logger.info("Initializing PostgreSQL client...")
        await postgres_client.initialize()
        await postgres_client.create_tables()
        logger.info("PostgreSQL client initialized successfully")
        
        # Run email processing
        logger.info("Starting email processing...")
        await pull_and_process_emails_logic()
        logger.info("Email processing completed")
        
    except Exception as e:
        logger.error("Error during email processing: %s", e, exc_info=True)
    finally:
        # Clean up
        await postgres_client.close()

if __name__ == "__main__":
    asyncio.run(main()) 
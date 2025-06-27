#!/usr/bin/env python3
"""
Standalone script to run email processing with proper initialization.
"""
import asyncio
import logging
from app.services.postgres_client import postgres_client
from app.tasks.email_tasks import pull_and_process_emails_logic

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Initialize services and run email processing."""
    try:
        logger.info("Initializing PostgreSQL connection pool...")
        await postgres_client.initialize()
        
        logger.info("Running email processing...")
        await pull_and_process_emails_logic()
        
        logger.info("Email processing completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during email processing: {e}", exc_info=True)
        raise
    finally:
        # Clean up connections
        if hasattr(postgres_client, '_pool') and postgres_client._pool:
            await postgres_client._pool.close()
        logger.info("Cleanup completed.")

if __name__ == "__main__":
    asyncio.run(main()) 
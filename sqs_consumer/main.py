import logging
from consumer import SQSConsumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

def main():
    """
    Main function to initialize and start the SQS consumer.
    """
    logger.info("Initializing SQS consumer service.")
    try:
        consumer = SQSConsumer()
        consumer.start_consuming()
    except Exception as e:
        logger.critical(f"Failed to start SQS consumer: {e}", exc_info=True)

if __name__ == "__main__":
    main() 
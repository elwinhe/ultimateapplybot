from dotenv import load_dotenv
import os

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")

# Google Sheets settings
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
GOOGLE_SERVICE_ACCOUNT_CREDS = os.getenv("GOOGLE_SERVICE_ACCOUNT_CREDS") 
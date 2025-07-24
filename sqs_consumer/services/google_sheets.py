import logging
import gspread
import json
from google.oauth2.service_account import Credentials
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
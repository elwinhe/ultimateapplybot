import logging
import gspread
import json
from google.oauth2.service_account import Credentials
import config

logger = logging.getLogger(__name__)

class GoogleSheetsService:
    def __init__(self):
        creds_json = json.loads(config.GOOGLE_SERVICE_ACCOUNT_CREDS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open(config.GOOGLE_SHEET_NAME).sheet1
        self._initialize_sheet()

    def _initialize_sheet(self):
        if not self.sheet.get_all_values():
            self.sheet.append_row([
                "URL", "Source Message ID", "To Address", "Timestamp", 
                "Status", "Job Title", "Seniority", "Technologies"
            ])
            logger.info("Wrote header row to empty sheet.")

    def update_status(self, row: int, status: str):
        """Updates the status in a specific row."""
        try:
            self.sheet.update_cell(row, 5, status) # Column E for status
            logger.info(f"Updated status to '{status}' for row {row}")
        except Exception as e:
            logger.error(f"Failed to update status for row {row}: {e}")
    
    def update_job_details(self, row: int, job_title: str, seniority: str, technologies: str):
        """Updates the job details in a specific row."""
        try:
            # Columns F, G, H
            self.sheet.update_range(f'F{row}:H{row}', [[job_title, seniority, technologies]])
            logger.info(f"Updated job details for row {row}")
        except Exception as e:
            logger.error(f"Failed to update job details for row {row}: {e}") 
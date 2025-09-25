"""
app/api/v1/sheets_jobs.py

API endpoints for job management using Google Sheets as the data store.
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl
import gspread
from google.oauth2.service_account import Credentials
import json

from app.api.v1.email import get_current_user_id
from app.services.sqs_client import sqs_client
from app.config import settings
from app.celery_app import celery

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sheets-jobs",
    tags=["Sheets Jobs"],
)

# Pydantic Models
class SheetJob(BaseModel):
    """Job model that matches Google Sheets structure"""
    row_number: int
    url: str
    subject: Optional[str] = None
    user_id: str
    received_date_time: Optional[str] = None
    status: str = "PENDING"
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    technologies: Optional[str] = None

class JobIngestRequest(BaseModel):
    url: HttpUrl
    subject: Optional[str] = None

class JobIngestResponse(BaseModel):
    message: str
    status: str = "queued"

class GoogleSheetsClient:
    """Client for interacting with Google Sheets"""
    def __init__(self):
        try:
            # Parse service account credentials from environment
            creds_json = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_CREDS)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open(settings.GOOGLE_SHEET_NAME).sheet1
            logger.info(f"Connected to Google Sheet: {settings.GOOGLE_SHEET_NAME}")
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            raise

    def get_user_jobs(self, user_id: str, status: Optional[str] = None) -> List[SheetJob]:
        """Get all jobs for a specific user from the sheet"""
        try:
            # Get all rows
            all_rows = self.sheet.get_all_values()
            
            if not all_rows:
                return []
            
            # Skip header row
            header = all_rows[0]
            jobs = []
            
            for idx, row in enumerate(all_rows[1:], start=2):  # Start at row 2 (after header)
                # Map row data to expected columns
                if len(row) >= 5:  # Ensure we have minimum columns
                    row_data = {
                        'url': row[0] if len(row) > 0 else '',
                        'subject': row[1] if len(row) > 1 else '',
                        'user_id': row[2] if len(row) > 2 else '',
                        'received_date_time': row[3] if len(row) > 3 else '',
                        'status': row[4] if len(row) > 4 else 'PENDING',
                        'job_title': row[5] if len(row) > 5 else None,
                        'seniority': row[6] if len(row) > 6 else None,
                        'technologies': row[7] if len(row) > 7 else None,
                    }
                    
                    # Filter by user_id
                    if row_data['user_id'] == user_id:
                        # Apply status filter if provided
                        if status is None or row_data['status'].upper() == status.upper():
                            jobs.append(SheetJob(
                                row_number=idx,
                                **row_data
                            ))
            
            return jobs
            
        except Exception as e:
            logger.error(f"Failed to get jobs from sheet: {e}")
            raise

    def check_duplicate_url(self, url: str, user_id: str) -> bool:
        """Check if URL already exists for this user"""
        jobs = self.get_user_jobs(user_id)
        return any(job.url == url for job in jobs)

# Dependency to get sheets client
def get_sheets_client() -> GoogleSheetsClient:
    return GoogleSheetsClient()

# API Endpoints
@router.get("", response_model=List[SheetJob])
async def get_jobs_from_sheet(
    current_user_id: str = Depends(get_current_user_id),
    status: Optional[str] = Query(None, description="Filter by status (PENDING, APPLIED, FAILED)"),
    sheets_client: GoogleSheetsClient = Depends(get_sheets_client),
) -> List[SheetJob]:
    """
    Get jobs from Google Sheets for the current user.
    """
    try:
        jobs = sheets_client.get_user_jobs(current_user_id, status)
        return jobs
    except Exception as e:
        logger.error(f"Failed to fetch jobs from sheet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch jobs from Google Sheets")

@router.post("/ingest-url", response_model=JobIngestResponse)
async def ingest_job_url_to_sheet(
    request: JobIngestRequest,
    current_user_id: str = Depends(get_current_user_id),
    sheets_client: GoogleSheetsClient = Depends(get_sheets_client),
) -> JobIngestResponse:
    """
    Add a new job URL to the processing queue (which writes to Google Sheets).
    """
    try:
        # Check for duplicates
        if sheets_client.check_duplicate_url(str(request.url), current_user_id):
            return JobIngestResponse(
                message="Job URL already exists in your sheet",
                status="duplicate"
            )
        
        # Send to SQS for processing (consumer will write to sheet)
        await sqs_client.send_message({
            "url": str(request.url),
            "subject": request.subject or f"Manual submission: {request.url}",
            "user_id": current_user_id,
            "received_date_time": datetime.utcnow().isoformat(),
            "source": "manual_ingest"
        })
        
        return JobIngestResponse(
            message="Job URL queued for processing",
            status="queued"
        )
        
    except Exception as e:
        logger.error(f"Failed to ingest job URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to queue job URL")

@router.post("/{row_number}/apply")
async def trigger_job_application(
    row_number: int,
    current_user_id: str = Depends(get_current_user_id),
    sheets_client: GoogleSheetsClient = Depends(get_sheets_client),
) -> Dict[str, Any]:
    """
    Trigger auto-apply for a job at a specific row in the sheet.
    """
    try:
        # Verify the job belongs to the user
        jobs = sheets_client.get_user_jobs(current_user_id)
        job = next((j for j in jobs if j.row_number == row_number), None)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status == "APPLIED":
            raise HTTPException(status_code=400, detail="Job already applied")
        
        # Send to apply queue
        await sqs_client.send_message({
            "url": job.url,
            "sheet_row": row_number,
            "user_id": current_user_id
        }, queue_url=settings.SQS_APPLY_QUEUE_URL)
        
        return {
            "message": "Application queued",
            "row_number": row_number,
            "status": "queued"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger application: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to queue application")

@router.get("/stats")
async def get_job_stats(
    current_user_id: str = Depends(get_current_user_id),
    sheets_client: GoogleSheetsClient = Depends(get_sheets_client),
) -> Dict[str, Any]:
    """
    Get statistics about jobs in the sheet.
    """
    try:
        jobs = sheets_client.get_user_jobs(current_user_id)
        
        stats = {
            "total": len(jobs),
            "pending": sum(1 for j in jobs if j.status == "PENDING"),
            "applied": sum(1 for j in jobs if j.status == "APPLIED"),
            "failed": sum(1 for j in jobs if j.status == "FAILED"),
            "by_seniority": {},
            "last_updated": datetime.utcnow().isoformat()
        }
        
        # Count by seniority
        for job in jobs:
            if job.seniority:
                stats["by_seniority"][job.seniority] = stats["by_seniority"].get(job.seniority, 0) + 1
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get job stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to calculate statistics")

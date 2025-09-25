"""
app/api/v1/jobs.py

API endpoints for job management functionality.
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl

from app.api.v1.email import get_current_user_id
from app.services.postgres_client import postgres_client
from app.services.sqs_client import sqs_client
from app.celery_app import celery

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)

# Pydantic Models
class Job(BaseModel):
    id: str
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    status: str = Field(default="pending", description="pending, applied, failed, rejected")
    created_at: datetime
    updated_at: datetime
    applied_at: Optional[datetime] = None
    sheet_row: Optional[int] = None
    technologies: Optional[str] = None
    seniority: Optional[str] = None
    user_id: str

class JobIngestRequest(BaseModel):
    url: HttpUrl
    title: Optional[str] = None
    company: Optional[str] = None

class JobIngestResponse(BaseModel):
    id: str
    message: str
    status: str = "queued"

class AutoApplyRequest(BaseModel):
    resume_version_id: Optional[str] = None

class AutoApplyResponse(BaseModel):
    task_id: str
    message: str
    status: str = "processing"

# API Endpoints
@router.get("", response_model=List[Job])
async def get_jobs(
    current_user_id: str = Depends(get_current_user_id),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search in title, company, or URL"),
) -> List[Job]:
    """
    Get jobs list with optional filtering and pagination.
    """
    try:
        # Build dynamic query
        query = """
            SELECT id, url, title, company, location, status, 
                   created_at, updated_at, applied_at, sheet_row,
                   technologies, seniority, user_id
            FROM jobs
            WHERE user_id = $1
        """
        params = [current_user_id]
        param_count = 2
        
        if status:
            query += f" AND status = ${param_count}"
            params.append(status)
            param_count += 1
            
        if search:
            query += f" AND (title ILIKE ${param_count} OR company ILIKE ${param_count} OR url ILIKE ${param_count})"
            params.append(f"%{search}%")
            param_count += 1
            
        query += f" ORDER BY created_at DESC LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([limit, offset])
        
        rows = await postgres_client.fetch_all(query, *params)
        
        return [Job(**row) for row in rows]
        
    except Exception as e:
        logger.error(f"Failed to fetch jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch jobs")

@router.post("/ingest-url", response_model=JobIngestResponse)
async def ingest_job_url(
    request: JobIngestRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> JobIngestResponse:
    """
    Add a new job from URL to the processing queue.
    """
    try:
        job_id = str(uuid4())
        
        # First, check if this URL already exists for this user
        existing = await postgres_client.fetch_one(
            "SELECT id FROM jobs WHERE user_id = $1 AND url = $2",
            current_user_id, str(request.url)
        )
        
        if existing:
            return JobIngestResponse(
                id=existing["id"],
                message="Job URL already exists in your list",
                status="duplicate"
            )
        
        # Insert new job record
        await postgres_client.execute(
            """
            INSERT INTO jobs (id, url, title, company, status, user_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'pending', $5, NOW(), NOW())
            """,
            job_id, str(request.url), request.title, request.company, current_user_id
        )
        
        # Send to SQS for processing
        await sqs_client.send_message({
            "url": str(request.url),
            "job_id": job_id,
            "user_id": current_user_id,
            "source": "manual_ingest"
        })
        
        return JobIngestResponse(
            id=job_id,
            message="Job URL added to processing queue",
            status="queued"
        )
        
    except Exception as e:
        logger.error(f"Failed to ingest job URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to ingest job URL")

@router.post("/{job_id}/auto-apply", response_model=AutoApplyResponse)
async def trigger_auto_apply(
    job_id: str,
    request: AutoApplyRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> AutoApplyResponse:
    """
    Trigger auto-apply for a specific job.
    """
    try:
        # Verify job exists and belongs to user
        job = await postgres_client.fetch_one(
            "SELECT * FROM jobs WHERE id = $1 AND user_id = $2",
            job_id, current_user_id
        )
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
            
        if job["status"] == "applied":
            raise HTTPException(status_code=400, detail="Job already applied")
            
        # Send auto-apply task to Celery
        task = celery.send_task(
            'app.tasks.apply_tasks.auto_apply_job',
            args=[job_id, current_user_id, request.resume_version_id]
        )
        
        # Update job status
        await postgres_client.execute(
            "UPDATE jobs SET status = 'processing', updated_at = NOW() WHERE id = $1",
            job_id
        )
        
        return AutoApplyResponse(
            task_id=task.id,
            message="Auto-apply task started",
            status="processing"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger auto-apply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to trigger auto-apply")

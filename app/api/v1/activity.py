"""
app/api/v1/activity.py

API endpoints for activity/event tracking.
"""
import logging
from datetime import datetime
from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.email import get_current_user_id
from app.services.postgres_client import postgres_client

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/activity",
    tags=["Activity"],
)

# Enums and Models
class ActivityType(str, Enum):
    JOB_ADDED = "job_added"
    JOB_APPLIED = "job_applied"
    APPLICATION_FAILED = "application_failed"
    EMAIL_PROCESSED = "email_processed"
    RESUME_UPDATED = "resume_updated"
    INTEGRATION_CONNECTED = "integration_connected"
    INTEGRATION_DISCONNECTED = "integration_disconnected"

class ActivityEvent(BaseModel):
    id: str
    type: ActivityType
    title: str
    description: Optional[str] = None
    metadata: Optional[dict] = Field(default_factory=dict)
    created_at: datetime
    user_id: str

# API Endpoints
@router.get("", response_model=List[ActivityEvent])
async def get_activity_log(
    current_user_id: str = Depends(get_current_user_id),
    type: Optional[ActivityType] = Query(None, description="Filter by activity type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    start_date: Optional[datetime] = Query(None, description="Filter activities after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter activities before this date"),
) -> List[ActivityEvent]:
    """
    Get activity log with optional filters.
    """
    try:
        # Build query
        query = """
            SELECT id, type, title, description, metadata, created_at, user_id
            FROM activity_events
            WHERE user_id = $1
        """
        params = [current_user_id]
        param_count = 2
        
        if type:
            query += f" AND type = ${param_count}"
            params.append(type.value)
            param_count += 1
            
        if start_date:
            query += f" AND created_at >= ${param_count}"
            params.append(start_date)
            param_count += 1
            
        if end_date:
            query += f" AND created_at <= ${param_count}"
            params.append(end_date)
            param_count += 1
            
        query += f" ORDER BY created_at DESC LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([limit, offset])
        
        rows = await postgres_client.fetch_all(query, *params)
        
        return [ActivityEvent(**row) for row in rows]
        
    except Exception as e:
        logger.error(f"Failed to fetch activity log: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch activity log")

# Helper function to log activities (used by other modules)
async def log_activity(
    user_id: str,
    activity_type: ActivityType,
    title: str,
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Helper function to log an activity event.
    """
    try:
        await postgres_client.execute(
            """
            INSERT INTO activity_events (type, title, description, metadata, user_id, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            activity_type.value, title, description, metadata or {}, user_id
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}", exc_info=True)
        # Don't raise - activity logging should not break main functionality

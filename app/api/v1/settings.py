"""
app/api/v1/settings.py

API endpoints for managing user settings and email filtering.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from celery.result import AsyncResult

from app.api.v1.email import get_current_user_id
from app.services.postgres_client import postgres_client
from app.celery_app import celery
import redis

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
)

# Initialize Redis client
redis_client = redis.Redis.from_url(app_settings.REDIS_URL, decode_responses=True)

# Pydantic Models
class EmailFilterSettings(BaseModel):
    enabled: bool = Field(default=True, description="Whether email filtering is active")
    keywords: List[str] = Field(default_factory=list, description="Keywords to filter emails")
    sender_whitelist: List[str] = Field(default_factory=list, description="Whitelisted email addresses")
    check_interval_minutes: int = Field(default=30, ge=5, le=1440, description="Email check interval")
    
class EmailFilterResponse(BaseModel):
    settings: EmailFilterSettings
    last_checked: Optional[datetime] = None
    status: str = Field(description="active, paused, stopped")

class CacheClearResponse(BaseModel):
    message: str
    cleared_items: int

# API Endpoints
@router.get("/email-filter", response_model=EmailFilterResponse)
async def get_email_filter_settings(
    current_user_id: str = Depends(get_current_user_id),
) -> EmailFilterResponse:
    """
    Get current email filter settings for the user.
    """
    try:
        # Get settings from database
        settings = await postgres_client.fetch_one(
            """
            SELECT enabled, keywords, sender_whitelist, check_interval_minutes, last_checked
            FROM email_filter_settings
            WHERE user_id = $1
            """,
            current_user_id
        )
        
        if not settings:
            # Return defaults if no settings exist
            return EmailFilterResponse(
                settings=EmailFilterSettings(),
                last_checked=None,
                status="stopped"
            )
        
        # Check if filtering task is active
        task_key = f"email_filter_task:{current_user_id}"
        task_id = redis_client.get(task_key)
        status = "stopped"
        
        if task_id:
            task_result = AsyncResult(task_id, app=celery)
            if task_result.state in ['PENDING', 'STARTED', 'RETRY']:
                status = "active"
            elif settings["enabled"]:
                status = "paused"
        
        return EmailFilterResponse(
            settings=EmailFilterSettings(**settings),
            last_checked=settings.get("last_checked"),
            status=status
        )
        
    except Exception as e:
        logger.error(f"Failed to get email filter settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get email filter settings")

@router.post("/email-filter", response_model=EmailFilterResponse)
async def update_email_filter_settings(
    settings: EmailFilterSettings,
    current_user_id: str = Depends(get_current_user_id),
) -> EmailFilterResponse:
    """
    Update email filter settings for the user.
    """
    try:
        # Upsert settings
        await postgres_client.execute(
            """
            INSERT INTO email_filter_settings (user_id, enabled, keywords, sender_whitelist, check_interval_minutes, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                keywords = EXCLUDED.keywords,
                sender_whitelist = EXCLUDED.sender_whitelist,
                check_interval_minutes = EXCLUDED.check_interval_minutes,
                updated_at = NOW()
            """,
            current_user_id, settings.enabled, settings.keywords, 
            settings.sender_whitelist, settings.check_interval_minutes
        )
        
        # If settings are being disabled, cancel any active task
        if not settings.enabled:
            task_key = f"email_filter_task:{current_user_id}"
            task_id = redis_client.get(task_key)
            if task_id:
                celery.control.revoke(task_id, terminate=True)
                redis_client.delete(task_key)
        
        return await get_email_filter_settings(current_user_id)
        
    except Exception as e:
        logger.error(f"Failed to update email filter settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update email filter settings")

@router.post("/email-filter/start")
async def start_email_filtering(
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """
    Start email filtering for the current user.
    """
    try:
        # Check if filtering is enabled
        settings = await postgres_client.fetch_one(
            "SELECT enabled FROM email_filter_settings WHERE user_id = $1",
            current_user_id
        )
        
        if not settings or not settings["enabled"]:
            raise HTTPException(
                status_code=400, 
                detail="Email filtering is not enabled. Please enable it in settings first."
            )
        
        # Check if task is already running
        task_key = f"email_filter_task:{current_user_id}"
        existing_task_id = redis_client.get(task_key)
        
        if existing_task_id:
            task_result = AsyncResult(existing_task_id, app=celery)
            if task_result.state in ['PENDING', 'STARTED', 'RETRY']:
                return {"message": "Email filtering is already active", "task_id": existing_task_id}
        
        # Start new filtering task
        task = celery.send_task(
            'app.tasks.email_tasks.process_single_mailbox',
            args=[current_user_id]
        )
        
        # Store task ID in Redis
        redis_client.setex(task_key, 86400, task.id)  # Expire after 24 hours
        
        return {"message": "Email filtering started", "task_id": task.id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start email filtering: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start email filtering")

@router.post("/email-filter/stop")
async def stop_email_filtering(
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """
    Stop email filtering for the current user.
    """
    try:
        task_key = f"email_filter_task:{current_user_id}"
        task_id = redis_client.get(task_key)
        
        if not task_id:
            return {"message": "No active email filtering task found"}
        
        # Revoke the task
        celery.control.revoke(task_id, terminate=True)
        redis_client.delete(task_key)
        
        return {"message": "Email filtering stopped", "task_id": task_id}
        
    except Exception as e:
        logger.error(f"Failed to stop email filtering: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to stop email filtering")

@router.post("/clear-cache", response_model=CacheClearResponse)
async def clear_cache(
    current_user_id: str = Depends(get_current_user_id),
) -> CacheClearResponse:
    """
    Clear application cache for the current user.
    """
    try:
        # Clear Redis cache entries for this user
        pattern = f"*:{current_user_id}:*"
        keys = redis_client.keys(pattern)
        
        cleared_count = 0
        if keys:
            cleared_count = redis_client.delete(*keys)
        
        # Also clear the email processor timestamp
        timestamp_key = f"email_processor:last_seen_timestamp:{current_user_id}"
        if redis_client.exists(timestamp_key):
            redis_client.delete(timestamp_key)
            cleared_count += 1
        
        return CacheClearResponse(
            message=f"Cache cleared successfully",
            cleared_items=cleared_count
        )
        
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear cache")

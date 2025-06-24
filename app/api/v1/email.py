#app/api/v1/email.py

from fastapi import APIRouter
from app.services.graph_client import fetch_emails

router = APIRouter()

@router.post("/emails")
async def get_emails():
    return fetch_emails()
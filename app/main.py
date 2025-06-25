# app/main.py
# • Builds app instance  
# • Mounts `/addin` static files  
# • Registers health-check & `api/v1` routers

from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.tasks.email_tasks import pull_new_emails

_LOGGER = logging.getLogger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(title="EmailReader API")

    # health-check
    @app.get("/healthcheck", include_in_schema=False)
    async def _healthcheck() -> JSONResponse:  # noqa: WPS430
        return JSONResponse({"status": "ok"})

    # test celery task
    @app.post("/test-celery")
    async def test_celery() -> JSONResponse:
        result = pull_new_emails.delay()
        return JSONResponse({
            "task_id": result.id,
            "status": "queued",
            "message": "Email pull task queued"
        })


    return app


app = create_app()

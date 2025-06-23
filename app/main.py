from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.workers.celery_worker import fetch_demo

_LOGGER = logging.getLogger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(title="EmailReader API")

    # health-check
    @app.get("/healthcheck", include_in_schema=False)
    async def _healthcheck() -> JSONResponse:  # noqa: WPS430
        return JSONResponse({"status": "ok"})

    # test celery task
    @app.post("/test-celery")
    async def test_celery(email_id: str = "test-123") -> JSONResponse:
        result = fetch_demo.delay(email_id)
        return JSONResponse({
            "task_id": result.id,
            "status": "queued",
            "message": f"Task queued for email: {email_id}"
        })

    # serve add-in assets
    app.mount(
        "/addin",
        StaticFiles(directory="static/addin", html=True),
        name="addin",
    )

    return app


app = create_app()

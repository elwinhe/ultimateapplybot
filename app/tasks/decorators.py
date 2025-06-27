"""
app/tasks/decorators.py

Provides reusable decorators for Celery tasks to manage resources
and other cross-cutting concerns.
"""
from __future__ import annotations

import functools
import logging
from typing import Awaitable, Callable, ParamSpec, TypeVar

from app.services.postgres_client import postgres_client

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def manage_postgres_connection(
    func: Callable[P, Awaitable[R]]
) -> Callable[P, Awaitable[R]]:
    """
    A decorator that manages the lifecycle of the postgres_client.

    It ensures that the client is initialized before the decorated async
    function is called and closed gracefully afterwards. This isolates the
    side-effect of connection management from the core task logic.
    """
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            await postgres_client.initialize()
            logger.debug("Postgres client initialized for task: %s", func.__name__)
            return await func(*args, **kwargs)
        except Exception:
            logger.exception("An error occurred in task: %s", func.__name__)
            raise  # Re-raise the exception after logging
        finally:
            if postgres_client._pool:
                await postgres_client.close()
                logger.debug("Postgres client closed for task: %s", func.__name__)

    return wrapper 
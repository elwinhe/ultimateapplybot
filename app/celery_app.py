"""
app/celery_app.py

Central configuration for the Celery application.

This module initializes the Celery instance, discovers tasks, and sets up the
Celery Beat schedule for the multi-user email processing dispatcher. It includes
production-grade settings for routing, reliability, and security.
"""
from __future__ import annotations

import logging

from celery import Celery
from kombu import Queue

from app.config import settings

logger = logging.getLogger(__name__)


celery = Celery("emailreader")

celery.conf.update(
    # Broker and Backend Configuration 
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    timezone='UTC',

    accept_content=['json'],
    task_serializer='json',
    result_serializer='json',
    # A secret key for signing messages (should be set in production).
    security_key=settings.CELERY_SECURITY_KEY if hasattr(settings, 'CELERY_SECURITY_KEY') else None,

    # Define separate queues for different types of work.
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("email_processing", routing_key="email_processing"),
    ),
    task_default_queue="default",
    # Route specific tasks to the email_processing queue.
    task_routes={
        'app.tasks.email_tasks.dispatch_email_processing': {'queue': 'email_processing'},
        'app.tasks.email_tasks.process_single_mailbox': {'queue': 'email_processing'},
    },

    # Worker Reliability and Performance Tuning 
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100, # Prevents memory leaks in long-running workers.
    worker_max_memory_per_child=200000,  # 200MB memory limit per worker process.
    task_soft_time_limit=300,  # 5 minutes soft timeout.
    task_time_limit=600,       # 10 minutes hard timeout.
    task_reject_on_worker_lost=True, # Requeue task if worker is killed.

    # Monitoring and Events 
    # Send events to allow monitoring with tools like Flower.
    worker_send_task_events=True,
    task_send_sent_event=True,

    # Celery Beat Configuration 
    beat_schedule_filename='/tmp/celerybeat-schedule',
    beat_scheduler='celery.beat.PersistentScheduler',

    # Periodic Task Schedule (Celery Beat) 
    beat_schedule={
        'dispatch-email-processing-every-15-minutes': {
            'task': 'dispatch-email-processing',
            'schedule': 30.0, # 900 seconds = 15 minutes
            'options': {'queue': 'email_processing'},
        },
    },
)

# This finds any function decorated with @celery.task in the specified modules.
celery.autodiscover_tasks(["app.tasks"])

# Log configuration on startup for observability.
logger.info("Celery application configured with Redis broker: %s", settings.REDIS_URL)
logger.info("Task queues configured: %s", [q.name for q in celery.conf.task_queues])
logger.info("Beat schedule configured with %d tasks", len(celery.conf.beat_schedule))

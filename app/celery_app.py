"""
app/celery_app.py

Central configuration for the Celery application.

This module initializes the Celery instance, Celery Beat schedule for
periodic jobs.
"""
from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.config import settings

celery = Celery("emailreader")

celery.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    timezone='UTC',

    # Task Routing and Queues
    task_queues=(Queue("default"),),
    task_default_queue="default",

    # Worker Reliability and Performance Tuning
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={'visibility_timeout': 3600}, # 1 hour

    # Periodic Task Schedule (Celery Beat
    beat_schedule={
        'pull-new-emails-every-15-minutes': {
            'task': 'app.tasks.email_tasks.pull_new_emails',
            'schedule': 900.0, # 900 seconds = 15 minutes
        },
    },
)

# This finds any function decorated with @celery.task.
celery.autodiscover_tasks(["app.tasks"])
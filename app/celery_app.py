"""
app/celery_app.py

Central configuration for the Celery application.

This module initializes the Celery instance, Celery Beat schedule for
periodic jobs.
"""
from __future__ import annotations
import os

from celery import Celery
from kombu import Queue

from app.config import settings

celery = Celery("emailreader")

celery.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    timezone='UTC',
    enable_utc=True,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],

    # Task Routing and Queues
    task_queues=(Queue("default"),),
    task_default_queue="default",

    # Worker Reliability and Performance Tuning
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=1_000_000,   # ~1 GB
    # worker_concurrency left unset → defaults to CPU-count

    # Celery Beat Configuration - Use writable directory
    beat_schedule_filename='/tmp/celerybeat-schedule',
    beat_scheduler='celery.beat.PersistentScheduler',

    # Periodic Task Schedule (Celery Beat
    beat_schedule={
        'pull-new-emails-every-15-minutes': {
            'task': 'app.tasks.email_tasks.pull_and_process_emails',
            'schedule': 900.0, # 900 seconds = 15 minutes
        },
    },
)

# This finds any function decorated with @celery.task.
celery.autodiscover_tasks(["app.tasks"])
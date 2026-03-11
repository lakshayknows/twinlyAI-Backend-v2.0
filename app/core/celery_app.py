from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "twinlyai_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Optional: define beat schedule here for fallback syncs
celery_app.conf.beat_schedule = {
    # 'sync-github-repos-every-hour': {
    #     'task': 'app.worker.tasks.sync_all_repos',
    #     'schedule': 3600.0,
    # },
}

import os

from celery import Celery

from app import db

MQ_DIR = "/data/mq"

try:
    os.makedirs(MQ_DIR, exist_ok=True)
except OSError:
    pass

celery_app = Celery("uroki")
celery_app.conf.update(
    broker_url="filesystem://",
    broker_transport_options={
        "data_folder_in": MQ_DIR,
        "data_folder_out": MQ_DIR,
        "control_folder": os.path.join(MQ_DIR, "control"),
        "store_processed": False,
    },
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    timezone="UTC",
    enable_utc=True,
    beat_scheduler="app.scheduler:JournalScheduler",
)


@celery_app.task
def flip_lesson(lesson_id: int) -> None:
    db.mark_done(lesson_id)

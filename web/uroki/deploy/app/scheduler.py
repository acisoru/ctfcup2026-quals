from datetime import datetime, timezone

from celery.beat import PersistentScheduler
from celery.schedules import crontab

from . import db


def lesson_entry(lesson: dict) -> dict:
    dt = datetime.fromtimestamp(lesson["scheduled_at"], tz=timezone.utc)
    return {
        "task": "app.tasks.flip_lesson",
        "schedule": crontab(
            minute=dt.minute,
            hour=dt.hour,
            day_of_month=dt.day,
            month_of_year=dt.month,
        ),
        "args": (lesson["id"],),
    }


class JournalScheduler(PersistentScheduler):
    def setup_schedule(self):
        super().setup_schedule()
        self._load_lessons_from_sqlite()

    def _load_lessons_from_sqlite(self):
        planned = {f"lesson-{r['id']}": lesson_entry(r) for r in db.list_planned()}
        self.update_from_dict(planned)

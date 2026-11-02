import subprocess

SUPERVISOR_CONF = "/etc/supervisord.conf"
APPLY_CMD = ["supervisorctl", "-c", SUPERVISOR_CONF, "restart", "celery"]


def apply_schedule_changes() -> None:
    subprocess.run(APPLY_CMD, check=False)

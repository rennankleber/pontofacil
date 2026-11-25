from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app


def local_now():
    timezone = ZoneInfo(current_app.config["TIMEZONE"])
    return datetime.now(timezone).replace(tzinfo=None)


def local_today():
    return local_now().date()

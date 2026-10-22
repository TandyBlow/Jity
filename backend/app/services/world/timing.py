"""Time advancement over WorldTime.

Pinned by trace anchors: a zero-duration point keeps the dateTime and bumps
instantOrdinal; any advancement resets the ordinal to 0. Month/year additions
clamp to the calendar month end.
"""
import calendar
from datetime import datetime, timedelta

from app.schemas.world.contracts import TimeAdvance, WorldTime

_SECONDS = {'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400}


def advance_time(at: WorldTime, advance: TimeAdvance) -> WorldTime:
    if advance.duration.amount == 0:
        return at.model_copy(update={'instantOrdinal': at.instantOrdinal + 1})
    moment = datetime.fromisoformat(at.dateTime)
    unit = advance.duration.unit
    if unit in ('month', 'year'):
        months = advance.duration.amount * (12 if unit == 'year' else 1)
        index = moment.month - 1 + months
        year, month = moment.year + index // 12, index % 12 + 1
        moment = moment.replace(
            year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))
    else:
        moment += timedelta(seconds=advance.duration.amount * _SECONDS[unit])
    return WorldTime(calendar=at.calendar, dateTime=moment.isoformat(), instantOrdinal=0)

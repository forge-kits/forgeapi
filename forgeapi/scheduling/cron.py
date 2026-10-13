from __future__ import annotations

from datetime import datetime, timedelta

_MONTHS = {n: i for i, n in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_DAYS = {n: i for i, n in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))}

# (min, max, names)
_FIELDS = (
    (0, 59, {}),
    (0, 23, {}),
    (1, 31, {}),
    (1, 12, _MONTHS),
    (0, 7, _DAYS),  # 0 and 7 are both Sunday
)


def _parse_field(text: str, lo: int, hi: int, names: dict[str, int]) -> set[int]:
    values: set[int] = set()
    for part in text.split(","):
        rng, _, step_s = part.partition("/")
        step = 1
        if step_s:
            if not step_s.isdigit() or int(step_s) < 1:
                raise ValueError(f"invalid step '{step_s}'")
            step = int(step_s)

        def num(token: str) -> int:
            token = token.lower()
            if token in names:
                return names[token]
            if not token.isdigit():
                raise ValueError(f"invalid value '{token}'")
            return int(token)

        if rng == "*":
            start, end = lo, hi
        elif "-" in rng:
            a, _, b = rng.partition("-")
            start, end = num(a), num(b)
        else:
            start = num(rng)
            end = hi if step_s else start
        if not (lo <= start <= hi and lo <= end <= hi) or start > end:
            raise ValueError(f"value out of range {lo}-{hi}: '{part}'")
        values.update(range(start, end + 1, step))
    return values


class CronExpression:
    """Standard 5-field cron: ``minute hour day-of-month month day-of-week``.

    Supports ``*``, lists (``1,15``), ranges (``1-5``), steps (``*/5``, ``10-30/5``)
    and month/day names (``jan``, ``mon-fri``). Like classic cron, when both
    day-of-month and day-of-week are restricted, a date matching either one runs.
    """

    def __init__(self, expression: str) -> None:
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron expression must have 5 fields (minute hour day month weekday), got '{expression}'."
            )
        try:
            parsed = [_parse_field(f, lo, hi, names) for f, (lo, hi, names) in zip(fields, _FIELDS)]
        except ValueError as exc:
            raise ValueError(f"Invalid cron expression '{expression}': {exc}") from None
        self.expression = expression
        self.minutes, self.hours, self.days, self.months, weekdays = parsed
        # cron: 0=Sunday..6=Saturday (7 also Sunday) -> python weekday(): 0=Monday
        self.weekdays = {(d - 1) % 7 for d in weekdays}
        self._dom_any = fields[2] == "*"
        self._dow_any = fields[4] == "*"

    def _day_matches(self, dt: datetime) -> bool:
        dom = dt.day in self.days
        dow = dt.weekday() in self.weekdays
        if self._dom_any or self._dow_any:
            return dom and dow
        return dom or dow

    def next_after(self, after: datetime) -> datetime:
        """First matching minute strictly after ``after``."""
        dt = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = after.year + 9  # enough for Feb 29 on a restricted weekday
        while dt.year <= limit:
            if dt.month not in self.months:
                dt = (dt.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
                continue
            if not self._day_matches(dt):
                dt = dt.replace(hour=0, minute=0) + timedelta(days=1)
                continue
            if dt.hour not in self.hours:
                dt = dt.replace(minute=0) + timedelta(hours=1)
                continue
            if dt.minute not in self.minutes:
                dt += timedelta(minutes=1)
                continue
            return dt
        raise ValueError(f"Cron expression '{self.expression}' never matches.")

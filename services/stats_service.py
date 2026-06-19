"""
services/stats_service.py — BookClub

Computes reading statistics for a user: streak, books finished this month,
and total pages read.
"""

from datetime import date, datetime, timezone
from services import reading_service


def _utc_to_local_date(dt: datetime) -> date:
    """
    Convert a UTC-stored datetime to the server's local calendar date.

    finished_at is stored as UTC. Using .date() directly gives the UTC date,
    which can be one day behind the user's local date for late-night finishes.
    We convert to local time first so the streak reflects the user's calendar day.
    """
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC (SQLite strips tzinfo on round-trip).
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def calculate_streak(user_id: str) -> int:
    """
    Calculate a user's current reading streak in consecutive days.

    A streak is the number of consecutive calendar days on which the user
    finished at least one book, counting back from today (or yesterday, if
    nothing has been finished today yet).

    finished_at timestamps are stored in UTC and converted to local calendar
    dates before comparison, so a book finished at 11:58 PM local time is
    counted on the correct local date even when the server clock is UTC.

    Returns 0 if the user has no reading history or if there is a gap of
    more than one day since their most recent finished book.

    Args:
        user_id: ID of the user.

    Returns:
        The streak count as an integer.
    """
    events = reading_service.get_reading_history(user_id)
    if not events:
        return 0

    # Collect unique local-calendar finish dates, most recent first.
    dates = sorted(
        set(_utc_to_local_date(e.finished_at) for e in events),
        reverse=True,
    )

    today = date.today()

    # Streak must start from today or yesterday — otherwise it has already broken.
    if (today - dates[0]).days > 1:
        return 0

    streak = 1
    for i in range(len(dates) - 1):
        delta = (dates[i] - dates[i + 1]).days
        if delta == 1:
            streak += 1
        else:
            break

    return streak


def calculate_genre_streak(user_id: str, genre: str) -> int:
    """
    Calculate a user's current reading streak for a specific genre.

    Counts consecutive calendar days on which the user finished at least one
    book in the given genre, counting back from today (or yesterday).

    Args:
        user_id: ID of the user.
        genre:   Genre string to filter by (case-insensitive).

    Returns:
        The genre streak count as an integer.
    """
    events = reading_service.get_reading_history(user_id)
    genre_events = [e for e in events if e.book.genre and e.book.genre.lower() == genre.lower()]
    if not genre_events:
        return 0

    dates = sorted(
        set(_utc_to_local_date(e.finished_at) for e in genre_events),
        reverse=True,
    )

    today = date.today()

    if (today - dates[0]).days > 1:
        return 0

    streak = 1
    for i in range(len(dates) - 1):
        delta = (dates[i] - dates[i + 1]).days
        if delta == 1:
            streak += 1
        else:
            break

    return streak


def books_this_month(user_id: str) -> int:
    """
    Count the number of books the user finished in the current calendar month.

    Uses local calendar dates (converted from UTC) so a book finished just
    before midnight local time on the last day of the month is counted correctly.

    Edge case: if a book has pages=0, it still counts toward this total — the
    function counts completions, not pages.

    Args:
        user_id: ID of the user.

    Returns:
        Count of books finished this month.
    """
    events = reading_service.get_reading_history(user_id)
    today = date.today()
    return sum(
        1
        for e in events
        if _utc_to_local_date(e.finished_at).year == today.year
        and _utc_to_local_date(e.finished_at).month == today.month
    )


def total_pages_read(user_id: str) -> int:
    """
    Sum the page counts of all books the user has finished.

    Edge case: books with pages=0 contribute 0 to the total. This is correct
    by design — the data is what it is — but callers should be aware that a
    zero-page book won't raise an error.

    Args:
        user_id: ID of the user.

    Returns:
        Total pages read as an integer. Returns 0 if no books finished or all
        finished books have pages=0.
    """
    events = reading_service.get_reading_history(user_id)
    return sum(e.book.pages for e in events)

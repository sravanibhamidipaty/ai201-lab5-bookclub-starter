"""
tests/test_stats.py — BookClub

Unit tests for calculate_streak() and get_reading_history().
Uses a SQLite in-memory database so tests are isolated and fast.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app import create_app
from extensions import db
from models import User, Book, ReadingEvent
from services import stats_service, reading_service


@pytest.fixture
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def ctx(app):
    """Push an app context so db.session is available in tests."""
    with app.app_context():
        yield


def make_user(username="testuser"):
    user = User(username=username, email=f"{username}@test.com")
    db.session.add(user)
    db.session.flush()
    return user


def make_book(added_by, title="Test Book", pages=100, genre="fiction"):
    book = Book(title=title, author="Author", pages=pages, genre=genre, added_by=added_by)
    db.session.add(book)
    db.session.flush()
    return book


def make_event(user_id, book_id, finished_days_ago):
    """Create a finished ReadingEvent with finished_at set N days ago."""
    now = datetime.now(timezone.utc)
    event = ReadingEvent(
        user_id=user_id,
        book_id=book_id,
        started_at=now - timedelta(days=finished_days_ago + 1),
        finished_at=now - timedelta(days=finished_days_ago),
    )
    db.session.add(event)
    db.session.flush()
    return event


# --- calculate_streak tests ---

def test_streak_no_history(ctx):
    user = make_user()
    db.session.commit()
    assert stats_service.calculate_streak(user.id) == 0


def test_streak_three_consecutive_days(ctx):
    user = make_user()
    book1 = make_book(user.id, title="Book A")
    book2 = make_book(user.id, title="Book B")
    book3 = make_book(user.id, title="Book C")
    make_event(user.id, book1.id, finished_days_ago=0)
    make_event(user.id, book2.id, finished_days_ago=1)
    make_event(user.id, book3.id, finished_days_ago=2)
    db.session.commit()
    assert stats_service.calculate_streak(user.id) == 3


def test_streak_gap_resets_to_zero(ctx):
    user = make_user()
    book1 = make_book(user.id, title="Book A")
    book2 = make_book(user.id, title="Book B")
    # Finished today and 3 days ago — gap of 2 days breaks the streak.
    make_event(user.id, book1.id, finished_days_ago=0)
    make_event(user.id, book2.id, finished_days_ago=3)
    db.session.commit()
    assert stats_service.calculate_streak(user.id) == 1


def test_streak_last_book_too_old(ctx):
    """Most recent finish was 2+ days ago — streak is already broken."""
    user = make_user()
    book1 = make_book(user.id, title="Book A")
    make_event(user.id, book1.id, finished_days_ago=3)
    db.session.commit()
    assert stats_service.calculate_streak(user.id) == 0


def test_streak_multiple_books_same_day(ctx):
    """Two books finished on the same day count as one streak day."""
    user = make_user()
    book1 = make_book(user.id, title="Book A")
    book2 = make_book(user.id, title="Book B")
    book3 = make_book(user.id, title="Book C")
    # Two books finished today, one yesterday — streak should be 2.
    now = datetime.now(timezone.utc)
    e1 = ReadingEvent(user_id=user.id, book_id=book1.id,
                      started_at=now - timedelta(days=2),
                      finished_at=now - timedelta(hours=2))
    e2 = ReadingEvent(user_id=user.id, book_id=book2.id,
                      started_at=now - timedelta(days=2),
                      finished_at=now - timedelta(hours=5))
    e3 = ReadingEvent(user_id=user.id, book_id=book3.id,
                      started_at=now - timedelta(days=3),
                      finished_at=now - timedelta(days=1))
    db.session.add_all([e1, e2, e3])
    db.session.commit()
    assert stats_service.calculate_streak(user.id) == 2


# --- get_reading_history order tests ---

def test_history_most_recently_finished_first(ctx):
    user = make_user()
    book1 = make_book(user.id, title="Older Book")
    book2 = make_book(user.id, title="Newer Book")
    make_event(user.id, book1.id, finished_days_ago=5)
    make_event(user.id, book2.id, finished_days_ago=1)
    db.session.commit()

    history = reading_service.get_reading_history(user.id)
    assert len(history) == 2
    assert history[0].book.title == "Newer Book"
    assert history[1].book.title == "Older Book"


def test_history_excludes_in_progress(ctx):
    user = make_user()
    book1 = make_book(user.id, title="Finished Book")
    book2 = make_book(user.id, title="In Progress Book")
    make_event(user.id, book1.id, finished_days_ago=1)
    # In-progress: started but no finished_at.
    in_progress = ReadingEvent(
        user_id=user.id,
        book_id=book2.id,
        started_at=datetime.now(timezone.utc) - timedelta(days=2),
        finished_at=None,
    )
    db.session.add(in_progress)
    db.session.commit()

    history = reading_service.get_reading_history(user.id)
    assert len(history) == 1
    assert history[0].book.title == "Finished Book"


def test_history_empty_for_new_user(ctx):
    user = make_user()
    db.session.commit()
    assert reading_service.get_reading_history(user.id) == []


# --- calculate_genre_streak tests ---

def test_genre_streak_correct_genre(ctx):
    user = make_user()
    book1 = make_book(user.id, title="Sci-fi A", genre="sci-fi")
    book2 = make_book(user.id, title="Sci-fi B", genre="sci-fi")
    book3 = make_book(user.id, title="Other", genre="fiction")
    make_event(user.id, book1.id, finished_days_ago=0)
    make_event(user.id, book2.id, finished_days_ago=1)
    make_event(user.id, book3.id, finished_days_ago=2)
    db.session.commit()
    # Only sci-fi books: days 0 and 1 — streak of 2.
    assert stats_service.calculate_genre_streak(user.id, "sci-fi") == 2


def test_genre_streak_case_insensitive(ctx):
    user = make_user()
    book1 = make_book(user.id, title="Book A", genre="Sci-Fi")
    make_event(user.id, book1.id, finished_days_ago=0)
    db.session.commit()
    assert stats_service.calculate_genre_streak(user.id, "sci-fi") == 1


def test_genre_streak_no_matching_books(ctx):
    user = make_user()
    book1 = make_book(user.id, title="Book A", genre="fiction")
    make_event(user.id, book1.id, finished_days_ago=0)
    db.session.commit()
    assert stats_service.calculate_genre_streak(user.id, "sci-fi") == 0


# --- edge case audits ---

def test_books_this_month_zero_page_book_still_counted(ctx):
    """A book with pages=0 still counts as a finished book this month."""
    user = make_user()
    book = make_book(user.id, pages=0)
    make_event(user.id, book.id, finished_days_ago=0)
    db.session.commit()
    assert stats_service.books_this_month(user.id) == 1


def test_total_pages_zero_page_book(ctx):
    """A book with pages=0 contributes 0 to total_pages_read — no error raised."""
    user = make_user()
    book = make_book(user.id, pages=0)
    make_event(user.id, book.id, finished_days_ago=0)
    db.session.commit()
    assert stats_service.total_pages_read(user.id) == 0

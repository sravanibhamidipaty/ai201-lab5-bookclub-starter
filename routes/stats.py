"""
routes/stats.py — BookClub

Routes for reading statistics: streak, books this month, total pages read.
"""

from flask import Blueprint, jsonify
from services import stats_service

stats_bp = Blueprint("stats", __name__)


@stats_bp.route("/<user_id>", methods=["GET"])
def get_stats(user_id):
    """
    Return reading statistics for a user.

    Response JSON:
        reading_streak    (int) — consecutive days with at least one book finished
        books_this_month  (int) — books finished in the current calendar month
        total_pages_read  (int) — total pages across all finished books
    """
    return jsonify(
        {
            "user_id": user_id,
            "reading_streak": stats_service.calculate_streak(user_id),
            "books_this_month": stats_service.books_this_month(user_id),
            "total_pages_read": stats_service.total_pages_read(user_id),
        }
    )


@stats_bp.route("/<user_id>/genre-streak/<genre>", methods=["GET"])
def get_genre_streak(user_id, genre):
    """
    Return the user's current reading streak for a specific genre.

    Response JSON:
        genre          (str) — the genre queried
        genre_streak   (int) — consecutive days with at least one book of this genre finished
    """
    return jsonify(
        {
            "user_id": user_id,
            "genre": genre,
            "genre_streak": stats_service.calculate_genre_streak(user_id, genre),
        }
    )

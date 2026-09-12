import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

PROFILE_TONES = ["accent", "accent-2", "neutral"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return render_template("register.html", error="All fields are required.")

        if len(password) < 8:
            return render_template(
                "register.html", error="Password must be at least 8 characters."
            )

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing is not None:
            db.close()
            return render_template(
                "register.html", error="An account with that email already exists."
            )

        password_hash = generate_password_hash(password)
        try:
            db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.close()
            return render_template(
                "register.html", error="An account with that email already exists."
            )
        db.close()

        return redirect(url_for("login", registered=1))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template(
                "login.html", error="Invalid email or password."
            )

        db = get_db()
        user = db.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        db.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template(
                "login.html", error="Invalid email or password."
            )

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
@login_required
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


def _get_recent_transactions(db, user_id):
    """Return the 5 most recent expenses for user_id, newest first."""
    rows = db.execute(
        "SELECT date, description, category, amount FROM expenses "
        "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 5",
        (user_id,),
    ).fetchall()

    transactions = []
    for idx, row in enumerate(rows):
        transactions.append({
            "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%b %d"),
            "description": row["description"],
            "category": row["category"],
            "amount": f"₹{row['amount']:.2f}",
            "tone": PROFILE_TONES[idx % 3],
        })
    return transactions


def _get_profile_user(db, user_id):
    """Return user dict: name, email, initials, member_since."""
    row = db.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    words = row["name"].split()
    initials = "".join(word[0].upper() for word in words[:2])

    member_since = datetime.strptime(
        row["created_at"][:10], "%Y-%m-%d"
    ).strftime("%B %Y")

    return {
        "name": row["name"],
        "email": row["email"],
        "initials": initials,
        "member_since": member_since,
    }


def _get_profile_stats(db, user_id):
    """Return stats dict: total_spent, transaction_count, top_category."""
    totals_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
        "FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    top_row = db.execute(
        "SELECT category, SUM(amount) AS cat_total FROM expenses "
        "WHERE user_id = ? GROUP BY category ORDER BY cat_total DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    return {
        "total_spent": f"₹{totals_row['total']:.2f}",
        "transaction_count": totals_row["cnt"],
        "top_category": top_row["category"] if top_row else "—",
    }


def _get_category_breakdown(db, user_id):
    """Return list of per-category spend dicts, ordered by amount desc."""
    rows = db.execute(
        "SELECT category, SUM(amount) AS total FROM expenses WHERE user_id = ? "
        "GROUP BY category ORDER BY total DESC",
        (user_id,),
    ).fetchall()

    grand_total = sum(row["total"] for row in rows)

    breakdown = []
    for idx, row in enumerate(rows):
        percent = round(row["total"] / grand_total * 100) if grand_total else 0
        breakdown.append(
            {
                "name": row["category"],
                "amount": f"₹{row['total']:.2f}",
                "percent": percent,
                "tone": PROFILE_TONES[idx % 3],
            }
        )
    return breakdown


@app.route("/profile")
@login_required
def profile():
    db = get_db()
    user = _get_profile_user(db, session["user_id"])
    stats = _get_profile_stats(db, session["user_id"])
    transactions = _get_recent_transactions(db, session["user_id"])
    categories = _get_category_breakdown(db, session["user_id"])
    db.close()

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
@login_required
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
@login_required
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
@login_required
def delete_expense(id):
    return "Delete expense — coming in Step 9"


# ------------------------------------------------------------------ #
# Database setup                                                      #
# ------------------------------------------------------------------ #

with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)

import math
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

PROFILE_TONES = ["accent", "accent-2", "neutral"]
EXPENSE_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]
EXPENSE_DESCRIPTION_MAX_LENGTH = 255


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
            return render_template("login.html", error="Invalid email or password.")

        db = get_db()
        user = db.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        db.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.")

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


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


def _validate_date_filter(args):
    """Parse start_date/end_date from query args.

    Returns (start_date, end_date, error, start_raw, end_raw) — the raw
    values are returned alongside so callers can repopulate the filter
    form without re-reading request.args themselves.
    """
    start_raw = args.get("start_date", "").strip()
    end_raw = args.get("end_date", "").strip()

    if not start_raw and not end_raw:
        return None, None, None, start_raw, end_raw
    if not start_raw or not end_raw:
        return (
            None,
            None,
            "Enter both a start and end date to filter.",
            start_raw,
            end_raw,
        )

    try:
        start_date = datetime.strptime(start_raw, "%Y-%m-%d").strftime("%Y-%m-%d")
        end_date = datetime.strptime(end_raw, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None, None, "Enter valid dates.", start_raw, end_raw

    if start_date > end_date:
        return None, None, "Start date must be before end date.", start_raw, end_raw

    return start_date, end_date, None, start_raw, end_raw


def _add_date_range(query, params, start_date, end_date):
    """Append a BETWEEN clause to query/params when both dates are given."""
    if start_date and end_date:
        query += " AND date BETWEEN ? AND ?"
        params += [start_date, end_date]
    return query, params


def _get_recent_transactions(db, user_id, start_date=None, end_date=None):
    """Return the 5 most recent expenses for user_id, newest first."""
    query = (
        "SELECT id, date, description, category, amount FROM expenses "
        "WHERE user_id = ?"
    )
    params = [user_id]
    query, params = _add_date_range(query, params, start_date, end_date)
    query += " ORDER BY date DESC, id DESC LIMIT 5"

    rows = db.execute(query, params).fetchall()

    transactions = []
    for idx, row in enumerate(rows):
        transactions.append(
            {
                "id": row["id"],
                "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%b %d"),
                "description": row["description"],
                "category": row["category"],
                "amount": f"Rs. {row['amount']:.2f}",
                "tone": PROFILE_TONES[idx % 3],
            }
        )
    return transactions


def _get_profile_user(db, user_id):
    """Return user dict: name, email, initials, member_since."""
    row = db.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    words = row["name"].split()
    initials = "".join(word[0].upper() for word in words[:2])

    member_since = datetime.strptime(row["created_at"][:10], "%Y-%m-%d").strftime(
        "%B %Y"
    )

    return {
        "name": row["name"],
        "email": row["email"],
        "initials": initials,
        "member_since": member_since,
    }


def _get_profile_stats(db, user_id, start_date=None, end_date=None):
    """Return stats dict: total_spent, transaction_count, top_category."""
    totals_query = (
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
        "FROM expenses WHERE user_id = ?"
    )
    top_query = (
        "SELECT category, SUM(amount) AS cat_total FROM expenses WHERE user_id = ?"
    )
    params = [user_id]
    totals_query, params = _add_date_range(totals_query, params, start_date, end_date)
    if start_date and end_date:
        top_query += " AND date BETWEEN ? AND ?"
    top_query += " GROUP BY category ORDER BY cat_total DESC LIMIT 1"

    totals_row = db.execute(totals_query, params).fetchone()
    top_row = db.execute(top_query, params).fetchone()

    return {
        "total_spent": f"Rs. {totals_row['total']:.2f}",
        "transaction_count": totals_row["cnt"],
        "top_category": top_row["category"] if top_row else "—",
    }


def _get_category_breakdown(db, user_id, start_date=None, end_date=None):
    """Return list of per-category spend dicts, ordered by amount desc."""
    query = "SELECT category, SUM(amount) AS total FROM expenses WHERE user_id = ?"
    params = [user_id]
    query, params = _add_date_range(query, params, start_date, end_date)
    query += " GROUP BY category ORDER BY total DESC"

    rows = db.execute(query, params).fetchall()

    grand_total = sum(row["total"] for row in rows)

    breakdown = []
    for idx, row in enumerate(rows):
        percent = round(row["total"] / grand_total * 100) if grand_total else 0
        breakdown.append(
            {
                "name": row["category"],
                "amount": f"Rs. {row['total']:.2f}",
                "percent": percent,
                "tone": PROFILE_TONES[idx % 3],
            }
        )
    return breakdown


@app.route("/profile")
@login_required
def profile():
    start_date, end_date, filter_error, start_raw, end_raw = _validate_date_filter(
        request.args
    )

    db = get_db()
    user = _get_profile_user(db, session["user_id"])
    stats = _get_profile_stats(db, session["user_id"], start_date, end_date)
    transactions = _get_recent_transactions(
        db, session["user_id"], start_date, end_date
    )
    categories = _get_category_breakdown(db, session["user_id"], start_date, end_date)
    db.close()

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        date_filter={
            "start_date": start_date or start_raw,
            "end_date": end_date or end_raw,
            "error": filter_error,
            "active": bool(start_date and end_date),
        },
    )


def _validate_expense_form(form):
    """Validate submitted amount/category/date/description.

    Returns (amount, amount_raw, category, date, date_raw, description,
    error). On success, `amount` and `date` hold the parsed values and
    `error` is None. On failure, `amount`/`date` are None and the `_raw`
    fields let the caller repopulate the form with what was submitted.
    """
    amount_raw = form.get("amount", "").strip()
    category = form.get("category", "").strip()
    date_raw = form.get("date", "").strip()
    description = form.get("description", "").strip()

    amount = None
    date = None
    error = None

    try:
        amount = float(amount_raw)
        if not math.isfinite(amount) or amount <= 0:
            amount = None
            error = "Enter a valid amount greater than 0."
    except ValueError:
        error = "Enter a valid amount greater than 0."

    if not error and category not in EXPENSE_CATEGORIES:
        error = "Select a valid category."

    if not error and len(description) > EXPENSE_DESCRIPTION_MAX_LENGTH:
        error = (
            f"Description must be {EXPENSE_DESCRIPTION_MAX_LENGTH} characters or fewer."
        )

    if not error:
        try:
            date = datetime.strptime(date_raw, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            error = "Enter a valid date."

    return amount, amount_raw, category, date, date_raw, description, error


def _render_expense_form(error=None, amount="", category="", date="", description=""):
    return render_template(
        "expenses_add.html",
        categories=EXPENSE_CATEGORIES,
        error=error,
        amount=amount,
        category=category,
        date=date,
        description=description,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        amount, amount_raw, category, date, date_raw, description, error = (
            _validate_expense_form(request.form)
        )

        if error:
            return _render_expense_form(
                error=error,
                amount=amount_raw,
                category=category,
                date=date_raw,
                description=description,
            )

        db = get_db()
        db.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (session["user_id"], amount, category, date, description or None),
        )
        db.commit()
        db.close()

        return redirect(url_for("profile"))

    return _render_expense_form(date=datetime.now().strftime("%Y-%m-%d"))


def _get_owned_expense(db, expense_id, user_id):
    """Return the expenses row with expense_id owned by user_id, or None."""
    return db.execute(
        "SELECT id, amount, category, date, description FROM expenses "
        "WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    ).fetchone()


def _render_edit_expense_form(
    expense_id, error=None, amount="", category="", date="", description=""
):
    return render_template(
        "expenses_edit.html",
        categories=EXPENSE_CATEGORIES,
        expense_id=expense_id,
        error=error,
        amount=amount,
        category=category,
        date=date,
        description=description,
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    db = get_db()
    expense = _get_owned_expense(db, id, session["user_id"])
    if expense is None:
        db.close()
        abort(404)

    if request.method == "POST":
        amount, amount_raw, category, date, date_raw, description, error = (
            _validate_expense_form(request.form)
        )

        if error:
            db.close()
            return _render_edit_expense_form(
                id,
                error=error,
                amount=amount_raw,
                category=category,
                date=date_raw,
                description=description,
            )

        db.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? "
            "WHERE id = ? AND user_id = ?",
            (amount, category, date, description or None, id, session["user_id"]),
        )
        db.commit()
        db.close()

        return redirect(url_for("profile"))

    db.close()
    return _render_edit_expense_form(
        id,
        amount=expense["amount"],
        category=expense["category"],
        date=expense["date"],
        description=expense["description"] or "",
    )


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

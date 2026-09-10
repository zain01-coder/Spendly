import sqlite3
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"


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


@app.route("/profile")
@login_required
def profile():
    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "March 2025",
    }

    stats = {
        "total_spent": "₹313.50",
        "transaction_count": 8,
        "top_category": "Bills",
    }

    transactions = [
        {"date": "Sep 21", "description": "Groceries", "category": "Food", "tone": "accent-2", "amount": "₹22.00"},
        {"date": "Sep 18", "description": "Miscellaneous", "category": "Other", "tone": "neutral", "amount": "₹8.25"},
        {"date": "Sep 14", "description": "New shoes", "category": "Shopping", "tone": "accent", "amount": "₹60.00"},
        {"date": "Sep 10", "description": "Movie ticket", "category": "Entertainment", "tone": "neutral", "amount": "₹15.75"},
        {"date": "Sep 05", "description": "Electricity bill", "category": "Bills", "tone": "accent-2", "amount": "₹120.00"},
    ]

    categories = [
        {"name": "Bills", "amount": "₹120.00", "percent": 38, "tone": "accent-2"},
        {"name": "Shopping", "amount": "₹60.00", "percent": 19, "tone": "accent"},
        {"name": "Transport", "amount": "₹45.00", "percent": 14, "tone": "neutral"},
        {"name": "Food", "amount": "₹34.50", "percent": 11, "tone": "accent-2"},
    ]

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

import sqlite3

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)


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


@app.route("/login")
def login():
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
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
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

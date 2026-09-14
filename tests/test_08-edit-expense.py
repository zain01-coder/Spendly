"""
Tests for the /expenses/<id>/edit feature (Step 8 — Edit Expense).

Spec: .claude/specs/08-edit-expense.md

Scope covered (per the spec's Definition of Done):
- GET /expenses/<id>/edit for an expense the logged-in user owns shows a
  form pre-filled with its current amount, category, date, and description
- A valid POST updates the expense and redirects to /profile, where the
  updated values are visible
- POST with an invalid amount (e.g. 0 or -5) re-renders the edit form with
  an inline error and keeps the submitted (not original) values in the
  fields, without mutating the database
- POST with an invalid/missing category or date shows a validation error
  and does not modify the database
- GET on an expense id that does not exist returns a 404
- GET on an expense owned by a different user returns a 404 (never that
  expense's data)
- POST on a nonexistent or foreign expense id also returns a 404 and does
  not mutate the database
- GET while logged out redirects to /login

Design notes:
- These tests never read edit_expense()'s implementation to derive expected
  behavior — only the spec, and template landmarks (element ids, CSS
  classes) read from templates/expenses_edit.html and
  templates/expenses_add.html, the same way test_07-add-expense.py and
  test_profile_date_filter.py do for their respective templates.
- The app performs `init_db()`/`seed_db()` against a real on-disk sqlite
  file at import time. Each test function here redirects
  `database.db.DB_PATH` to a fresh per-test temp file and re-runs
  `init_db()` against it (without seeding), matching the isolation
  strategy of the existing test suites exactly.
- Amounts are compared numerically (via float()/pytest.approx), not as
  exact strings, since the spec doesn't dictate a specific display
  formatting for the pre-filled amount field.
"""

import re
from pathlib import Path

import pytest

import database.db as db_module
import app as app_module

SPEC_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A Spendly app wired to a fresh, empty, isolated sqlite file per test."""
    db_path = tmp_path / "test_expense_tracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))

    flask_app = app_module.app
    flask_app.config.update({"TESTING": True})

    with flask_app.app_context():
        db_module.init_db()
        # Deliberately NOT calling seed_db(): every test seeds only the
        # exact rows it needs, so assertions never depend on incidental
        # seed-data values.

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------- #
# Test helpers
# --------------------------------------------------------------------------- #


def register_and_login(client, name, email, password="password123"):
    """Register a brand-new user through the real /register + /login routes
    and return their user_id (looked up via a parameterised SELECT)."""
    resp = client.post(
        "/register",
        data={"name": name, "email": email, "password": password},
    )
    assert resp.status_code in (302, 200), "Registration was expected to succeed"

    resp = client.post(
        "/login",
        data={"email": email, "password": password},
    )
    assert (
        resp.status_code == 302
    ), "Login with freshly-registered credentials should succeed"

    db = db_module.get_db()
    row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    assert row is not None, "Expected the newly-registered user to exist in the DB"
    return row["id"]


def login(client, email, password="password123"):
    resp = client.post("/login", data={"email": email, "password": password})
    assert resp.status_code == 302, f"Re-login as {email} should succeed"
    return resp


def insert_expense(user_id, amount, category, date_str, description):
    """Insert one fully-controlled expense row using parameterised SQL and
    return its id."""
    db = db_module.get_db()
    cur = db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date_str, description),
    )
    db.commit()
    expense_id = cur.lastrowid
    db.close()
    return expense_id


def get_expense_by_id(expense_id):
    """Fetch a single expense row (regardless of owner) via a parameterised
    SELECT, for asserting on db state after edit attempts."""
    db = db_module.get_db()
    row = db.execute(
        "SELECT id, user_id, amount, category, date, description "
        "FROM expenses WHERE id = ?",
        (expense_id,),
    ).fetchone()
    db.close()
    return row


def count_all_expenses():
    db = db_module.get_db()
    row = db.execute("SELECT COUNT(*) AS cnt FROM expenses").fetchone()
    db.close()
    return row["cnt"]


def get_input_value(html, field_name):
    """Extract the `value="..."` attribute of the named input, matching the
    landmark-extraction pattern used in the add-expense/profile test suites."""
    pattern = rf'id="{field_name}"[^>]*value="([^"]*)"'
    match = re.search(pattern, html)
    assert match, f"Could not find input '{field_name}' in the rendered page"
    return match.group(1)


def is_category_selected(html, category):
    """True if the given category's <option> is marked selected in the
    rendered <select id="category">."""
    return bool(re.search(rf'value="{re.escape(category)}"\s+selected', html))


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


VALID_UPDATE = {
    "amount": "88.00",
    "category": "Bills",
    "date": "2024-07-04",
    "description": "Updated description",
}


def submit_edit(client, expense_id, **overrides):
    data = dict(VALID_UPDATE, **overrides)
    return client.post(edit_url(expense_id), data=data)


# --------------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------------- #


class TestEditExpenseAuthGuard:
    def test_get_edit_expense_while_logged_out_redirects_to_login(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(alice_id, 10.00, "Food", "2024-01-01", "DESC_A")
        client.get("/logout")

        response = client.get(edit_url(expense_id))

        assert (
            response.status_code == 302
        ), "Unauthenticated GET /expenses/<id>/edit should redirect"
        assert (
            "/login" in response.headers["Location"]
        ), "Should redirect to the login page"

    def test_post_edit_expense_while_logged_out_redirects_to_login_and_does_not_mutate(
        self, client
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(alice_id, 10.00, "Food", "2024-01-01", "DESC_A")
        client.get("/logout")

        response = submit_edit(client, expense_id)

        assert (
            response.status_code == 302
        ), "Unauthenticated POST /expenses/<id>/edit should redirect"
        assert "/login" in response.headers["Location"]

        row = get_expense_by_id(expense_id)
        assert row["amount"] == pytest.approx(
            10.00
        ), "Unauthenticated POST must not mutate the expense"
        assert row["description"] == "DESC_A"


# --------------------------------------------------------------------------- #
# GET pre-fills the form
# --------------------------------------------------------------------------- #


class TestEditExpenseFormPrefill:
    def test_get_edit_expense_prefills_existing_values(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 55.25, "Health", "2024-02-14", "Doctor visit"
        )

        response = client.get(edit_url(expense_id))
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert float(get_input_value(html, "amount")) == pytest.approx(55.25)
        assert get_input_value(html, "date") == "2024-02-14"
        assert get_input_value(html, "description") == "Doctor visit"
        assert is_category_selected(html, "Health")

    def test_get_edit_expense_has_no_error_on_fresh_load(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 20.00, "Transport", "2024-03-03", "Bus fare"
        )

        response = client.get(edit_url(expense_id))
        html = response.get_data(as_text=True)

        assert (
            "auth-error" not in html
        ), "No error should be shown on a fresh GET of the edit form"

    def test_get_edit_expense_offers_all_fixed_categories(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 20.00, "Transport", "2024-03-03", "Bus fare"
        )

        response = client.get(edit_url(expense_id))
        html = response.get_data(as_text=True)

        for category in SPEC_CATEGORIES:
            assert (
                f'value="{category}"' in html
            ), f"Expected '{category}' to be an available category option"


# --------------------------------------------------------------------------- #
# Happy path — valid update
# --------------------------------------------------------------------------- #


class TestEditExpenseHappyPath:
    def test_valid_update_changes_row_and_redirects_to_profile(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_edit(client, expense_id)

        assert (
            response.status_code == 302
        ), "A valid update should redirect, not re-render the form"
        assert (
            "/profile" in response.headers["Location"]
        ), "Should redirect to the profile page"

        row = get_expense_by_id(expense_id)
        assert (
            row["user_id"] == alice_id
        ), "The expense must still belong to the same owner"
        assert row["amount"] == pytest.approx(88.00)
        assert row["category"] == "Bills"
        assert row["date"] == "2024-07-04"
        assert row["description"] == "Updated description"

    def test_valid_update_does_not_create_a_new_row(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        submit_edit(client, expense_id)

        assert (
            count_all_expenses() == 1
        ), "Editing must update the existing row, not insert a new one"

    def test_updated_values_appear_on_profile_page(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        submit_edit(
            client,
            expense_id,
            description="DESC_AFTER_EDIT",
            amount="123.45",
            category="Shopping",
        )

        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert (
            "DESC_AFTER_EDIT" in html
        ), "Updated description should appear on the profile page"
        assert (
            "Original desc" not in html
        ), "Stale/original description should no longer appear"
        assert (
            "Shopping" in html
        ), "Updated category should appear in the category breakdown"


# --------------------------------------------------------------------------- #
# Amount validation
# --------------------------------------------------------------------------- #


class TestEditExpenseAmountValidation:
    @pytest.mark.parametrize("bad_amount", ["", "0", "-10", "abc", "-0.01"])
    def test_invalid_amount_rerenders_form_with_error_and_does_not_mutate(
        self, client, bad_amount
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_edit(client, expense_id, amount=bad_amount)
        html = response.get_data(as_text=True)

        assert (
            response.status_code == 200
        ), "Validation failure must re-render the form, not redirect"
        assert (
            "auth-error" in html
        ), f"Expected an inline error for amount={bad_amount!r}"

        row = get_expense_by_id(expense_id)
        assert row["amount"] == pytest.approx(
            10.00
        ), "Original amount must be unchanged"
        assert row["category"] == "Food"
        assert row["date"] == "2024-01-01"
        assert row["description"] == "Original desc"

    def test_invalid_amount_repopulates_submitted_not_original_values(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_edit(
            client,
            expense_id,
            amount="not-a-number",
            category="Bills",
            date="2024-06-01",
            description="Repopulate me",
        )
        html = response.get_data(as_text=True)

        assert get_input_value(html, "amount") == "not-a-number"
        assert get_input_value(html, "date") == "2024-06-01"
        assert get_input_value(html, "description") == "Repopulate me"
        assert is_category_selected(html, "Bills")


# --------------------------------------------------------------------------- #
# Category validation
# --------------------------------------------------------------------------- #


class TestEditExpenseCategoryValidation:
    @pytest.mark.parametrize("bad_category", ["NotACategory", "food", "<script>", ""])
    def test_invalid_category_rerenders_form_with_error_and_does_not_mutate(
        self, client, bad_category
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_edit(client, expense_id, category=bad_category)
        html = response.get_data(as_text=True)

        assert (
            response.status_code == 200
        ), "Validation failure must re-render the form, not redirect"
        assert (
            "auth-error" in html
        ), f"Expected an inline error for category={bad_category!r}"

        row = get_expense_by_id(expense_id)
        assert row["category"] == "Food", "Original category must be unchanged"
        assert row["amount"] == pytest.approx(10.00)
        assert row["date"] == "2024-01-01"
        assert row["description"] == "Original desc"

    def test_invalid_category_repopulates_submitted_not_original_values(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_edit(
            client,
            expense_id,
            amount="15.00",
            category="NotACategory",
            date="2024-06-01",
            description="Keep me",
        )
        html = response.get_data(as_text=True)

        assert get_input_value(html, "amount") == "15.00"
        assert get_input_value(html, "date") == "2024-06-01"
        assert get_input_value(html, "description") == "Keep me"


# --------------------------------------------------------------------------- #
# Date validation
# --------------------------------------------------------------------------- #


class TestEditExpenseDateValidation:
    @pytest.mark.parametrize(
        "bad_date",
        ["not-a-date", "2024/06/01", "2024-13-40", "2024-02-30", ""],
    )
    def test_malformed_date_rerenders_form_with_error_and_does_not_mutate(
        self, client, bad_date
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_edit(client, expense_id, date=bad_date)
        html = response.get_data(as_text=True)

        assert (
            response.status_code == 200
        ), "Validation failure must re-render the form, not redirect"
        assert "auth-error" in html, f"Expected an inline error for date={bad_date!r}"

        row = get_expense_by_id(expense_id)
        assert row["date"] == "2024-01-01", "Original date must be unchanged"
        assert row["amount"] == pytest.approx(10.00)
        assert row["category"] == "Food"
        assert row["description"] == "Original desc"

    def test_malformed_date_repopulates_submitted_not_original_values(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_edit(
            client,
            expense_id,
            amount="15.00",
            category="Health",
            date="not-a-date",
            description="Keep me too",
        )
        html = response.get_data(as_text=True)

        assert get_input_value(html, "amount") == "15.00"
        assert is_category_selected(html, "Health")
        assert get_input_value(html, "description") == "Keep me too"


# --------------------------------------------------------------------------- #
# 404s — nonexistent id / cross-user ownership
# --------------------------------------------------------------------------- #


class TestEditExpenseNotFound:
    def test_get_nonexistent_expense_id_returns_404(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = client.get(edit_url(999999))

        assert (
            response.status_code == 404
        ), "GET on a nonexistent expense id must return 404"

    def test_get_expense_owned_by_another_user_returns_404(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "DESC_ALICE_ONLY"
        )

        register_and_login(client, "Bob", "bob@example.com")
        response = client.get(edit_url(expense_id))
        html = response.get_data(as_text=True)

        assert (
            response.status_code == 404
        ), "GET on another user's expense must return 404"
        assert (
            "DESC_ALICE_ONLY" not in html
        ), "Another user's expense data must never be leaked"

    def test_post_nonexistent_expense_id_returns_404(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_edit(client, 999999)

        assert (
            response.status_code == 404
        ), "POST on a nonexistent expense id must return 404"
        assert (
            count_all_expenses() == 0
        ), "No row should exist or be created for a nonexistent id"

    def test_post_expense_owned_by_another_user_returns_404_and_does_not_mutate(
        self, client
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        register_and_login(client, "Bob", "bob@example.com")
        response = submit_edit(client, expense_id, description="HACKED_BY_BOB")

        assert (
            response.status_code == 404
        ), "POST on another user's expense must return 404"

        row = get_expense_by_id(expense_id)
        assert row["user_id"] == alice_id, "Ownership must be unchanged"
        assert row["amount"] == pytest.approx(
            10.00
        ), "Another user's POST must never mutate the expense"
        assert row["category"] == "Food"
        assert row["date"] == "2024-01-01"
        assert row["description"] == "Original desc"


# --------------------------------------------------------------------------- #
# Static template check (spec's "Use CSS variables — never hardcode hex values")
# --------------------------------------------------------------------------- #


class TestEditExpenseTemplateStaticRules:
    def test_expenses_edit_template_has_no_hardcoded_hex_colours(self):
        template_path = (
            Path(__file__).resolve().parent.parent / "templates" / "expenses_edit.html"
        )
        content = template_path.read_text(encoding="utf-8")

        hex_color_matches = re.findall(r"#[0-9a-fA-F]{3,8}\b", content)
        assert not hex_color_matches, (
            f"expenses_edit.html must use CSS variables, not hardcoded hex colours; "
            f"found: {hex_color_matches}"
        )

    def test_expenses_edit_template_extends_base(self):
        template_path = (
            Path(__file__).resolve().parent.parent / "templates" / "expenses_edit.html"
        )
        content = template_path.read_text(encoding="utf-8")

        assert (
            '{% extends "base.html" %}' in content
        ), "expenses_edit.html must extend base.html"

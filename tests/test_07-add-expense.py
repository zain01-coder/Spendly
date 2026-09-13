"""
Tests for the /expenses/add feature (Step 7 — Add Expense).

Spec: .claude/specs/07-add-expense.md

Scope covered (per the spec's Definition of Done):
- GET /expenses/add while logged out redirects to /login
- POST /expenses/add while logged out redirects to /login and inserts nothing
- GET /expenses/add while logged in returns HTTP 200 with the form, the date
  field defaulting to today, and all fixed categories offered as options
- A valid POST creates a new row in `expenses` with the correct user_id and
  redirects to /profile
- The newly added expense is reflected on the profile page (recent
  transactions, summary stats, category breakdown)
- A negative, zero, or non-numeric amount re-renders the form with an inline
  error, HTTP 200, and does not create a row
- An invalid/unlisted category re-renders the form with an inline error and
  does not create a row
- A malformed date re-renders the form with an inline error and does not
  create a row
- On a validation failure, the fields the user already filled in are
  re-populated rather than lost
- Leaving the optional description blank still succeeds
- `user_id` is always taken from session["user_id"] — a client-supplied
  user_id in the POST body must never be trusted
- An expense added by one user never appears under another user's /profile
- expenses_add.html contains no hardcoded hex colours (CSS variables only)

Design notes:
- These tests never read add_expense()'s implementation to derive expected
  behavior — only the spec, and template landmarks (element ids, CSS
  classes) the same way the existing date-filter test suite does for
  profile.html.
- The app performs `init_db()`/`seed_db()` against a real on-disk sqlite
  file at import time. Each test function here redirects
  `database.db.DB_PATH` to a fresh per-test temp file and re-runs
  `init_db()` against it (without seeding), matching
  tests/test_profile_date_filter.py's isolation strategy exactly.
"""
import re
from pathlib import Path

import pytest

import database.db as db_module
import app as app_module

# Fixed category list as documented in the spec (Templates section) —
# intentionally spelled out here rather than imported from app.py, so this
# test file doesn't depend on the implementation's internal constant name.
SPEC_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
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
    assert resp.status_code == 302, "Login with freshly-registered credentials should succeed"

    db = db_module.get_db()
    row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    assert row is not None, "Expected the newly-registered user to exist in the DB"
    return row["id"]


def login(client, email, password="password123"):
    resp = client.post("/login", data={"email": email, "password": password})
    assert resp.status_code == 302, f"Re-login as {email} should succeed"
    return resp


def count_expenses_for_user(user_id):
    db = db_module.get_db()
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchone()
    db.close()
    return row["cnt"]


def count_all_expenses():
    db = db_module.get_db()
    row = db.execute("SELECT COUNT(*) AS cnt FROM expenses").fetchone()
    db.close()
    return row["cnt"]


def get_expenses_for_user(user_id):
    """Return all expense rows for user_id, newest first, via a
    parameterised SELECT against the app's own get_db()."""
    db = db_module.get_db()
    rows = db.execute(
        "SELECT id, user_id, amount, category, date, description "
        "FROM expenses WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    db.close()
    return rows


def get_input_value(html, field_name):
    """Extract the `value="..."` attribute of the named input, matching the
    landmark-extraction pattern used in test_profile_date_filter.py."""
    pattern = rf'id="{field_name}"[^>]*value="([^"]*)"'
    match = re.search(pattern, html)
    assert match, f"Could not find input '{field_name}' in the rendered page"
    return match.group(1)


def is_category_selected(html, category):
    """True if the given category's <option> is marked selected in the
    rendered <select id="category">."""
    return bool(re.search(rf'value="{re.escape(category)}"\s+selected', html))


VALID_FORM = {
    "amount": "42.50",
    "category": "Food",
    "date": "2024-05-15",
    "description": "Lunch",
}


def submit_expense(client, **overrides):
    data = dict(VALID_FORM, **overrides)
    return client.post("/expenses/add", data=data)


# --------------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------------- #

class TestAddExpenseAuthGuard:
    def test_get_add_expense_requires_login_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302, "Unauthenticated GET /expenses/add should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to the login page"

    def test_post_add_expense_requires_login_redirects_to_login(self, client):
        response = submit_expense(client)
        assert response.status_code == 302, "Unauthenticated POST /expenses/add should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to the login page"

    def test_post_add_expense_while_logged_out_does_not_insert_a_row(self, client):
        submit_expense(client)
        assert count_all_expenses() == 0, "No row should be created for an unauthenticated request"


# --------------------------------------------------------------------------- #
# GET renders the form
# --------------------------------------------------------------------------- #

class TestAddExpenseFormRendering:
    def test_get_add_expense_when_logged_in_returns_200_with_form(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = client.get("/expenses/add")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'id="amount"' in html
        assert 'id="category"' in html
        assert 'id="date"' in html
        assert 'id="description"' in html

    def test_get_add_expense_date_defaults_to_today(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        response = client.get("/expenses/add")
        html = response.get_data(as_text=True)

        assert get_input_value(html, "date") == today, "Date field should default to today's date"

    def test_get_add_expense_offers_all_fixed_categories(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = client.get("/expenses/add")
        html = response.get_data(as_text=True)

        for category in SPEC_CATEGORIES:
            assert f'value="{category}"' in html, f"Expected '{category}' to be an available category option"

    def test_get_add_expense_has_no_error_and_empty_amount_description(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = client.get("/expenses/add")
        html = response.get_data(as_text=True)

        assert "auth-error" not in html, "No error should be shown on a fresh GET"
        assert get_input_value(html, "amount") == ""
        assert get_input_value(html, "description") == ""


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #

class TestAddExpenseHappyPath:
    def test_valid_submission_creates_row_and_redirects_to_profile(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(client)

        assert response.status_code == 302, "A valid submission should redirect, not re-render the form"
        assert "/profile" in response.headers["Location"], "Should redirect to the profile page"

        rows = get_expenses_for_user(alice_id)
        assert len(rows) == 1, "Exactly one expense row should be created"
        row = rows[0]
        assert row["user_id"] == alice_id
        assert row["amount"] == pytest.approx(42.50)
        assert row["category"] == "Food"
        assert row["date"] == "2024-05-15"
        assert row["description"] == "Lunch"

    def test_valid_submission_appears_on_profile_page(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        submit_expense(client, description="DESC_NEW_EXPENSE", amount="99.99", category="Shopping")

        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "DESC_NEW_EXPENSE" in html, "New expense should appear in recent transactions"
        assert "Shopping" in html, "New expense's category should appear in the category breakdown"

    def test_optional_description_left_blank_still_succeeds(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(client, description="")

        assert response.status_code == 302, "A blank description should not block submission"
        rows = get_expenses_for_user(alice_id)
        assert len(rows) == 1, "The row should still be created with a blank description"
        assert rows[0]["description"] in (None, ""), "Blank description should be stored as None/empty"


# --------------------------------------------------------------------------- #
# Validation errors
# --------------------------------------------------------------------------- #

class TestAddExpenseAmountValidation:
    @pytest.mark.parametrize("bad_amount", ["", "0", "-10", "abc", "-0.01"])
    def test_invalid_amount_rerenders_form_with_error_and_creates_no_row(self, client, bad_amount):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(client, amount=bad_amount)
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Validation failure must re-render the form, not redirect"
        assert "auth-error" in html, f"Expected an inline error for amount={bad_amount!r}"
        assert count_all_expenses() == 0, f"No row should be created for invalid amount={bad_amount!r}"

    def test_invalid_amount_repopulates_other_submitted_fields(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(
            client, amount="not-a-number", category="Bills",
            date="2024-06-01", description="Repopulate me",
        )
        html = response.get_data(as_text=True)

        assert get_input_value(html, "amount") == "not-a-number"
        assert get_input_value(html, "date") == "2024-06-01"
        assert get_input_value(html, "description") == "Repopulate me"
        assert is_category_selected(html, "Bills")


class TestAddExpenseCategoryValidation:
    @pytest.mark.parametrize("bad_category", ["NotACategory", "food", "<script>", ""])
    def test_invalid_category_rerenders_form_with_error_and_creates_no_row(self, client, bad_category):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(client, category=bad_category)
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Validation failure must re-render the form, not redirect"
        assert "auth-error" in html, f"Expected an inline error for category={bad_category!r}"
        assert count_all_expenses() == 0, f"No row should be created for invalid category={bad_category!r}"

    def test_invalid_category_repopulates_other_submitted_fields(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(
            client, amount="15.00", category="NotACategory",
            date="2024-06-01", description="Keep me",
        )
        html = response.get_data(as_text=True)

        assert get_input_value(html, "amount") == "15.00"
        assert get_input_value(html, "date") == "2024-06-01"
        assert get_input_value(html, "description") == "Keep me"


class TestAddExpenseDateValidation:
    @pytest.mark.parametrize(
        "bad_date",
        ["not-a-date", "2024/06/01", "2024-13-40", "2024-02-30", ""],
    )
    def test_malformed_date_rerenders_form_with_error_and_creates_no_row(self, client, bad_date):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(client, date=bad_date)
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Validation failure must re-render the form, not redirect"
        assert "auth-error" in html, f"Expected an inline error for date={bad_date!r}"
        assert count_all_expenses() == 0, f"No row should be created for malformed date={bad_date!r}"

    def test_malformed_date_repopulates_other_submitted_fields(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_expense(
            client, amount="15.00", category="Health",
            date="not-a-date", description="Keep me too",
        )
        html = response.get_data(as_text=True)

        assert get_input_value(html, "amount") == "15.00"
        assert is_category_selected(html, "Health")
        assert get_input_value(html, "description") == "Keep me too"


# --------------------------------------------------------------------------- #
# user_id scoping / cross-user isolation
# --------------------------------------------------------------------------- #

class TestAddExpenseUserScoping:
    def test_inserted_expense_uses_session_user_id_never_client_supplied(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        bob_id = register_and_login(client, "Bob", "bob@example.com")

        # Log back in as Alice, then try to smuggle Bob's user_id in the POST body.
        login(client, "alice@example.com")
        response = submit_expense(client, user_id=str(bob_id))

        assert response.status_code == 302, "A valid submission with an extra user_id field should still succeed"

        alice_rows = get_expenses_for_user(alice_id)
        bob_rows = get_expenses_for_user(bob_id)

        assert len(alice_rows) == 1, "The expense must be attributed to the logged-in session user (Alice)"
        assert len(bob_rows) == 0, "A client-supplied user_id must never be trusted"

    def test_added_expense_never_appears_under_another_users_profile(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        bob_id = register_and_login(client, "Bob", "bob@example.com")

        # Bob adds an expense while logged in as Bob.
        submit_expense(client, description="DESC_BOB_ONLY", amount="77.00", category="Entertainment")

        # Switch to Alice and confirm isolation.
        login(client, "alice@example.com")
        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert "DESC_BOB_ONLY" not in html, "Bob's newly added expense must not leak into Alice's profile"
        assert count_expenses_for_user(alice_id) == 0
        assert count_expenses_for_user(bob_id) == 1


# --------------------------------------------------------------------------- #
# Static template check (Definition of Done: no hardcoded hex colours)
# --------------------------------------------------------------------------- #

class TestAddExpenseTemplateStaticRules:
    def test_expenses_add_template_has_no_hardcoded_hex_colours(self):
        template_path = (
            Path(__file__).resolve().parent.parent / "templates" / "expenses_add.html"
        )
        content = template_path.read_text(encoding="utf-8")

        hex_color_matches = re.findall(r"#[0-9a-fA-F]{3,8}\b", content)
        assert not hex_color_matches, (
            f"expenses_add.html must use CSS variables, not hardcoded hex colours; "
            f"found: {hex_color_matches}"
        )

    def test_expenses_add_template_extends_base(self):
        template_path = (
            Path(__file__).resolve().parent.parent / "templates" / "expenses_add.html"
        )
        content = template_path.read_text(encoding="utf-8")

        assert '{% extends "base.html" %}' in content, "expenses_add.html must extend base.html"

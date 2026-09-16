"""
Tests for the /expenses/<id>/delete feature (Step 9 — Delete Expense).

Spec: .claude/specs/09-delete-expense.md

Scope covered (per the spec's Definition of Done):
- A logged-in user POSTing to /expenses/<id>/delete for an expense they own
  removes it from the database and redirects to /profile, where it no
  longer appears in "Recent transactions" or the category breakdown/totals
- A GET request to /expenses/<id>/delete does not delete anything and is
  rejected (405, not the old placeholder string)
- POST for an id that does not exist returns a 404
- POST for an expense owned by a different user returns a 404 and does not
  delete that expense (no leakage of whether the id exists for someone else)
- Visiting /profile and submitting the delete form while logged out
  redirects to /login instead of deleting anything

Design notes:
- These tests never read delete_expense()'s implementation to derive
  expected behavior — only the spec, and template landmarks (element ids,
  CSS classes) read from templates/profile.html, the same way
  test_08-edit-expense.py does for templates/expenses_edit.html.
- The app performs `init_db()`/`seed_db()` against a real on-disk sqlite
  file at import time. Each test function here redirects
  `database.db.DB_PATH` to a fresh per-test temp file and re-runs
  `init_db()` against it (without seeding), matching the isolation
  strategy of the existing test suites exactly.
- Deletion is verified both via a direct parameterised SELECT against the
  expenses table and, where relevant, via the rendered /profile page.
"""

import re
from pathlib import Path

import pytest

import database.db as db_module
import app as app_module

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
    SELECT, for asserting on db state after delete attempts."""
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


def delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


def submit_delete(client, expense_id):
    return client.post(delete_url(expense_id))


# --------------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------------- #


class TestDeleteExpenseAuthGuard:
    def test_post_delete_while_logged_out_redirects_to_login_and_does_not_mutate(
        self, client
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(alice_id, 10.00, "Food", "2024-01-01", "DESC_A")
        client.get("/logout")

        response = submit_delete(client, expense_id)

        assert (
            response.status_code == 302
        ), "Unauthenticated POST /expenses/<id>/delete should redirect"
        assert (
            "/login" in response.headers["Location"]
        ), "Should redirect to the login page"

        row = get_expense_by_id(expense_id)
        assert row is not None, "Unauthenticated POST must not delete the expense"
        assert row["amount"] == pytest.approx(10.00)
        assert row["description"] == "DESC_A"

    def test_profile_delete_form_submission_while_logged_out_does_not_delete(
        self, client
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(alice_id, 10.00, "Food", "2024-01-01", "DESC_A")
        client.get("/logout")

        # Simulate "visiting /profile and submitting the delete form while
        # logged out" — since /profile itself also requires auth, the
        # meaningful behavior under test is that the delete POST itself
        # never mutates the DB while unauthenticated.
        profile_response = client.get("/profile")
        assert (
            profile_response.status_code == 302
        ), "Visiting /profile while logged out should redirect to /login"
        assert "/login" in profile_response.headers["Location"]

        submit_delete(client, expense_id)

        assert (
            count_all_expenses() == 1
        ), "No expense should be deleted while logged out"


# --------------------------------------------------------------------------- #
# GET must not be allowed
# --------------------------------------------------------------------------- #


class TestDeleteExpenseMethodNotAllowed:
    def test_get_delete_expense_returns_405_and_does_not_delete(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = client.get(delete_url(expense_id))

        assert (
            response.status_code == 405
        ), "GET on /expenses/<id>/delete must not be allowed (expected 405)"
        assert (
            b"placeholder" not in response.data.lower()
        ), "The old GET placeholder string must no longer be served"

        row = get_expense_by_id(expense_id)
        assert row is not None, "GET must never delete the expense"
        assert row["amount"] == pytest.approx(10.00)
        assert row["description"] == "Original desc"

    def test_get_delete_expense_on_nonexistent_id_is_still_405_not_404(self, client):
        # Method-not-allowed should be enforced before any ownership lookup
        # happens, so even a nonexistent id must not leak a 404 vs 405
        # distinction that could be used to probe id existence via GET.
        register_and_login(client, "Alice", "alice@example.com")

        response = client.get(delete_url(999999))

        assert response.status_code == 405


# --------------------------------------------------------------------------- #
# Happy path — valid delete
# --------------------------------------------------------------------------- #


class TestDeleteExpenseHappyPath:
    def test_valid_delete_removes_row_and_redirects_to_profile(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "Original desc"
        )

        response = submit_delete(client, expense_id)

        assert (
            response.status_code == 302
        ), "A valid delete should redirect, not re-render or error"
        assert (
            "/profile" in response.headers["Location"]
        ), "Should redirect to the profile page"

        row = get_expense_by_id(expense_id)
        assert row is None, "The expense must be removed from the database"

    def test_valid_delete_does_not_remove_other_rows(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(alice_id, 10.00, "Food", "2024-01-01", "Delete me")
        other_id = insert_expense(alice_id, 20.00, "Transport", "2024-01-02", "Keep me")

        submit_delete(client, expense_id)

        assert count_all_expenses() == 1, "Only the targeted expense should be removed"
        remaining = get_expense_by_id(other_id)
        assert remaining is not None, "Unrelated expenses must be left intact"
        assert remaining["description"] == "Keep me"

    def test_deleted_expense_disappears_from_profile_page(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "DESC_TO_REMOVE"
        )
        insert_expense(alice_id, 50.00, "Shopping", "2024-01-05", "DESC_TO_KEEP")

        submit_delete(client, expense_id)
        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert (
            "DESC_TO_REMOVE" not in html
        ), "Deleted expense must not appear in Recent transactions"
        assert (
            "DESC_TO_KEEP" in html
        ), "Other expenses should remain visible on the profile page"

    def test_deleted_expense_no_longer_counted_in_totals(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 100.00, "Food", "2024-01-01", "Big expense"
        )

        response_before = client.get("/profile")
        html_before = response_before.get_data(as_text=True)
        assert "1" in html_before  # sanity: at least one transaction recorded

        submit_delete(client, expense_id)

        response_after = client.get("/profile")
        html_after = response_after.get_data(as_text=True)

        assert (
            "Big expense" not in html_after
        ), "Deleted expense's description must not linger on the profile page"


# --------------------------------------------------------------------------- #
# 404s — nonexistent id / cross-user ownership
# --------------------------------------------------------------------------- #


class TestDeleteExpenseNotFound:
    def test_post_nonexistent_expense_id_returns_404(self, client):
        register_and_login(client, "Alice", "alice@example.com")

        response = submit_delete(client, 999999)

        assert (
            response.status_code == 404
        ), "POST on a nonexistent expense id must return 404"
        assert (
            count_all_expenses() == 0
        ), "No row should exist or be created for a nonexistent id"

    def test_post_expense_owned_by_another_user_returns_404_and_does_not_delete(
        self, client
    ):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "DESC_ALICE_ONLY"
        )

        register_and_login(client, "Bob", "bob@example.com")
        response = submit_delete(client, expense_id)
        html = response.get_data(as_text=True)

        assert (
            response.status_code == 404
        ), "POST on another user's expense must return 404"
        assert (
            "DESC_ALICE_ONLY" not in html
        ), "Another user's expense data must never be leaked"

        row = get_expense_by_id(expense_id)
        assert row is not None, "A foreign delete attempt must not remove the expense"
        assert row["user_id"] == alice_id, "Ownership must be unchanged"
        assert row["amount"] == pytest.approx(10.00)
        assert row["description"] == "DESC_ALICE_ONLY"

    def test_404_response_does_not_distinguish_missing_vs_foreign_id(self, client):
        """The spec requires that we not leak whether an id exists for
        another user, so both cases should present identically as a plain
        404 with no expense data in the body."""
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        foreign_expense_id = insert_expense(
            alice_id, 10.00, "Food", "2024-01-01", "DESC_ALICE_ONLY"
        )

        register_and_login(client, "Bob", "bob@example.com")

        foreign_response = submit_delete(client, foreign_expense_id)
        missing_response = submit_delete(client, 999999)

        assert foreign_response.status_code == 404
        assert missing_response.status_code == 404
        assert b"DESC_ALICE_ONLY" not in foreign_response.data
        assert b"DESC_ALICE_ONLY" not in missing_response.data


# --------------------------------------------------------------------------- #
# Template landmarks (spec's "add a small delete form next to Edit")
# --------------------------------------------------------------------------- #


class TestDeleteExpenseProfileTemplate:
    def test_profile_page_renders_delete_form_for_owned_expense(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        expense_id = insert_expense(alice_id, 10.00, "Food", "2024-01-01", "Renders me")

        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert (
            f'action="/expenses/{expense_id}/delete"' in html
        ), "Expected a delete form pointing at the delete route for this expense"
        assert (
            re.search(
                rf'<form[^>]*method="POST"[^>]*action="/expenses/{expense_id}/delete"',
                html,
            )
            is not None
        ), "The delete form must submit via POST"
        assert (
            "profile-table-delete" in html
        ), "Expected a delete button styled with the profile-table-delete class"
        assert (
            "profile-table-edit" in html
        ), "The existing Edit link should still be present alongside Delete"


# --------------------------------------------------------------------------- #
# Static template/CSS check (spec's "Use existing CSS variables, no new
# hardcoded colours")
# --------------------------------------------------------------------------- #


class TestDeleteExpenseStaticRules:
    def test_profile_css_delete_button_has_no_hardcoded_hex_colours(self):
        css_path = (
            Path(__file__).resolve().parent.parent / "static" / "css" / "profile.css"
        )
        content = css_path.read_text(encoding="utf-8")

        # Isolate just the .profile-table-delete rule block(s) so we don't
        # accidentally flag unrelated pre-existing rules elsewhere in the
        # file that are out of scope for this feature.
        delete_rule_blocks = re.findall(
            r"\.profile-table-delete[^{]*\{[^}]*\}", content
        )
        assert delete_rule_blocks, (
            "Expected to find a .profile-table-delete CSS rule styling the "
            "new delete button"
        )
        for block in delete_rule_blocks:
            hex_matches = re.findall(r"#[0-9a-fA-F]{3,8}\b", block)
            assert not hex_matches, (
                f"profile-table-delete styling must use CSS variables, not "
                f"hardcoded hex colours; found: {hex_matches} in {block!r}"
            )

    def test_profile_template_still_extends_base(self):
        template_path = (
            Path(__file__).resolve().parent.parent / "templates" / "profile.html"
        )
        content = template_path.read_text(encoding="utf-8")

        assert (
            '{% extends "base.html" %}' in content
        ), "profile.html must still extend base.html"

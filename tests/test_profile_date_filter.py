"""
Tests for the /profile date-range filter feature.

Spec: .claude/specs/06-date-filter-for-profile-page.md

Scope covered (per the spec's Definition of Done):
- GET /profile with no query params is unaffected by this feature (all-time data)
- GET /profile?start_date=...&end_date=... with a valid range scopes stats,
  transactions, and category breakdown to that inclusive range
- The filter form re-populates start_date/end_date after a valid submission
- "Clear filter" is only shown when a filter is actually active/applied
- start_date > end_date -> inline error + fallback to all-time data (no crash)
- malformed date -> inline error + fallback to all-time data (no crash)
- a valid range with zero matches shows the existing empty-state text, not an error
- filtering never leaks another user's expenses, even on overlapping ranges
- SQL-injection-shaped input in the date fields is treated as invalid input,
  never crashes the app, and never leaks data across users
- profile.html contains no hardcoded hex colours (CSS variables only)

Design notes:
- These tests never read app.py's SQL/query logic to derive expected values.
  Instead, each test seeds its own fully-controlled expense rows (unique,
  test-chosen descriptions/categories/amounts/dates) directly through the
  app's own `database.db.get_db()` connection (parameterised placeholders
  only), then asserts on the rendered page using landmarks read from
  templates/profile.html (CSS classes, labels, empty-state copy). This keeps
  assertions grounded in the documented contract rather than incidental
  seed-data values or SQL internals.
- The app performs `init_db()`/`seed_db()` against a real on-disk sqlite file
  at import time (module-level code in app.py, run once per test session).
  Each test function here redirects `database.db.DB_PATH` to a fresh
  per-test temp file and re-runs `init_db()` against it, so tests never share
  state and never depend on that first, real seeded database.
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
    assert resp.status_code == 302, "Login with freshly-registered credentials should succeed"

    db = db_module.get_db()
    row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    assert row is not None, "Expected the newly-registered user to exist in the DB"
    return row["id"]


def insert_expense(user_id, amount, category, date_str, description):
    """Insert one fully-controlled expense row using parameterised SQL."""
    db = db_module.get_db()
    db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date_str, description),
    )
    db.commit()
    db.close()


def get_stat_value(html, label):
    """Extract the value shown in a `.profile-stat-card` for the given label,
    e.g. get_stat_value(html, "Total spent") -> "₹150.00"."""
    pattern = (
        r'profile-stat-label">' + re.escape(label) + r'</span>\s*'
        r'<span class="profile-stat-value">([^<]*)</span>'
    )
    match = re.search(pattern, html)
    assert match, f"Could not find a '{label}' stat card in the rendered page"
    return match.group(1).strip()


def numeric_part(stat_value):
    """Strip any currency symbol/formatting, leaving just the numeric text
    (e.g. '₹150.00' -> '150.00'), so tests don't assume a specific currency
    symbol."""
    return re.sub(r"[^0-9.]", "", stat_value)


def get_input_value(html, field_name):
    """Extract the `value="..."` attribute of the named date input."""
    pattern = rf'id="{field_name}"[^>]*value="([^"]*)"'
    match = re.search(pattern, html)
    assert match, f"Could not find input '{field_name}' in the rendered page"
    return match.group(1)


# --------------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------------- #

class TestProfileAuthGuard:
    def test_profile_requires_login_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile should redirect"
        assert "/login" in response.headers["Location"], "Should redirect to the login page"

    def test_profile_with_filter_params_still_requires_login(self, client):
        """The auth guard must apply before any query-param parsing happens."""
        response = client.get("/profile?start_date=2024-01-01&end_date=2024-01-31")
        assert response.status_code == 302, "Unauthenticated /profile should redirect regardless of query params"
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------------- #
# No filter -> unaffected, all-time behavior
# --------------------------------------------------------------------------- #

class TestNoFilterIsAllTime:
    def test_no_query_params_shows_all_time_data(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 100.00, "Old Stuff", "2019-01-15", "DESC_OLD")
        insert_expense(user_id, 50.00, "New Stuff", "2030-06-20", "DESC_NEW")

        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "DESC_OLD" in html, "All-time view must include very old expenses"
        assert "DESC_NEW" in html, "All-time view must include very future expenses"
        assert numeric_part(get_stat_value(html, "Total spent")) == "150.00"
        assert get_stat_value(html, "Transactions") == "2"

    def test_no_query_params_has_no_error_and_no_clear_filter_link(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2024-01-01", "DESC_A")

        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert "auth-error" not in html, "No filter applied -> no inline error expected"
        assert "Clear filter" not in html, "No filter applied -> no Clear filter link expected"
        assert get_input_value(html, "start_date") == ""
        assert get_input_value(html, "end_date") == ""

    def test_empty_string_filter_params_behave_like_no_filter(self, client):
        """Blank ?start_date=&end_date= should be treated as 'no filter', not an error."""
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2024-01-01", "DESC_A")

        response = client.get("/profile?start_date=&end_date=")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "auth-error" not in html, "Blank filter fields should not surface a validation error"
        assert "DESC_A" in html


# --------------------------------------------------------------------------- #
# Valid range scopes stats / transactions / category breakdown
# --------------------------------------------------------------------------- #

class TestValidRangeScoping:
    def test_valid_range_scopes_transactions_and_stats(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        # In range: 2024-03-05 .. 2024-03-10
        insert_expense(user_id, 100.00, "InRangeCatA", "2024-03-05", "DESC_IN_1")
        insert_expense(user_id, 25.00, "InRangeCatB", "2024-03-10", "DESC_IN_2")
        # Out of range
        insert_expense(user_id, 999.00, "OutOfRangeCat", "2024-01-01", "DESC_OUT_BEFORE")
        insert_expense(user_id, 999.00, "OutOfRangeCat", "2024-12-31", "DESC_OUT_AFTER")

        response = client.get("/profile?start_date=2024-03-01&end_date=2024-03-31")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "DESC_IN_1" in html and "DESC_IN_2" in html, "In-range transactions must appear"
        assert "DESC_OUT_BEFORE" not in html, "Out-of-range transactions must not appear"
        assert "DESC_OUT_AFTER" not in html, "Out-of-range transactions must not appear"

        assert numeric_part(get_stat_value(html, "Total spent")) == "125.00"
        assert get_stat_value(html, "Transactions") == "2"
        assert get_stat_value(html, "Top category") == "InRangeCatA"

    def test_valid_range_is_inclusive_of_boundary_dates(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2024-05-01", "DESC_START_BOUNDARY")
        insert_expense(user_id, 10.00, "Food", "2024-05-31", "DESC_END_BOUNDARY")
        insert_expense(user_id, 10.00, "Food", "2024-04-30", "DESC_JUST_BEFORE")
        insert_expense(user_id, 10.00, "Food", "2024-06-01", "DESC_JUST_AFTER")

        response = client.get("/profile?start_date=2024-05-01&end_date=2024-05-31")
        html = response.get_data(as_text=True)

        assert "DESC_START_BOUNDARY" in html, "The start_date itself must be included"
        assert "DESC_END_BOUNDARY" in html, "The end_date itself must be included"
        assert "DESC_JUST_BEFORE" not in html
        assert "DESC_JUST_AFTER" not in html

    def test_valid_range_scopes_category_breakdown(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 40.00, "InRangeCategoryXYZ", "2024-07-10", "DESC_IN")
        insert_expense(user_id, 999.00, "OutOfRangeCategoryXYZ", "2024-01-10", "DESC_OUT")

        response = client.get("/profile?start_date=2024-07-01&end_date=2024-07-31")
        html = response.get_data(as_text=True)

        assert "InRangeCategoryXYZ" in html
        assert "OutOfRangeCategoryXYZ" not in html

    def test_valid_range_still_limits_to_five_most_recent_transactions(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        # Six in-range expenses on distinct dates; only the 5 most recent
        # should be listed per the existing "5 most recent" behavior.
        dates_and_descriptions = [
            ("2024-08-01", "DESC_D1_OLDEST"),
            ("2024-08-02", "DESC_D2"),
            ("2024-08-03", "DESC_D3"),
            ("2024-08-04", "DESC_D4"),
            ("2024-08-05", "DESC_D5"),
            ("2024-08-06", "DESC_D6_NEWEST"),
        ]
        for date_str, desc in dates_and_descriptions:
            insert_expense(user_id, 5.00, "Food", date_str, desc)

        response = client.get("/profile?start_date=2024-08-01&end_date=2024-08-31")
        html = response.get_data(as_text=True)

        assert "DESC_D1_OLDEST" not in html, "Only the 5 most recent in-range transactions should show"
        assert "DESC_D2" in html
        assert "DESC_D6_NEWEST" in html


# --------------------------------------------------------------------------- #
# Form pre-fill + Clear filter link
# --------------------------------------------------------------------------- #

class TestFilterFormState:
    def test_form_inputs_prefilled_after_valid_filter_submission(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2024-03-05", "DESC_IN")

        response = client.get("/profile?start_date=2024-03-01&end_date=2024-03-31")
        html = response.get_data(as_text=True)

        assert get_input_value(html, "start_date") == "2024-03-01"
        assert get_input_value(html, "end_date") == "2024-03-31"

    def test_clear_filter_link_shown_when_valid_filter_active(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2024-03-05", "DESC_IN")

        response = client.get("/profile?start_date=2024-03-01&end_date=2024-03-31")
        html = response.get_data(as_text=True)

        assert "Clear filter" in html, "Clear filter link should show when a valid filter is applied"

    def test_clear_filter_link_absent_when_no_filter_applied(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2024-03-05", "DESC_IN")

        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert "Clear filter" not in html


# --------------------------------------------------------------------------- #
# Invalid input: falls back to all-time data with an inline error, no crash
# --------------------------------------------------------------------------- #

class TestInvalidFilterFallsBackSafely:
    def test_start_after_end_shows_error_and_falls_back_to_all_time(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2020-01-01", "DESC_FAR_PAST")
        insert_expense(user_id, 20.00, "Food", "2030-01-01", "DESC_FAR_FUTURE")

        # start_date is after end_date
        response = client.get("/profile?start_date=2024-06-30&end_date=2024-06-01")
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Invalid range must not crash the app"
        assert "auth-error" in html, "An inline error should be shown for start > end"
        assert "DESC_FAR_PAST" in html, "Should fall back to showing all-time data"
        assert "DESC_FAR_FUTURE" in html, "Should fall back to showing all-time data"

    def test_malformed_date_shows_error_and_falls_back_to_all_time(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2020-01-01", "DESC_FAR_PAST")
        insert_expense(user_id, 20.00, "Food", "2030-01-01", "DESC_FAR_FUTURE")

        response = client.get("/profile?start_date=not-a-date&end_date=2024-06-30")
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "Malformed date must not crash the app"
        assert "auth-error" in html, "An inline error should be shown for a malformed date"
        assert "DESC_FAR_PAST" in html
        assert "DESC_FAR_FUTURE" in html

    @pytest.mark.parametrize(
        "start_date,end_date",
        [
            ("2024-02-30", "2024-03-01"),   # not a real calendar date
            ("2024/03/01", "2024-03-31"),   # wrong separator
            ("", "2024-03-31"),             # only one side supplied
        ],
    )
    def test_various_malformed_or_incomplete_inputs_do_not_crash(self, client, start_date, end_date):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2020-01-01", "DESC_FAR_PAST")

        response = client.get(f"/profile?start_date={start_date}&end_date={end_date}")

        assert response.status_code == 200, "Invalid/incomplete filter input must never crash the app"
        assert "DESC_FAR_PAST" in response.get_data(as_text=True), "Should fall back to all-time data"

    def test_sql_injection_shaped_date_input_does_not_crash_or_leak(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        bob_id = register_and_login(client, "Bob", "bob@example.com")
        insert_expense(alice_id, 10.00, "Food", "2024-03-05", "DESC_ALICE")
        insert_expense(bob_id, 999.00, "Secret", "2024-03-05", "DESC_BOB_SECRET")

        relogin = client.post("/login", data={"email": "alice@example.com", "password": "password123"})
        assert relogin.status_code == 302, "Re-login as alice must succeed before asserting her view"
        injection_payload = "2024-01-01' OR '1'='1"
        response = client.get(
            "/profile",
            query_string={"start_date": injection_payload, "end_date": "2024-12-31"},
        )
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "SQL-injection-shaped input must not crash the app"
        assert "DESC_ALICE" in html
        assert "DESC_BOB_SECRET" not in html, "Must never leak another user's data, even on bad input"


# --------------------------------------------------------------------------- #
# Valid range, zero matches -> existing empty-state, not an error
# --------------------------------------------------------------------------- #

class TestZeroMatchEmptyState:
    def test_valid_range_with_no_matching_expenses_shows_empty_state(self, client):
        user_id = register_and_login(client, "Alice", "alice@example.com")
        insert_expense(user_id, 10.00, "Food", "2024-01-01", "DESC_JAN")

        response = client.get("/profile?start_date=2024-06-01&end_date=2024-06-30")
        html = response.get_data(as_text=True)

        assert response.status_code == 200, "A valid, empty-result range must not crash the app"
        assert "auth-error" not in html, "Zero matches for a valid range is not an error state"
        assert "No transactions yet" in html
        assert "No expenses recorded yet" in html
        assert numeric_part(get_stat_value(html, "Total spent")) == "0.00"
        assert get_stat_value(html, "Transactions") == "0"

    def test_valid_range_with_no_matches_for_this_user_does_not_show_other_users_data(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        bob_id = register_and_login(client, "Bob", "bob@example.com")
        insert_expense(bob_id, 10.00, "Food", "2024-06-15", "DESC_BOB_IN_RANGE")

        relogin = client.post("/login", data={"email": "alice@example.com", "password": "password123"})
        assert relogin.status_code == 302, "Re-login as alice must succeed before asserting her view"
        response = client.get("/profile?start_date=2024-06-01&end_date=2024-06-30")
        html = response.get_data(as_text=True)

        assert "DESC_BOB_IN_RANGE" not in html
        assert "No transactions yet" in html


# --------------------------------------------------------------------------- #
# Cross-user isolation
# --------------------------------------------------------------------------- #

class TestFilterNeverLeaksOtherUsers:
    def test_overlapping_date_ranges_do_not_leak_between_users(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        bob_id = register_and_login(client, "Bob", "bob@example.com")

        # Same exact date, different users.
        insert_expense(alice_id, 15.00, "AliceCategory", "2024-09-10", "DESC_ALICE_SEP")
        insert_expense(bob_id, 500.00, "BobCategory", "2024-09-10", "DESC_BOB_SEP")

        relogin = client.post("/login", data={"email": "alice@example.com", "password": "password123"})
        assert relogin.status_code == 302, "Re-login as alice must succeed before asserting her view"
        response = client.get("/profile?start_date=2024-09-01&end_date=2024-09-30")
        html = response.get_data(as_text=True)

        assert "DESC_ALICE_SEP" in html
        assert "DESC_BOB_SEP" not in html
        assert "BobCategory" not in html
        assert numeric_part(get_stat_value(html, "Total spent")) == "15.00"

    def test_unfiltered_view_also_does_not_leak_other_users(self, client):
        alice_id = register_and_login(client, "Alice", "alice@example.com")
        bob_id = register_and_login(client, "Bob", "bob@example.com")

        insert_expense(alice_id, 15.00, "AliceCategory", "2024-09-10", "DESC_ALICE")
        insert_expense(bob_id, 500.00, "BobCategory", "2024-09-10", "DESC_BOB")

        relogin = client.post("/login", data={"email": "alice@example.com", "password": "password123"})
        assert relogin.status_code == 302, "Re-login as alice must succeed before asserting her view"
        response = client.get("/profile")
        html = response.get_data(as_text=True)

        assert "DESC_ALICE" in html
        assert "DESC_BOB" not in html


# --------------------------------------------------------------------------- #
# Static template check (Definition of Done: no hardcoded hex colours)
# --------------------------------------------------------------------------- #

class TestProfileTemplateStaticRules:
    def test_profile_template_has_no_hardcoded_hex_colours(self):
        template_path = (
            Path(__file__).resolve().parent.parent / "templates" / "profile.html"
        )
        content = template_path.read_text(encoding="utf-8")

        hex_color_matches = re.findall(r"#[0-9a-fA-F]{3,8}\b", content)
        assert not hex_color_matches, (
            f"profile.html must use CSS variables, not hardcoded hex colours; "
            f"found: {hex_color_matches}"
        )

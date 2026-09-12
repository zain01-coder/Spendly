# Spec: Date Filter for Profile Page

## Overview
Step 5 wired the `/profile` view up to real queries against the `users` and `expenses` tables, but those queries always cover a user's entire expense history — there's no way to narrow the profile view down to a specific time window. This step adds an optional date-range filter to `/profile`: a small form with "from" and "to" date inputs that, when submitted, scopes the summary stats, category breakdown, and recent-transactions table to expenses whose `date` falls within that range. With no filter applied, the page behaves exactly as it does today (all-time data).

## Depends on
- Step 1: Database setup (`expenses.date` column, stored as `YYYY-MM-DD` text)
- Step 3: Login + Logout (`session["user_id"]` must be set)
- Step 4: Profile Page (template/CSS and the `/profile` route already exist)
- Step 5: Backend Routes for Profile Page (`profile()` already pulls real data via `_get_profile_stats`, `_get_recent_transactions`, `_get_category_breakdown` — this step adds date-range scoping to those same helpers)

## Routes
- `GET /profile` — unchanged path, extended behavior — logged-in only
  - Accepts optional query params `start_date` and `end_date` (both `YYYY-MM-DD`)
  - When both are present and valid, scopes stats/transactions/categories to that inclusive range
  - When absent, behaves exactly as before (all-time data)
  - When present but invalid (malformed date, or `start_date` after `end_date`), ignores the filter, renders all-time data, and shows an inline error message

No other new routes.

## Database changes
No database changes. The existing `expenses.date` column (`TEXT`, `YYYY-MM-DD` format) is sufficient to filter on with `date BETWEEN ? AND ?`.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a small filter form above the "Recent transactions" card (or as its own card): two `<input type="date">` fields (`start_date`, `end_date`) and an "Apply" submit button, using `method="GET"` so the range shows up in the URL and survives a page refresh/bookmark
  - Pre-fill the inputs with the current `start_date`/`end_date` (if any) so the applied range is visible after submitting
  - Add a "Clear filter" link that points to plain `/profile` (no query params), shown only when a filter is active
  - Show the inline error message (from the invalid-range case above) near the filter form, styled consistently with the existing `.auth-error`-style pattern used elsewhere in the app
  - No changes to the stats row, transactions table, or category breakdown markup themselves — they keep rendering whatever `stats`/`transactions`/`categories` the view passes in, same as Step 5

## Files to change
- `app.py`:
  - `profile()` — read `start_date`/`end_date` from `request.args`, validate them, and pass the (possibly `None`) validated range into the three helper functions below; pass a `date_filter` context dict to the template (`start_date`, `end_date`, `error`) so it can re-populate the form and show any error
  - `_get_profile_stats(db, user_id, start_date=None, end_date=None)` — add `AND date BETWEEN ? AND ?` to the existing query only when a range is supplied
  - `_get_recent_transactions(db, user_id, start_date=None, end_date=None)` — same conditional filter; keep the existing `ORDER BY date DESC, id DESC LIMIT 5` behavior (still "5 most recent," just within the filtered range when one is applied)
  - `_get_category_breakdown(db, user_id, start_date=None, end_date=None)` — same conditional filter applied before the `GROUP BY`
- `templates/profile.html` — filter form, pre-filled values, clear-filter link, inline error display

## Files to create
None.

## New dependencies
No new dependencies. Validate/parse dates with `datetime.strptime(..., "%Y-%m-%d")`, already imported in `app.py`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — the date range must be bound with `?` placeholders, never string-formatted/concatenated into the SQL, including the `BETWEEN` clause
- Passwords hashed with werkzeug (unaffected by this step — no auth logic changes)
- Use CSS variables — never hardcode hex values in any template/CSS touched
- All templates extend `base.html`
- Validate both dates server-side even though `<input type="date">` constrains the client UI: reject malformed values and reject `start_date > end_date`, falling back to unfiltered (all-time) data with an error message rather than crashing or silently misbehaving
- Close the `db` connection before returning, matching the existing pattern in `profile()`
- Keep the three helper functions' existing signatures backward-compatible (`start_date`/`end_date` default to `None`, meaning "no filter") so nothing else calling them breaks
- Guard against division by zero in the category `percent` calculation exactly as Step 5 already does — a filtered range with zero matching expenses must not raise `ZeroDivisionError`
- Filtering must never leak another user's expenses — every query still filters by `user_id` first, with the date range as an additional `AND` condition

## Definition of done
- [ ] Visiting `/profile` with no query params shows the same all-time data as before this feature existed
- [ ] Visiting `/profile?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` with a valid range shows stats, transactions, and category breakdown scoped to only that range
- [ ] The filter form's inputs are pre-filled with the currently applied `start_date`/`end_date` after submitting
- [ ] A "Clear filter" link is visible when a filter is active and returns the page to `/profile` with no params
- [ ] Submitting a range where `start_date` is after `end_date` shows an inline error and falls back to unfiltered all-time data (no crash)
- [ ] Submitting a malformed date value shows an inline error and falls back to unfiltered all-time data (no crash)
- [ ] A date range with zero matching expenses shows the existing empty-state messaging (no transactions / no categories) instead of an error
- [ ] Applying a filter for one user never shows another user's expenses, even for overlapping date ranges
- [ ] No hex colour values appear in `profile.html` — only CSS variables
- [ ] All SQL queries touched in this step use parameterised placeholders

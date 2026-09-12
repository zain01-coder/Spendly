# Spec: Backend Routes for Profile Page

## Overview
Step 4 built the `/profile` view as a static mockup — the route renders `templates/profile.html` with hardcoded Python dicts/lists (a fake "Demo User", fixed stats, fixed transactions, fixed category breakdown). This step replaces that hardcoded data with real queries against the `users` and `expenses` tables, scoped to the logged-in user via `session["user_id"]`. The route, template, and CSS all already exist; only the data source changes.

## Depends on
- Step 1: Database setup (`users` and `expenses` tables must exist)
- Step 2: Registration (accounts must be creatable)
- Step 3: Login + Logout (`session["user_id"]` must be set on login)
- Step 4: Profile Page (template/CSS and the hardcoded `/profile` route must already exist — this step only swaps the data source)

## Routes
No new routes. `GET /profile` already exists (Step 4, `login_required`); this step changes its implementation to pull real data instead of hardcoded values.

## Database changes
No database changes. The existing `users` (id, name, email, password_hash, created_at) and `expenses` (id, user_id, amount, category, date, description, created_at) tables are sufficient for every value the template needs.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html` — add empty-state handling so a user with zero expenses doesn't see a broken or empty-looking page:
  - Recent transactions table: if `transactions` is empty, show a single "No transactions yet" row/message instead of an empty `<tbody>`
  - Category breakdown: if `categories` is empty, show a "No expenses recorded yet" message instead of an empty list
  - No other structural changes — the `user`, `stats`, `transactions`, `categories` context shapes stay the same as Step 4

## Files to change
- `app.py` — replace the hardcoded data in the `profile()` view with real queries:
  - `user`: `name`, `email` from the `users` row for `session["user_id"]`; `initials` derived from `name` (uppercase first letters of up to the first two words); `member_since` derived from the user's `created_at` (formatted like "March 2025")
  - `stats.total_spent`: sum of `amount` across the user's expenses, formatted `"₹{:.2f}"`; `0.00` if none
  - `stats.transaction_count`: count of the user's expenses
  - `stats.top_category`: the category with the highest total spend for the user; `"—"` if the user has no expenses
  - `transactions`: the user's 5 most recent expenses, ordered by `date DESC, id DESC`, each formatted into `date`, `description`, `category`, `amount` (`"₹{:.2f}"`), plus a `tone` assigned round-robin (`accent`, `accent-2`, `neutral` by row index % 3)
  - `categories`: one row per distinct category the user has spent in, with summed `amount`, `percent` of the user's total spend (rounded to nearest integer), ordered by amount descending, `tone` assigned round-robin the same way as transactions
- `templates/profile.html` — empty-state handling as described above

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use `get_db()` from `database/db.py` with raw `sqlite3`
- Parameterised queries only — every query filters by `user_id` using a `?` placeholder, never string-formatted/concatenated SQL
- Passwords hashed with werkzeug (unaffected by this step — no auth logic changes)
- Use CSS variables — never hardcode hex values in any template/CSS touched
- All templates extend `base.html`
- Close the `db` connection before returning, matching the existing `register`/`login` pattern in `app.py`
- Guard against division by zero when computing category `percent` (a user with $0 total must not raise `ZeroDivisionError`)
- Tone cycling (`accent` / `accent-2` / `neutral`) must work for any number of transactions/categories, not just the 3-4 rows Step 4 hardcoded

## Definition of done
- [ ] Visiting `/profile` without being logged in still redirects to `/login`
- [ ] Visiting `/profile` while logged in returns HTTP 200 and shows the logged-in user's real `name` and `email`, not "Demo User"
- [ ] `stats.total_spent` and `stats.transaction_count` match the actual sum/count of that user's rows in the `expenses` table
- [ ] `stats.top_category` matches the category with the highest total for that user
- [ ] The transaction history table shows only that user's expenses, most recent first, and never another user's data
- [ ] The category breakdown shows only that user's categories with correct totals and percentages
- [ ] Logging in as a second seeded/registered user with different expenses shows different profile data than the first user
- [ ] A newly registered user with zero expenses sees the empty-state message instead of an error or a blank/broken table
- [ ] No hex colour values appear in `profile.html` — only CSS variables
- [ ] All SQL queries in the `profile()` view use parameterised placeholders

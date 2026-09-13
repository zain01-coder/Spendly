# Spec: Add Expense

## Overview
Wires up expense creation for Spendly. The `/expenses/add` route currently
returns a plain placeholder string behind `@login_required`; this step
replaces it with a real GET (render form) / POST (validate + insert) view
that lets a logged-in user add a new row to the `expenses` table. On
success the user is redirected to `/profile`, where Step 5/6's real queries
will immediately reflect the new expense. Editing and deleting expenses
remain out of scope — they are Step 8 and Step 9.

## Depends on
- Step 1 (Database Setup) — requires the `expenses` table and `get_db()` /
  `init_db()` from `database/db.py`. They exist.
- Step 3 (Login + Logout) — requires `session["user_id"]` and the existing
  `login_required` decorator, already applied to `/expenses/add`.
- Step 5 (Backend Routes for Profile Page) — the profile page already reads
  real rows from `expenses`, so a newly inserted expense is visible there
  with no further changes needed.

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate the submitted amount/category/date/
  description, insert a new row into `expenses` scoped to
  `session["user_id"]`, then redirect to `/profile` — logged-in only

## Database changes
No database changes. The existing `expenses` table (`id`, `user_id`,
`amount`, `category`, `date`, `description`, `created_at`) already has
everything this form needs. `user_id` is set from `session["user_id"]`,
never from client input.

## Templates
- **Create:** `templates/expenses_add.html` — form extending `base.html`
  with fields:
  - `amount` — `type="number"`, `step="0.01"`, `min="0.01"`, required
  - `category` — `<select>` populated from the fixed category list already
    used elsewhere in the app (Food, Transport, Bills, Health,
    Entertainment, Shopping, Other)
  - `date` — `type="date"`, required, defaults to today's date
  - `description` — optional free-text input
  - Submit button, plus a link back to `/profile`
  - On validation failure, re-render this same template with an inline
    error (same `.auth-error`-style pattern used in `register.html` /
    `login.html`) and the submitted values re-populated in the fields
- **Modify:** none

## Files to change
- `app.py` — replace the stub `add_expense()` view with a function handling
  both GET and POST (`methods=["GET", "POST"]`):
  - GET: render `expenses_add.html` with today's date as the default
    `date` value
  - POST: read `amount`, `category`, `date`, `description` from
    `request.form`, validate them, insert via a parameterised `INSERT`
    scoped to `session["user_id"]`, close the connection, then redirect to
    `url_for('profile')`
  - Define the fixed category list as a module-level constant (next to
    `PROFILE_TONES`) so both this route and the template's `<select>`
    options share one source of truth

## Files to create
- `templates/expenses_add.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never string-format/concatenate SQL
- Passwords hashed with werkzeug (unaffected by this step — no auth logic
  changes)
- Use CSS variables — never hardcode hex values (reuse `style.css`
  variables and existing `.auth-*`/`.form-*` classes rather than
  introducing a new stylesheet, unless an existing class doesn't fit — in
  that case add rules to `static/css/style.css` using the existing
  variables, not a new page-specific CSS file)
- All templates extend `base.html`
- Validate on the server even though the form has `required`/`type`
  HTML attributes:
  - `amount` must parse as a positive number (> 0); reject empty, zero,
    negative, or non-numeric values
  - `category` must be one of the fixed category values; reject anything
    else (don't trust the submitted value just because it came from a
    `<select>`)
  - `date` must parse with `datetime.strptime(..., "%Y-%m-%d")`; reject
    malformed values
  - `description` is optional — store `None`/empty string if blank, don't
    require it
- On any validation failure, re-render `expenses_add.html` with `error`
  set and HTTP 200 (don't redirect), re-populating the fields the user
  already filled in so they don't lose their input
- Always insert with `user_id = session["user_id"]` — never accept a
  `user_id` from the form
- Close the `db` connection before returning, matching the existing
  pattern in `app.py`
- Do not touch `/expenses/<id>/edit` or `/expenses/<id>/delete` — they stay
  as placeholder stubs for Steps 8 and 9

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in returns HTTP 200 with a form,
      the date field defaulting to today
- [ ] Submitting a valid amount/category/date creates a new row in
      `expenses` with the correct `user_id`, then redirects to `/profile`
- [ ] The newly added expense appears in the profile page's recent
      transactions and is reflected in the summary stats and category
      breakdown
- [ ] Submitting a negative, zero, or non-numeric amount re-renders the
      form with an inline error and does not create a row
- [ ] Submitting an invalid/unlisted category re-renders the form with an
      inline error and does not create a row
- [ ] Submitting a malformed date re-renders the form with an inline error
      and does not create a row
- [ ] Submitting with the optional description left blank still succeeds
- [ ] Adding an expense as one logged-in user never appears under another
      user's `/profile`
- [ ] No hex colour values appear in `expenses_add.html` — only CSS
      variables
- [ ] `python app.py` starts without errors and existing routes
      (`/`, `/register`, `/login`, `/profile`, `/terms`, `/privacy`) are
      unaffected

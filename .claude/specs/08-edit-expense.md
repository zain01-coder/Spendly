# Spec: Edit Expense

## Overview
This feature replaces the placeholder `/expenses/<id>/edit` route with a real
edit flow: a logged-in user can open one of their existing expenses in a
pre-filled form, change its amount, category, date, and/or description, and
save the changes back to the database. It follows directly on from Step 7
(Add Expense), reusing the same validation rules and form styling, but for
an UPDATE instead of an INSERT — and it must enforce that a user can only
edit their own expenses.

## Depends on
- Step 01 — Database Setup (`users` and `expenses` tables, `get_db()`)
- Step 03 — Login/Logout (`session["user_id"]`, `login_required`)
- Step 07 — Add Expense (`EXPENSE_CATEGORIES`, `_validate_expense_form`,
  `expenses_add.html` form markup/styling to mirror)

## Routes
- `GET /expenses/<int:id>/edit` — load the expense owned by the current user
  and render it pre-filled in an edit form — logged-in
- `POST /expenses/<int:id>/edit` — validate and save changes to the expense,
  then redirect to `/profile` — logged-in

If the expense `id` does not exist, or exists but belongs to a different
`user_id`, respond with a 404 (do not reveal whether the id exists for
another user).

## Database changes
No database changes. The existing `expenses` table (`id`, `user_id`,
`amount`, `category`, `date`, `description`, `created_at`) already supports
updates via `UPDATE expenses SET ... WHERE id = ? AND user_id = ?`.

## Templates
- **Create:** `templates/expenses_edit.html` — same structure/classes as
  `expenses_add.html` (`auth-section` / `auth-container` / `auth-card` /
  `form-group` / `form-input` / `btn-submit`), pre-filled with the expense's
  current values, form posting to `url_for('edit_expense', id=expense.id)`,
  submit button reading "Save changes", and a "Back to profile" link.
- **Modify:** None required. `profile.html` already links recent
  transactions; wiring an "Edit" link/button there is optional polish and
  not required for this spec's definition of done.

## Files to change
- `app.py` — replace the placeholder `edit_expense` view with GET/POST
  logic; add a small helper to fetch one expense scoped to `user_id`
  (mirroring the ownership-check pattern, not the existing profile helpers).

## Files to create
- `templates/expenses_edit.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Reuse `_validate_expense_form` from `app.py` for validating submitted
  data (same rules as Add Expense: amount > 0, category in
  `EXPENSE_CATEGORIES`, valid date, description length limit)
- Every `SELECT`/`UPDATE` against `expenses` in this route must filter by
  `user_id = ?` as well as `id = ?` — never trust the URL `id` alone
- Return a 404 (`abort(404)`) for an expense that doesn't exist or isn't
  owned by the current user, rather than redirecting or leaking details
- On validation error, re-render `expenses_edit.html` with the submitted
  (not the original) values and the error message, same pattern as
  `add_expense`

## Definition of done
- [ ] Logging in and visiting `/expenses/<id>/edit` for an expense you own
      shows a form pre-filled with its current amount, category, date, and
      description
- [ ] Submitting the form with changed values updates the expense and
      redirects to `/profile`, where the updated values are visible
- [ ] Submitting the form with an invalid amount (e.g. `0` or `-5`) re-renders
      the edit form with an error and keeps the submitted values in the
      fields
- [ ] Submitting the form with an invalid/missing category or date shows the
      corresponding validation error and does not modify the database
- [ ] Visiting `/expenses/<id>/edit` for an id that does not exist returns a
      404
- [ ] Visiting `/expenses/<id>/edit` for an expense owned by a different
      user returns a 404 (not the expense's data)
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`

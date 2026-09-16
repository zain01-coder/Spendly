# Spec: Delete Expense

## Overview
This feature replaces the placeholder `/expenses/<id>/delete` route with a
real delete flow: a logged-in user can remove one of their own expenses from
the "Recent transactions" table on the profile page. It follows on from Step
7 (Add Expense) and Step 8 (Edit Expense), reusing the same ownership-check
pattern, but for a DELETE instead of an INSERT/UPDATE — and it must enforce
that a user can only delete their own expenses.

## Depends on
- Step 01 — Database Setup (`users` and `expenses` tables, `get_db()`)
- Step 03 — Login/Logout (`session["user_id"]`, `login_required`)
- Step 04/05 — Profile Page (`profile.html`, `/profile` route rendering
  recent transactions)
- Step 08 — Edit Expense (`_get_owned_expense` ownership-check pattern to
  mirror for the delete lookup)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense owned by the current
  user, then redirect to `/profile` — logged-in

The existing route is GET-only and only returns a placeholder string; it
must be changed to accept POST so deletion is not triggerable by a plain
link/GET request. If the expense `id` does not exist, or exists but belongs
to a different `user_id`, respond with a 404 (do not reveal whether the id
exists for another user).

## Database changes
No database changes. The existing `expenses` table (`id`, `user_id`,
`amount`, `category`, `date`, `description`, `created_at`) already supports
deletion via `DELETE FROM expenses WHERE id = ? AND user_id = ?`.

## Templates
- **Create:** None.
- **Modify:** `templates/profile.html` — in the "Recent transactions" table's
  actions cell (`profile-table-actions`), add a small delete form next to
  the existing "Edit" link: a `<form method="POST" action="{{ url_for('delete_expense', id=tx.id) }}">`
  containing a submit button styled to match the existing action link (e.g.
  a `profile-table-delete` class alongside the existing `profile-table-edit`
  class), so the row offers both "Edit" and "Delete".

## Files to change
- `app.py` — replace the placeholder `delete_expense` view (currently GET,
  returns a placeholder string) with a POST-only view that looks up the
  expense scoped to `user_id`, deletes it, commits, and redirects to
  `/profile`.
- `templates/profile.html` — add the delete form/button described above.
- `static/css/profile.css` — add styling for the new `profile-table-delete`
  button so it visually matches `profile-table-edit` (using existing CSS
  variables, not new hardcoded colors).

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Reuse the ownership-check pattern from `_get_owned_expense` (Step 08) to
  confirm the expense exists and belongs to `session["user_id"]` before
  deleting
- Every `SELECT`/`DELETE` against `expenses` in this route must filter by
  `user_id = ?` as well as `id = ?` — never trust the URL `id` alone
- Return a 404 (`abort(404)`) for an expense that doesn't exist or isn't
  owned by the current user, rather than redirecting or leaking details
- The delete action must only be reachable via `POST` (no GET handler), so
  it can't be triggered by crawling links or prefetching
- No JavaScript `confirm()` dialog is required for this step — a plain
  submit button is sufficient

## Definition of done
- [ ] Logging in and clicking "Delete" next to an expense you own on
      `/profile` removes it from the database and redirects back to
      `/profile`, where it no longer appears in "Recent transactions" or the
      category breakdown/totals
- [ ] Sending a GET request to `/expenses/<id>/delete` (e.g. visiting the URL
      directly) does not delete anything (405 or equivalent, not a
      placeholder string)
- [ ] Submitting the delete form for an id that does not exist returns a 404
- [ ] Submitting the delete form for an expense owned by a different user
      returns a 404 and does not delete that expense
- [ ] Visiting `/profile` and submitting a delete form while logged out
      redirects to `/login` instead of deleting anything

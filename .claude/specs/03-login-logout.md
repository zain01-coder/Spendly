# Spec: Login and Logout

## Overview
Wires up session-based authentication for Spendly. The `/login` route
currently only renders a form on GET (the template already posts to
`/login` and already has an `{% if error %}` block ready to use); this step
adds the POST handler that verifies the submitted email/password against
the `users` table from Step 1, starts a session on success, and turns
`/logout` from a placeholder string into a real session-clearing route.
It also adds a `login_required` guard and applies it to the existing
placeholder routes (`/profile`, `/expenses/add`, `/expenses/<id>/edit`,
`/expenses/<id>/delete`, `/logout`) so those stubs are only reachable while
signed in — without implementing their actual page content, which remains
out of scope for later steps. The navbar is updated to reflect signed-in
vs signed-out state so the feature is visibly testable end to end.

## Depends on
- Step 1 (Database Setup) — requires the `users` table and `get_db()` from
  `database/db.py`. They exist.
- Step 2 (Registration) — requires `password_hash` values written by
  `/register` to check logins against. It exists.

## Routes
- `POST /login` — verify email/password against `users`, start a session,
  redirect to `/profile` — public
- `GET /login` — unchanged, already renders `login.html`
- `GET /logout` — clear the session, redirect to `/login` — logged-in only

No other new routes. `/profile`, `/expenses/add`, `/expenses/<id>/edit`,
`/expenses/<id>/delete` keep their existing placeholder response bodies —
only a `login_required` guard is added in front of them.

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email`,
`password_hash`) already has everything login needs.

## Templates
- **Create:** none
- **Modify:**
  - `templates/base.html` — navbar currently always shows "Sign in" /
    "Get started". Change it to check `session.get('user_id')`: signed out
    keeps the current two links; signed in shows a link to `/profile`
    (e.g. the user's name) and a "Sign out" link to `/logout` instead.
  - `templates/login.html` — no structural changes; it already posts to
    `/login` and already renders `{{ error }}` via the `auth-error` div,
    which the new POST handler will populate on invalid credentials.

## Files to change
- `app.py`:
  - Set `app.secret_key` (required for Flask sessions) — a hardcoded dev
    value is fine at this stage, consistent with the rest of the app not
    yet having environment-based config.
  - Add a `login_required` decorator (redirects to `/login` if
    `session.get('user_id')` is missing).
  - Replace the stub `login()` view with a function handling both GET and
    POST (`methods=["GET", "POST"]`).
  - Replace the stub `logout()` view with one that pops `user_id` from the
    session and redirects to `/login`; decorate it with `@login_required`.
  - Decorate `/profile`, `/expenses/add`, `/expenses/<int:id>/edit`,
    `/expenses/<int:id>/delete` with `@login_required`, leaving their
    existing placeholder return values untouched.
- `templates/base.html` — conditional navbar links described above.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting/f-strings to
  build SQL
- Passwords hashed with werkzeug — use
  `werkzeug.security.check_password_hash` against the stored
  `password_hash`; never compare plaintext passwords
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Validate on the server: email and password both non-empty before
  querying
- Look up the user by email first; if no row matches, or
  `check_password_hash` fails, re-render `login.html` with a single
  generic error (e.g. "Invalid email or password.") and HTTP 200 — do not
  reveal whether the email exists
- On successful login, store only `session['user_id']` (the integer id) —
  never store the password or password hash in the session
- `login_required` must redirect unauthenticated requests to `/login`,
  not raise an error or return a placeholder string
- Do not implement the actual content of `/profile` or the `/expenses/*`
  routes — they keep their current placeholder strings, only gated behind
  login now
- Do not add any new database tables/columns — sessions are server-side
  Flask sessions, not persisted to SQLite

## Definition of done
- [ ] Submitting the login form with the seeded demo account
      (`demo@spendly.com` / `demo123`) redirects to `/profile`
- [ ] Submitting the login form with a wrong password re-renders
      `login.html` with an inline error and does not start a session
- [ ] Submitting the login form with an email that doesn't exist
      re-renders `login.html` with the same inline error (no hint about
      which field was wrong)
- [ ] After logging in, the navbar shows a "Sign out" link instead of
      "Sign in" / "Get started"
- [ ] Visiting `/profile` while logged out redirects to `/login`
- [ ] Visiting `/profile` while logged in returns the existing placeholder
      response (unchanged content)
- [ ] Visiting `/logout` while logged in clears the session and redirects
      to `/login`; the navbar reverts to the signed-out state
- [ ] Visiting `/logout` while logged out redirects to `/login` rather
      than erroring
- [ ] `python app.py` starts without errors and existing routes
      (`/`, `/register`, `/terms`, `/privacy`) are unaffected

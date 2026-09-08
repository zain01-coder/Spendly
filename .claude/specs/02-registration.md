# Spec: Registration

## Overview
Wires up account creation for Spendly. The `/register` route currently only
renders a form on GET; this step adds the POST handler that validates the
submitted data, hashes the password, and inserts a new row into the `users`
table created in Step 1. Session/login logic and `/logout` are explicitly
out of scope here — they belong to the login/logout step that follows and
consumes the `password_hash` this step writes. On success the user is sent
to `/login` to sign in with their new credentials.

## Depends on
- Step 1 (Database Setup) — requires the `users` table and `get_db()` /
  `init_db()` from `database/db.py` to already exist. They do.

## Routes
- `POST /register` — validate the submitted name/email/password, hash the
  password, insert a new user, then redirect to `/login` — public
- `GET /register` — unchanged, already renders `register.html`

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email`,
`password_hash`, `created_at`) already has everything registration needs.
`email` is already `UNIQUE NOT NULL`, so duplicate-email protection is
enforced at the DB level as well as validated in the route.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — no structural changes; it already posts to
    `/register` and already renders `{{ error }}` via the `auth-error` div,
    which the new POST handler will populate on validation/duplicate-email
    failures.
  - `templates/login.html` — add a small success banner (reusing the
    existing `.auth-error`-style block, or a new `.auth-success` class using
    CSS variables) shown when the redirect includes `?registered=1`, e.g.
    "Account created — sign in below."

## Files to change
- `app.py` — replace the stub `register()` view with a function handling
  both GET and POST (`methods=["GET", "POST"]`)
- `templates/login.html` — render the post-registration success message

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting/f-strings to
  build SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` before
  insert; never store or log plaintext passwords
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Validate on the server even though the form has `required`/`type=email`
  HTML attributes (don't trust client-side validation alone):
  - name, email, password all non-empty
  - password is at least 8 characters (matches the placeholder text already
    in `register.html`)
  - email not already registered — catch the case yourself with a `SELECT`
    before inserting (clearer error message) and still handle the
    `sqlite3.IntegrityError` from the `UNIQUE` constraint as a fallback
- On any validation failure, re-render `register.html` with `error` set and
  HTTP 200 (don't redirect) so the user doesn't lose the ability to see
  the message and correct the form
- Do not add session/login logic, `session[...]` writes, or touch `/logout`
  — that is the next step's responsibility

## Definition of done
- [ ] Submitting the register form with a new name/email/password creates a
      row in `users` with a hashed (not plaintext) password
- [ ] After a successful submission, the browser is redirected to `/login`
      and a success message is visible on the login page
- [ ] Submitting with an email that already exists re-renders
      `register.html` with an inline error and does not create a duplicate
      row
- [ ] Submitting with a password under 8 characters re-renders
      `register.html` with an inline error and does not create a row
- [ ] Submitting with a missing name/email/password re-renders
      `register.html` with an inline error and does not create a row
- [ ] `GET /register` still renders the empty form as before
- [ ] `python app.py` starts without errors and existing routes
      (`/`, `/login`, `/terms`, `/privacy`) are unaffected

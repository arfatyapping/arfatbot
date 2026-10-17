# Auto Welcome Bot — Premium Demo Web App

A mobile-first Flask + SQLite dashboard with a purple neon UI, account-connection explainer, configuration editor, message templates, preview, statistics, logs, authentication, CSRF checks, and security headers.

## Important Instagram compatibility note

This project **does not log in to Instagram, collect Instagram passwords/session IDs/cookies, or send real Instagram messages**. Delivery is explicitly simulated in demo mode. Instagram's official APIs have eligibility, permission, account-type, and messaging-scope requirements; private group-chat welcome automation is not assumed to be supported. Do not add unofficial private APIs or scraping. Review Meta's current official documentation and app review requirements before implementing any live integration.

The Account Connection page links to official Meta developer resources and clearly explains that no account is connected. The app does not pretend to have a live OAuth integration.

## Requirements

- Python 3.10+
- pip

## Run locally

1. Extract the ZIP and enter the project folder.
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
   Android/Termux may use `python -m venv .venv` if venv support is installed.
3. Activate it:
   - Linux/macOS: `source .venv/bin/activate`
   - Windows: `.venv\\Scripts\\activate`
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Copy `.env.example` to `.env`. Export its values into your shell, or use a dotenv loader of your choice. At minimum set:
   ```bash
   export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
   export ADMIN_USERNAME="your-admin-name"
   export ADMIN_PASSWORD="a-long-unique-password-12chars-minimum"
   ```
   On PowerShell, use `$env:ADMIN_USERNAME="your-admin-name"` and `$env:ADMIN_PASSWORD="your-long-password"`.
6. Start the app:
   ```bash
   python app.py
   ```
7. Open `http://127.0.0.1:5000`.

The first run creates the account only when both `ADMIN_USERNAME` and `ADMIN_PASSWORD` are supplied and the password is at least 12 characters. If you start without them, the database will not contain a login user. Set them and restart to initialize the account.

## Deploy behind HTTPS

Use a production WSGI server such as Gunicorn behind a reverse proxy:
```bash
pip install gunicorn
export SECRET_KEY="your-random-secret"
export ADMIN_USERNAME="your-admin-name"
export ADMIN_PASSWORD="your-unique-long-password"
export COOKIE_SECURE=1
gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```
Configure your reverse proxy to serve HTTPS and forward requests to Gunicorn. Keep `.env`, the SQLite database, and backups private. Never expose the SQLite file publicly. Use a managed database and secrets manager for multi-user production deployments.

## Included functionality

- Sign-in with hashed passwords; server-side session and expiration.
- CSRF token validation on POST requests.
- Secure response headers and basic request size limit.
- Configuration persistence in SQLite.
- Message editor with `{username}` and `{group_name}` live preview.
- Template create, set-default, and delete actions.
- Dashboard counters, activity logs, status display, and demo delivery simulation.
- Explicit demo labeling; simulated delivery never sends Instagram messages.
- No collection or browser storage of Instagram passwords, session cookies, or raw session IDs.

## Test checklist

- Sign in and sign out.
- Navigate Dashboard / Configuration / Templates / Connection / Statistics.
- Save configuration and refresh to confirm persistence.
- Create a template, set it as default, and delete it.
- Preview placeholders in the editor.
- Run a demo delivery and confirm the activity log updates.
- Try invalid delay/check-interval values and an empty message.
- Confirm Connection page says no account is connected.

## Notes

This is a single-admin starter project, not a hardened multi-tenant SaaS. Before opening it to public users, add rate limiting, password reset, email verification, audit-log retention controls, database migrations/backups, and deployment monitoring. The demo database stores only application configuration and activity records; it does not store Instagram secrets.

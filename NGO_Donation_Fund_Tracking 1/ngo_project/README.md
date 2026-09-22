<!-- Project overview, setup instructions, and operational notes. -->
# NGO Donation Fund Tracking System

A Flask + MySQL web application for tracking donors, donations (across
multiple payment modes), project-wise fund allocation, expenses, and
generating printable donation receipts and reports.

## Features

- **Admin login** with hashed passwords (session-based auth)
- **Dashboard** — total donors, total donations, total expenses, fund
  balance, active projects, recent activity
- **Donors** — add / edit / delete / search donor records
- **Donations** — record donations against a donor and optionally a
  project, with payment mode (**Online, Cheque, Bank Transfer, Cash**),
  auto-generated receipt numbers, and a printable receipt page
- **Projects** — create projects with a fundraising target; each project
  card shows raised vs. spent vs. balance with a progress bar
- **Expenses** — record project expenses; the form shows the project's
  current fund balance so overspending is visible before you save
- **Reports** — Chart.js visuals: donations by payment mode, monthly
  donation trend, project-wise raised vs. spent, plus a top-donors table

## Tech Stack

| Layer          | Technology                     |
|----------------|---------------------------------|
| Frontend       | HTML, CSS, vanilla JavaScript   |
| Backend        | Python (Flask)                  |
| Database       | MySQL                           |
| Data/Reporting | SQL aggregation + Chart.js       |
| Version Control| Git / GitHub                    |

## Project Structure

```
NGO_Donation_Fund_Tracking/
│
├── app.py                  # Flask app: routes, auth, all CRUD logic
├── config.py                # DB connection & app configuration
├── requirements.txt
│
├── database/
│   └── ngo_database.sql     # Schema + seed data (admin user, sample data)
│
├── templates/
│   ├── base.html             # Shared layout (sidebar, flashes)
│   ├── _flashes.html         # Flash-message partial
│   ├── login.html
│   ├── dashboard.html
│   ├── donors.html
│   ├── donations.html
│   ├── projects.html
│   ├── expenses.html
│   ├── reports.html
│   └── receipt.html
│
├── static/
│   ├── css/style.css
│   └── js/script.js
│
└── README.md
```

## Setup

### 1. Create the database

Make sure MySQL is installed and running, then:

```bash
mysql -u root -p < database/ngo_database.sql
```

This creates the `ngo_fund_tracking` database, all tables, and seeds
3 sample projects and 3 sample donors. **No admin account is seeded** —
create your own via the signup page or the CLI helper below.

### 2. Configure the connection

`config.py` reads from environment variables (with sensible local
defaults). Set these if your MySQL setup differs from `root` @
`localhost` with no password:

```bash
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=yourpassword
export MYSQL_DB=ngo_fund_tracking
export SECRET_KEY=some-random-secret-string
```

### 3. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run the app

```bash
python app.py
```

Visit **http://localhost:5000** and click **"Create an account"** on the
login page to sign up as a new staff/admin with your own email and
password — there is no default/seeded login.

Login is by **email + password** — any admin/staff member can sign in with
their own Gmail address once an account exists for it, either by signing up
through the app or via the CLI helper below. This is plain email/password
authentication, not "Sign in with Google" OAuth — no Google account access is
requested.

### 5. (Optional) Create/reset an admin account from the CLI

```bash
python app.py create-admin yourname@gmail.com yourpassword "Your Full Name"
```

## Notes on the fund-tracking model

- Every **donation** is recorded against a donor and, optionally, a
  **project**. Donations without a project are treated as unearmarked
  "General Fund" contributions.
- Every **expense** is recorded against a project.
- A project's **fund balance** = (sum of its donations) − (sum of its
  expenses). This is computed live from the `donations` and `expenses`
  tables rather than stored, so it's always accurate.
- Each donation gets an auto-generated receipt number in the form
  `NGO-RCPT-YYYYMMDD-NNNN`, viewable/printable from the Donations page.

## Security notes for production use

- Change `SECRET_KEY` before deploying.
- The `/signup` page currently lets **anyone** create an account with no
  approval step — fine for an internal tool on a trusted network, but for a
  public-facing deployment you should gate it (invite-only codes, email
  verification, or an admin-approval step) before going live.
- Run behind HTTPS; set `SESSION_COOKIE_SECURE = True` in `config.py`.
- Consider adding CSRF protection (e.g. `Flask-WTF`) for the forms.
- Restrict MySQL user privileges to only what the app needs.

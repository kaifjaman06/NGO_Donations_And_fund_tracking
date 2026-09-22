# ============================================
# NGO Fund Tracking Flask application
# Handles login, dashboard, donations, expenses,
# projects, receipts, and financial reporting.
# ============================================
import functools
import re
import secrets
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
import mysql.connector
from mysql.connector import Error as MySQLError
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)
from flask.json.provider import DefaultJSONProvider
from werkzeug.security import check_password_hash, generate_password_hash

# Import the project configuration and database settings.
from config import Config

# Regex used for validating email addresses in the login and signup flows.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# Convert text input to a safe lowercase email string for database checks.
def normalize_email(value):
    return (value or "").strip().lower()


# Verify that the supplied email address matches the application format.
def is_valid_email(value):
    return bool(EMAIL_RE.fullmatch(normalize_email(value)))


# Validate money inputs and reject zero or negative values unless explicitly allowed.
def validate_amount(value, field_name, *, allow_zero=False):
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")

    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a valid number.")

    if allow_zero:
        if amount < 0:
            raise ValueError(f"{field_name} cannot be negative.")
    elif amount <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")

    return amount


# Custom JSON provider so Decimal values and dates can be safely converted to JSON.
class NGOJSONProvider(DefaultJSONProvider):
    """Serializes Decimal (MySQL numeric columns) and dates as plain
    JSON-friendly values, so `|tojson` works on raw DB rows in templates."""

    @staticmethod
    def default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return DefaultJSONProvider.default(obj)


# Create the Flask app instance and attach the custom JSON provider.
app = Flask(__name__)
app.config.from_object(Config)
app.json = NGOJSONProvider(app)

# Database helpers keep connection handling in one place for all routes.
def get_db():
    """Open a fresh MySQL connection. Closed explicitly after each use."""
    return mysql.connector.connect(
        host=app.config["MYSQL_HOST"],
        port=app.config["MYSQL_PORT"],
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        database=app.config["MYSQL_DB"],
    )


# Run SQL statements and return rows as dictionaries for the rest of the app.
def query_db(sql, params=None, fetchone=False, commit=False):
    """Run a query and return results as dicts. Handles commit for writes."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params or ())
        if commit:
            conn.commit()
            last_id = cur.lastrowid
            return last_id
        rows = cur.fetchone() if fetchone else cur.fetchall()
        return rows
    finally:
        cur.close()
        conn.close()
# Protect routes so only logged-in admin users can access them.
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# Generate and validate the session token before each request to protect forms.
@app.before_request
def ensure_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)

    if request.method == "POST":
        token = request.form.get("csrf_token")
        if token != session.get("csrf_token"):
            abort(400, description="Invalid CSRF token.")


# Share the current admin name with all templates for navigation and headers.
@app.context_processor
def inject_user():
    return {"current_admin": session.get("admin_name")}


# Public home page for the NGO landing experience.
@app.route("/", methods=["GET"])
def index():
    featured_projects = query_db("""
        SELECT p.project_id, p.project_name, p.description, p.target_amount, p.status,
               COALESCE(d.total, 0) AS raised,
               COALESCE(e.total, 0) AS spent
        FROM projects p
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM donations GROUP BY project_id) d
               ON d.project_id = p.project_id
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM expenses GROUP BY project_id) e
               ON e.project_id = p.project_id
        WHERE p.status = 'Active'
        ORDER BY raised DESC, p.created_at DESC
        LIMIT 3
    """)

    total_donors = query_db("SELECT COUNT(*) c FROM donors", fetchone=True)["c"]
    total_donations = query_db("SELECT COALESCE(SUM(amount),0) s FROM donations", fetchone=True)["s"]
    total_expenses = query_db("SELECT COALESCE(SUM(amount),0) s FROM expenses", fetchone=True)["s"]
    balance = float(total_donations) - float(total_expenses)

    return render_template(
        "home.html",
        featured_projects=featured_projects,
        total_donors=total_donors,
        total_donations=total_donations,
        total_expenses=total_expenses,
        balance=balance,
    )


# Admin login page and authentication flow.
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")

        if not is_valid_email(email):
            flash("Please enter a valid email address.", "danger")
            return render_template("login.html", email=email)

        try:
            admin = query_db(
                "SELECT * FROM admin WHERE email = %s", (email,), fetchone=True
            )
        except MySQLError as e:
            flash(f"Database error: {e}", "danger")
            return render_template("login.html", email=email)

        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["admin_id"]
            session["admin_name"] = admin["full_name"] or admin["username"]
            flash(f"Welcome back, {session['admin_name']}!", "success")
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# Register a new admin account for the NGO system.
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []
        if not full_name:
            errors.append("Please enter your name.")
        if not is_valid_email(email):
            errors.append("Please enter a valid email address.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if not errors:
            try:
                existing = query_db(
                    "SELECT admin_id FROM admin WHERE email = %s", (email,), fetchone=True
                )
                if existing:
                    errors.append("An account with that email already exists. Try logging in instead.")
            except MySQLError as e:
                errors.append(f"Database error: {e}")

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template("signup.html", full_name=full_name, email=email)

        try:
            pw_hash = generate_password_hash(password)
            query_db(
                "INSERT INTO admin (username, email, password_hash, full_name) VALUES (%s, %s, %s, %s)",
                (email, email, pw_hash, full_name),
                commit=True,
            )
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("login"))
        except MySQLError as e:
            flash(f"Could not create account: {e}", "danger")
            return render_template("signup.html", full_name=full_name, email=email)

    return render_template("signup.html")


# End the current admin session and redirect back to the login page.
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))
# Dashboard aggregates the current financial and project totals.
@app.route("/dashboard")
@login_required
def dashboard():
    total_donors = query_db("SELECT COUNT(*) c FROM donors", fetchone=True)["c"]
    total_donations = query_db(
        "SELECT COALESCE(SUM(amount),0) s FROM donations", fetchone=True
    )["s"]
    total_expenses = query_db(
        "SELECT COALESCE(SUM(amount),0) s FROM expenses", fetchone=True
    )["s"]
    active_projects = query_db(
        "SELECT COUNT(*) c FROM projects WHERE status = 'Active'", fetchone=True
    )["c"]

    balance = float(total_donations) - float(total_expenses)

    recent_donations = query_db("""
        SELECT d.donation_id, d.amount, d.donation_date, d.payment_mode,
               dn.name AS donor_name, p.project_name
        FROM donations d
        JOIN donors dn ON dn.donor_id = d.donor_id
        LEFT JOIN projects p ON p.project_id = d.project_id
        ORDER BY d.donation_date DESC, d.donation_id DESC
        LIMIT 8
    """)

    project_funds = query_db("""
        SELECT p.project_id, p.project_name, p.target_amount, p.status,
               COALESCE(don.total, 0) AS raised,
               COALESCE(exp.total, 0) AS spent
        FROM projects p
        LEFT JOIN (
            SELECT project_id, SUM(amount) AS total
            FROM donations GROUP BY project_id
        ) AS don ON don.project_id = p.project_id
        LEFT JOIN (
            SELECT project_id, SUM(amount) AS total
            FROM expenses GROUP BY project_id
        ) AS exp ON exp.project_id = p.project_id
        ORDER BY p.created_at DESC
    """)

    return render_template(
        "dashboard.html",
        total_donors=total_donors,
        total_donations=total_donations,
        total_expenses=total_expenses,
        active_projects=active_projects,
        balance=balance,
        recent_donations=recent_donations,
        project_funds=project_funds,
    )


# Donation landing form used to add a donor and record a contribution.
@app.route("/donate-now", methods=["GET", "POST"])
@login_required
def donate_now():
    donor_list = query_db("SELECT donor_id, name, email FROM donors ORDER BY name")
    project_list = query_db("SELECT project_id, project_name FROM projects ORDER BY project_name")

    if request.method == "POST":
        form = request.form
        donor_name = (form.get("donor_name") or "").strip()
        if not donor_name:
            flash("Donor name is required before submitting a donation.", "danger")
            return redirect(url_for("donate_now"))

        try:
            amount = validate_amount(form.get("amount"), "Donation amount")
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("donate_now"))

        donor_id = form.get("donor_id")
        if not donor_id:
            donor_email = (form.get("donor_email") or "").strip() or None
            donor_phone = (form.get("donor_phone") or "").strip() or None
            donor_pan = (form.get("donor_pan") or "").strip() or None
            existing_donor = query_db(
                "SELECT donor_id FROM donors WHERE email=%s OR phone=%s LIMIT 1",
                (donor_email, donor_phone),
                fetchone=True,
            )
            if existing_donor:
                donor_id = existing_donor["donor_id"]
            else:
                donor_id = query_db(
                    "INSERT INTO donors (name, email, phone, donor_type, pan_number) VALUES (%s, %s, %s, %s, %s)",
                    (
                        donor_name,
                        donor_email,
                        donor_phone,
                        "Individual",
                        donor_pan,
                    ),
                    commit=True,
                )

        receipt_no = generate_receipt_no()
        payment_service = (form.get("payment_service") or form.get("payment_mode") or "UPI").strip()

        valid_payment_modes = {
            "UPI": "Online",
            "Razorpay": "Online",
            "Stripe": "Online",
            "PayPal": "Online",
            "Debit Card": "Online",
            "Credit Card": "Online",
            "Bank Transfer": "Bank Transfer",
            "Cash": "Cash",
            "Cheque": "Cheque",
            "Online": "Online",
        }
        payment_mode = valid_payment_modes.get(payment_service, "Online")

        try:
            donation_id = query_db(
                """INSERT INTO donations (donor_id, project_id, amount, payment_mode,
                   transaction_reference, donation_date, receipt_no, remarks)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    donor_id,
                    form.get("project_id") or None,
                    amount,
                    payment_mode,
                    (form.get("transaction_reference") or "").strip() or None,
                    form.get("donation_date") or date.today().isoformat(),
                    receipt_no,
                    (form.get("remarks") or "").strip() or None,
                ),
                commit=True,
            )
            flash(f"Thank you! Your donation of ₹{amount} via {payment_service} was recorded successfully.", "success")
            return redirect(url_for("view_receipt", donation_id=donation_id))
        except MySQLError as e:
            flash(f"Could not record donation: {e}", "danger")
            return redirect(url_for("donate_now"))

    total_donors = query_db("SELECT COUNT(*) c FROM donors", fetchone=True)["c"]
    total_donations = query_db("SELECT COALESCE(SUM(amount),0) s FROM donations", fetchone=True)["s"]
    active_projects = query_db("SELECT COUNT(*) c FROM projects WHERE status = 'Active'", fetchone=True)["c"]
    balance = float(total_donations) - float(query_db("SELECT COALESCE(SUM(amount),0) s FROM expenses", fetchone=True)["s"])
    donation_summary = query_db("""
        SELECT payment_mode, COALESCE(SUM(amount),0) AS total
        FROM donations
        GROUP BY payment_mode
        ORDER BY total DESC
        LIMIT 4
    """)
    donation_summary = {
        "labels": [row["payment_mode"] for row in donation_summary],
        "values": [float(row["total"]) for row in donation_summary],
    }

    return render_template(
        "donate_now.html",
        donor_list=donor_list,
        project_list=project_list,
        total_donors=total_donors,
        total_donations=total_donations,
        active_projects=active_projects,
        balance=balance,
        donation_summary=donation_summary,
    )


# Donor routes provide listing, searching, creation, editing, and deletion.
@app.route("/donors")
@login_required
def donors():
    search = request.args.get("q", "").strip()
    if search:
        rows = query_db(
            """SELECT * FROM donors
               WHERE name LIKE %s OR email LIKE %s OR phone LIKE %s
               ORDER BY created_at DESC""",
            (f"%{search}%", f"%{search}%", f"%{search}%"),
        )
    else:
        rows = query_db("SELECT * FROM donors ORDER BY created_at DESC")
    return render_template("donors.html", donors=rows, search=search)


@app.route("/donors/add", methods=["POST"])
@login_required
def add_donor():
    form = request.form
    try:
        query_db(
            """INSERT INTO donors (name, email, phone, address, donor_type, pan_number)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                form["name"].strip(),
                form.get("email", "").strip() or None,
                form.get("phone", "").strip() or None,
                form.get("address", "").strip() or None,
                form.get("donor_type", "Individual"),
                form.get("pan_number", "").strip() or None,
            ),
            commit=True,
        )
        flash("Donor added successfully.", "success")
    except MySQLError as e:
        flash(f"Could not add donor: {e}", "danger")
    return redirect(url_for("donors"))


@app.route("/donors/edit/<int:donor_id>", methods=["POST"])
@login_required
def edit_donor(donor_id):
    form = request.form
    try:
        query_db(
            """UPDATE donors SET name=%s, email=%s, phone=%s, address=%s,
               donor_type=%s, pan_number=%s WHERE donor_id=%s""",
            (
                form["name"].strip(),
                form.get("email", "").strip() or None,
                form.get("phone", "").strip() or None,
                form.get("address", "").strip() or None,
                form.get("donor_type", "Individual"),
                form.get("pan_number", "").strip() or None,
                donor_id,
            ),
            commit=True,
        )
        flash("Donor updated.", "success")
    except MySQLError as e:
        flash(f"Could not update donor: {e}", "danger")
    return redirect(url_for("donors"))


@app.route("/donors/delete/<int:donor_id>", methods=["POST"])
@login_required
def delete_donor(donor_id):
    try:
        query_db("DELETE FROM donors WHERE donor_id=%s", (donor_id,), commit=True)
        flash("Donor deleted.", "info")
    except MySQLError as e:
        flash(f"Could not delete donor (they may have linked donations): {e}", "danger")
    return redirect(url_for("donors"))
# Project routes manage fundraising targets and project status.
@app.route("/projects")
@login_required
def projects():
    rows = query_db("""
        SELECT p.*,
               COALESCE(d.total, 0) AS raised,
               COALESCE(e.total, 0) AS spent
        FROM projects p
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM donations GROUP BY project_id) d
               ON d.project_id = p.project_id
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM expenses GROUP BY project_id) e
               ON e.project_id = p.project_id
        ORDER BY p.created_at DESC
    """)
    return render_template("projects.html", projects=rows)


@app.route("/projects/add", methods=["POST"])
@login_required
def add_project():
    form = request.form
    try:
        query_db(
            """INSERT INTO projects (project_name, description, target_amount,
               start_date, end_date, status)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                form["project_name"].strip(),
                form.get("description", "").strip() or None,
                form.get("target_amount") or 0,
                form.get("start_date") or None,
                form.get("end_date") or None,
                form.get("status", "Active"),
            ),
            commit=True,
        )
        flash("Project created.", "success")
    except MySQLError as e:
        flash(f"Could not create project: {e}", "danger")
    return redirect(url_for("projects"))


@app.route("/projects/edit/<int:project_id>", methods=["POST"])
@login_required
def edit_project(project_id):
    form = request.form
    try:
        query_db(
            """UPDATE projects SET project_name=%s, description=%s, target_amount=%s,
               start_date=%s, end_date=%s, status=%s WHERE project_id=%s""",
            (
                form["project_name"].strip(),
                form.get("description", "").strip() or None,
                form.get("target_amount") or 0,
                form.get("start_date") or None,
                form.get("end_date") or None,
                form.get("status", "Active"),
                project_id,
            ),
            commit=True,
        )
        flash("Project updated.", "success")
    except MySQLError as e:
        flash(f"Could not update project: {e}", "danger")
    return redirect(url_for("projects"))


@app.route("/projects/delete/<int:project_id>", methods=["POST"])
@login_required
def delete_project(project_id):
    try:
        query_db("DELETE FROM projects WHERE project_id=%s", (project_id,), commit=True)
        flash("Project deleted.", "info")
    except MySQLError as e:
        flash(f"Could not delete project: {e}", "danger")
    return redirect(url_for("projects"))
# Create unique receipt numbers for donations based on the current date and sequence.
def generate_receipt_no():
    today = date.today().strftime("%Y%m%d")
    count = query_db(
        "SELECT COUNT(*) c FROM donations WHERE receipt_no LIKE %s",
        (f"{app.config['RECEIPT_PREFIX']}-{today}-%",),
        fetchone=True,
    )["c"]
    return f"{app.config['RECEIPT_PREFIX']}-{today}-{count + 1:04d}"


# Donation routes record contributions and expose printable receipts.
@app.route("/donations")
@login_required
def donations():
    mode_filter = request.args.get("mode", "")
    project_filter = request.args.get("project_id", "")

    sql = """
        SELECT d.*, dn.name AS donor_name, p.project_name
        FROM donations d
        JOIN donors dn ON dn.donor_id = d.donor_id
        LEFT JOIN projects p ON p.project_id = d.project_id
        WHERE 1=1
    """
    params = []
    if mode_filter:
        sql += " AND d.payment_mode = %s"
        params.append(mode_filter)
    if project_filter:
        sql += " AND d.project_id = %s"
        params.append(project_filter)
    sql += " ORDER BY d.donation_date DESC, d.donation_id DESC"

    rows = query_db(sql, params)
    donor_list = query_db("SELECT donor_id, name FROM donors ORDER BY name")
    project_list = query_db("SELECT project_id, project_name FROM projects ORDER BY project_name")

    return render_template(
        "donations.html",
        donations=rows,
        donor_list=donor_list,
        project_list=project_list,
        mode_filter=mode_filter,
        project_filter=project_filter,
    )


@app.route("/donations/add", methods=["POST"])
@login_required
def add_donation():
    form = request.form
    try:
        amount = validate_amount(form.get("amount"), "Donation amount")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("donations"))

    try:
        receipt_no = generate_receipt_no()
        donation_id = query_db(
            """INSERT INTO donations (donor_id, project_id, amount, payment_mode,
               transaction_reference, donation_date, receipt_no, remarks)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                form["donor_id"],
                form.get("project_id") or None,
                amount,
                form["payment_mode"],
                form.get("transaction_reference", "").strip() or None,
                form.get("donation_date") or date.today().isoformat(),
                receipt_no,
                form.get("remarks", "").strip() or None,
            ),
            commit=True,
        )
        flash(f"Donation recorded. Receipt No: {receipt_no}", "success")
        return redirect(url_for("view_receipt", donation_id=donation_id))
    except MySQLError as e:
        flash(f"Could not record donation: {e}", "danger")
        return redirect(url_for("donations"))


@app.route("/donations/delete/<int:donation_id>", methods=["POST"])
@login_required
def delete_donation(donation_id):
    try:
        query_db("DELETE FROM donations WHERE donation_id=%s", (donation_id,), commit=True)
        flash("Donation record deleted.", "info")
    except MySQLError as e:
        flash(f"Could not delete donation: {e}", "danger")
    return redirect(url_for("donations"))


# Render a printable receipt for a stored donation entry.
@app.route("/receipt/<int:donation_id>")
@login_required
def view_receipt(donation_id):
    donation = query_db("""
        SELECT d.*, dn.name AS donor_name, dn.email, dn.phone, dn.address,
               dn.pan_number, p.project_name
        FROM donations d
        JOIN donors dn ON dn.donor_id = d.donor_id
        LEFT JOIN projects p ON p.project_id = d.project_id
        WHERE d.donation_id = %s
    """, (donation_id,), fetchone=True)
    if not donation:
        abort(404)
    return render_template("receipt.html", donation=donation)
# Expense routes record spending against a project.
@app.route("/expenses")
@login_required
def expenses():
    project_filter = request.args.get("project_id", "")
    sql = """
        SELECT e.*, p.project_name
        FROM expenses e
        JOIN projects p ON p.project_id = e.project_id
        WHERE 1=1
    """
    params = []
    if project_filter:
        sql += " AND e.project_id = %s"
        params.append(project_filter)
    sql += " ORDER BY e.expense_date DESC, e.expense_id DESC"

    rows = query_db(sql, params)
    project_list = query_db("SELECT project_id, project_name FROM projects ORDER BY project_name")

    # Fund balance per project so the form can warn on overspend
    balances = query_db("""
        SELECT p.project_id, p.project_name,
               COALESCE(d.total,0) - COALESCE(e.total,0) AS balance
        FROM projects p
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM donations GROUP BY project_id) d
               ON d.project_id = p.project_id
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM expenses GROUP BY project_id) e
               ON e.project_id = p.project_id
    """)

    return render_template(
        "expenses.html",
        expenses=rows,
        project_list=project_list,
        project_filter=project_filter,
        balances=balances,
    )


@app.route("/expenses/add", methods=["POST"])
@login_required
def add_expense():
    form = request.form
    try:
        amount = validate_amount(form.get("amount"), "Expense amount")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("expenses"))

    try:
        query_db(
            """INSERT INTO expenses (project_id, category, amount, expense_date,
               description, approved_by)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                form["project_id"],
                form["category"].strip(),
                amount,
                form.get("expense_date") or date.today().isoformat(),
                form.get("description", "").strip() or None,
                form.get("approved_by", "").strip() or None,
            ),
            commit=True,
        )
        flash("Expense recorded.", "success")
    except MySQLError as e:
        flash(f"Could not record expense: {e}", "danger")
    return redirect(url_for("expenses"))


@app.route("/expenses/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete_expense(expense_id):
    try:
        query_db("DELETE FROM expenses WHERE expense_id=%s", (expense_id,), commit=True)
        flash("Expense record deleted.", "info")
    except MySQLError as e:
        flash(f"Could not delete expense: {e}", "danger")
    return redirect(url_for("expenses"))
# Reporting routes provide server-rendered and chart-oriented summaries.
@app.route("/reports")
@login_required
def reports():
    total_donations = query_db(
        "SELECT COALESCE(SUM(amount),0) AS total FROM donations",
        fetchone=True,
    )["total"]
    total_expenses = query_db(
        "SELECT COALESCE(SUM(amount),0) AS total FROM expenses",
        fetchone=True,
    )["total"]
    remaining_balance = float(total_donations) - float(total_expenses)

    by_mode = query_db("""
        SELECT payment_mode, COALESCE(SUM(amount),0) AS total, COUNT(*) AS cnt
        FROM donations GROUP BY payment_mode
    """)

    by_project = query_db("""
        SELECT p.project_name,
               COALESCE(d.total,0) AS raised,
               COALESCE(e.total,0) AS spent,
               (COALESCE(d.total,0) - COALESCE(e.total,0)) AS remaining
        FROM projects p
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM donations GROUP BY project_id) d
               ON d.project_id = p.project_id
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM expenses GROUP BY project_id) e
               ON e.project_id = p.project_id
        ORDER BY raised DESC
    """)

    monthly = query_db("""
        SELECT DATE_FORMAT(donation_date, '%Y-%m') AS month,
               COALESCE(SUM(amount),0) AS total
        FROM donations
        GROUP BY month
        ORDER BY month
    """)

    top_donors = query_db("""
        SELECT dn.name, COALESCE(SUM(d.amount),0) AS total
        FROM donors dn
        JOIN donations d ON d.donor_id = dn.donor_id
        GROUP BY dn.donor_id
        ORDER BY total DESC
        LIMIT 5
    """)

    return render_template(
        "reports.html",
        total_donations=total_donations,
        total_expenses=total_expenses,
        remaining_balance=remaining_balance,
        by_mode=by_mode,
        by_project=by_project,
        monthly=monthly,
        top_donors=top_donors,
    )


# JSON endpoint used by chart widgets on the dashboard and reports pages.
@app.route("/api/reports/summary")
@login_required
def api_reports_summary():
    """JSON endpoint feeding the Chart.js visuals on the reports page."""
    by_mode = query_db("""
        SELECT payment_mode, COALESCE(SUM(amount),0) AS total
        FROM donations GROUP BY payment_mode
    """)
    monthly = query_db("""
        SELECT DATE_FORMAT(donation_date, '%Y-%m') AS month,
               COALESCE(SUM(amount),0) AS total
        FROM donations GROUP BY month ORDER BY month
    """)
    by_project = query_db("""
        SELECT p.project_name,
               COALESCE(d.total,0) AS raised,
               COALESCE(e.total,0) AS spent
        FROM projects p
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM donations GROUP BY project_id) d
               ON d.project_id = p.project_id
        LEFT JOIN (SELECT project_id, SUM(amount) total FROM expenses GROUP BY project_id) e
               ON e.project_id = p.project_id
    """)
    return jsonify({
        "by_mode": by_mode,
        "monthly": monthly,
        "by_project": by_project,
    })
@app.errorhandler(404)
def not_found(e):
    if "admin_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.errorhandler(500)
def server_error(e):
    if "admin_id" in session:
        flash("An internal server error occurred. Please try again.", "danger")
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 4 and sys.argv[1] == "create-admin":
        email = sys.argv[2].strip().lower()
        pwd = sys.argv[3]
        full_name = " ".join(sys.argv[4:]) or email
        pw_hash = generate_password_hash(pwd)
        try:
            existing = query_db("SELECT admin_id FROM admin WHERE email=%s", (email,), fetchone=True)
            if existing:
                query_db("UPDATE admin SET password_hash=%s WHERE email=%s", (pw_hash, email), commit=True)
                print(f"Password updated for '{email}'.")
            else:
                # `username` is still a required/unique column in the schema;
                # default it to the email so plain Gmail-based logins work.
                query_db(
                    "INSERT INTO admin (username, email, password_hash, full_name) VALUES (%s,%s,%s,%s)",
                    (email, email, pw_hash, full_name),
                    commit=True,
                )
                print(f"Admin '{email}' created.")
        except MySQLError as e:
            print(f"Error: {e}")
        sys.exit(0)

    app.run(debug=True, host="0.0.0.0", port=5000)

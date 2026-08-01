from functools import wraps
from pathlib import Path
import sys

from psycopg2 import IntegrityError

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)
from werkzeug.utils import secure_filename

from database_postgres import (
    execute_query,
    fetch_all,
    fetch_one,
    initialize_database,
)
from xml_reader import (
    InvoiceXMLReadError,
    read_invoice_xml,
)

from backup_routes import backup_blueprint
from print_routes import print_blueprint
from excel_routes import excel_blueprint
from pdf_routes import pdf_blueprint
from settings_routes import settings_blueprint


# =========================================================
# إعدادات البرنامج
# =========================================================

if getattr(sys, "frozen", False):
    RESOURCE_DIR = Path(sys._MEIPASS)
else:
    RESOURCE_DIR = Path(__file__).resolve().parent


app = Flask(
    __name__,
    template_folder=str(
        RESOURCE_DIR / "templates"
    ),
    static_folder=str(
        RESOURCE_DIR / "static"
    ),
)

app.register_blueprint(backup_blueprint)
app.register_blueprint(settings_blueprint)
app.register_blueprint(print_blueprint)
app.register_blueprint(pdf_blueprint)
app.register_blueprint(excel_blueprint)
app.config["SECRET_KEY"] = (
    "electronic-invoice-manager-secret-key-change-this"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {"xml"}


# =========================================================
# دوال المستخدمين والصلاحيات
# =========================================================

def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash(
                "يجب تسجيل الدخول أولًا.",
                "warning",
            )

            return redirect(
                url_for("login")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash(
                "يجب تسجيل الدخول أولًا.",
                "warning",
            )

            return redirect(
                url_for("login")
            )

        if session.get("user_role") != "admin":
            flash(
                "ليس لديك صلاحية لتنفيذ هذا الإجراء.",
                "danger",
            )

            return redirect(
                url_for("dashboard")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


def get_current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    return fetch_one(
        """
        SELECT
            id,
            full_name,
            username,
            role,
            is_active,
            created_at

        FROM users

        WHERE id = ?
        """,
        (user_id,),
    )


@app.context_processor
def inject_current_user():
    return {
        "current_user": get_current_user(),
    }


# =========================================================
# دوال مساعدة
# =========================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def get_dashboard_statistics():
    customer_count = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM customers
        """
    )

    invoice_count = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM invoices
        """
    )

    financial_totals = fetch_one(
        """
        SELECT
            COALESCE(
                SUM(before_tax),
                0
            ) AS before_tax,

            COALESCE(
                SUM(vat),
                0
            ) AS vat,

            COALESCE(
                SUM(withholding_tax),
                0
            ) AS withholding_tax,

            COALESCE(
                SUM(after_tax),
                0
            ) AS after_tax

        FROM invoices
        """
    )

    return {
        "customer_count":
            customer_count["total"],

        "invoice_count":
            invoice_count["total"],

        "before_tax":
            financial_totals["before_tax"],

        "vat":
            financial_totals["vat"],

        "withholding_tax":
            financial_totals["withholding_tax"],

        "after_tax":
            financial_totals["after_tax"],
    }


# =========================================================
# تسجيل الدخول والخروج
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":
        username = request.form.get(
            "username",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        if not username or not password:
            flash(
                "اكتب اسم المستخدم وكلمة المرور.",
                "danger",
            )

            return render_template(
                "login.html"
            )

        user = fetch_one(
            """
            SELECT
                id,
                full_name,
                username,
                password_hash,
                role,
                is_active

            FROM users

            WHERE username = ?
            """,
            (username,),
        )

        if user is None:
            flash(
                "اسم المستخدم أو كلمة المرور غير صحيحة.",
                "danger",
            )

            return render_template(
                "login.html"
            )

        if not user["is_active"]:
            flash(
                "هذا المستخدم موقوف. تواصل مع مدير النظام.",
                "danger",
            )

            return render_template(
                "login.html"
            )

        if not check_password_hash(
            user["password_hash"],
            password,
        ):
            flash(
                "اسم المستخدم أو كلمة المرور غير صحيحة.",
                "danger",
            )

            return render_template(
                "login.html"
            )

        session.clear()

        session["user_id"] = user["id"]
        session["user_full_name"] = user["full_name"]
        session["username"] = user["username"]
        session["user_role"] = user["role"]

        flash(
            f"مرحبًا {user['full_name']}.",
            "success",
        )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )


@app.route("/logout")
@login_required
def logout():
    session.clear()

    flash(
        "تم تسجيل الخروج بنجاح.",
        "success",
    )

    return redirect(
        url_for("login")
    )


# =========================================================
# الصفحة الرئيسية
# =========================================================

@app.route("/")
@login_required
def dashboard():
    statistics = get_dashboard_statistics()

    latest_invoices = fetch_all(
        """
        SELECT
            invoices.id,
            invoices.invoice_number,
            invoices.invoice_date,
            invoices.before_tax,
            invoices.vat,
            invoices.withholding_tax,
            invoices.after_tax,
            customers.name AS customer_name

        FROM invoices

        INNER JOIN customers
            ON customers.id =
               invoices.customer_id

        ORDER BY invoices.id DESC

        LIMIT 10
        """
    )

    return render_template(
        "dashboard.html",
        statistics=statistics,
        latest_invoices=latest_invoices,
    )


# =========================================================
# العملاء
# =========================================================

@app.route("/customers")
@login_required
def customers():
    search_text = request.args.get(
        "search",
        "",
    ).strip()

    query = """
        SELECT
            customers.id,
            customers.name,
            customers.phone,
            customers.notes,
            customers.created_at,

            COUNT(
                invoices.id
            ) AS invoice_count,

            COALESCE(
                SUM(
                    invoices.before_tax
                ),
                0
            ) AS total_before_tax,

            COALESCE(
                SUM(
                    invoices.vat
                ),
                0
            ) AS total_vat,

            COALESCE(
                SUM(
                    invoices.withholding_tax
                ),
                0
            ) AS total_discount,

            COALESCE(
                SUM(
                    invoices.after_tax
                ),
                0
            ) AS total_work

        FROM customers

        LEFT JOIN invoices
            ON invoices.customer_id =
               customers.id
    """

    parameters = []

    if search_text:
        query += """
            WHERE customers.name LIKE ?
               OR customers.phone LIKE ?
        """

        search_value = (
            f"%{search_text}%"
        )

        parameters.extend(
            [
                search_value,
                search_value,
            ]
        )

    query += """
        GROUP BY customers.id

        ORDER BY customers.id DESC
    """

    customers_list = fetch_all(
        query,
        tuple(parameters),
    )

    return render_template(
        "customers.html",
        customers=customers_list,
        search_text=search_text,
    )


@app.route(
    "/customers/add",
    methods=["POST"],
)
@login_required
def add_customer():
    name = request.form.get(
        "name",
        "",
    ).strip()

    phone = request.form.get(
        "phone",
        "",
    ).strip()

    notes = request.form.get(
        "notes",
        "",
    ).strip()

    if not name:
        flash(
            "من فضلك اكتب اسم العميل.",
            "danger",
        )

        return redirect(
            url_for("customers")
        )

    try:
        customer_id = execute_query(
            """
            INSERT INTO customers (
                name,
                phone,
                notes
            )

            VALUES (?, ?, ?)
            """,
            (
                name,
                phone,
                notes,
            ),
        )

        print(
            f"تمت إضافة العميل إلى PostgreSQL بنجاح. ID={customer_id}"
        )

        flash(
            "تمت إضافة العميل بنجاح.",
            "success",
        )

    except IntegrityError:
        flash(
            "اسم العميل موجود بالفعل.",
            "warning",
        )

    except Exception as error:
        print(
            "حدث خطأ أثناء إضافة العميل إلى PostgreSQL:",
            repr(error),
        )

        raise

    return redirect(
        url_for("customers")
    )


@app.route(
    "/customers/<int:customer_id>/edit",
    methods=["POST"],
)
@login_required
def edit_customer(customer_id):
    customer = fetch_one(
        """
        SELECT id
        FROM customers
        WHERE id = ?
        """,
        (customer_id,),
    )

    if customer is None:
        flash(
            "العميل غير موجود.",
            "danger",
        )

        return redirect(
            url_for("customers")
        )

    name = request.form.get(
        "name",
        "",
    ).strip()

    phone = request.form.get(
        "phone",
        "",
    ).strip()

    notes = request.form.get(
        "notes",
        "",
    ).strip()

    if not name:
        flash(
            "اسم العميل لا يمكن أن يكون فارغًا.",
            "danger",
        )

        return redirect(
            url_for("customers")
        )

    try:
        execute_query(
            """
            UPDATE customers

            SET
                name = ?,
                phone = ?,
                notes = ?

            WHERE id = ?
            """,
            (
                name,
                phone,
                notes,
                customer_id,
            ),
        )

        flash(
            "تم تعديل بيانات العميل بنجاح.",
            "success",
        )

    except IntegrityError:
        flash(
            "يوجد عميل آخر بنفس الاسم.",
            "warning",
        )

    return redirect(
        url_for("customers")
    )


@app.route(
    "/customers/<int:customer_id>/delete",
    methods=["POST"],
)
@login_required
def delete_customer(customer_id):
    customer = fetch_one(
        """
        SELECT
            customers.id,
            customers.name,

            COUNT(
                invoices.id
            ) AS invoice_count

        FROM customers

        LEFT JOIN invoices
            ON invoices.customer_id =
               customers.id

        WHERE customers.id = ?

        GROUP BY customers.id
        """,
        (customer_id,),
    )

    if customer is None:
        flash(
            "العميل غير موجود.",
            "danger",
        )

        return redirect(
            url_for("customers")
        )

    if customer["invoice_count"] > 0:
        flash(
            "لا يمكن حذف العميل لأنه مرتبط بفواتير.",
            "warning",
        )

        return redirect(
            url_for("customers")
        )

    execute_query(
        """
        DELETE FROM customers
        WHERE id = ?
        """,
        (customer_id,),
    )

    flash(
        "تم حذف العميل بنجاح.",
        "success",
    )

    return redirect(
        url_for("customers")
    )


# =========================================================
# الفواتير
# =========================================================

@app.route("/invoices")
@login_required
def invoices():
    search_text = request.args.get(
        "search",
        "",
    ).strip()

    customer_id = request.args.get(
        "customer_id",
        "",
    ).strip()

    query = """
        SELECT
            invoices.id,
            invoices.invoice_number,
            invoices.invoice_date,
            invoices.before_tax,
            invoices.vat,
            invoices.withholding_tax,
            invoices.after_tax,
            invoices.xml_filename,
            invoices.created_at,

            customers.id AS customer_id,
            customers.name AS customer_name

        FROM invoices

        INNER JOIN customers
            ON customers.id =
               invoices.customer_id

        WHERE 1 = 1
    """

    parameters = []

    if search_text:
        query += """
            AND (
                invoices.invoice_number LIKE ?
                OR customers.name LIKE ?
                OR invoices.buyer_name LIKE ?
                OR invoices.seller_name LIKE ?
            )
        """

        search_value = (
            f"%{search_text}%"
        )

        parameters.extend(
            [
                search_value,
                search_value,
                search_value,
                search_value,
            ]
        )

    if customer_id.isdigit():
        query += """
            AND customers.id = ?
        """

        parameters.append(
            int(customer_id)
        )

    query += """
        ORDER BY invoices.id DESC
    """

    invoices_list = fetch_all(
        query,
        tuple(parameters),
    )

    customers_list = fetch_all(
        """
        SELECT
            id,
            name

        FROM customers

        ORDER BY name
        """
    )

    return render_template(
        "invoices.html",
        invoices=invoices_list,
        customers=customers_list,
        search_text=search_text,
        selected_customer_id=customer_id,
    )


@app.route(
    "/invoices/upload",
    methods=["POST"],
)
@login_required
def upload_invoice():
    customer_id = request.form.get(
        "customer_id",
        "",
    ).strip()

    xml_file = request.files.get(
        "xml_file"
    )

    if not customer_id.isdigit():
        flash(
            "من فضلك اختر العميل.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    customer = fetch_one(
        """
        SELECT
            id,
            name

        FROM customers

        WHERE id = ?
        """,
        (int(customer_id),),
    )

    if customer is None:
        flash(
            "العميل المحدد غير موجود.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    if (
        xml_file is None
        or not xml_file.filename
    ):
        flash(
            "من فضلك اختر ملف XML.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    if not allowed_file(
        xml_file.filename
    ):
        flash(
            "مسموح برفع ملفات XML فقط.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    try:
        invoice_data = read_invoice_xml(
            xml_file
        )

    except InvoiceXMLReadError as error:
        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    except Exception:
        flash(
            "حدث خطأ غير متوقع أثناء قراءة ملف الفاتورة.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    invoice_number = str(
        invoice_data.get(
            "invoice_number",
            "",
        )
    ).strip()

    if not invoice_number:
        flash(
            "تعذر العثور على رقم الفاتورة داخل ملف XML.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    filename = secure_filename(
        xml_file.filename
    )

    try:
        execute_query(
            """
            INSERT INTO invoices (
                customer_id,
                invoice_number,
                invoice_date,

                buyer_name,
                buyer_registration,
                buyer_address,

                seller_name,
                seller_registration,
                seller_address,

                before_tax,
                vat,
                withholding_tax,
                after_tax,

                xml_filename
            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                int(customer_id),

                invoice_number,

                invoice_data.get(
                    "invoice_date",
                    "",
                ),

                invoice_data.get(
                    "buyer_name",
                    "",
                ),

                invoice_data.get(
                    "buyer_registration",
                    "",
                ),

                invoice_data.get(
                    "buyer_address",
                    "",
                ),

                invoice_data.get(
                    "seller_name",
                    "",
                ),

                invoice_data.get(
                    "seller_registration",
                    "",
                ),

                invoice_data.get(
                    "seller_address",
                    "",
                ),

                invoice_data.get(
                    "before_tax",
                    0,
                ),

                invoice_data.get(
                    "vat",
                    0,
                ),

                invoice_data.get(
                    "withholding_tax",
                    0,
                ),

                invoice_data.get(
                    "after_tax",
                    0,
                ),

                filename,
            ),
        )

        flash(
            f"تمت إضافة الفاتورة رقم {invoice_number} بنجاح.",
            "success",
        )

    except IntegrityError:
        flash(
            "هذه الفاتورة مسجلة بالفعل لهذا العميل.",
            "warning",
        )

    return redirect(
        url_for("invoices")
    )


@app.route(
    "/invoices/<int:invoice_id>"
)
@login_required
def invoice_details(invoice_id):
    invoice = fetch_one(
        """
        SELECT
            invoices.*,

            customers.name
                AS customer_name,

            customers.phone
                AS customer_phone,

            customers.notes
                AS customer_notes

        FROM invoices

        INNER JOIN customers
            ON customers.id =
               invoices.customer_id

        WHERE invoices.id = ?
        """,
        (invoice_id,),
    )

    if invoice is None:
        flash(
            "الفاتورة غير موجودة.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    return render_template(
        "invoice_details.html",
        invoice=invoice,
    )


@app.route(
    "/invoices/<int:invoice_id>/delete",
    methods=["POST"],
)
@login_required
def delete_invoice(invoice_id):
    invoice = fetch_one(
        """
        SELECT
            id,
            invoice_number

        FROM invoices

        WHERE id = ?
        """,
        (invoice_id,),
    )

    if invoice is None:
        flash(
            "الفاتورة غير موجودة.",
            "danger",
        )

        return redirect(
            url_for("invoices")
        )

    execute_query(
        """
        DELETE FROM invoices
        WHERE id = ?
        """,
        (invoice_id,),
    )

    flash(
        f"تم حذف الفاتورة رقم {invoice['invoice_number']}.",
        "success",
    )

    return redirect(
        url_for("invoices")
    )


# =========================================================
# التقارير
# =========================================================

@app.route("/reports")
@login_required
def reports():
    statistics = get_dashboard_statistics()

    customer_reports = fetch_all(
        """
        SELECT
            customers.id,
            customers.name,

            COUNT(
                invoices.id
            ) AS invoice_count,

            COALESCE(
                SUM(
                    invoices.before_tax
                ),
                0
            ) AS before_tax,

            COALESCE(
                SUM(
                    invoices.vat
                ),
                0
            ) AS vat,

            COALESCE(
                SUM(
                    invoices.withholding_tax
                ),
                0
            ) AS withholding_tax,

            COALESCE(
                SUM(
                    invoices.after_tax
                ),
                0
            ) AS after_tax

        FROM customers

        LEFT JOIN invoices
            ON invoices.customer_id =
               customers.id

        GROUP BY customers.id

        ORDER BY after_tax DESC
        """
    )

    return render_template(
        "reports.html",
        statistics=statistics,
        customer_reports=customer_reports,
    )


# =========================================================
# إدارة المستخدمين
# =========================================================

@app.route("/users")
@admin_required
def users():
    search_text = request.args.get(
        "search",
        "",
    ).strip()

    if search_text:
        search_value = (
            f"%{search_text}%"
        )

        users_list = fetch_all(
            """
            SELECT
                id,
                full_name,
                username,
                role,
                is_active,
                created_at

            FROM users

            WHERE full_name LIKE ?
               OR username LIKE ?

            ORDER BY id DESC
            """,
            (
                search_value,
                search_value,
            ),
        )

    else:
        users_list = fetch_all(
            """
            SELECT
                id,
                full_name,
                username,
                role,
                is_active,
                created_at

            FROM users

            ORDER BY id DESC
            """
        )

    return render_template(
        "users.html",
        users=users_list,
        search_text=search_text,
    )


@app.route(
    "/users/add",
    methods=["POST"],
)
@admin_required
def add_user():
    full_name = request.form.get(
        "full_name",
        "",
    ).strip()

    username = request.form.get(
        "username",
        "",
    ).strip()

    password = request.form.get(
        "password",
        "",
    )

    role = request.form.get(
        "role",
        "employee",
    ).strip()

    if role not in {
        "admin",
        "employee",
    }:
        role = "employee"

    if (
        not full_name
        or not username
        or not password
    ):
        flash(
            "يجب إدخال الاسم واسم المستخدم وكلمة المرور.",
            "danger",
        )

        return redirect(
            url_for("users")
        )

    if len(password) < 6:
        flash(
            "كلمة المرور يجب ألا تقل عن 6 أحرف.",
            "warning",
        )

        return redirect(
            url_for("users")
        )

    password_hash = generate_password_hash(
        password
    )

    try:
        execute_query(
            """
            INSERT INTO users (
                full_name,
                username,
                password_hash,
                role,
                is_active
            )

            VALUES (?, ?, ?, ?, 1)
            """,
            (
                full_name,
                username,
                password_hash,
                role,
            ),
        )

        flash(
            "تمت إضافة المستخدم بنجاح.",
            "success",
        )

    except IntegrityError:
        flash(
            "اسم المستخدم موجود بالفعل.",
            "warning",
        )

    return redirect(
        url_for("users")
    )


@app.route(
    "/users/<int:user_id>/edit",
    methods=["POST"],
)
@admin_required
def edit_user(user_id):
    user = fetch_one(
        """
        SELECT
            id,
            role

        FROM users

        WHERE id = ?
        """,
        (user_id,),
    )

    if user is None:
        flash(
            "المستخدم غير موجود.",
            "danger",
        )

        return redirect(
            url_for("users")
        )

    full_name = request.form.get(
        "full_name",
        "",
    ).strip()

    username = request.form.get(
        "username",
        "",
    ).strip()

    role = request.form.get(
        "role",
        "employee",
    ).strip()

    if role not in {
        "admin",
        "employee",
    }:
        role = "employee"

    if not full_name or not username:
        flash(
            "الاسم واسم المستخدم مطلوبان.",
            "danger",
        )

        return redirect(
            url_for("users")
        )

    try:
        execute_query(
            """
            UPDATE users

            SET
                full_name = ?,
                username = ?,
                role = ?

            WHERE id = ?
            """,
            (
                full_name,
                username,
                role,
                user_id,
            ),
        )

        if user_id == session.get("user_id"):
            session["user_full_name"] = full_name
            session["username"] = username
            session["user_role"] = role

        flash(
            "تم تعديل المستخدم بنجاح.",
            "success",
        )

    except IntegrityError:
        flash(
            "اسم المستخدم مستخدم بالفعل.",
            "warning",
        )

    return redirect(
        url_for("users")
    )


@app.route(
    "/users/<int:user_id>/reset-password",
    methods=["POST"],
)
@admin_required
def reset_user_password(user_id):
    user = fetch_one(
        """
        SELECT id
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )

    if user is None:
        flash(
            "المستخدم غير موجود.",
            "danger",
        )

        return redirect(
            url_for("users")
        )

    new_password = request.form.get(
        "new_password",
        "",
    )

    if len(new_password) < 6:
        flash(
            "كلمة المرور الجديدة يجب ألا تقل عن 6 أحرف.",
            "warning",
        )

        return redirect(
            url_for("users")
        )

    password_hash = generate_password_hash(
        new_password
    )

    execute_query(
        """
        UPDATE users

        SET password_hash = ?

        WHERE id = ?
        """,
        (
            password_hash,
            user_id,
        ),
    )

    flash(
        "تم تغيير كلمة المرور بنجاح.",
        "success",
    )

    return redirect(
        url_for("users")
    )


@app.route(
    "/users/<int:user_id>/toggle",
    methods=["POST"],
)
@admin_required
def toggle_user(user_id):
    if user_id == session.get("user_id"):
        flash(
            "لا يمكنك إيقاف حسابك أثناء تسجيل الدخول.",
            "warning",
        )

        return redirect(
            url_for("users")
        )

    user = fetch_one(
        """
        SELECT
            id,
            is_active

        FROM users

        WHERE id = ?
        """,
        (user_id,),
    )

    if user is None:
        flash(
            "المستخدم غير موجود.",
            "danger",
        )

        return redirect(
            url_for("users")
        )

    new_status = (
        0
        if user["is_active"]
        else 1
    )

    execute_query(
        """
        UPDATE users

        SET is_active = ?

        WHERE id = ?
        """,
        (
            new_status,
            user_id,
        ),
    )

    message = (
        "تم تفعيل المستخدم."
        if new_status
        else "تم إيقاف المستخدم."
    )

    flash(
        message,
        "success",
    )

    return redirect(
        url_for("users")
    )


@app.route(
    "/users/<int:user_id>/delete",
    methods=["POST"],
)
@admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash(
            "لا يمكنك حذف حسابك أثناء تسجيل الدخول.",
            "warning",
        )

        return redirect(
            url_for("users")
        )

    user = fetch_one(
        """
        SELECT
            id,
            role

        FROM users

        WHERE id = ?
        """,
        (user_id,),
    )

    if user is None:
        flash(
            "المستخدم غير موجود.",
            "danger",
        )

        return redirect(
            url_for("users")
        )

    if user["role"] == "admin":
        admin_count = fetch_one(
            """
            SELECT COUNT(*) AS total

            FROM users

            WHERE role = 'admin'
              AND is_active = 1
            """
        )

        if admin_count["total"] <= 1:
            flash(
                "لا يمكن حذف آخر مدير نشط في النظام.",
                "warning",
            )

            return redirect(
                url_for("users")
            )

    execute_query(
        """
        DELETE FROM users
        WHERE id = ?
        """,
        (user_id,),
    )

    flash(
        "تم حذف المستخدم بنجاح.",
        "success",
    )

    return redirect(
        url_for("users")
    )


# =========================================================
# تغيير كلمة مرور المستخدم الحالي
# =========================================================

@app.route(
    "/change-password",
    methods=["POST"],
)
@login_required
def change_password():
    current_password = request.form.get(
        "current_password",
        "",
    )

    new_password = request.form.get(
        "new_password",
        "",
    )

    confirm_password = request.form.get(
        "confirm_password",
        "",
    )

    user = fetch_one(
        """
        SELECT
            id,
            password_hash

        FROM users

        WHERE id = ?
        """,
        (session["user_id"],),
    )

    if user is None:
        session.clear()

        return redirect(
            url_for("login")
        )

    if not check_password_hash(
        user["password_hash"],
        current_password,
    ):
        flash(
            "كلمة المرور الحالية غير صحيحة.",
            "danger",
        )

        return redirect(
            request.referrer
            or url_for("dashboard")
        )

    if len(new_password) < 6:
        flash(
            "كلمة المرور الجديدة يجب ألا تقل عن 6 أحرف.",
            "warning",
        )

        return redirect(
            request.referrer
            or url_for("dashboard")
        )

    if new_password != confirm_password:
        flash(
            "كلمتا المرور الجديدتان غير متطابقتين.",
            "warning",
        )

        return redirect(
            request.referrer
            or url_for("dashboard")
        )

    password_hash = generate_password_hash(
        new_password
    )

    execute_query(
        """
        UPDATE users

        SET password_hash = ?

        WHERE id = ?
        """,
        (
            password_hash,
            session["user_id"],
        ),
    )

    flash(
        "تم تغيير كلمة المرور بنجاح.",
        "success",
    )

    return redirect(
        request.referrer
        or url_for("dashboard")
    )


# =========================================================
# معالجة الأخطاء
# =========================================================

@app.errorhandler(413)
def file_too_large(error):
    flash(
        "حجم الملف كبير جدًا. الحد الأقصى المسموح به 10 ميجابايت.",
        "danger",
    )

    return redirect(
        url_for("invoices")
    )


@app.errorhandler(404)
def page_not_found(error):
    return render_template(
        "404.html"
    ), 404


# =========================================================
# تشغيل البرنامج
# =========================================================

if __name__ == "__main__":
    initialize_database()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False,
    )
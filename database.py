import os
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash


# =========================================================
# مسار قاعدة البيانات
# =========================================================

APP_DATA_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "InvoiceManager"
)

APP_DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DATABASE_PATH = APP_DATA_DIR / "invoices.db"


# =========================================================
# الاتصال بقاعدة البيانات
# =========================================================

def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# =========================================================
# إنشاء قاعدة البيانات والجداول
# =========================================================

def initialize_database():
    connection = get_connection()

    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                full_name TEXT NOT NULL,

                username TEXT NOT NULL UNIQUE,

                password_hash TEXT NOT NULL,

                role TEXT NOT NULL DEFAULT 'employee'
                    CHECK (
                        role IN (
                            'admin',
                            'employee'
                        )
                    ),

                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (
                        is_active IN (
                            0,
                            1
                        )
                    ),

                created_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            );


            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL UNIQUE,

                phone TEXT DEFAULT '',

                notes TEXT DEFAULT '',

                created_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            );


            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                customer_id INTEGER NOT NULL,

                invoice_number TEXT NOT NULL,

                invoice_date TEXT DEFAULT '',

                buyer_name TEXT DEFAULT '',

                buyer_registration TEXT DEFAULT '',

                buyer_address TEXT DEFAULT '',

                seller_name TEXT DEFAULT '',

                seller_registration TEXT DEFAULT '',

                seller_address TEXT DEFAULT '',

                before_tax REAL DEFAULT 0,

                vat REAL DEFAULT 0,

                withholding_tax REAL DEFAULT 0,

                after_tax REAL DEFAULT 0,

                xml_filename TEXT DEFAULT '',

                created_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (
                    customer_id
                )
                REFERENCES customers (
                    id
                )
                ON DELETE RESTRICT,

                UNIQUE (
                    customer_id,
                    invoice_number
                )
            );


            CREATE INDEX IF NOT EXISTS
                idx_users_username
            ON users (
                username
            );


            CREATE INDEX IF NOT EXISTS
                idx_customers_name
            ON customers (
                name
            );


            CREATE INDEX IF NOT EXISTS
                idx_invoices_customer
            ON invoices (
                customer_id
            );


            CREATE INDEX IF NOT EXISTS
                idx_invoices_number
            ON invoices (
                invoice_number
            );


            CREATE INDEX IF NOT EXISTS
                idx_invoices_date
            ON invoices (
                invoice_date
            );
            """
        )

        create_default_admin(connection)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# =========================================================
# إنشاء مستخدم المدير الافتراضي
# =========================================================

def create_default_admin(connection):
    admin_user = connection.execute(
        """
        SELECT
            id
        FROM users
        WHERE username = ?
        """,
        (
            "admin",
        ),
    ).fetchone()

    if admin_user is not None:
        return

    password_hash = generate_password_hash(
        "Admin@123"
    )

    connection.execute(
        """
        INSERT INTO users (
            full_name,
            username,
            password_hash,
            role,
            is_active
        )
        VALUES (
            ?, ?, ?, ?, ?
        )
        """,
        (
            "مدير النظام",
            "admin",
            password_hash,
            "admin",
            1,
        ),
    )


# =========================================================
# إحضار عدة سجلات
# =========================================================

def fetch_all(query, parameters=()):
    connection = get_connection()

    try:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

        return rows

    finally:
        connection.close()


# =========================================================
# إحضار سجل واحد
# =========================================================

def fetch_one(query, parameters=()):
    connection = get_connection()

    try:
        row = connection.execute(
            query,
            parameters,
        ).fetchone()

        return row

    finally:
        connection.close()


# =========================================================
# تنفيذ إضافة أو تعديل أو حذف
# =========================================================

def execute_query(query, parameters=()):
    connection = get_connection()

    try:
        cursor = connection.execute(
            query,
            parameters,
        )

        connection.commit()

        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# =========================================================
# تنفيذ مجموعة أوامر داخل معاملة واحدة
# =========================================================

def execute_script(script):
    connection = get_connection()

    try:
        connection.executescript(script)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
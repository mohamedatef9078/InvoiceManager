import os

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash


# =========================================================
# قراءة بيانات الاتصال من ملف .env
# =========================================================

load_dotenv()


class PostgreSQLDatabaseError(Exception):
    """خطأ خاص بقاعدة بيانات PostgreSQL."""

    pass


# =========================================================
# تجهيز بيانات الاتصال
# =========================================================

def get_database_url():
    """
    يدعم رابط اتصال كامل إذا كان موجودًا داخل .env.
    """

    database_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URL")
        or ""
    ).strip()

    if database_url:
        database_url = database_url.replace(
            "postgresql+psycopg2://",
            "postgresql://",
        )

        return database_url

    return ""


def get_database_config():
    """
    قراءة بيانات Supabase من متغيرات منفصلة.
    """

    config = {
        "user": (
            os.getenv("DB_USER")
            or os.getenv("POSTGRES_USER")
            or ""
        ).strip(),

        "password": (
            os.getenv("DB_PASSWORD")
            or os.getenv("POSTGRES_PASSWORD")
            or ""
        ).strip(),

        "host": (
            os.getenv("DB_HOST")
            or os.getenv("POSTGRES_HOST")
            or ""
        ).strip(),

        "port": (
            os.getenv("DB_PORT")
            or os.getenv("POSTGRES_PORT")
            or "5432"
        ).strip(),

        "dbname": (
            os.getenv("DB_NAME")
            or os.getenv("POSTGRES_DB")
            or "postgres"
        ).strip(),
    }

    missing_values = [
        key
        for key, value in config.items()
        if not value
    ]

    if missing_values:
        raise PostgreSQLDatabaseError(
            "بيانات الاتصال ناقصة داخل ملف .env."
        )

    return config


# =========================================================
# الاتصال بقاعدة البيانات
# =========================================================

def get_connection():
    database_url = get_database_url()

    try:
        if database_url:
            connection = psycopg2.connect(
                database_url,
                sslmode="require",
                cursor_factory=RealDictCursor,
            )

        else:
            config = get_database_config()

            connection = psycopg2.connect(
                user=config["user"],
                password=config["password"],
                host=config["host"],
                port=config["port"],
                dbname=config["dbname"],
                sslmode="require",
                cursor_factory=RealDictCursor,
            )

        return connection

    except psycopg2.Error as error:
        raise PostgreSQLDatabaseError(
            "تعذر الاتصال بقاعدة بيانات Supabase."
        ) from error


# =========================================================
# تحويل علامات SQLite إلى PostgreSQL
# =========================================================

def prepare_query(query):
    """
    البرنامج الحالي يستخدم ? مكان القيم،
    بينما PostgreSQL يستخدم %s.
    """

    return query.replace("?", "%s")


# =========================================================
# إنشاء الجداول
# =========================================================

def initialize_database():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,

                full_name TEXT NOT NULL,

                username TEXT NOT NULL UNIQUE,

                password_hash TEXT NOT NULL,

                role TEXT NOT NULL
                    DEFAULT 'employee'
                    CHECK (
                        role IN (
                            'admin',
                            'employee'
                        )
                    ),

                is_active SMALLINT NOT NULL
                    DEFAULT 1
                    CHECK (
                        is_active IN (
                            0,
                            1
                        )
                    ),

                created_at TIMESTAMP
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,

                name TEXT NOT NULL UNIQUE,

                phone TEXT DEFAULT '',

                notes TEXT DEFAULT '',

                created_at TIMESTAMP
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id SERIAL PRIMARY KEY,

                customer_id INTEGER NOT NULL,

                invoice_number TEXT NOT NULL,

                invoice_date TEXT DEFAULT '',

                buyer_name TEXT DEFAULT '',

                buyer_registration TEXT DEFAULT '',

                buyer_address TEXT DEFAULT '',

                seller_name TEXT DEFAULT '',

                seller_registration TEXT DEFAULT '',

                seller_address TEXT DEFAULT '',

                before_tax DOUBLE PRECISION DEFAULT 0,

                vat DOUBLE PRECISION DEFAULT 0,

                withholding_tax DOUBLE PRECISION DEFAULT 0,

                after_tax DOUBLE PRECISION DEFAULT 0,

                xml_filename TEXT DEFAULT '',

                created_at TIMESTAMP
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT fk_invoices_customer
                    FOREIGN KEY (customer_id)
                    REFERENCES customers(id)
                    ON DELETE RESTRICT,

                CONSTRAINT unique_customer_invoice
                    UNIQUE (
                        customer_id,
                        invoice_number
                    )
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_users_username
            ON users(username)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_customers_name
            ON customers(name)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_invoices_customer
            ON invoices(customer_id)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_invoices_number
            ON invoices(invoice_number)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_invoices_date
            ON invoices(invoice_date)
            """
        )

        create_default_admin(
            connection
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# =========================================================
# إنشاء المدير الافتراضي
# =========================================================

def create_default_admin(connection):
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE username = %s
        """,
        (
            "admin",
        ),
    )

    admin_user = cursor.fetchone()

    if admin_user is not None:
        return

    password_hash = generate_password_hash(
        "Admin@123"
    )

    cursor.execute(
        """
        INSERT INTO users (
            full_name,
            username,
            password_hash,
            role,
            is_active
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s
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
        cursor = connection.cursor()

        cursor.execute(
            prepare_query(query),
            parameters,
        )

        return cursor.fetchall()

    finally:
        connection.close()


# =========================================================
# إحضار سجل واحد
# =========================================================

def fetch_one(query, parameters=()):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            prepare_query(query),
            parameters,
        )

        return cursor.fetchone()

    finally:
        connection.close()


# =========================================================
# تنفيذ إضافة أو تعديل أو حذف
# =========================================================

def execute_query(query, parameters=()):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        prepared_query = prepare_query(
            query
        ).strip()

        query_type = (
            prepared_query
            .split(None, 1)[0]
            .upper()
        )

        if (
            query_type == "INSERT"
            and "RETURNING" not in prepared_query.upper()
        ):
            prepared_query = (
                prepared_query.rstrip(";")
                + " RETURNING id"
            )

        cursor.execute(
            prepared_query,
            parameters,
        )

        result = None

        if query_type == "INSERT":
            inserted_row = cursor.fetchone()

            if inserted_row:
                result = inserted_row["id"]

        else:
            result = cursor.rowcount

        connection.commit()

        return result

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# =========================================================
# تنفيذ مجموعة أوامر
# =========================================================

def execute_script(script):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            script
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# =========================================================
# اختبار الاتصال
# =========================================================

def test_connection():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                current_database() AS database_name,
                CURRENT_TIMESTAMP AS server_time
            """
        )

        return cursor.fetchone()

    finally:
        connection.close()


# =========================================================
# تشغيل اختبار مستقل
# =========================================================

if __name__ == "__main__":
    try:
        connection_result = test_connection()

        print(
            "تم الاتصال بقاعدة البيانات بنجاح."
        )

        print(
            "Database:",
            connection_result["database_name"],
        )

        print(
            "Server time:",
            connection_result["server_time"],
        )

        initialize_database()

        print(
            "تم إنشاء الجداول والمستخدم الافتراضي بنجاح."
        )

    except Exception as error:
        print(
            "حدث خطأ:"
        )

        print(
            error
        )

        if error.__cause__:
            print(
                "التفاصيل:"
            )

            print(
                error.__cause__
            )
from pathlib import Path

import psycopg2
from werkzeug.utils import secure_filename

from database_postgres import get_connection


# =========================================================
# إعدادات الملفات
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

UPLOADS_DIRECTORY = (
    BASE_DIR
    / "static"
    / "uploads"
)

UPLOADS_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)

ALLOWED_LOGO_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


# =========================================================
# خطأ خاص بإعدادات الشركة
# =========================================================

class CompanySettingsError(Exception):
    """خطأ أثناء حفظ أو قراءة إعدادات الشركة."""

    pass


# =========================================================
# إنشاء جدول إعدادات الشركة
# =========================================================

def initialize_company_settings():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS company_settings (
                id INTEGER PRIMARY KEY
                    CHECK (id = 1),

                company_name TEXT DEFAULT '',

                commercial_name TEXT DEFAULT '',

                tax_registration_number TEXT DEFAULT '',

                commercial_registration_number TEXT DEFAULT '',

                phone TEXT DEFAULT '',

                email TEXT DEFAULT '',

                address TEXT DEFAULT '',

                website TEXT DEFAULT '',

                logo_filename TEXT DEFAULT '',

                invoice_footer TEXT DEFAULT '',

                updated_at TIMESTAMP
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            INSERT INTO company_settings (
                id,
                company_name,
                commercial_name,
                tax_registration_number,
                commercial_registration_number,
                phone,
                email,
                address,
                website,
                logo_filename,
                invoice_footer
            )
            VALUES (
                1,
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                ''
            )
            ON CONFLICT (id) DO NOTHING
            """
        )

        connection.commit()

    except psycopg2.Error as error:
        connection.rollback()

        raise CompanySettingsError(
            "تعذر إنشاء جدول إعدادات الشركة على PostgreSQL."
        ) from error

    finally:
        connection.close()


# =========================================================
# قراءة إعدادات الشركة
# =========================================================

def get_company_settings():
    initialize_company_settings()

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                company_name,
                commercial_name,
                tax_registration_number,
                commercial_registration_number,
                phone,
                email,
                address,
                website,
                logo_filename,
                invoice_footer,
                updated_at

            FROM company_settings

            WHERE id = 1
            """
        )

        return cursor.fetchone()

    except psycopg2.Error as error:
        raise CompanySettingsError(
            "تعذر قراءة إعدادات الشركة من PostgreSQL."
        ) from error

    finally:
        connection.close()


# =========================================================
# تنظيف النصوص
# =========================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


# =========================================================
# التحقق من ملف الشعار
# =========================================================

def validate_logo_file(logo_file):
    if logo_file is None:
        return False

    filename = clean_text(
        logo_file.filename
    )

    if not filename:
        return False

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in ALLOWED_LOGO_EXTENSIONS:
        raise CompanySettingsError(
            "صيغة الشعار غير مسموحة. استخدم PNG أو JPG أو WEBP."
        )

    return True


# =========================================================
# حفظ شعار الشركة
# =========================================================

def save_company_logo(logo_file):
    if not validate_logo_file(
        logo_file
    ):
        return ""

    original_filename = secure_filename(
        logo_file.filename
    )

    extension = Path(
        original_filename
    ).suffix.lower()

    saved_filename = (
        f"company_logo{extension}"
    )

    saved_path = (
        UPLOADS_DIRECTORY
        / saved_filename
    )

    remove_old_logo_files(
        except_filename=saved_filename
    )

    try:
        logo_file.save(
            saved_path
        )

    except OSError as error:
        raise CompanySettingsError(
            "تعذر حفظ شعار الشركة على الجهاز."
        ) from error

    return saved_filename


# =========================================================
# حذف الشعارات القديمة
# =========================================================

def remove_old_logo_files(
    except_filename="",
):
    for extension in ALLOWED_LOGO_EXTENSIONS:
        logo_path = (
            UPLOADS_DIRECTORY
            / f"company_logo{extension}"
        )

        if (
            logo_path.exists()
            and logo_path.name
            != except_filename
        ):
            try:
                logo_path.unlink()

            except OSError:
                pass


# =========================================================
# تحديث إعدادات الشركة
# =========================================================

def update_company_settings(
    company_name,
    commercial_name,
    tax_registration_number,
    commercial_registration_number,
    phone,
    email,
    address,
    website,
    invoice_footer,
    logo_file=None,
):
    initialize_company_settings()

    company_name = clean_text(
        company_name
    )

    commercial_name = clean_text(
        commercial_name
    )

    tax_registration_number = clean_text(
        tax_registration_number
    )

    commercial_registration_number = clean_text(
        commercial_registration_number
    )

    phone = clean_text(
        phone
    )

    email = clean_text(
        email
    )

    address = clean_text(
        address
    )

    website = clean_text(
        website
    )

    invoice_footer = clean_text(
        invoice_footer
    )

    if not company_name:
        raise CompanySettingsError(
            "اسم الشركة مطلوب."
        )

    current_settings = (
        get_company_settings()
    )

    logo_filename = (
        current_settings["logo_filename"]
        if current_settings
        else ""
    )

    if (
        logo_file is not None
        and clean_text(
            logo_file.filename
        )
    ):
        logo_filename = save_company_logo(
            logo_file
        )

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE company_settings

            SET
                company_name = %s,
                commercial_name = %s,
                tax_registration_number = %s,
                commercial_registration_number = %s,
                phone = %s,
                email = %s,
                address = %s,
                website = %s,
                logo_filename = %s,
                invoice_footer = %s,
                updated_at = CURRENT_TIMESTAMP

            WHERE id = 1
            """,
            (
                company_name,
                commercial_name,
                tax_registration_number,
                commercial_registration_number,
                phone,
                email,
                address,
                website,
                logo_filename,
                invoice_footer,
            ),
        )

        connection.commit()

    except psycopg2.Error as error:
        connection.rollback()

        raise CompanySettingsError(
            "تعذر حفظ إعدادات الشركة على PostgreSQL."
        ) from error

    finally:
        connection.close()


# =========================================================
# حذف شعار الشركة
# =========================================================

def delete_company_logo():
    initialize_company_settings()

    remove_old_logo_files()

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE company_settings

            SET
                logo_filename = '',
                updated_at = CURRENT_TIMESTAMP

            WHERE id = 1
            """
        )

        connection.commit()

    except psycopg2.Error as error:
        connection.rollback()

        raise CompanySettingsError(
            "تعذر حذف شعار الشركة من الإعدادات."
        ) from error

    finally:
        connection.close()


# =========================================================
# رابط الشعار داخل static
# =========================================================

def get_company_logo_path():
    settings = get_company_settings()

    if (
        settings is None
        or not settings["logo_filename"]
    ):
        return ""

    logo_path = (
        UPLOADS_DIRECTORY
        / settings["logo_filename"]
    )

    if not logo_path.exists():
        return ""

    return (
        "uploads/"
        + settings["logo_filename"]
    )
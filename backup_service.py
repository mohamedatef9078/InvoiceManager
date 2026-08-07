import json
import tempfile
from datetime import datetime
from pathlib import Path

from database_postgres import get_connection


class BackupError(Exception):
    """خطأ أثناء إنشاء أو استعادة النسخة الاحتياطية."""
    pass


REQUIRED_TABLES = {
    "users",
    "customers",
    "invoices",
}


# =========================================================
# مكان الملفات المؤقتة
# =========================================================

def get_temporary_directory():
    """
    استخدام مجلد مؤقت قابل للكتابة.

    يعمل على:
    - Windows
    - Linux
    - Vercel
    """

    temporary_directory = Path(
        tempfile.gettempdir()
    ) / "invoice_manager"

    temporary_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return temporary_directory


# =========================================================
# تحويل البيانات إلى JSON
# =========================================================

def json_serializer(value):
    """
    تحويل القيم غير المدعومة مباشرة في JSON
    مثل datetime والتاريخ.
    """

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


# =========================================================
# إنشاء نسخة احتياطية من PostgreSQL
# =========================================================

def create_backup_file():
    """
    إنشاء نسخة احتياطية من PostgreSQL بصيغة JSON.

    تشمل:
    - المستخدمين
    - العملاء
    - الفواتير
    """

    connection = None

    try:
        connection = get_connection()

        cursor = connection.cursor()

        backup_data = {
            "backup_version": 1,
            "created_at": datetime.now().isoformat(),
            "database_type": "postgresql",
            "tables": {},
        }

        table_names = (
            "users",
            "customers",
            "invoices",
        )

        for table_name in table_names:
            cursor.execute(
                f"""
                SELECT *
                FROM {table_name}
                ORDER BY id
                """
            )

            rows = cursor.fetchall()

            backup_data["tables"][table_name] = [
                dict(row)
                for row in rows
            ]

        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        backup_filename = (
            f"invoice_backup_{timestamp}.json"
        )

        backup_path = (
            get_temporary_directory()
            / backup_filename
        )

        with backup_path.open(
            "w",
            encoding="utf-8",
        ) as backup_file:
            json.dump(
                backup_data,
                backup_file,
                ensure_ascii=False,
                indent=2,
                default=json_serializer,
            )

        if not validate_database(
            backup_path
        ):
            backup_path.unlink(
                missing_ok=True
            )

            raise BackupError(
                "تعذر التحقق من سلامة النسخة الاحتياطية."
            )

        return backup_path

    except BackupError:
        raise

    except Exception as error:
        print(
            "Backup creation error:",
            repr(error),
        )

        raise BackupError(
            "حدث خطأ أثناء إنشاء النسخة الاحتياطية السحابية."
        ) from error

    finally:
        if connection is not None:
            connection.close()


# =========================================================
# التحقق من ملف النسخة الاحتياطية
# =========================================================

def validate_database(database_path):
    """
    التأكد من أن ملف JSON نسخة احتياطية صحيحة للبرنامج.
    """

    try:
        database_path = Path(
            database_path
        )

        if not database_path.exists():
            return False

        if database_path.stat().st_size == 0:
            return False

        with database_path.open(
            "r",
            encoding="utf-8",
        ) as backup_file:
            backup_data = json.load(
                backup_file
            )

        if not isinstance(
            backup_data,
            dict,
        ):
            return False

        if (
            backup_data.get(
                "database_type"
            )
            != "postgresql"
        ):
            return False

        tables = backup_data.get(
            "tables"
        )

        if not isinstance(
            tables,
            dict,
        ):
            return False

        if not REQUIRED_TABLES.issubset(
            tables.keys()
        ):
            return False

        for table_name in REQUIRED_TABLES:
            if not isinstance(
                tables.get(table_name),
                list,
            ):
                return False

        return True

    except (
        OSError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ):
        return False


# =========================================================
# قراءة ملف الاستعادة
# =========================================================

def load_backup_data(backup_path):
    try:
        with Path(backup_path).open(
            "r",
            encoding="utf-8",
        ) as backup_file:
            return json.load(
                backup_file
            )

    except Exception as error:
        raise BackupError(
            "تعذر قراءة ملف النسخة الاحتياطية."
        ) from error


# =========================================================
# استعادة نسخة احتياطية إلى PostgreSQL
# =========================================================

def restore_backup_file(uploaded_file):
    """
    استعادة البيانات من ملف JSON إلى PostgreSQL.

    تنبيه:
    الاستعادة تستبدل البيانات الحالية
    داخل الجداول الأساسية.
    """

    if uploaded_file is None:
        raise BackupError(
            "لم يتم اختيار ملف للاستعادة."
        )

    filename = (
        uploaded_file.filename
        or ""
    ).strip()

    if not filename:
        raise BackupError(
            "لم يتم اختيار ملف للاستعادة."
        )

    if (
        Path(filename).suffix.lower()
        != ".json"
    ):
        raise BackupError(
            "نوع الملف غير مسموح. اختر نسخة احتياطية بصيغة JSON."
        )

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    temporary_path = (
        get_temporary_directory()
        / f"restore_{timestamp}.json"
    )

    emergency_backup = None
    connection = None

    try:
        uploaded_file.save(
            str(temporary_path)
        )

        if not validate_database(
            temporary_path
        ):
            raise BackupError(
                "الملف المختار ليس نسخة احتياطية سليمة للبرنامج."
            )

        # =================================================
        # إنشاء نسخة أمان تلقائية قبل الاستعادة
        # =================================================

        emergency_backup = (
            create_backup_file()
        )

        backup_data = load_backup_data(
            temporary_path
        )

        tables = backup_data[
            "tables"
        ]

        connection = get_connection()

        cursor = connection.cursor()

        # =================================================
        # حذف البيانات الحالية
        # =================================================

        cursor.execute(
            """
            TRUNCATE TABLE
                invoices,
                customers,
                users
            RESTART IDENTITY
            CASCADE
            """
        )

        # =================================================
        # استعادة المستخدمين
        # =================================================

        for row in tables["users"]:
            cursor.execute(
                """
                INSERT INTO users (
                    id,
                    full_name,
                    username,
                    password_hash,
                    role,
                    is_active,
                    created_at
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    row["id"],
                    row["full_name"],
                    row["username"],
                    row["password_hash"],
                    row["role"],
                    row["is_active"],
                    row["created_at"],
                ),
            )

        # =================================================
        # استعادة العملاء
        # =================================================

        for row in tables["customers"]:
            cursor.execute(
                """
                INSERT INTO customers (
                    id,
                    name,
                    phone,
                    notes,
                    created_at
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
                    row["id"],
                    row["name"],
                    row.get(
                        "phone",
                        "",
                    ),
                    row.get(
                        "notes",
                        "",
                    ),
                    row["created_at"],
                ),
            )

        # =================================================
        # استعادة الفواتير
        # =================================================

        for row in tables["invoices"]:
            cursor.execute(
                """
                INSERT INTO invoices (
                    id,
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

                    xml_filename,
                    created_at
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,

                    %s,
                    %s,
                    %s,

                    %s,
                    %s,
                    %s,

                    %s,
                    %s,
                    %s,
                    %s,

                    %s,
                    %s
                )
                """,
                (
                    row["id"],

                    row["customer_id"],

                    row["invoice_number"],

                    row.get(
                        "invoice_date",
                        "",
                    ),

                    row.get(
                        "buyer_name",
                        "",
                    ),

                    row.get(
                        "buyer_registration",
                        "",
                    ),

                    row.get(
                        "buyer_address",
                        "",
                    ),

                    row.get(
                        "seller_name",
                        "",
                    ),

                    row.get(
                        "seller_registration",
                        "",
                    ),

                    row.get(
                        "seller_address",
                        "",
                    ),

                    row.get(
                        "before_tax",
                        0,
                    ),

                    row.get(
                        "vat",
                        0,
                    ),

                    row.get(
                        "withholding_tax",
                        0,
                    ),

                    row.get(
                        "after_tax",
                        0,
                    ),

                    row.get(
                        "xml_filename",
                        "",
                    ),

                    row["created_at"],
                ),
            )

        # =================================================
        # ضبط عدادات ID
        # =================================================

        for table_name in (
            "users",
            "customers",
            "invoices",
        ):
            cursor.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence(
                        '{table_name}',
                        'id'
                    ),

                    COALESCE(
                        (
                            SELECT MAX(id)
                            FROM {table_name}
                        ),
                        1
                    ),

                    (
                        SELECT COUNT(*)
                        FROM {table_name}
                    ) > 0
                )
                """
            )

        connection.commit()

        return emergency_backup

    except BackupError:
        if connection is not None:
            connection.rollback()

        raise

    except Exception as error:
        if connection is not None:
            connection.rollback()

        print(
            "Backup restore error:",
            repr(error),
        )

        raise BackupError(
            "حدث خطأ أثناء استعادة النسخة الاحتياطية السحابية."
        ) from error

    finally:
        if connection is not None:
            connection.close()

        temporary_path.unlink(
            missing_ok=True
        )
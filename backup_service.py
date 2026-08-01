import json
from datetime import datetime
from pathlib import Path

from database_postgres import get_connection


class BackupError(Exception):
    """خطأ أثناء إنشاء أو استعادة النسخة الاحتياطية."""


REQUIRED_TABLES = {
    "users",
    "customers",
    "invoices",
}


# =========================================================
# مكان حفظ النسخ الاحتياطية
# =========================================================

def get_backups_directory():
    backups_directory = (
        Path(__file__).resolve().parent
        / "backups"
    )

    backups_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return backups_directory


# =========================================================
# إنشاء نسخة احتياطية من PostgreSQL
# =========================================================

def create_backup_file():
    """
    إنشاء نسخة احتياطية من جداول PostgreSQL بصيغة JSON.

    تشمل:
    - المستخدمين
    - العملاء
    - الفواتير
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        backup_data = {
            "backup_version": 1,
            "created_at": datetime.now().isoformat(),
            "database_type": "postgresql",
            "tables": {},
        }

        for table_name in (
            "users",
            "customers",
            "invoices",
        ):
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

        backup_path = (
            get_backups_directory()
            / f"invoice_backup_{timestamp}.json"
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
                default=str,
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
        raise BackupError(
            "حدث خطأ أثناء إنشاء النسخة الاحتياطية السحابية."
        ) from error

    finally:
        connection.close()


# =========================================================
# التحقق من ملف النسخة الاحتياطية
# =========================================================

def validate_database(database_path):
    """
    التأكد من أن ملف JSON نسخة احتياطية صحيحة للبرنامج.
    """

    database_path = Path(
        database_path
    )

    if not database_path.exists():
        return False

    if database_path.stat().st_size == 0:
        return False

    try:
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
            backup_data.get("database_type")
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
                tables[table_name],
                list,
            ):
                return False

        return True

    except (
        OSError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return False


# =========================================================
# استعادة نسخة احتياطية إلى PostgreSQL
# =========================================================

def restore_backup_file(uploaded_file):
    """
    استعادة البيانات من ملف JSON إلى PostgreSQL.

    تنبيه:
    الاستعادة تستبدل البيانات الحالية في الجداول الأساسية.
    """

    if uploaded_file is None:
        raise BackupError(
            "لم يتم اختيار ملف للاستعادة."
        )

    filename = (
        uploaded_file.filename or ""
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

    temporary_directory = (
        Path(__file__).resolve().parent
        / "temporary_backups"
    )

    temporary_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    temporary_path = (
        temporary_directory
        / f"restore_{timestamp}.json"
    )

    emergency_backup = None

    try:
        uploaded_file.save(
            temporary_path
        )

        if not validate_database(
            temporary_path
        ):
            raise BackupError(
                "الملف المختار ليس نسخة احتياطية سليمة للبرنامج."
            )

        # إنشاء نسخة أمان تلقائية قبل الاستعادة
        emergency_backup = (
            create_backup_file()
        )

        with temporary_path.open(
            "r",
            encoding="utf-8",
        ) as backup_file:
            backup_data = json.load(
                backup_file
            )

        tables = backup_data["tables"]

        connection = get_connection()

        try:
            cursor = connection.cursor()

            # حذف البيانات بالترتيب الصحيح
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

            # استعادة المستخدمين
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
                        %s, %s, %s, %s,
                        %s, %s, %s
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

            # استعادة العملاء
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
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        row["id"],
                        row["name"],
                        row.get("phone", ""),
                        row.get("notes", ""),
                        row["created_at"],
                    ),
                )

            # استعادة الفواتير
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
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        row["id"],
                        row["customer_id"],
                        row["invoice_number"],
                        row.get("invoice_date", ""),
                        row.get("buyer_name", ""),
                        row.get("buyer_registration", ""),
                        row.get("buyer_address", ""),
                        row.get("seller_name", ""),
                        row.get("seller_registration", ""),
                        row.get("seller_address", ""),
                        row.get("before_tax", 0),
                        row.get("vat", 0),
                        row.get("withholding_tax", 0),
                        row.get("after_tax", 0),
                        row.get("xml_filename", ""),
                        row["created_at"],
                    ),
                )

            # ضبط العدادات بعد إدخال IDs القديمة
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
                        true
                    )
                    """
                )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

        return emergency_backup

    except BackupError:
        raise

    except Exception as error:
        raise BackupError(
            "حدث خطأ أثناء استعادة النسخة الاحتياطية السحابية."
        ) from error

    finally:
        temporary_path.unlink(
            missing_ok=True
        )
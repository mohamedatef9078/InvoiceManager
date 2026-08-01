from functools import wraps
from io import BytesIO
from datetime import datetime

import xlsxwriter

from flask import (
    Blueprint,
    flash,
    redirect,
    send_file,
    session,
    url_for,
)

from database_postgres import (
    fetch_all,
    fetch_one,
)

from settings_service import (
    get_company_settings,
)


excel_blueprint = Blueprint(
    "excel_export",
    __name__,
)


# =========================================================
# حماية الصفحة
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


# =========================================================
# تصدير التقارير إلى Excel
# =========================================================

@excel_blueprint.route(
    "/reports/export-excel"
)
@login_required
def export_reports_excel():
    company_settings = get_company_settings()

    statistics = fetch_one(
        """
        SELECT
            COUNT(*) AS invoice_count,

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

    customer_count = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM customers
        """
    )

    customer_reports = fetch_all(
        """
        SELECT
            customers.name,

            customers.phone,

            COUNT(
                invoices.id
            ) AS invoice_count,

            COALESCE(
                SUM(invoices.before_tax),
                0
            ) AS before_tax,

            COALESCE(
                SUM(invoices.vat),
                0
            ) AS vat,

            COALESCE(
                SUM(invoices.withholding_tax),
                0
            ) AS withholding_tax,

            COALESCE(
                SUM(invoices.after_tax),
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

    invoices = fetch_all(
        """
        SELECT
            invoices.invoice_number,
            invoices.invoice_date,

            customers.name
                AS customer_name,

            invoices.buyer_name,
            invoices.seller_name,

            invoices.before_tax,
            invoices.vat,
            invoices.withholding_tax,
            invoices.after_tax

        FROM invoices

        INNER JOIN customers
            ON customers.id =
               invoices.customer_id

        ORDER BY invoices.id DESC
        """
    )

    output = BytesIO()

    workbook = xlsxwriter.Workbook(
        output,
        {
            "in_memory": True,
        },
    )

    workbook.set_properties(
        {
            "title":
                "تقرير إدارة الفواتير",

            "subject":
                "العملاء والفواتير والإجماليات",

            "author":
                company_settings["company_name"]
                or "برنامج إدارة الفواتير",
        }
    )

    # =====================================================
    # التنسيقات
    # =====================================================

    title_format = workbook.add_format(
        {
            "bold": True,
            "font_size": 18,
            "font_color": "#FFFFFF",
            "bg_color": "#1D4ED8",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#1D4ED8",
        }
    )

    subtitle_format = workbook.add_format(
        {
            "bold": True,
            "font_size": 11,
            "font_color": "#475569",
            "align": "center",
            "valign": "vcenter",
        }
    )

    section_format = workbook.add_format(
        {
            "bold": True,
            "font_size": 14,
            "font_color": "#1E3A8A",
            "bg_color": "#DBEAFE",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#BFDBFE",
        }
    )

    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#2563EB",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#1D4ED8",
            "text_wrap": True,
        }
    )

    label_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#334155",
            "bg_color": "#F8FAFC",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
        }
    )

    value_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#0F172A",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
        }
    )

    text_format = workbook.add_format(
        {
            "align": "right",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
        }
    )

    number_format = workbook.add_format(
        {
            "num_format": "#,##0.00",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
        }
    )

    total_number_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#15803D",
            "bg_color": "#F0FDF4",
            "num_format": "#,##0.00",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#BBF7D0",
        }
    )

    date_format = workbook.add_format(
        {
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
        }
    )

    # =====================================================
    # ورقة الملخص
    # =====================================================

    summary_sheet = workbook.add_worksheet(
        "الملخص"
    )

    summary_sheet.right_to_left()

    summary_sheet.hide_gridlines(2)

    summary_sheet.set_column(
        "A:A",
        4,
    )

    summary_sheet.set_column(
        "B:B",
        31,
    )

    summary_sheet.set_column(
        "C:C",
        22,
    )

    summary_sheet.set_row(
        0,
        34,
    )

    summary_sheet.merge_range(
        "A1:C1",
        company_settings["company_name"]
        or "برنامج إدارة الفواتير",
        title_format,
    )

    summary_sheet.merge_range(
        "A2:C2",
        "تقرير شامل للعملاء والفواتير",
        subtitle_format,
    )

    summary_sheet.merge_range(
        "A4:C4",
        "ملخص عام",
        section_format,
    )

    summary_rows = [
        (
            "عدد العملاء",
            customer_count["total"],
        ),
        (
            "عدد الفواتير",
            statistics["invoice_count"],
        ),
        (
            "الإجمالي قبل الضريبة",
            statistics["before_tax"],
        ),
        (
            "ضريبة القيمة المضافة",
            statistics["vat"],
        ),
        (
            "خصم تحت حساب الضريبة",
            statistics["withholding_tax"],
        ),
        (
            "الإجمالي بعد الضريبة",
            statistics["after_tax"],
        ),
    ]

    current_row = 4

    for label, value in summary_rows:
        summary_sheet.write(
            current_row,
            1,
            label,
            label_format,
        )

        if isinstance(
            value,
            (int, float),
        ) and label not in {
            "عدد العملاء",
            "عدد الفواتير",
        }:
            summary_sheet.write_number(
                current_row,
                2,
                float(value or 0),
                total_number_format
                if label
                == "الإجمالي بعد الضريبة"
                else number_format,
            )

        else:
            summary_sheet.write(
                current_row,
                2,
                value,
                value_format,
            )

        current_row += 1

    summary_sheet.write(
        current_row + 1,
        1,
        "تاريخ إنشاء التقرير",
        label_format,
    )

    summary_sheet.write(
        current_row + 1,
        2,
        datetime.now().strftime(
            "%d/%m/%Y %H:%M"
        ),
        value_format,
    )

    # =====================================================
    # ورقة العملاء
    # =====================================================

    customers_sheet = workbook.add_worksheet(
        "تقرير العملاء"
    )

    customers_sheet.right_to_left()

    customers_sheet.freeze_panes(
        1,
        0,
    )

    customers_sheet.hide_gridlines(2)

    customers_sheet.set_column(
        "A:A",
        7,
    )

    customers_sheet.set_column(
        "B:B",
        27,
    )

    customers_sheet.set_column(
        "C:C",
        18,
    )

    customers_sheet.set_column(
        "D:D",
        14,
    )

    customers_sheet.set_column(
        "E:H",
        20,
    )

    customer_headers = [
        "#",
        "اسم العميل",
        "رقم الهاتف",
        "عدد الفواتير",
        "قبل الضريبة",
        "ضريبة القيمة المضافة",
        "خصم تحت حساب الضريبة",
        "الإجمالي بعد الضريبة",
    ]

    for column, header in enumerate(
        customer_headers
    ):
        customers_sheet.write(
            0,
            column,
            header,
            header_format,
        )

    for index, customer in enumerate(
        customer_reports,
        start=1,
    ):
        customers_sheet.write_number(
            index,
            0,
            index,
            value_format,
        )

        customers_sheet.write(
            index,
            1,
            customer["name"] or "",
            text_format,
        )

        customers_sheet.write(
            index,
            2,
            customer["phone"] or "",
            text_format,
        )

        customers_sheet.write_number(
            index,
            3,
            int(
                customer["invoice_count"]
                or 0
            ),
            value_format,
        )

        customers_sheet.write_number(
            index,
            4,
            float(
                customer["before_tax"]
                or 0
            ),
            number_format,
        )

        customers_sheet.write_number(
            index,
            5,
            float(
                customer["vat"]
                or 0
            ),
            number_format,
        )

        customers_sheet.write_number(
            index,
            6,
            float(
                customer[
                    "withholding_tax"
                ]
                or 0
            ),
            number_format,
        )

        customers_sheet.write_number(
            index,
            7,
            float(
                customer["after_tax"]
                or 0
            ),
            total_number_format,
        )

    if customer_reports:
        last_row = (
            len(customer_reports)
            + 1
        )

        customers_sheet.autofilter(
            0,
            0,
            last_row - 1,
            7,
        )

    # =====================================================
    # ورقة الفواتير
    # =====================================================

    invoices_sheet = workbook.add_worksheet(
        "الفواتير"
    )

    invoices_sheet.right_to_left()

    invoices_sheet.freeze_panes(
        1,
        0,
    )

    invoices_sheet.hide_gridlines(2)

    invoices_sheet.set_column(
        "A:A",
        7,
    )

    invoices_sheet.set_column(
        "B:B",
        20,
    )

    invoices_sheet.set_column(
        "C:C",
        15,
    )

    invoices_sheet.set_column(
        "D:F",
        25,
    )

    invoices_sheet.set_column(
        "G:J",
        19,
    )

    invoice_headers = [
        "#",
        "رقم الفاتورة",
        "التاريخ",
        "العميل",
        "اسم المشتري",
        "اسم البائع",
        "قبل الضريبة",
        "ضريبة القيمة المضافة",
        "خصم تحت حساب الضريبة",
        "الإجمالي بعد الضريبة",
    ]

    for column, header in enumerate(
        invoice_headers
    ):
        invoices_sheet.write(
            0,
            column,
            header,
            header_format,
        )

    for index, invoice in enumerate(
        invoices,
        start=1,
    ):
        invoices_sheet.write_number(
            index,
            0,
            index,
            value_format,
        )

        invoices_sheet.write(
            index,
            1,
            invoice[
                "invoice_number"
            ]
            or "",
            text_format,
        )

        invoices_sheet.write(
            index,
            2,
            invoice["invoice_date"]
            or "",
            date_format,
        )

        invoices_sheet.write(
            index,
            3,
            invoice["customer_name"]
            or "",
            text_format,
        )

        invoices_sheet.write(
            index,
            4,
            invoice["buyer_name"]
            or "",
            text_format,
        )

        invoices_sheet.write(
            index,
            5,
            invoice["seller_name"]
            or "",
            text_format,
        )

        invoices_sheet.write_number(
            index,
            6,
            float(
                invoice["before_tax"]
                or 0
            ),
            number_format,
        )

        invoices_sheet.write_number(
            index,
            7,
            float(
                invoice["vat"]
                or 0
            ),
            number_format,
        )

        invoices_sheet.write_number(
            index,
            8,
            float(
                invoice[
                    "withholding_tax"
                ]
                or 0
            ),
            number_format,
        )

        invoices_sheet.write_number(
            index,
            9,
            float(
                invoice["after_tax"]
                or 0
            ),
            total_number_format,
        )

    if invoices:
        last_row = len(invoices) + 1

        invoices_sheet.autofilter(
            0,
            0,
            last_row - 1,
            9,
        )

    workbook.close()

    output.seek(0)

    file_name = (
        "invoice_report_"
        + datetime.now().strftime(
            "%Y-%m-%d_%H-%M"
        )
        + ".xlsx"
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=file_name,
        mimetype=(
            "application/"
            "vnd.openxmlformats-"
            "officedocument."
            "spreadsheetml.sheet"
        ),
    )
from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)

from database_postgres import fetch_one
from settings_service import (
    get_company_logo_path,
    get_company_settings,
)


print_blueprint = Blueprint(
    "print_invoice",
    __name__,
)


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


@print_blueprint.route(
    "/invoices/<int:invoice_id>/print"
)
@login_required
def print_invoice(invoice_id):
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

    company_settings = (
        get_company_settings()
    )

    logo_path = (
        get_company_logo_path()
    )

    return render_template(
        "invoice_print.html",
        invoice=invoice,
        company_settings=company_settings,
        logo_path=logo_path,
    )
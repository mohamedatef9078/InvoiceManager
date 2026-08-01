from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from settings_service import (
    CompanySettingsError,
    delete_company_logo,
    get_company_settings,
    get_company_logo_path,
    update_company_settings,
)


settings_blueprint = Blueprint(
    "settings",
    __name__,
)


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
                "ليس لديك صلاحية للوصول إلى الإعدادات.",
                "danger",
            )

            return redirect(
                url_for("dashboard")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


@settings_blueprint.route(
    "/settings",
    methods=["GET", "POST"],
)
@admin_required
def settings_page():
    if request.method == "POST":
        try:
            update_company_settings(
                company_name=request.form.get(
                    "company_name",
                    "",
                ),
                commercial_name=request.form.get(
                    "commercial_name",
                    "",
                ),
                tax_registration_number=request.form.get(
                    "tax_registration_number",
                    "",
                ),
                commercial_registration_number=request.form.get(
                    "commercial_registration_number",
                    "",
                ),
                phone=request.form.get(
                    "phone",
                    "",
                ),
                email=request.form.get(
                    "email",
                    "",
                ),
                address=request.form.get(
                    "address",
                    "",
                ),
                website=request.form.get(
                    "website",
                    "",
                ),
                invoice_footer=request.form.get(
                    "invoice_footer",
                    "",
                ),
                logo_file=request.files.get(
                    "logo_file"
                ),
            )

            flash(
                "تم حفظ إعدادات الشركة بنجاح.",
                "success",
            )

        except CompanySettingsError as error:
            flash(
                str(error),
                "danger",
            )

        return redirect(
            url_for("settings.settings_page")
        )

    company_settings = get_company_settings()
    logo_path = get_company_logo_path()

    return render_template(
        "settings.html",
        company_settings=company_settings,
        logo_path=logo_path,
    )


@settings_blueprint.route(
    "/settings/delete-logo",
    methods=["POST"],
)
@admin_required
def delete_logo():
    try:
        delete_company_logo()

        flash(
            "تم حذف شعار الشركة.",
            "success",
        )

    except CompanySettingsError as error:
        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for("settings.settings_page")
    )
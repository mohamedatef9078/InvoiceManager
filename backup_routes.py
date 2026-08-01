from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from backup_service import (
    BackupError,
    create_backup_file,
    restore_backup_file,
)


backup_blueprint = Blueprint(
    "backup",
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
                "ليس لديك صلاحية للوصول إلى النسخ الاحتياطي.",
                "danger",
            )

            return redirect(
                url_for("dashboard")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


@backup_blueprint.route("/backup")
@admin_required
def backup_page():
    return render_template(
        "backup.html"
    )


@backup_blueprint.route("/backup/download")
@admin_required
def download_backup():
    try:
        backup_path = create_backup_file()

        return send_file(
            backup_path,
            as_attachment=True,
            download_name=backup_path.name,
        )

    except BackupError as error:
        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for("backup.backup_page")
        )


@backup_blueprint.route(
    "/backup/restore",
    methods=["POST"],
)
@admin_required
def restore_backup():
    uploaded_file = request.files.get(
        "backup_file"
    )

    try:
        restore_backup_file(
            uploaded_file
        )

        session.clear()

        flash(
            "تمت استعادة النسخة الاحتياطية بنجاح. سجّل الدخول مرة أخرى.",
            "success",
        )

        return redirect(
            url_for("login")
        )

    except BackupError as error:
        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for("backup.backup_page")
        )
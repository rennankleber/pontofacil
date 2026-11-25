from flask import abort, request
from flask_login import current_user
from app.models import User


def get_admin_scope():
    if current_user.role == "admin":
        if current_user.company_id is None:
            abort(403)
        return current_user.company_id, current_user

    if current_user.role != "owner":
        abort(403)

    admin_id = request.values.get("admin_id", "").strip()
    if not admin_id.isdigit():
        abort(403)
    admin = User.query.filter_by(id=int(admin_id), role="admin").first_or_404()
    if admin.company_id is None:
        abort(404)
    return admin.company_id, admin

from datetime import datetime, time, timedelta
from flask import Blueprint, redirect, render_template, url_for
from flask_login import login_required, current_user
from app.models import User, Employee, Punch
from app.time_utils import local_today

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def dashboard():
    if current_user.role == "owner":
        return redirect(url_for("owner.index"))

    today = local_today()
    if current_user.role == "admin":
        users_count = User.query.filter_by(
            role="employee",
            company_id=current_user.company_id,
        ).count()
        employees_count = Employee.query.filter_by(
            active=True,
            company_id=current_user.company_id,
        ).count()
        punches_today = None
        employees = Employee.query.filter_by(
            company_id=current_user.company_id,
        ).order_by(Employee.name).all()
        punches = Punch.query.join(User).filter(
            User.company_id == current_user.company_id,
            Punch.occurred_at >= datetime.combine(today, time.min),
            Punch.occurred_at < datetime.combine(today + timedelta(days=1), time.min),
        ).order_by(Punch.occurred_at).all()
        punches_by_user = {}
        for punch in punches:
            punches_by_user.setdefault(punch.user_id, {})[punch.punch_type] = punch.occurred_at.strftime("%H:%M")
        daily_employee_punches = [
            {
                "employee": employee,
                "punches": punches_by_user.get(employee.user_id, {}),
            }
            for employee in employees
        ]
    else:
        users_count = employees_count = daily_employee_punches = None
        punches_today = Punch.query.filter(
            Punch.user_id == current_user.id,
            Punch.occurred_at >= datetime.combine(today, time.min),
            Punch.occurred_at < datetime.combine(today + timedelta(days=1), time.min),
        ).count()
    return render_template(
        "dashboard.html",
        users_count=users_count,
        employees_count=employees_count,
        punches_today=punches_today,
        daily_employee_punches=daily_employee_punches,
    )

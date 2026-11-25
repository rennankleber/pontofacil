from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Employee, User
from app.company_scope import get_admin_scope
from app.profile_validation import (
    is_valid_cpf,
    normalize_cpf,
    parse_birth_date,
    profile_identity_conflicts,
)

employees_bp = Blueprint("employees", __name__)

def get_company_employee(employee_id, company_id):
    return Employee.query.filter_by(
        id=employee_id,
        company_id=company_id,
    ).first_or_404()

@employees_bp.route("/")
@login_required
def index():
    company_id, selected_admin = get_admin_scope()
    employees = Employee.query.filter_by(
        company_id=company_id,
    ).order_by(Employee.name).all()
    owner_admin_id = selected_admin.id if current_user.role == "owner" else None
    return render_template(
        "employees.html",
        employees=employees,
        selected_admin=selected_admin,
        owner_admin_id=owner_admin_id,
    )

@employees_bp.route("/novo", methods=["GET", "POST"])
@login_required
def create():
    company_id, selected_admin = get_admin_scope()
    owner_admin_id = selected_admin.id if current_user.role == "owner" else None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        registration = request.form.get("registration", "").strip()
        cpf = normalize_cpf(request.form.get("cpf", ""))
        birth_date_input = request.form.get("birth_date", "")
        birth_date = parse_birth_date(birth_date_input)
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        department = request.form.get("department", "").strip()
        position = request.form.get("position", "").strip()
        cpf_conflict, registration_conflict = profile_identity_conflicts(
            cpf,
            registration,
        )
        if not all(
            [
                name,
                registration,
                cpf,
                birth_date_input,
                email,
                password,
                department,
                position,
            ]
        ):
            flash("Preencha todos os campos do funcionário.", "danger")
        elif (
            len(name) > 120
            or len(registration) > 30
            or len(email) > 160
            or len(department) > 80
            or len(position) > 80
        ):
            flash("Confira o tamanho dos campos informados.", "danger")
        elif not is_valid_cpf(cpf):
            flash("Informe um CPF válido com 11 dígitos.", "danger")
        elif birth_date is None:
            flash("Informe uma data de nascimento válida.", "danger")
        elif birth_date > date.today():
            flash("A data de nascimento não pode estar no futuro.", "danger")
        elif cpf_conflict:
            flash("Este CPF já está cadastrado.", "danger")
        elif registration_conflict:
            flash("Esta matrícula já está cadastrada.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado.", "danger")
        elif len(password) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "danger")
        else:
            user = User(
                name=name,
                email=email,
                role="employee",
                company_id=company_id,
            )
            user.set_password(password)
            employee = Employee(
                name=name,
                registration=registration,
                cpf=cpf,
                birth_date=birth_date,
                company_id=company_id,
                department=department,
                position=position,
                user=user,
            )
            db.session.add(user)
            db.session.add(employee)
            db.session.commit()
            flash("Funcionário cadastrado com acesso ao sistema.", "success")
            return redirect(url_for("employees.index", admin_id=owner_admin_id))
    return render_template(
        "employee_form.html",
        selected_admin=selected_admin,
        owner_admin_id=owner_admin_id,
    )

@employees_bp.route("/<int:employee_id>/editar", methods=["GET", "POST"])
@login_required
def edit(employee_id):
    company_id, selected_admin = get_admin_scope()
    owner_admin_id = selected_admin.id if current_user.role == "owner" else None
    employee = get_company_employee(employee_id, company_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        registration = request.form.get("registration", "").strip()
        cpf = normalize_cpf(request.form.get("cpf", ""))
        birth_date_input = request.form.get("birth_date", "")
        birth_date = parse_birth_date(birth_date_input)
        email = request.form.get("email", "").strip().lower()
        department = request.form.get("department", "").strip()
        position = request.form.get("position", "").strip()
        cpf_conflict, registration_conflict = profile_identity_conflicts(
            cpf,
            registration,
            employee_id=employee.id,
        )
        if not all(
            [name, registration, cpf, birth_date_input, department, position]
        ) or (employee.user and not email):
            flash("Preencha todos os campos do funcionário.", "danger")
        elif (
            len(name) > 120
            or len(registration) > 30
            or len(email) > 160
            or len(department) > 80
            or len(position) > 80
        ):
            flash("Confira o tamanho dos campos informados.", "danger")
        elif not is_valid_cpf(cpf):
            flash("Informe um CPF válido com 11 dígitos.", "danger")
        elif birth_date is None:
            flash("Informe uma data de nascimento válida.", "danger")
        elif birth_date > date.today():
            flash("A data de nascimento não pode estar no futuro.", "danger")
        elif cpf_conflict:
            flash("Este CPF já está cadastrado.", "danger")
        elif registration_conflict:
            flash("Esta matrícula já está cadastrada.", "danger")
        elif employee.user and User.query.filter(User.email == email, User.id != employee.user.id).first():
            flash("Este e-mail já está cadastrado.", "danger")
        else:
            employee.name = name
            employee.registration = registration
            employee.cpf = cpf
            employee.birth_date = birth_date
            employee.department = department
            employee.position = position
            if employee.user:
                employee.user.name = name
                employee.user.email = email
            db.session.commit()
            flash("Funcionário atualizado.", "success")
            return redirect(url_for("employees.index", admin_id=owner_admin_id))
    return render_template(
        "employee_form.html",
        employee=employee,
        selected_admin=selected_admin,
        owner_admin_id=owner_admin_id,
    )

@employees_bp.route("/<int:employee_id>/excluir", methods=["POST"])
@login_required
def delete(employee_id):
    company_id, selected_admin = get_admin_scope()
    owner_admin_id = selected_admin.id if current_user.role == "owner" else None
    employee = get_company_employee(employee_id, company_id)
    # Preserva o histórico de ponto: desativa o funcionário e seu acesso.
    employee.active = False
    if employee.user:
        employee.user.active = False
    db.session.commit()
    flash("Funcionário desativado.", "warning")
    return redirect(url_for("employees.index", admin_id=owner_admin_id))

@employees_bp.route("/<int:employee_id>/ativar", methods=["POST"])
@login_required
def activate(employee_id):
    company_id, selected_admin = get_admin_scope()
    owner_admin_id = selected_admin.id if current_user.role == "owner" else None
    employee = get_company_employee(employee_id, company_id)
    employee.active = True
    if employee.user:
        employee.user.active = True
    db.session.commit()
    flash("Funcionário ativado.", "success")
    return redirect(url_for("employees.index", admin_id=owner_admin_id))

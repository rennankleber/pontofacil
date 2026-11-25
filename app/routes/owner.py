import re
from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.models import (
    Company,
    Employee,
    Punch,
    PunchCorrection,
    SupportConversation,
    SupportMessage,
    User,
)
from app.profile_validation import (
    is_valid_cpf,
    normalize_cpf,
    parse_birth_date,
    profile_identity_conflicts,
)

owner_bp = Blueprint("owner", __name__)


def normalize_cnpj(value):
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def valid_cnpj_format(value):
    return len(value) == 14 and value[:12].isalnum() and value[-2:].isdigit()


def owner_required():
    if current_user.role != "owner":
        abort(403)


@owner_bp.route("/")
@login_required
def index():
    owner_required()
    company_count = Company.query.count()
    admin_count = User.query.filter_by(role="admin").count()
    active_company_count = Company.query.filter_by(active=True).count()
    return render_template(
        "owner_dashboard.html",
        company_count=company_count,
        admin_count=admin_count,
        active_company_count=active_company_count,
    )


@owner_bp.route("/empresas")
@login_required
def companies():
    owner_required()
    companies = (
        db.session.query(Company, func.count(User.id))
        .outerjoin(User, (User.company_id == Company.id) & (User.role == "admin"))
        .group_by(Company.id)
        .order_by(Company.name)
        .all()
    )
    return render_template("owner_companies.html", companies=companies)


@owner_bp.route("/empresas/<int:company_id>")
@login_required
def company_detail(company_id):
    owner_required()
    company = db.get_or_404(Company, company_id)
    admins = (
        User.query.filter_by(company_id=company.id, role="admin")
        .order_by(User.name)
        .all()
    )
    employees = Employee.query.filter_by(company_id=company.id).order_by(Employee.name).all()
    scope_admin = next((admin for admin in admins if admin.active), None)
    if scope_admin is None and admins:
        scope_admin = admins[0]
    return render_template(
        "owner_company_detail.html",
        company=company,
        admins=admins,
        employees=employees,
        scope_admin=scope_admin,
        active_employee_count=sum(employee.active for employee in employees),
    )


@owner_bp.route("/empresas/nova", methods=["GET", "POST"])
@login_required
def create_company():
    owner_required()
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        phone = request.form.get("phone", "").strip()
        cnpj = normalize_cnpj(request.form.get("cnpj", ""))
        admin_name = request.form.get("admin_name", "").strip()
        admin_email = request.form.get("admin_email", "").strip().lower()
        admin_cpf = normalize_cpf(request.form.get("admin_cpf", ""))
        admin_birth_date_input = request.form.get("admin_birth_date", "")
        admin_birth_date = parse_birth_date(admin_birth_date_input)
        admin_registration = request.form.get("admin_registration", "").strip()
        admin_department = request.form.get("admin_department", "").strip()
        admin_position = request.form.get("admin_position", "").strip()
        password = request.form.get("password", "")
        cpf_conflict, registration_conflict = profile_identity_conflicts(
            admin_cpf,
            admin_registration,
        )

        if not all(
            [
                company_name,
                phone,
                cnpj,
                admin_name,
                admin_email,
                admin_cpf,
                admin_birth_date_input,
                admin_registration,
                admin_department,
                admin_position,
                password,
            ]
        ):
            flash("Preencha os dados da empresa e do primeiro administrador.", "danger")
        elif len(company_name) > 160 or len(phone) > 30 or len(admin_name) > 120 or len(admin_email) > 160:
            flash("Confira o tamanho dos campos informados.", "danger")
        elif not valid_cnpj_format(cnpj):
            flash("Informe um CNPJ com 14 letras ou números e dois dígitos verificadores.", "danger")
        elif Company.query.filter_by(cnpj=cnpj).first():
            flash("Este CNPJ já está cadastrado.", "danger")
        elif not is_valid_cpf(admin_cpf):
            flash("Informe um CPF válido com 11 dígitos.", "danger")
        elif admin_birth_date is None:
            flash("Informe uma data de nascimento válida.", "danger")
        elif admin_birth_date > date.today():
            flash("A data de nascimento não pode estar no futuro.", "danger")
        elif (
            len(admin_registration) > 30
            or len(admin_department) > 80
            or len(admin_position) > 80
        ):
            flash("Confira o tamanho da matrícula, departamento e cargo.", "danger")
        elif cpf_conflict:
            flash("Este CPF já está cadastrado.", "danger")
        elif registration_conflict:
            flash("Esta matrícula já está cadastrada.", "danger")
        elif User.query.filter_by(email=admin_email).first():
            flash("Este e-mail já está cadastrado.", "danger")
        elif len(password) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "danger")
        else:
            company = Company(name=company_name, phone=phone, cnpj=cnpj)
            admin = User(
                name=admin_name,
                email=admin_email,
                cpf=admin_cpf,
                birth_date=admin_birth_date,
                registration=admin_registration,
                department=admin_department,
                position=admin_position,
                role="admin",
                company=company,
            )
            admin.set_password(password)
            db.session.add_all([company, admin])
            db.session.commit()
            flash("Empresa e administrador cadastrados com sucesso.", "success")
            return redirect(url_for("owner.company_detail", company_id=company.id))

    return render_template("owner_company_form.html")


@owner_bp.route("/empresas/<int:company_id>/editar", methods=["GET", "POST"])
@login_required
def edit_company(company_id):
    owner_required()
    company = db.get_or_404(Company, company_id)
    initial_admin = (
        User.query.filter_by(company_id=company.id, role="admin")
        .order_by(User.created_at, User.id)
        .first()
    )
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        cnpj = normalize_cnpj(request.form.get("cnpj", ""))
        admin_name = request.form.get("admin_name", "").strip()
        admin_email = request.form.get("admin_email", "").strip().lower()
        admin_cpf = normalize_cpf(request.form.get("admin_cpf", ""))
        admin_birth_date_input = request.form.get("admin_birth_date", "")
        admin_birth_date = parse_birth_date(admin_birth_date_input)
        admin_registration = request.form.get("admin_registration", "").strip()
        admin_department = request.form.get("admin_department", "").strip()
        admin_position = request.form.get("admin_position", "").strip()
        admin_password = request.form.get("admin_password", "")
        cpf_conflict, registration_conflict = profile_identity_conflicts(
            admin_cpf,
            admin_registration,
            user_id=initial_admin.id if initial_admin else None,
        )

        if not all([name, phone, cnpj]):
            flash("Nome, telefone e CNPJ da empresa são obrigatórios.", "danger")
        elif len(name) > 160 or len(phone) > 30:
            flash("Confira o tamanho do nome e do telefone.", "danger")
        elif not valid_cnpj_format(cnpj):
            flash("Informe um CNPJ com 14 letras ou números e dois dígitos verificadores.", "danger")
        elif Company.query.filter(Company.cnpj == cnpj, Company.id != company.id).first():
            flash("Este CNPJ já está cadastrado.", "danger")
        elif initial_admin and not all(
            [
                admin_name,
                admin_email,
                admin_cpf,
                admin_birth_date_input,
                admin_registration,
                admin_department,
                admin_position,
            ]
        ):
            flash("Preencha todos os dados do administrador inicial.", "danger")
        elif initial_admin and (
            len(admin_name) > 120
            or len(admin_email) > 160
            or len(admin_registration) > 30
            or len(admin_department) > 80
            or len(admin_position) > 80
        ):
            flash("Confira o tamanho dos campos do administrador.", "danger")
        elif initial_admin and not is_valid_cpf(admin_cpf):
            flash("Informe um CPF válido com 11 dígitos.", "danger")
        elif initial_admin and admin_birth_date is None:
            flash("Informe uma data de nascimento válida.", "danger")
        elif initial_admin and admin_birth_date > date.today():
            flash("A data de nascimento não pode estar no futuro.", "danger")
        elif initial_admin and cpf_conflict:
            flash("Este CPF já está cadastrado.", "danger")
        elif initial_admin and registration_conflict:
            flash("Esta matrícula já está cadastrada.", "danger")
        elif initial_admin and User.query.filter(
            User.email == admin_email,
            User.id != initial_admin.id,
        ).first():
            flash("Este e-mail já está cadastrado.", "danger")
        elif admin_password and len(admin_password) < 8:
            flash("A nova senha do administrador deve ter pelo menos 8 caracteres.", "danger")
        else:
            company.name = name
            company.phone = phone
            company.cnpj = cnpj
            if initial_admin:
                initial_admin.name = admin_name
                initial_admin.email = admin_email
                initial_admin.cpf = admin_cpf
                initial_admin.birth_date = admin_birth_date
                initial_admin.registration = admin_registration
                initial_admin.department = admin_department
                initial_admin.position = admin_position
                if admin_password:
                    initial_admin.set_password(admin_password)
            db.session.commit()
            flash(
                "Empresa e dados do administrador inicial atualizados."
                if initial_admin
                else "Empresa atualizada.",
                "success",
            )
            return redirect(url_for("owner.company_detail", company_id=company.id))

    return render_template(
        "owner_company_edit.html",
        company=company,
        initial_admin=initial_admin,
    )


@owner_bp.route("/empresas/<int:company_id>/status", methods=["POST"])
@login_required
def toggle_company(company_id):
    owner_required()
    company = db.get_or_404(Company, company_id)
    company.active = not company.active
    db.session.commit()
    flash(
        "Empresa ativada." if company.active else "Empresa desativada. Seus usuários não poderão entrar.",
        "success" if company.active else "warning",
    )
    return redirect(url_for("owner.companies"))


@owner_bp.route("/empresas/<int:company_id>/excluir", methods=["POST"])
@login_required
def delete_company(company_id):
    owner_required()
    company = db.get_or_404(Company, company_id)

    user_ids = {
        user_id
        for (user_id,) in db.session.query(User.id).filter_by(company_id=company.id).all()
    }
    employee_user_ids = {
        user_id
        for (user_id,) in db.session.query(Employee.user_id)
        .filter(Employee.company_id == company.id, Employee.user_id.isnot(None))
        .all()
    }
    user_ids.update(employee_user_ids)

    punch_ids = [
        punch_id
        for (punch_id,) in db.session.query(Punch.id)
        .filter(Punch.user_id.in_(user_ids))
        .all()
    ] if user_ids else []

    correction_filters = []
    if punch_ids:
        correction_filters.append(PunchCorrection.punch_id.in_(punch_ids))
    if user_ids:
        correction_filters.append(PunchCorrection.changed_by_id.in_(user_ids))
    if correction_filters:
        db.session.query(PunchCorrection).filter(or_(*correction_filters)).delete(
            synchronize_session=False
        )
    conversation_filter = SupportConversation.company_id == company.id
    if user_ids:
        conversation_filter = or_(
            conversation_filter,
            SupportConversation.requester_id.in_(user_ids),
        )
    conversation_ids = [
        conversation_id
        for (conversation_id,) in db.session.query(SupportConversation.id)
        .filter(conversation_filter)
        .all()
    ]
    message_filters = []
    if conversation_ids:
        message_filters.append(SupportMessage.conversation_id.in_(conversation_ids))
    if user_ids:
        message_filters.append(SupportMessage.sender_id.in_(user_ids))
    if message_filters:
        db.session.query(SupportMessage).filter(or_(*message_filters)).delete(
            synchronize_session=False
        )
    if conversation_ids:
        db.session.query(SupportConversation).filter(
            SupportConversation.id.in_(conversation_ids)
        ).delete(synchronize_session=False)
    if punch_ids:
        db.session.query(Punch).filter(Punch.id.in_(punch_ids)).delete(
            synchronize_session=False
        )

    employee_filter = Employee.company_id == company.id
    if user_ids:
        employee_filter = or_(employee_filter, Employee.user_id.in_(user_ids))
    db.session.query(Employee).filter(employee_filter).delete(synchronize_session=False)
    if user_ids:
        db.session.query(User).filter(User.id.in_(user_ids)).delete(
            synchronize_session=False
        )

    db.session.delete(company)
    db.session.commit()
    flash("Empresa e todos os dados vinculados foram excluídos permanentemente.", "success")
    return redirect(url_for("owner.companies"))


@owner_bp.route("/administradores")
@login_required
def administrators():
    owner_required()
    return redirect(url_for("owner.companies"))


@owner_bp.route("/administradores/<int:user_id>")
@login_required
def administrator_detail(user_id):
    owner_required()
    admin = User.query.filter_by(id=user_id, role="admin").first_or_404()
    if admin.company_id is None:
        return redirect(url_for("owner.companies"))
    return redirect(url_for("owner.company_detail", company_id=admin.company_id))


@owner_bp.route(
    "/administradores/novo",
    defaults={"company_id": None},
    methods=["GET", "POST"],
)
@owner_bp.route(
    "/empresas/<int:company_id>/administradores/novo",
    methods=["GET", "POST"],
)
@login_required
def create_administrator(company_id):
    owner_required()
    if company_id is None:
        return redirect(url_for("owner.companies"))
    company = db.get_or_404(Company, company_id)
    if not company.active:
        flash("Ative a empresa antes de cadastrar um administrador.", "warning")
        return redirect(url_for("owner.company_detail", company_id=company.id))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        cpf = normalize_cpf(request.form.get("cpf", ""))
        birth_date_input = request.form.get("birth_date", "")
        birth_date = parse_birth_date(birth_date_input)
        registration = request.form.get("registration", "").strip()
        department = request.form.get("department", "").strip()
        position = request.form.get("position", "").strip()
        password = request.form.get("password", "")
        cpf_conflict, registration_conflict = profile_identity_conflicts(
            cpf,
            registration,
        )

        if not all(
            [name, email, cpf, birth_date_input, registration, department, position, password]
        ):
            flash("Preencha todos os campos.", "danger")
        elif (
            len(name) > 120
            or len(email) > 160
            or len(registration) > 30
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
            admin = User(
                name=name,
                email=email,
                cpf=cpf,
                birth_date=birth_date,
                registration=registration,
                department=department,
                position=position,
                role="admin",
                company=company,
            )
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            flash("Administrador cadastrado com sucesso.", "success")
            return redirect(url_for("owner.company_detail", company_id=company.id))

    return render_template(
        "owner_admin_form.html",
        companies=[],
        selected_company=company,
    )


@owner_bp.route("/administradores/<int:user_id>/editar", methods=["GET", "POST"])
@login_required
def edit_administrator(user_id):
    owner_required()
    admin = User.query.filter_by(id=user_id, role="admin").first_or_404()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        cpf = normalize_cpf(request.form.get("cpf", ""))
        birth_date_input = request.form.get("birth_date", "")
        birth_date = parse_birth_date(birth_date_input)
        registration = request.form.get("registration", "").strip()
        department = request.form.get("department", "").strip()
        position = request.form.get("position", "").strip()
        password = request.form.get("password", "")
        cpf_conflict, registration_conflict = profile_identity_conflicts(
            cpf,
            registration,
            user_id=admin.id,
        )

        if not all([name, email, cpf, birth_date_input, registration, department, position]):
            flash("Preencha todos os campos do administrador.", "danger")
        elif (
            len(name) > 120
            or len(email) > 160
            or len(registration) > 30
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
        elif User.query.filter(User.email == email, User.id != admin.id).first():
            flash("Este e-mail já está cadastrado.", "danger")
        elif password and len(password) < 8:
            flash("A nova senha deve ter pelo menos 8 caracteres.", "danger")
        else:
            admin.name = name
            admin.email = email
            admin.cpf = cpf
            admin.birth_date = birth_date
            admin.registration = registration
            admin.department = department
            admin.position = position
            if password:
                admin.set_password(password)
            db.session.commit()
            flash("Administrador atualizado.", "success")
            if admin.company_id is not None:
                return redirect(url_for("owner.company_detail", company_id=admin.company_id))
            return redirect(url_for("owner.companies"))

    return render_template(
        "owner_admin_form.html",
        admin=admin,
        companies=[],
        selected_company=admin.company,
    )


@owner_bp.route("/administradores/<int:user_id>/status", methods=["POST"])
@login_required
def toggle_administrator(user_id):
    owner_required()
    admin = User.query.filter_by(id=user_id, role="admin").first_or_404()
    admin.active = not admin.active
    db.session.commit()
    flash(
        "Administrador ativado." if admin.active else "Administrador desativado.",
        "success" if admin.active else "warning",
    )
    if admin.company_id is not None:
        return redirect(url_for("owner.company_detail", company_id=admin.company_id))
    return redirect(url_for("owner.companies"))

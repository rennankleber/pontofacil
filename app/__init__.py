from pathlib import Path
import secrets
from flask import Flask
from sqlalchemy import inspect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "warning"


def _migrate_company_profile():
    columns = {column["name"] for column in inspect(db.engine).get_columns("company")}
    with db.engine.begin() as connection:
        if "phone" not in columns:
            connection.exec_driver_sql(
                'ALTER TABLE "company" ADD COLUMN phone VARCHAR(30)'
            )
        if "cnpj" not in columns:
            connection.exec_driver_sql(
                'ALTER TABLE "company" ADD COLUMN cnpj VARCHAR(18)'
            )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_company_cnpj ON company (cnpj)"
        )


def _migrate_company_membership():
    from app.models import Company, Employee, User

    for table in ("user", "employee"):
        columns = {column["name"] for column in inspect(db.engine).get_columns(table)}
        if "company_id" not in columns:
            with db.engine.begin() as connection:
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table}" ADD COLUMN company_id INTEGER REFERENCES company(id)'
                )

    users = User.query.filter(User.role != "owner", User.company_id.is_(None)).all()
    employees = Employee.query.filter(Employee.company_id.is_(None)).all()
    if not users and not employees:
        return

    company = Company.query.filter_by(name="Empresa migrada").first()
    if company is None:
        company = Company(name="Empresa migrada")
        db.session.add(company)
        db.session.flush()

    for user in users:
        user.company_id = company.id
    for employee in employees:
        employee.company_id = (
            employee.user.company_id
            if employee.user and employee.user.company_id
            else company.id
        )
    db.session.commit()


def _migrate_staff_profiles():
    profile_columns = {
        "user": {
            "cpf": "VARCHAR(11)",
            "birth_date": "DATE",
            "registration": "VARCHAR(30)",
            "department": "VARCHAR(80)",
            "position": "VARCHAR(80)",
        },
        "employee": {
            "cpf": "VARCHAR(11)",
            "birth_date": "DATE",
        },
    }

    with db.engine.begin() as connection:
        for table, columns_to_add in profile_columns.items():
            existing_columns = {
                column["name"] for column in inspect(db.engine).get_columns(table)
            }
            for column, column_type in columns_to_add.items():
                if column not in existing_columns:
                    connection.exec_driver_sql(
                        f'ALTER TABLE "{table}" ADD COLUMN "{column}" {column_type}'
                    )

        connection.exec_driver_sql(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_user_cpf ON "user" (cpf)'
        )
        connection.exec_driver_sql(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_user_registration ON "user" (registration)'
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_cpf ON employee (cpf)"
        )


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import (
        Company,
        Employee,
        Punch,
        PunchCorrection,
        SupportConversation,
        SupportMessage,
        User,
    )
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.employees import employees_bp
    from app.routes.owner import owner_bp
    from app.routes.punches import punches_bp
    from app.routes.support import support_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(employees_bp, url_prefix="/funcionarios")
    app.register_blueprint(owner_bp, url_prefix="/dono")
    app.register_blueprint(punches_bp, url_prefix="/ponto")
    app.register_blueprint(support_bp, url_prefix="/suporte")

    with app.app_context():
        db.create_all()
        _migrate_company_profile()
        _migrate_staff_profiles()
        _migrate_company_membership()

        owner_email = app.config["INITIAL_OWNER_EMAIL"].strip().lower()
        owner = User.query.filter_by(email=owner_email).first()
        if owner and owner.role != "owner":
            raise RuntimeError(f"O e-mail configurado para o dono já pertence a outro perfil: {owner_email}")
        if owner is None:
            owner_password = app.config.get("INITIAL_OWNER_PASSWORD") or None
            generated_password = owner_password is None
            owner_password = owner_password or secrets.token_urlsafe(18)
            owner = User(
                name="Dono do sistema",
                email=owner_email,
                role="owner",
                active=True,
            )
            owner.set_password(owner_password)
            db.session.add(owner)
            db.session.commit()
            if generated_password:
                print(f"E-mail do dono do sistema: {owner_email}")
                print(f"Senha temporária do dono do sistema: {owner_password}")

    return app

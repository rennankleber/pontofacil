import argparse
import re
import sys
from datetime import date
from getpass import getpass

from sqlalchemy import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app, db
from app.models import Company, Employee, User
from app.profile_validation import (
    is_valid_cpf,
    normalize_cpf,
    parse_birth_date,
    profile_identity_conflicts,
)
from app.routes.owner import normalize_cnpj, valid_cnpj_format
from config import Config


EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class SetupError(ValueError):
    pass


def _required(data, key, label, maximum):
    value = str(data.get(key, "")).strip()
    if not value:
        raise SetupError(f"Informe {label}.")
    if len(value) > maximum:
        raise SetupError(f"{label.capitalize()} excede {maximum} caracteres.")
    return value


def _email(value, label):
    value = value.strip().lower()
    if len(value) > 160 or not EMAIL_PATTERN.fullmatch(value):
        raise SetupError(f"Informe um e-mail válido para {label}.")
    return value


def _password(data, key, label, required=True):
    value = data.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) < 8:
        raise SetupError(f"A senha de {label} precisa ter pelo menos 8 caracteres.")
    return value


def _profile(data, label):
    name = _required(data, "name", f"nome de {label}", 120)
    email = _email(str(data.get("email", "")), label)
    cpf = normalize_cpf(str(data.get("cpf", "")))
    if not is_valid_cpf(cpf):
        raise SetupError(f"Informe um CPF válido para {label}.")

    birth_date_input = str(data.get("birth_date", "")).strip()
    birth_date = parse_birth_date(birth_date_input)
    if birth_date is None or birth_date > date.today():
        raise SetupError(f"Informe uma data de nascimento válida para {label} (AAAA-MM-DD).")

    registration = _required(data, "registration", f"matrícula de {label}", 30)
    department = _required(data, "department", f"departamento de {label}", 80)
    position = _required(data, "position", f"cargo de {label}", 80)
    password = _password(data, "password", label)
    return {
        "name": name,
        "email": email,
        "cpf": cpf,
        "birth_date": birth_date,
        "registration": registration,
        "department": department,
        "position": position,
        "password": password,
    }


def _company_from_data(company_data):
    company_name = _required(company_data, "name", "nome da empresa", 160)
    phone = _required(company_data, "phone", "telefone da empresa", 30)
    cnpj = normalize_cnpj(str(company_data.get("cnpj", "")))
    if not valid_cnpj_format(cnpj):
        raise SetupError("Informe um CNPJ com 14 letras ou números e dois dígitos.")

    companies = Company.query.filter_by(cnpj=cnpj).all()
    if len(companies) > 1:
        raise SetupError("Há mais de uma empresa com esse CNPJ; corrija o cadastro primeiro.")
    company = companies[0] if companies else None
    if company is not None and not company.active:
        raise SetupError("A empresa encontrada pelo CNPJ está inativa.")
    if company is None:
        company = Company(name=company_name, phone=phone, cnpj=cnpj)
        db.session.add(company)
    return company


def _check_profile_available(profile):
    if User.query.filter_by(email=profile["email"]).first():
        raise SetupError(f"O e-mail {profile['email']} já está cadastrado.")
    cpf_conflict, registration_conflict = profile_identity_conflicts(
        profile["cpf"],
        profile["registration"],
    )
    if cpf_conflict:
        raise SetupError(f"O CPF de {profile['name']} já está cadastrado.")
    if registration_conflict:
        raise SetupError(f"A matrícula de {profile['name']} já está cadastrada.")


def _commit_access_changes():
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise SetupError(
            "O banco recusou dados duplicados; nenhuma conta nova foi salva."
        ) from error


def create_owner_access(app, owner_data):
    with app.app_context():
        owner_email = _email(str(owner_data.get("email", "")), "dono")
        owner = User.query.filter_by(email=owner_email).first()
        existing_owners = User.query.filter_by(role="owner").all()
        if owner is not None and owner.role != "owner":
            raise SetupError("O e-mail informado para o dono já pertence a outro perfil.")
        if existing_owners and owner is None:
            raise SetupError(
                "Já existe um dono cadastrado. Use o e-mail de uma conta de dono existente."
            )

        owner_password = _password(
            owner_data,
            "password",
            "dono",
            required=owner is None or owner_data.get("reset_existing", False),
        )
        if owner is None:
            owner = User(
                name=_required(owner_data, "name", "nome do dono", 120),
                email=owner_email,
                role="owner",
                active=True,
            )
            owner.set_password(owner_password)
            db.session.add(owner)
        elif owner_password is not None:
            owner.set_password(owner_password)

        _commit_access_changes()
        return {"owner_email": owner.email}


def create_admin_access(app, company_data, admin_data):
    with app.app_context():
        admin = _profile(admin_data, "administrador")
        _check_profile_available(admin)
        company = _company_from_data(company_data)

        admin_user = User(
            name=admin["name"],
            email=admin["email"],
            cpf=admin["cpf"],
            birth_date=admin["birth_date"],
            registration=admin["registration"],
            department=admin["department"],
            position=admin["position"],
            role="admin",
            company=company,
        )
        admin_user.set_password(admin["password"])
        db.session.add(admin_user)
        _commit_access_changes()
        return {"admin_email": admin_user.email, "company_name": company.name}


def create_employee_access(app, company_data, employee_data):
    with app.app_context():
        employee = _profile(employee_data, "funcionário")
        _check_profile_available(employee)
        company = _company_from_data(company_data)

        employee_user = User(
            name=employee["name"],
            email=employee["email"],
            role="employee",
            company=company,
        )
        employee_user.set_password(employee["password"])
        employee_record = Employee(
            name=employee["name"],
            registration=employee["registration"],
            cpf=employee["cpf"],
            birth_date=employee["birth_date"],
            company=company,
            department=employee["department"],
            position=employee["position"],
            user=employee_user,
        )
        db.session.add_all([employee_user, employee_record])
        _commit_access_changes()
        return {"employee_email": employee_user.email, "company_name": company.name}


def create_accesses(app, owner_data, company_data, admin_data, employee_data):
    with app.app_context():
        owner_email = _email(str(owner_data.get("email", "")), "dono")
        owner = User.query.filter_by(email=owner_email).first()
        existing_owners = User.query.filter_by(role="owner").all()
        if owner is not None and owner.role != "owner":
            raise SetupError("O e-mail informado para o dono já pertence a outro perfil.")
        if existing_owners and owner is None:
            raise SetupError(
                "Já existe um dono cadastrado. Use o e-mail de uma conta de dono existente."
            )

        owner_password = _password(
            owner_data,
            "password",
            "dono",
            required=owner is None or owner_data.get("reset_existing", False),
        )
        owner_name = None
        if owner is None:
            owner_name = _required(owner_data, "name", "nome do dono", 120)

        company_name = _required(company_data, "name", "nome da empresa", 160)
        phone = _required(company_data, "phone", "telefone da empresa", 30)
        cnpj = normalize_cnpj(str(company_data.get("cnpj", "")))
        if not valid_cnpj_format(cnpj):
            raise SetupError("Informe um CNPJ com 14 letras ou números e dois dígitos.")

        admin = _profile(admin_data, "administrador")
        employee = _profile(employee_data, "funcionário")
        if admin["email"] == employee["email"]:
            raise SetupError("Administrador e funcionário precisam de e-mails diferentes.")
        if admin["cpf"] == employee["cpf"]:
            raise SetupError("Administrador e funcionário precisam de CPFs diferentes.")
        if admin["registration"] == employee["registration"]:
            raise SetupError("Administrador e funcionário precisam de matrículas diferentes.")

        for account in (admin, employee):
            if User.query.filter_by(email=account["email"]).first():
                raise SetupError(f"O e-mail {account['email']} já está cadastrado.")
            cpf_conflict, registration_conflict = profile_identity_conflicts(
                account["cpf"],
                account["registration"],
            )
            if cpf_conflict:
                raise SetupError(f"O CPF de {account['name']} já está cadastrado.")
            if registration_conflict:
                raise SetupError(f"A matrícula de {account['name']} já está cadastrada.")

        companies = Company.query.filter_by(cnpj=cnpj).all()
        if len(companies) > 1:
            raise SetupError("Há mais de uma empresa com esse CNPJ; corrija o cadastro primeiro.")
        company = companies[0] if companies else None
        if company is not None and not company.active:
            raise SetupError("A empresa encontrada pelo CNPJ está inativa.")
        if company is None:
            company = Company(name=company_name, phone=phone, cnpj=cnpj)

        if owner is None:
            owner = User(
                name=owner_name,
                email=owner_email,
                role="owner",
                active=True,
            )
            owner.set_password(owner_password)
            db.session.add(owner)
        elif owner_password is not None:
            owner.set_password(owner_password)

        admin_user = User(
            name=admin["name"],
            email=admin["email"],
            cpf=admin["cpf"],
            birth_date=admin["birth_date"],
            registration=admin["registration"],
            department=admin["department"],
            position=admin["position"],
            role="admin",
            company=company,
        )
        admin_user.set_password(admin["password"])

        employee_user = User(
            name=employee["name"],
            email=employee["email"],
            role="employee",
            company=company,
        )
        employee_user.set_password(employee["password"])
        employee_record = Employee(
            name=employee["name"],
            registration=employee["registration"],
            cpf=employee["cpf"],
            birth_date=employee["birth_date"],
            company=company,
            department=employee["department"],
            position=employee["position"],
            user=employee_user,
        )

        db.session.add_all([company, admin_user, employee_user, employee_record])
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise SetupError(
                "O banco recusou dados duplicados; nenhuma conta nova foi salva."
            ) from error

        return {
            "owner_email": owner.email,
            "admin_email": admin_user.email,
            "employee_email": employee_user.email,
            "company_name": company.name,
        }


def _read_text(label, maximum):
    value = input(f"{label}: ").strip()
    if not value:
        raise SetupError(f"Informe {label.lower()}.")
    if len(value) > maximum:
        raise SetupError(f"{label.capitalize()} excede {maximum} caracteres.")
    return value


def _read_email(label):
    return _email(_read_text(label, 160), label.lower())


def _read_password(label):
    while True:
        password = getpass(f"Senha de {label} (mínimo 8 caracteres): ")
        confirmation = getpass("Confirme a senha: ")
        if password != confirmation:
            print("As senhas não conferem; tente novamente.")
        elif len(password) < 8:
            print("A senha precisa ter pelo menos 8 caracteres.")
        else:
            return password


def _prompt_owner(owners):
    if owners:
        if len(owners) == 1:
            owner = owners[0]
        else:
            owner_email = _read_email("E-mail de uma conta de dono existente")
            owner = next((item for item in owners if item.email == owner_email), None)
            if owner is None:
                raise SetupError("O e-mail informado não pertence a uma conta de dono.")
        print(f"Usando a conta de dono existente: {owner.email}")
        reset = input("Redefinir a senha desse dono? [s/N]: ").strip().lower() in {
            "s",
            "sim",
        }
        return {
            "name": owner.name,
            "email": owner.email,
            "password": _read_password("dono") if reset else None,
            "reset_existing": reset,
        }

    print("Nenhum dono existe; será criada a conta inicial.")
    return {
        "name": _read_text("Nome do dono", 120),
        "email": _read_email("E-mail do dono"),
        "password": _read_password("dono"),
        "reset_existing": False,
    }


def _prompt_profile(label):
    return {
        "name": _read_text(f"Nome do {label}", 120),
        "email": _read_email(f"E-mail do {label}"),
        "cpf": _read_text(f"CPF do {label}", 20),
        "birth_date": _read_text(
            f"Data de nascimento do {label} (AAAA-MM-DD)", 10
        ),
        "registration": _read_text(f"Matrícula do {label}", 30),
        "department": _read_text(f"Departamento do {label}", 80),
        "position": _read_text(f"Cargo do {label}", 80),
        "password": _read_password(label),
    }


def _prompt_company():
    return {
        "name": _read_text("Nome da empresa", 160),
        "phone": _read_text("Telefone da empresa", 30),
        "cnpj": _read_text("CNPJ da empresa", 20),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cria separadamente o acesso de um perfil do PontoFácil."
    )
    parser.add_argument(
        "perfil",
        choices=("dono", "administrador", "funcionario"),
        help="perfil para o qual criar ou redefinir o acesso",
    )
    args = parser.parse_args(argv)

    if make_url(Config.SQLALCHEMY_DATABASE_URI).get_backend_name() != "sqlite":
        print("Este assistente cria acessos somente no banco SQLite local.")
        return 1

    try:
        app = create_app({"SEED_INITIAL_OWNER": False})
        if args.perfil == "dono":
            with app.app_context():
                owners = User.query.filter_by(role="owner").order_by(User.id).all()
            result = create_owner_access(app, _prompt_owner(owners))
            print(f"\nAcesso de dono pronto: {result['owner_email']}")
        elif args.perfil == "administrador":
            result = create_admin_access(
                app,
                _prompt_company(),
                _prompt_profile("administrador"),
            )
            print(f"\nAcesso de administrador criado: {result['admin_email']}")
            print(f"Empresa: {result['company_name']}")
        else:
            result = create_employee_access(
                app,
                _prompt_company(),
                _prompt_profile("funcionário"),
            )
            print(f"\nAcesso de funcionário criado: {result['employee_email']}")
            print(f"Empresa: {result['company_name']}")
    except (KeyboardInterrupt, EOFError):
        print("\nAssistente cancelado; nenhuma conta foi criada.")
        return 130
    except SetupError as error:
        print(f"Não foi possível criar os acessos: {error}")
        return 1
    except SQLAlchemyError as error:
        detail = getattr(error, "orig", None)
        message = str(detail) if detail else type(error).__name__
        print(f"Erro ao acessar o banco local: {message}")
        return 1

    print("A senha não foi exibida e foi salva somente como hash.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import re
from datetime import date


def normalize_cpf(value):
    return re.sub(r"\D", "", value)


def is_valid_cpf(value):
    if len(value) != 11 or not value.isdigit() or len(set(value)) == 1:
        return False

    digits = [int(digit) for digit in value]
    first_check = sum(digit * weight for digit, weight in zip(digits[:9], range(10, 1, -1)))
    first_check = (first_check * 10) % 11
    if first_check == 10:
        first_check = 0
    if digits[9] != first_check:
        return False

    second_check = sum(digit * weight for digit, weight in zip(digits[:10], range(11, 1, -1)))
    second_check = (second_check * 10) % 11
    if second_check == 10:
        second_check = 0
    return digits[10] == second_check


def parse_birth_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def profile_identity_conflicts(cpf, registration, user_id=None, employee_id=None):
    from app.models import Employee, User

    users_by_cpf = User.query.filter_by(cpf=cpf)
    users_by_registration = User.query.filter_by(registration=registration)
    employees_by_cpf = Employee.query.filter_by(cpf=cpf)
    employees_by_registration = Employee.query.filter_by(registration=registration)

    if user_id is not None:
        users_by_cpf = users_by_cpf.filter(User.id != user_id)
        users_by_registration = users_by_registration.filter(User.id != user_id)
    if employee_id is not None:
        employees_by_cpf = employees_by_cpf.filter(Employee.id != employee_id)
        employees_by_registration = employees_by_registration.filter(
            Employee.id != employee_id
        )

    return (
        users_by_cpf.first() is not None or employees_by_cpf.first() is not None,
        users_by_registration.first() is not None
        or employees_by_registration.first() is not None,
    )

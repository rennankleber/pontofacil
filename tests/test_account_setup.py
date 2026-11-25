import unittest

from app import create_app, db
from app.models import Company, Employee, User
from criar_acessos import SetupError, create_accesses


class AccountSetupTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-key",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "WTF_CSRF_ENABLED": False,
                "SEED_INITIAL_OWNER": False,
            }
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def access_data(self):
        owner = {
            "name": "Dono de teste",
            "email": "owner@example.test",
            "password": "OwnerPass123",
        }
        company = {
            "name": "Empresa de teste",
            "phone": "11999999999",
            "cnpj": "12345678000199",
        }
        admin = {
            "name": "Admin de teste",
            "email": "admin@example.test",
            "cpf": "52998224725",
            "birth_date": "1990-01-01",
            "registration": "A-001",
            "department": "Administrativo",
            "position": "Administrador",
            "password": "AdminPass123",
        }
        employee = {
            "name": "Funcionário de teste",
            "email": "employee@example.test",
            "cpf": "11144477735",
            "birth_date": "1995-02-02",
            "registration": "F-001",
            "department": "Operações",
            "position": "Assistente",
            "password": "EmployeePass123",
        }
        return owner, company, admin, employee

    def test_creates_owner_admin_and_employee_with_hashed_passwords(self):
        owner_data, company_data, admin_data, employee_data = self.access_data()

        result = create_accesses(
            self.app,
            owner_data,
            company_data,
            admin_data,
            employee_data,
        )

        with self.app.app_context():
            owner = User.query.filter_by(email="owner@example.test").one()
            admin = User.query.filter_by(email="admin@example.test").one()
            employee = User.query.filter_by(email="employee@example.test").one()
            employee_record = Employee.query.filter_by(user_id=employee.id).one()
            self.assertEqual(User.query.count(), 3)
            self.assertEqual(Company.query.count(), 1)
            self.assertEqual(owner.role, "owner")
            self.assertEqual(admin.role, "admin")
            self.assertEqual(employee.role, "employee")
            self.assertTrue(owner.check_password(owner_data["password"]))
            self.assertTrue(admin.check_password(admin_data["password"]))
            self.assertTrue(employee.check_password(employee_data["password"]))
            self.assertNotEqual(admin.password_hash, admin_data["password"])
            self.assertEqual(employee_record.company_id, admin.company_id)
            self.assertEqual(result["company_name"], company_data["name"])

    def test_rejects_duplicate_profiles_without_creating_accounts(self):
        owner_data, company_data, admin_data, employee_data = self.access_data()
        employee_data["registration"] = admin_data["registration"]

        with self.assertRaises(SetupError):
            create_accesses(
                self.app,
                owner_data,
                company_data,
                admin_data,
                employee_data,
            )

        with self.app.app_context():
            self.assertEqual(User.query.count(), 0)
            self.assertEqual(Company.query.count(), 0)

    def test_keeps_existing_owner_password_when_reset_is_not_requested(self):
        owner_data, company_data, admin_data, employee_data = self.access_data()
        owner_data["password"] = "OriginalPass123"
        create_accesses(
            self.app,
            owner_data,
            company_data,
            admin_data,
            employee_data,
        )

        owner_data["password"] = None
        owner_data["reset_existing"] = False
        owner_data["email"] = "owner@example.test"
        admin_data["email"] = "second-admin@example.test"
        employee_data["email"] = "second-employee@example.test"
        admin_data["cpf"] = "93541134780"
        employee_data["cpf"] = "98765432100"
        admin_data["registration"] = "A-002"
        employee_data["registration"] = "F-002"

        create_accesses(
            self.app,
            owner_data,
            company_data,
            admin_data,
            employee_data,
        )

        with self.app.app_context():
            owner = User.query.filter_by(email="owner@example.test").one()
            self.assertTrue(owner.check_password("OriginalPass123"))


if __name__ == "__main__":
    unittest.main()

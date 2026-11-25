import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace

from app import create_app, db
from app.models import (
    Company,
    Employee,
    Punch,
    PunchCorrection,
    SupportConversation,
    SupportMessage,
    User,
)
from app.routes.punches import calculate_worked_hours


class WorkedHoursTests(unittest.TestCase):
    def setUp(self):
        self.day = datetime(2026, 11, 19)

    def record(self, hour, minute, punch_type, user_id=1):
        return SimpleNamespace(
            user_id=user_id,
            punch_type=punch_type,
            occurred_at=self.day.replace(hour=hour, minute=minute),
        )

    def test_sums_work_segments_around_lunch(self):
        records = [
            self.record(18, 0, "saida"),
            self.record(13, 0, "fim_intervalo"),
            self.record(9, 0, "entrada"),
            self.record(12, 0, "inicio_intervalo"),
        ]

        totals = calculate_worked_hours(records)

        self.assertEqual(totals[1], timedelta(hours=8))

    def test_ignores_duplicate_and_out_of_order_marks(self):
        records = [
            self.record(9, 0, "entrada"),
            self.record(10, 0, "entrada"),
            self.record(12, 0, "inicio_intervalo"),
            self.record(13, 0, "fim_intervalo"),
            self.record(17, 0, "saida"),
        ]

        totals = calculate_worked_hours(records)

        self.assertEqual(totals[1], timedelta(hours=6))

    def test_counts_only_completed_work_segments(self):
        records = [
            self.record(9, 0, "entrada"),
            self.record(12, 0, "inicio_intervalo"),
            self.record(13, 0, "fim_intervalo"),
        ]

        totals = calculate_worked_hours(records)

        self.assertEqual(totals[1], timedelta(hours=3))


class PunchCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "INITIAL_OWNER_PASSWORD": "Owner@123",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_ENABLED": False,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            self.company = Company(name="Empresa de teste")
            self.admin = User(
                name="Administrador",
                email="admin@pontofacil.local",
                role="admin",
                company=self.company,
            )
            self.admin.set_password("Admin@123")
            db.session.add_all([self.company, self.admin])
            db.session.commit()
            self.company_id = self.company.id
            self.admin_id = self.admin.id
            self.punch = Punch(
                user_id=self.admin.id,
                punch_type="entrada",
                occurred_at=datetime(2026, 11, 19, 9, 0),
            )
            db.session.add(self.punch)
            db.session.commit()
            self.punch_id = self.punch.id
        self.client.post(
            "/login",
            data={"email": "admin@pontofacil.local", "password": "Admin@123"},
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_admin_correction_updates_mark_and_keeps_audit(self):
        response = self.client.post(
            f"/ponto/{self.punch_id}/corrigir",
            data={
                "punch_type": "entrada",
                "occurred_at": "2026-11-19T09:15",
                "reason": "Ajuste autorizado pelo gestor",
            },
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            punch = db.session.get(Punch, self.punch_id)
            correction = PunchCorrection.query.filter_by(punch_id=self.punch_id).one()
            self.assertEqual(punch.occurred_at, datetime(2026, 11, 19, 9, 15))
            self.assertEqual(correction.original_occurred_at, datetime(2026, 11, 19, 9, 0))
            self.assertEqual(correction.reason, "Ajuste autorizado pelo gestor")

    def test_invalid_reason_does_not_change_punch(self):
        response = self.client.post(
            f"/ponto/{self.punch_id}/corrigir",
            data={
                "punch_type": "entrada",
                "occurred_at": "2026-11-19T09:15",
                "reason": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            punch = db.session.get(Punch, self.punch_id)
            self.assertEqual(punch.occurred_at, datetime(2026, 11, 19, 9, 0))
            self.assertEqual(PunchCorrection.query.count(), 0)

    def test_user_can_change_password(self):
        response = self.client.post(
            "/alterar-senha",
            data={
                "current_password": "Admin@123",
                "new_password": "NovaSenha@123",
                "confirmation": "NovaSenha@123",
            },
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            admin = User.query.filter_by(email="admin@pontofacil.local").one()
            self.assertTrue(admin.check_password("NovaSenha@123"))

    def test_logout_requires_post(self):
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.client.post("/logout").status_code, 302)

    def test_admin_can_edit_employee_email(self):
        with self.app.app_context():
            user = User(
                name="Maria",
                email="maria@teste.local",
                role="employee",
                company_id=self.company_id,
            )
            user.set_password("Senha@123")
            employee = Employee(
                name="Maria",
                registration="EMP-001",
                company_id=self.company_id,
                department="Financeiro",
                position="Analista",
                user=user,
            )
            db.session.add_all([user, employee])
            db.session.commit()
            employee_id = employee.id

        form = self.client.get(f"/funcionarios/{employee_id}/editar")
        self.assertEqual(form.status_code, 200)
        self.assertIn("CPF", form.get_data(as_text=True))

        response = self.client.post(
            f"/funcionarios/{employee_id}/editar",
            data={
                "name": "Maria Silva",
                "registration": "EMP-001",
                "cpf": "529.982.247-25",
                "birth_date": "1990-01-15",
                "email": "maria.silva@teste.local",
                "department": "Financeiro",
                "position": "Analista",
            },
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            employee = db.session.get(Employee, employee_id)
            self.assertEqual(employee.name, "Maria Silva")
            self.assertEqual(employee.user.email, "maria.silva@teste.local")

    def test_employee_creation_rejects_invalid_cpf(self):
        response = self.client.post(
            "/funcionarios/novo",
            data={
                "name": "Pessoa Teste",
                "registration": "EMP-INVALID",
                "cpf": "111.111.111-11",
                "birth_date": "1990-01-15",
                "email": "pessoa@teste.local",
                "password": "Senha@123",
                "department": "Financeiro",
                "position": "Analista",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Informe um CPF válido", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertIsNone(User.query.filter_by(email="pessoa@teste.local").first())
            self.assertIsNone(Employee.query.filter_by(registration="EMP-INVALID").first())

    def test_employee_exclusion_is_logical_and_preserves_history(self):
        with self.app.app_context():
            user = User(
                name="Joao",
                email="joao@teste.local",
                role="employee",
                company_id=self.company_id,
            )
            user.set_password("Senha@123")
            employee = Employee(
                name="Joao",
                registration="EMP-002",
                company_id=self.company_id,
                user=user,
            )
            punch = Punch(
                user=user,
                punch_type="entrada",
                occurred_at=datetime(2026, 11, 19, 9, 0),
            )
            db.session.add_all([user, employee, punch])
            db.session.commit()
            employee_id = employee.id
            punch_id = punch.id

        response = self.client.post(f"/funcionarios/{employee_id}/excluir")

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            employee = db.session.get(Employee, employee_id)
            punch = db.session.get(Punch, punch_id)
            self.assertFalse(employee.active)
            self.assertFalse(employee.user.active)
            self.assertIsNotNone(punch)

    def test_owner_can_create_company_and_first_administrator(self):
        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )
        form = owner_client.get("/dono/empresas/nova")
        self.assertEqual(form.status_code, 200)
        self.assertIn("Data de nascimento", form.get_data(as_text=True))

        response = owner_client.post(
            "/dono/empresas/nova",
            data={
                "company_name": "Empresa Nova",
                "phone": "(11) 99999-1111",
                "cnpj": "12.345.678/0001-95",
                "admin_name": "Admin Nova",
                "admin_email": "admin.nova@teste.local",
                "admin_cpf": "111.444.777-35",
                "admin_birth_date": "1985-06-20",
                "admin_registration": "ADM-NOVA",
                "admin_department": "Gestão",
                "admin_position": "Gerente",
                "password": "NovaSenha@123",
            },
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            company = Company.query.filter_by(name="Empresa Nova").one()
            admin = User.query.filter_by(email="admin.nova@teste.local").one()
            self.assertEqual(company.phone, "(11) 99999-1111")
            self.assertEqual(company.cnpj, "12345678000195")
            self.assertEqual(admin.role, "admin")
            self.assertEqual(admin.company_id, company.id)
            self.assertEqual(admin.cpf, "11144477735")
            self.assertEqual(admin.birth_date, date(1985, 6, 20))
            self.assertEqual(admin.registration, "ADM-NOVA")
            self.assertEqual(admin.department, "Gestão")
            self.assertEqual(admin.position, "Gerente")

        duplicate_cnpj = owner_client.post(
            "/dono/empresas/nova",
            data={
                "company_name": "Outra empresa",
                "phone": "(11) 99999-2222",
                "cnpj": "12345678000195",
                "admin_name": "Outro administrador",
                "admin_email": "outro.admin@teste.local",
                "admin_cpf": "935.411.347-80",
                "admin_birth_date": "1980-03-10",
                "admin_registration": "ADM-OUTRO",
                "admin_department": "Comercial",
                "admin_position": "Coordenador",
                "password": "NovaSenha@123",
            },
        )
        self.assertEqual(duplicate_cnpj.status_code, 200)
        with self.app.app_context():
            self.assertEqual(Company.query.filter_by(cnpj="12345678000195").count(), 1)

    def test_owner_adds_administrator_from_company_detail(self):
        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )

        old_admin_section = owner_client.get("/dono/administradores")
        self.assertEqual(old_admin_section.status_code, 302)
        self.assertTrue(old_admin_section.location.endswith("/dono/empresas"))

        form = owner_client.get(
            f"/dono/empresas/{self.company_id}/administradores/novo"
        )
        self.assertEqual(form.status_code, 200)
        self.assertIn("Matrícula", form.get_data(as_text=True))

        created = owner_client.post(
            f"/dono/empresas/{self.company_id}/administradores/novo",
            data={
                "name": "Segundo administrador",
                "email": "segundo.admin@teste.local",
                "cpf": "935.411.347-80",
                "birth_date": "1980-03-10",
                "registration": "ADM-002",
                "department": "Operações",
                "position": "Coordenador",
                "password": "AdminNova@123",
            },
        )
        self.assertEqual(created.status_code, 302)
        detail = owner_client.get(f"/dono/empresas/{self.company_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("segundo.admin@teste.local", detail.get_data(as_text=True))
        with self.app.app_context():
            admin = User.query.filter_by(email="segundo.admin@teste.local").one()
            self.assertEqual(admin.company_id, self.company_id)
            self.assertEqual(admin.cpf, "93541134780")
            self.assertEqual(admin.birth_date, date(1980, 3, 10))
            self.assertEqual(admin.registration, "ADM-002")

    def test_owner_can_edit_company_and_initial_administrator(self):
        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )

        form = owner_client.get(f"/dono/empresas/{self.company_id}/editar")
        self.assertEqual(form.status_code, 200)
        self.assertIn("CPF", form.get_data(as_text=True))

        response = owner_client.post(
            f"/dono/empresas/{self.company_id}/editar",
            data={
                "name": "Empresa Renomeada",
                "phone": "(21) 98888-2222",
                "cnpj": "98.765.432/0001-10",
                "admin_name": "Administrador Atualizado",
                "admin_email": "admin.atualizado@pontofacil.local",
                "admin_cpf": "529.982.247-25",
                "admin_birth_date": "1990-01-15",
                "admin_registration": "ADM-EDIT",
                "admin_department": "Financeiro",
                "admin_position": "Diretor",
                "admin_password": "NovaSenha@123",
            },
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            company = db.session.get(Company, self.company_id)
            admin = db.session.get(User, self.admin_id)
            self.assertEqual(company.name, "Empresa Renomeada")
            self.assertEqual(company.phone, "(21) 98888-2222")
            self.assertEqual(company.cnpj, "98765432000110")
            self.assertEqual(admin.name, "Administrador Atualizado")
            self.assertEqual(admin.email, "admin.atualizado@pontofacil.local")
            self.assertEqual(admin.cpf, "52998224725")
            self.assertEqual(admin.birth_date, date(1990, 1, 15))
            self.assertEqual(admin.registration, "ADM-EDIT")
            self.assertEqual(admin.department, "Financeiro")
            self.assertEqual(admin.position, "Diretor")
            self.assertTrue(admin.check_password("NovaSenha@123"))

        preserved_password = owner_client.post(
            f"/dono/empresas/{self.company_id}/editar",
            data={
                "name": "Empresa Renomeada",
                "phone": "(21) 98888-2222",
                "cnpj": "98765432000110",
                "admin_name": "Administrador Atualizado",
                "admin_email": "admin.atualizado@pontofacil.local",
                "admin_cpf": "529.982.247-25",
                "admin_birth_date": "1990-01-15",
                "admin_registration": "ADM-EDIT",
                "admin_department": "Financeiro",
                "admin_position": "Diretor",
                "admin_password": "",
            },
        )
        self.assertEqual(preserved_password.status_code, 302)
        with self.app.app_context():
            admin = db.session.get(User, self.admin_id)
            self.assertTrue(admin.check_password("NovaSenha@123"))

    def test_owner_can_delete_company_and_linked_data(self):
        with self.app.app_context():
            employee_user = User(
                name="Funcionária",
                email="funcionaria@teste.local",
                role="employee",
                company_id=self.company_id,
            )
            employee_user.set_password("Employee@123")
            employee = Employee(
                name=employee_user.name,
                registration="EMP-DELETE",
                company_id=self.company_id,
                user=employee_user,
            )
            punch = Punch(
                user=employee_user,
                punch_type="entrada",
                occurred_at=datetime(2026, 11, 19, 9, 0),
            )
            correction = PunchCorrection(
                punch=punch,
                changed_by_id=self.admin_id,
                original_type="entrada",
                original_occurred_at=datetime(2026, 11, 19, 9, 0),
                new_type="entrada",
                new_occurred_at=datetime(2026, 11, 19, 9, 5),
                reason="Correção autorizada",
            )
            conversation = SupportConversation(
                kind="employee_admin",
                requester=employee_user,
                company_id=self.company_id,
            )
            support_message = SupportMessage(
                conversation=conversation,
                sender=employee_user,
                body="Preciso de ajuda.",
            )
            db.session.add_all(
                [employee_user, employee, punch, correction, conversation, support_message]
            )
            db.session.commit()
            employee_user_id = employee_user.id
            employee_id = employee.id
            punch_id = punch.id
            correction_id = correction.id
            conversation_id = conversation.id
            support_message_id = support_message.id
            admin_id = self.admin_id

        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )
        response = owner_client.post(f"/dono/empresas/{self.company_id}/excluir")

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Company, self.company_id))
            self.assertIsNone(db.session.get(User, admin_id))
            self.assertIsNone(db.session.get(User, employee_user_id))
            self.assertIsNone(db.session.get(Employee, employee_id))
            self.assertIsNone(db.session.get(Punch, punch_id))
            self.assertIsNone(db.session.get(PunchCorrection, correction_id))
            self.assertIsNone(db.session.get(SupportConversation, conversation_id))
            self.assertIsNone(db.session.get(SupportMessage, support_message_id))

    def test_non_owner_cannot_delete_company(self):
        response = self.client.post(f"/dono/empresas/{self.company_id}/excluir")

        self.assertEqual(response.status_code, 403)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Company, self.company_id))

    def test_employee_support_chat_is_shared_with_company_admins_only(self):
        with self.app.app_context():
            employee = User(
                name="Funcionária",
                email="suporte.funcionario@teste.local",
                role="employee",
                company_id=self.company_id,
            )
            employee.set_password("Employee@123")
            db.session.add(
                Employee(
                    name=employee.name,
                    registration="SUP-001",
                    company_id=self.company_id,
                    user=employee,
                )
            )
            other_company = Company(name="Outra empresa")
            other_admin = User(
                name="Outro administrador",
                email="outro.admin@teste.local",
                role="admin",
                company=other_company,
            )
            other_admin.set_password("Admin@123")
            db.session.add_all([employee, other_company, other_admin])
            db.session.commit()

        employee_client = self.app.test_client()
        employee_client.post(
            "/login",
            data={
                "email": "suporte.funcionario@teste.local",
                "password": "Employee@123",
            },
        )
        thread_response = employee_client.get("/suporte/")
        self.assertEqual(thread_response.status_code, 302)
        thread_url = thread_response.location
        sent = employee_client.post(
            thread_url,
            data={"body": "Preciso de ajuda com meu ponto."},
        )
        self.assertEqual(sent.status_code, 302)
        first_poll = employee_client.get(f"{thread_url}/mensagens?after=0")
        self.assertEqual(first_poll.status_code, 200)
        first_messages = first_poll.get_json()["messages"]
        self.assertEqual(first_messages[0]["body"], "Preciso de ajuda com meu ponto.")
        self.assertTrue(first_messages[0]["mine"])
        empty_poll = employee_client.get(
            f"{thread_url}/mensagens?after={first_messages[0]['id']}"
        )
        self.assertEqual(empty_poll.get_json()["messages"], [])

        admin_inbox = self.client.get("/suporte/")
        self.assertEqual(admin_inbox.status_code, 200)
        self.assertIn("Preciso de ajuda com meu ponto.", admin_inbox.get_data(as_text=True))
        admin_reply = self.client.post(
            thread_url,
            data={"body": "Vamos verificar para você."},
        )
        self.assertEqual(admin_reply.status_code, 302)
        employee_thread = employee_client.get(thread_url)
        self.assertIn("Vamos verificar para você.", employee_thread.get_data(as_text=True))

        with self.app.app_context():
            other_admin = User.query.filter_by(email="outro.admin@teste.local").one()
        other_client = self.app.test_client()
        other_client.post(
            "/login",
            data={"email": other_admin.email, "password": "Admin@123"},
        )
        self.assertEqual(other_client.get(thread_url).status_code, 403)
        self.assertEqual(
            other_client.get(f"{thread_url}/mensagens?after=0").status_code,
            403,
        )

        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )
        self.assertEqual(owner_client.get(thread_url).status_code, 403)

    def test_admin_support_chat_is_visible_to_owner(self):
        admin_inbox = self.client.get("/suporte/")
        self.assertIn("Falar com o suporte", admin_inbox.get_data(as_text=True))
        self.assertNotIn("Falar com o dono", admin_inbox.get_data(as_text=True))

        admin_thread = self.client.get("/suporte/dono")
        self.assertEqual(admin_thread.status_code, 302)
        thread_url = admin_thread.location
        sent = self.client.post(
            thread_url,
            data={"body": "Preciso falar com o dono."},
        )
        self.assertEqual(sent.status_code, 302)

        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )
        owner_inbox = owner_client.get("/suporte/")
        self.assertEqual(owner_inbox.status_code, 200)
        self.assertIn("Preciso falar com o dono.", owner_inbox.get_data(as_text=True))
        owner_reply = owner_client.post(
            thread_url,
            data={"body": "Pode contar comigo."},
        )
        self.assertEqual(owner_reply.status_code, 302)
        admin_thread = self.client.get(thread_url)
        self.assertIn("Pode contar comigo.", admin_thread.get_data(as_text=True))

    def test_owner_can_edit_and_deactivate_administrators(self):
        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )

        listing = owner_client.get(f"/dono/empresas/{self.company_id}")
        edit_form = owner_client.get(f"/dono/administradores/{self.admin_id}/editar")
        self.assertEqual(edit_form.status_code, 200)
        self.assertNotIn('value="None"', edit_form.get_data(as_text=True))
        edited = owner_client.post(
            f"/dono/administradores/{self.admin_id}/editar",
            data={
                "name": "Administrador Atualizado",
                "email": "admin.atualizado@teste.local",
                "cpf": "529.982.247-25",
                "birth_date": "1990-01-15",
                "registration": "ADM-EDIT",
                "department": "Financeiro",
                "position": "Diretor",
                "password": "",
            },
        )
        deactivated = owner_client.post(
            f"/dono/administradores/{self.admin_id}/status",
        )

        self.assertEqual(listing.status_code, 200)
        self.assertIn("admin@pontofacil.local", listing.get_data(as_text=True))
        self.assertEqual(edited.status_code, 302)
        self.assertEqual(deactivated.status_code, 302)
        with self.app.app_context():
            admin = db.session.get(User, self.admin_id)
            self.assertEqual(admin.name, "Administrador Atualizado")
            self.assertEqual(admin.cpf, "52998224725")
            self.assertEqual(admin.birth_date, date(1990, 1, 15))
            self.assertEqual(admin.registration, "ADM-EDIT")
            self.assertFalse(admin.active)

    def test_owner_can_manage_employees_and_correct_points_in_admin_scope(self):
        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )

        company_detail = owner_client.get(f"/dono/empresas/{self.company_id}")
        self.assertEqual(company_detail.status_code, 200)
        self.assertIn("Funcionários da empresa", company_detail.get_data(as_text=True))
        employee_list = owner_client.get(f"/funcionarios/?admin_id={self.admin_id}")
        self.assertEqual(employee_list.status_code, 200)
        create_response = owner_client.post(
            f"/funcionarios/novo?admin_id={self.admin_id}",
            data={
                "name": "Funcionário pelo dono",
                "registration": "OWN-001",
                "email": "funcionario.pelo.dono@teste.local",
                "password": "Employee@123",
                "cpf": "529.982.247-25",
                "birth_date": "1990-01-15",
                "department": "Operações",
                "position": "Analista",
            },
        )
        self.assertEqual(create_response.status_code, 302)

        with self.app.app_context():
            employee = Employee.query.filter_by(registration="OWN-001").one()
            employee_id = employee.id
            employee_user_id = employee.user_id
            self.assertEqual(employee.company_id, self.company_id)
            self.assertEqual(employee.cpf, "52998224725")
            self.assertEqual(employee.birth_date, date(1990, 1, 15))
            punch = Punch(
                user_id=employee_user_id,
                punch_type="entrada",
                occurred_at=datetime(2026, 11, 19, 9, 0),
            )
            db.session.add(punch)
            db.session.commit()
            punch_id = punch.id

        report = owner_client.get(
            f"/ponto/relatorio?admin_id={self.admin_id}&employee_id={employee_id}"
        )
        self.assertEqual(report.status_code, 200)
        self.assertIn("Funcionário pelo dono", report.get_data(as_text=True))
        csv_report = owner_client.get(f"/ponto/relatorio.csv?admin_id={self.admin_id}")
        pdf_report = owner_client.get(f"/ponto/relatorio.pdf?admin_id={self.admin_id}")
        self.assertEqual(csv_report.status_code, 200)
        self.assertEqual(pdf_report.status_code, 200)
        correction_url = f"/ponto/{punch_id}/corrigir?admin_id={self.admin_id}"
        correction_form = owner_client.get(correction_url)
        self.assertEqual(correction_form.status_code, 200)
        corrected = owner_client.post(
            correction_url,
            data={
                "punch_type": "entrada",
                "occurred_at": "2026-11-19T09:10",
                "reason": "Ajuste feito pelo dono",
            },
        )
        self.assertEqual(corrected.status_code, 302)
        with self.app.app_context():
            correction = PunchCorrection.query.filter_by(punch_id=punch_id).one()
            owner = User.query.filter_by(email="dono@pontofacil.local").one()
            self.assertEqual(correction.changed_by_id, owner.id)
            self.assertEqual(correction.reason, "Ajuste feito pelo dono")

        edit_response = owner_client.post(
            f"/funcionarios/{employee_id}/editar?admin_id={self.admin_id}",
            data={
                "name": "Funcionário atualizado pelo dono",
                "registration": "OWN-001",
                "cpf": "529.982.247-25",
                "birth_date": "1990-01-15",
                "email": "funcionario.pelo.dono@teste.local",
                "department": "Financeiro",
                "position": "Analista",
            },
        )
        self.assertEqual(edit_response.status_code, 302)
        deactivate_response = owner_client.post(
            f"/funcionarios/{employee_id}/excluir?admin_id={self.admin_id}",
        )
        self.assertEqual(deactivate_response.status_code, 302)
        with self.app.app_context():
            employee = db.session.get(Employee, employee_id)
            self.assertEqual(employee.name, "Funcionário atualizado pelo dono")
            self.assertFalse(employee.active)
            self.assertFalse(employee.user.active)

        other_company = Company(name="Empresa fora do escopo")
        with self.app.app_context():
            db.session.add(other_company)
            db.session.flush()
            outside_user = User(
                name="Funcionário externo",
                email="externo.escopo@teste.local",
                role="employee",
                company_id=other_company.id,
            )
            outside_user.set_password("Employee@123")
            outside_employee = Employee(
                name=outside_user.name,
                registration="OUT-001",
                company_id=other_company.id,
                user=outside_user,
            )
            db.session.add(outside_employee)
            db.session.commit()
            outside_employee_id = outside_employee.id

        outside_report = owner_client.get(
            f"/ponto/relatorio?admin_id={self.admin_id}&employee_id={outside_employee_id}"
        )
        outside_edit = owner_client.get(
            f"/funcionarios/{outside_employee_id}/editar?admin_id={self.admin_id}"
        )
        self.assertEqual(outside_report.status_code, 404)
        self.assertEqual(outside_edit.status_code, 404)

    def test_company_admin_cannot_access_another_company_records(self):
        with self.app.app_context():
            other_company = Company(name="Outra empresa")
            other_user = User(
                name="Funcionário externo",
                email="externo@teste.local",
                role="employee",
                company=other_company,
            )
            other_user.set_password("Senha@123")
            other_employee = Employee(
                name=other_user.name,
                registration="EMP-OUTRO",
                company=other_company,
                user=other_user,
            )
            other_punch = Punch(
                user=other_user,
                punch_type="entrada",
                occurred_at=datetime(2026, 11, 19, 9, 0),
            )
            db.session.add_all([other_company, other_user, other_employee, other_punch])
            db.session.commit()
            other_employee_id = other_employee.id
            other_punch_id = other_punch.id

        employee_list = self.client.get("/funcionarios/")
        csv_report = self.client.get("/ponto/relatorio.csv")
        edit_employee = self.client.get(f"/funcionarios/{other_employee_id}/editar")
        correct_punch = self.client.get(f"/ponto/{other_punch_id}/corrigir")

        self.assertNotIn("Funcionário externo", employee_list.get_data(as_text=True))
        self.assertNotIn("Funcionário externo", csv_report.get_data(as_text=True))
        self.assertEqual(edit_employee.status_code, 404)
        self.assertEqual(correct_punch.status_code, 404)

    def test_owner_cannot_open_employee_reports(self):
        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )

        self.assertEqual(owner_client.get("/ponto/relatorio").status_code, 403)

    def test_deactivated_company_ends_existing_admin_session(self):
        owner_client = self.app.test_client()
        owner_client.post(
            "/login",
            data={"email": "dono@pontofacil.local", "password": "Owner@123"},
        )
        owner_client.post(f"/dono/empresas/{self.company_id}/status")

        response = self.client.get("/funcionarios/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)


class SecurityBehaviorTests(unittest.TestCase):
    def test_first_owner_password_is_not_the_known_default(self):
        with redirect_stdout(StringIO()):
            app = create_app({
                "TESTING": True,
                "SECRET_KEY": "test-key",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "WTF_CSRF_ENABLED": False,
            })
        try:
            with app.app_context():
                owner = User.query.filter_by(email="dono@pontofacil.local").one()
                self.assertEqual(owner.role, "owner")
                self.assertFalse(owner.check_password("Admin@123"))
        finally:
            with app.app_context():
                db.session.remove()
                db.drop_all()

    def test_login_post_requires_csrf_token(self):
        app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "INITIAL_OWNER_PASSWORD": "Owner@123",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "WTF_CSRF_ENABLED": True,
        })
        try:
            response = app.test_client().post(
                "/login",
                data={"email": "dono@pontofacil.local", "password": "Owner@123"},
            )
            self.assertEqual(response.status_code, 400)
        finally:
            with app.app_context():
                db.session.remove()
                db.drop_all()

    def test_existing_users_are_assigned_to_a_migrated_company(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE company (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(160) NOT NULL,
                    active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL
                );
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    email VARCHAR(160) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL
                );
                CREATE TABLE employee (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    registration VARCHAR(30) NOT NULL UNIQUE,
                    department VARCHAR(80),
                    position VARCHAR(80),
                    user_id INTEGER UNIQUE,
                    active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL
                );
                INSERT INTO user
                    (id, name, email, password_hash, role, active, created_at)
                VALUES
                    (1, 'Admin antigo', 'admin.antigo@teste.local', 'hash', 'admin', 1, '2026-01-01');
                INSERT INTO employee
                    (id, name, registration, user_id, active, created_at)
                VALUES
                    (1, 'Funcionário antigo', 'LEG-001', 1, 1, '2026-01-01');
                """
            )
            connection.close()

            app = create_app({
                "TESTING": True,
                "SECRET_KEY": "test-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            })
            try:
                with app.app_context():
                    user = User.query.filter_by(email="admin.antigo@teste.local").one()
                    employee = Employee.query.filter_by(registration="LEG-001").one()
                    self.assertIsNotNone(user.company_id)
                    self.assertEqual(employee.company_id, user.company_id)
                    self.assertEqual(user.company.name, "Empresa migrada")
                    self.assertIsNone(user.company.phone)
                    self.assertIsNone(user.company.cnpj)
                    self.assertIsNone(user.cpf)
                    self.assertIsNone(user.birth_date)
                    self.assertIsNone(user.registration)
                    self.assertIsNone(employee.cpf)
                    self.assertIsNone(employee.birth_date)
            finally:
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()


if __name__ == "__main__":
    unittest.main()

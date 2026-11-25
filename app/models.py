from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
from app.time_utils import local_now

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(30))
    cnpj = db.Column(db.String(18))
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    users = db.relationship("User", back_populates="company")
    employees = db.relationship("Employee", back_populates="company")

class User(UserMixin, db.Model):
    __table_args__ = (
        db.Index("uq_user_cpf", "cpf", unique=True),
        db.Index("uq_user_registration", "registration", unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    cpf = db.Column(db.String(11))
    birth_date = db.Column(db.Date)
    registration = db.Column(db.String(30))
    department = db.Column(db.String(80))
    position = db.Column(db.String(80))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="employee")
    active = db.Column(db.Boolean, nullable=False, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"))
    company = db.relationship("Company", back_populates="users")
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.active and (
            self.role == "owner" or (self.company is not None and self.company.active)
        )

class Employee(db.Model):
    __table_args__ = (db.Index("uq_employee_cpf", "cpf", unique=True),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    registration = db.Column(db.String(30), unique=True, nullable=False)
    cpf = db.Column(db.String(11))
    birth_date = db.Column(db.Date)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
    company = db.relationship("Company", back_populates="employees")
    department = db.Column(db.String(80))
    position = db.Column(db.String(80))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True)
    user = db.relationship("User", backref=db.backref("employee", uselist=False))
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)

class Punch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    punch_type = db.Column(db.String(20), nullable=False)  # entrada, inicio_intervalo, fim_intervalo, saida
    occurred_at = db.Column(db.DateTime, nullable=False, default=local_now, index=True)
    note = db.Column(db.String(250))
    user = db.relationship("User", backref="punches")

class PunchCorrection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    punch_id = db.Column(db.Integer, db.ForeignKey("punch.id"), nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    original_type = db.Column(db.String(20), nullable=False)
    original_occurred_at = db.Column(db.DateTime, nullable=False)
    new_type = db.Column(db.String(20), nullable=False)
    new_occurred_at = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(250), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=local_now)
    punch = db.relationship("Punch", backref=db.backref("corrections", lazy="dynamic"))
    changed_by = db.relationship("User")


class SupportConversation(db.Model):
    __table_args__ = (
        db.UniqueConstraint("kind", "requester_id", name="uq_support_kind_requester"),
    )

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), nullable=False, index=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=local_now, nullable=False, index=True)
    requester = db.relationship("User", foreign_keys=[requester_id])
    company = db.relationship("Company")
    messages = db.relationship(
        "SupportMessage",
        back_populates="conversation",
        order_by="SupportMessage.id",
        cascade="all, delete-orphan",
    )


class SupportMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("support_conversation.id"),
        nullable=False,
        index=True,
    )
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False, index=True)
    conversation = db.relationship("SupportConversation", back_populates="messages")
    sender = db.relationship("User", foreign_keys=[sender_id])


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

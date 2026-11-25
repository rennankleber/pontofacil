from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.before_app_request
def enforce_active_account():
    if current_user.is_authenticated and not current_user.is_active:
        logout_user()
        flash("Sua conta ou empresa está inativa.", "warning")
        return redirect(url_for("auth.login"))

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.is_active and user.check_password(password):
            login_user(user)
            flash("Login realizado com sucesso.", "success")
            return redirect(url_for("main.dashboard"))
        flash("E-mail ou senha inválidos.", "danger")
    return render_template("login.html")

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/alterar-senha", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirmation = request.form.get("confirmation", "")
        if not current_user.check_password(current_password):
            flash("A senha atual está incorreta.", "danger")
        elif len(new_password) < 8:
            flash("A nova senha deve ter pelo menos 8 caracteres.", "danger")
        elif new_password != confirmation:
            flash("A confirmação da nova senha não confere.", "danger")
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash("Senha alterada com sucesso.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("change_password.html")

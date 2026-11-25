from datetime import date, datetime, time, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, abort
from flask_login import login_required, current_user
from app import db
from app.models import Punch, PunchCorrection, Employee, User
from app.time_utils import local_now, local_today
from app.company_scope import get_admin_scope
import csv
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

punches_bp = Blueprint("punches", __name__)
FLOW = ["entrada", "inicio_intervalo", "fim_intervalo", "saida"]
LABELS = {
    "entrada": "Entrada",
    "inicio_intervalo": "Início do intervalo",
    "fim_intervalo": "Fim do intervalo",
    "saida": "Saída",
}

def calculate_worked_hours(records):
    totals = {}
    records_by_day = {}
    for record in records:
        key = (record.user_id, record.occurred_at.date())
        records_by_day.setdefault(key, []).append(record)

    for (user_id, _punch_date), day_records in records_by_day.items():
        day_records.sort(key=lambda item: item.occurred_at)
        expected_index = 0
        work_start = None
        worked = timedelta()

        for record in day_records:
            if record.punch_type == "entrada" and expected_index != 0:
                expected_index = 0
                work_start = record.occurred_at
            if expected_index >= len(FLOW) or record.punch_type != FLOW[expected_index]:
                continue
            if record.punch_type == "entrada":
                work_start = record.occurred_at
            elif record.punch_type in ("inicio_intervalo", "saida") and work_start:
                worked += record.occurred_at - work_start
                work_start = None
            elif record.punch_type == "fim_intervalo":
                work_start = record.occurred_at
            expected_index += 1

        totals[user_id] = totals.get(user_id, timedelta()) + worked

    return totals

def format_duration(duration):
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{hours}:{minutes:02d}"

def report_query(start_date, end_date, employee_id, company_id=None):
    if current_user.role in ("admin", "owner"):
        if current_user.role == "admin":
            company_id = current_user.company_id
        elif company_id is None:
            abort(403)
        query = Punch.query.join(User).filter(
            User.company_id == company_id,
        )
        if employee_id:
            if not employee_id.isdigit():
                abort(400)
            employee = Employee.query.filter_by(
                id=int(employee_id),
                company_id=company_id,
            ).first_or_404()
            query = query.filter(Punch.user_id == (employee.user_id or -1))
    else:
        query = Punch.query.filter_by(user_id=current_user.id)

    if start_date:
        query = query.filter(Punch.occurred_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(Punch.occurred_at < datetime.combine(end_date + timedelta(days=1), time.min))
    return query

@punches_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if current_user.role == "owner":
        return redirect(url_for("owner.index"))
    if current_user.role == "admin":
        flash("Administradores não registram ponto. Use o relatório para acompanhar os funcionários.", "info")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        last = Punch.query.filter_by(user_id=current_user.id).order_by(Punch.occurred_at.desc()).first()
        expected = FLOW[0] if not last or last.occurred_at.date() != local_today() else (
            FLOW[FLOW.index(last.punch_type) + 1] if last.punch_type in FLOW and last.punch_type != "saida" else None
        )
        if not expected:
            flash("Você já concluiu as marcações de hoje.", "warning")
        elif (
            request.form.get("quick_action") != "true"
            and request.form.get("punch_type") != expected
        ):
            flash(f"A próxima marcação esperada é: {LABELS[expected]}.", "warning")
        else:
            db.session.add(Punch(user_id=current_user.id, punch_type=expected, occurred_at=local_now()))
            db.session.commit()
            flash(f"{LABELS[expected]} registrada com sucesso.", "success")
        return redirect(url_for("punches.index"))

    punches = Punch.query.filter_by(user_id=current_user.id).order_by(Punch.occurred_at.desc()).limit(30).all()
    last = punches[0] if punches else None
    expected = FLOW[0] if not last or last.occurred_at.date() != local_today() else (
        FLOW[FLOW.index(last.punch_type) + 1] if last.punch_type in FLOW and last.punch_type != "saida" else None
    )
    return render_template("punches.html", punches=punches, expected=expected, labels=LABELS)

@punches_bp.route("/relatorio")
@login_required
def report():
    owner_admin_id = None
    selected_admin = None
    company_id = None
    if current_user.role in ("admin", "owner"):
        company_id, selected_admin = get_admin_scope()
        if current_user.role == "owner":
            owner_admin_id = selected_admin.id

    start_text = request.args.get("inicio", "").strip()
    end_text = request.args.get("fim", "").strip()
    employee_id = request.args.get("employee_id", "").strip()
    start_date = None
    end_date = None

    try:
        if start_text:
            start_date = date.fromisoformat(start_text)
        if end_text:
            end_date = date.fromisoformat(end_text)
    except ValueError:
        flash("Informe um período válido.", "danger")
        start_date = end_date = None

    query = report_query(start_date, end_date, employee_id, company_id)
    records = query.order_by(Punch.occurred_at.desc()).all()
    worked_totals = calculate_worked_hours(records)
    employee_summaries = []

    if current_user.role in ("admin", "owner"):
        users = {}
        for record in records:
            users.setdefault(record.user_id, record.user)
        employee_summaries = [
            {
                "name": user.name,
                "hours": format_duration(worked_totals.get(user_id, timedelta())),
            }
            for user_id, user in sorted(users.items(), key=lambda item: item[1].name)
        ]
        employees = Employee.query.filter_by(
            company_id=company_id,
        ).order_by(Employee.name).all()
    else:
        employee_summaries = [{
            "name": current_user.name,
            "hours": format_duration(worked_totals.get(current_user.id, timedelta())),
        }]
        employees = []

    return render_template(
        "report.html",
        records=records,
        employee_summaries=employee_summaries,
        employees=employees,
        start_text=start_text,
        end_text=end_text,
        selected_employee_id=employee_id,
        owner_admin_id=owner_admin_id,
        selected_admin=selected_admin,
    )

@punches_bp.route("/<int:punch_id>/corrigir", methods=["GET", "POST"])
@login_required
def correct(punch_id):
    if current_user.role not in ("admin", "owner"):
        abort(403)
    company_id, selected_admin = get_admin_scope()
    owner_admin_id = selected_admin.id if current_user.role == "owner" else None

    punch = (
        Punch.query.join(User)
        .filter(
            Punch.id == punch_id,
            User.company_id == company_id,
        )
        .first_or_404()
    )
    corrections = PunchCorrection.query.filter_by(punch_id=punch.id).order_by(
        PunchCorrection.changed_at.desc()
    ).all()

    if request.method == "POST":
        new_type = request.form.get("punch_type", "")
        new_datetime_text = request.form.get("occurred_at", "")
        reason = request.form.get("reason", "").strip()
        try:
            new_datetime = datetime.strptime(new_datetime_text, "%Y-%m-%dT%H:%M")
        except ValueError:
            new_datetime = None

        if new_type not in FLOW:
            flash("Selecione um tipo de marcação válido.", "danger")
        elif new_datetime is None:
            flash("Informe uma data e hora válidas.", "danger")
        elif not reason or len(reason) > 250:
            flash("Informe uma justificativa de até 250 caracteres.", "danger")
        elif new_type == punch.punch_type and new_datetime == punch.occurred_at:
            flash("A correção precisa alterar o tipo ou a data e hora.", "warning")
        else:
            correction = PunchCorrection(
                punch=punch,
                changed_by=current_user,
                original_type=punch.punch_type,
                original_occurred_at=punch.occurred_at,
                new_type=new_type,
                new_occurred_at=new_datetime,
                reason=reason,
            )
            punch.punch_type = new_type
            punch.occurred_at = new_datetime
            db.session.add(correction)
            db.session.commit()
            flash("Marcação corrigida. A alteração foi registrada no histórico.", "success")
            return redirect(url_for("punches.report", admin_id=owner_admin_id))

    return render_template(
        "punch_edit.html",
        punch=punch,
        corrections=corrections,
        labels=LABELS,
        owner_admin_id=owner_admin_id,
        selected_admin=selected_admin,
    )

@punches_bp.route("/relatorio.csv")
@login_required
def report_csv():
    company_id = None
    if current_user.role in ("admin", "owner"):
        company_id, _selected_admin = get_admin_scope()

    start_text = request.args.get("inicio", "").strip()
    end_text = request.args.get("fim", "").strip()
    employee_id = request.args.get("employee_id", "").strip()
    start_date = end_date = None
    try:
        if start_text:
            start_date = date.fromisoformat(start_text)
        if end_text:
            end_date = date.fromisoformat(end_text)
    except ValueError:
        start_date = end_date = None

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Funcionario", "Tipo", "Data e hora"])
    query = report_query(start_date, end_date, employee_id, company_id)
    query = query.order_by(Punch.occurred_at.desc())
    for item in query.all():
        writer.writerow([item.user.name, LABELS.get(item.punch_type, item.punch_type), item.occurred_at.strftime("%d/%m/%Y %H:%M:%S")])
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=relatorio_ponto.csv"},
    )

@punches_bp.route("/relatorio.pdf")
@login_required
def report_pdf():
    company_id = None
    if current_user.role in ("admin", "owner"):
        company_id, _selected_admin = get_admin_scope()

    start_text = request.args.get("inicio", "").strip()
    end_text = request.args.get("fim", "").strip()
    employee_id = request.args.get("employee_id", "").strip()
    start_date = end_date = None
    try:
        if start_text:
            start_date = date.fromisoformat(start_text)
        if end_text:
            end_date = date.fromisoformat(end_text)
    except ValueError:
        start_date = end_date = None

    query = report_query(start_date, end_date, employee_id, company_id)
    records = query.order_by(Punch.occurred_at.desc()).all()
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("PontoFácil - Relatório de marcações", styles["Title"]),
        Spacer(1, 12),
    ]
    if start_text or end_text:
        elements.append(
            Paragraph(
                f"Período: {start_text or 'inicio não informado'} a {end_text or 'fim não informado'}",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 12))

    table_data = [["Funcionário", "Marcação", "Data e hora"]]
    table_data.extend([
        [
            item.user.name,
            LABELS.get(item.punch_type, item.punch_type),
            item.occurred_at.strftime("%d/%m/%Y %H:%M:%S"),
        ]
        for item in records
    ])
    if len(table_data) == 1:
        table_data.append(["Nenhum registro encontrado", "", ""])

    table = Table(table_data, repeatRows=1, colWidths=[220, 220, 180])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    document.build(elements)

    return Response(
        output.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=relatorio_ponto.pdf"},
    )

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from app import db
from app.models import SupportConversation, SupportMessage
from app.time_utils import local_now

support_bp = Blueprint("support", __name__)

EMPLOYEE_ADMIN = "employee_admin"
ADMIN_OWNER = "admin_owner"
MAX_MESSAGE_LENGTH = 2000


def _get_or_create_conversation(kind, requester):
    if requester.company_id is None:
        abort(403)

    conversation = SupportConversation.query.filter_by(
        kind=kind,
        requester_id=requester.id,
    ).first()
    if conversation is None:
        conversation = SupportConversation(
            kind=kind,
            requester_id=requester.id,
            company_id=requester.company_id,
        )
        db.session.add(conversation)
        db.session.commit()
    return conversation


def _get_authorized_conversation(conversation_id):
    conversation = db.get_or_404(SupportConversation, conversation_id)

    if conversation.kind == EMPLOYEE_ADMIN:
        allowed = (
            current_user.role == "employee"
            and conversation.requester_id == current_user.id
            and conversation.company_id == current_user.company_id
        ) or (
            current_user.role == "admin"
            and conversation.company_id == current_user.company_id
        )
    elif conversation.kind == ADMIN_OWNER:
        allowed = current_user.role == "owner" or (
            current_user.role == "admin"
            and conversation.requester_id == current_user.id
            and conversation.company_id == current_user.company_id
        )
    else:
        allowed = False

    if not allowed:
        abort(403)
    return conversation


@support_bp.route("/")
@login_required
def index():
    if current_user.role == "employee":
        conversation = _get_or_create_conversation(EMPLOYEE_ADMIN, current_user)
        return redirect(url_for("support.thread", conversation_id=conversation.id))

    if current_user.role == "admin":
        conversations = (
            SupportConversation.query.filter_by(
                kind=EMPLOYEE_ADMIN,
                company_id=current_user.company_id,
            )
            .order_by(SupportConversation.updated_at.desc())
            .all()
        )
        return render_template(
            "support_inbox.html",
            conversations=conversations,
            view_kind="admin",
        )

    if current_user.role == "owner":
        conversations = (
            SupportConversation.query.filter_by(kind=ADMIN_OWNER)
            .order_by(SupportConversation.updated_at.desc())
            .all()
        )
        return render_template(
            "support_inbox.html",
            conversations=conversations,
            view_kind="owner",
        )

    abort(403)


@support_bp.route("/dono")
@login_required
def owner_conversation():
    if current_user.role != "admin":
        abort(403)
    conversation = _get_or_create_conversation(ADMIN_OWNER, current_user)
    return redirect(url_for("support.thread", conversation_id=conversation.id))


@support_bp.route("/conversas/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def thread(conversation_id):
    conversation = _get_authorized_conversation(conversation_id)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if not body:
            flash("Digite uma mensagem antes de enviar.", "danger")
        elif len(body) > MAX_MESSAGE_LENGTH:
            flash("A mensagem deve ter no máximo 2.000 caracteres.", "danger")
        else:
            message = SupportMessage(
                conversation=conversation,
                sender=current_user,
                body=body,
            )
            conversation.updated_at = local_now()
            db.session.add(message)
            db.session.commit()
            return redirect(url_for("support.thread", conversation_id=conversation.id))

    messages = (
        SupportMessage.query.filter_by(conversation_id=conversation.id)
        .order_by(SupportMessage.id)
        .all()
    )
    if conversation.kind == EMPLOYEE_ADMIN:
        if current_user.role == "employee":
            title = "Suporte da empresa"
            subtitle = conversation.company.name
            back_url = url_for("main.dashboard")
        else:
            title = conversation.requester.name
            subtitle = f"Funcionário de {conversation.company.name}"
            back_url = url_for("support.index")
    elif current_user.role == "owner":
        title = conversation.requester.name
        subtitle = f"Administrador de {conversation.company.name}"
        back_url = url_for("support.index")
    else:
        title = "Suporte do sistema"
        subtitle = "Conversa privada com a equipe de suporte"
        back_url = url_for("support.index")

    return render_template(
        "support_thread.html",
        conversation=conversation,
        messages=messages,
        title=title,
        subtitle=subtitle,
        back_url=back_url,
        messages_url=url_for(
            "support.new_messages",
            conversation_id=conversation.id,
        ),
    )


@support_bp.route("/conversas/<int:conversation_id>/mensagens")
@login_required
def new_messages(conversation_id):
    conversation = _get_authorized_conversation(conversation_id)
    try:
        after_id = int(request.args.get("after", "0"))
    except ValueError:
        abort(400)
    if after_id < 0:
        abort(400)

    messages = (
        SupportMessage.query.filter(
            SupportMessage.conversation_id == conversation.id,
            SupportMessage.id > after_id,
        )
        .order_by(SupportMessage.id)
        .all()
    )
    response = jsonify(
        messages=[
            {
                "id": message.id,
                "sender_name": message.sender.name,
                "body": message.body,
                "created_at": message.created_at.strftime("%d/%m/%Y %H:%M"),
                "mine": message.sender_id == current_user.id,
            }
            for message in messages
        ]
    )
    response.headers["Cache-Control"] = "no-store"
    return response

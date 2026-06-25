import logging
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required

from models import db, Patient, UnregisteredUser, Notification

logger = logging.getLogger(__name__)
bale_bp = Blueprint("bale", __name__)


@bale_bp.route("/register-webhook", methods=["POST"])
@jwt_required()
def register_webhook():
    """Re-registers the Bale webhook. Call this after changing the bot token."""
    from services.bale_service import register_webhook as _register, get_webhook_info
    token = current_app.config.get("BALE_BOT_TOKEN", "")
    webhook_url = current_app.config.get("BALE_WEBHOOK_URL", "")
    if not token:
        return jsonify({"ok": False, "error": "BALE_BOT_TOKEN not configured"}), 400
    if not webhook_url:
        return jsonify({"ok": False, "error": "BALE_WEBHOOK_URL not configured"}), 400
    result = _register(token, webhook_url)
    info = get_webhook_info(token)
    return jsonify({"setWebhook": result, "webhookInfo": info})


@bale_bp.route("/webhook-info", methods=["GET"])
@jwt_required()
def webhook_info():
    """Returns the currently registered webhook info from Bale."""
    from services.bale_service import get_webhook_info
    token = current_app.config.get("BALE_BOT_TOKEN", "")
    if not token:
        return jsonify({"ok": False, "error": "BALE_BOT_TOKEN not configured"}), 400
    return jsonify(get_webhook_info(token))


@bale_bp.route("/webhook", methods=["POST"])
def webhook():
    """
    Receives incoming Bale bot messages. No JWT — public endpoint for Bale.
    Identifies new vs. registered patients and alerts the dashboard.
    """
    try:
        payload = request.get_json(silent=True) or {}
        message = payload.get("message") or payload.get("edited_message")

        if not message:
            return jsonify({"ok": True})

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "")

        if not chat_id:
            return jsonify({"ok": True})

        logger.info("Bale webhook received from chat_id=%s, text=%r", chat_id, text)

        patient = Patient.query.filter_by(bale_chat_id=chat_id).first()

        if patient:
            logger.info("Known patient %s messaged the bot: %r", patient.name, text)
            return jsonify({"ok": True})

        existing_unregistered = UnregisteredUser.query.filter_by(bale_chat_id=chat_id).first()
        if not existing_unregistered:
            unregistered = UnregisteredUser(bale_chat_id=chat_id)
            db.session.add(unregistered)

            notif = Notification(
                type="new_user",
                bale_chat_id=chat_id,
                message=f"New unregistered user detected. Bale Chat ID: {chat_id}",
            )
            db.session.add(notif)
            db.session.commit()

            from app import socketio
            socketio.emit("notification:new", notif.to_dict())
            logger.info("New unregistered Bale user: %s — notification emitted.", chat_id)

        return jsonify({"ok": True})

    except Exception:
        logger.exception("Error in Bale webhook handler.")
        return jsonify({"ok": True})

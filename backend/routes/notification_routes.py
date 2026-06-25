import logging
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from models import db, Notification

logger = logging.getLogger(__name__)
notification_bp = Blueprint("notifications", __name__)


@notification_bp.route("/", methods=["GET"])
@jwt_required()
def list_notifications():
    notifications = (
        Notification.query
        .filter_by(is_read=False)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([n.to_dict() for n in notifications])


@notification_bp.route("/<int:notif_id>/read", methods=["PUT"])
@jwt_required()
def mark_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    notif.is_read = True
    db.session.commit()
    return jsonify({"message": "Notification marked as read."})


@notification_bp.route("/read-all", methods=["PUT"])
@jwt_required()
def mark_all_read():
    Notification.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"message": "All notifications marked as read."})

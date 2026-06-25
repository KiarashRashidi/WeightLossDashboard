import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity
)
from models import db, Doctor

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required."}), 400

    doctor = Doctor.query.filter_by(username=username).first()
    if not doctor or not doctor.check_password(password):
        logger.warning("Failed login attempt for username: %s", username)
        return jsonify({"error": "Invalid credentials."}), 401

    token = create_access_token(identity=str(doctor.id))
    logger.info("Doctor %s logged in.", username)
    return jsonify({"access_token": token, "username": doctor.username})


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    doctor_id = get_jwt_identity()
    doctor = Doctor.query.get(int(doctor_id))
    if not doctor:
        return jsonify({"error": "Doctor not found."}), 404
    return jsonify({"id": doctor.id, "username": doctor.username})


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    doctor_id = get_jwt_identity()
    doctor = Doctor.query.get(int(doctor_id))
    data = request.get_json(silent=True) or {}
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")

    if not doctor.check_password(old_pw):
        return jsonify({"error": "Current password is incorrect."}), 400
    if len(new_pw) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400

    doctor.set_password(new_pw)
    db.session.commit()
    logger.info("Doctor %s changed their password.", doctor.username)
    return jsonify({"message": "Password updated successfully."})

import logging
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required

logger = logging.getLogger(__name__)
bluetooth_bp = Blueprint("bluetooth", __name__)


@bluetooth_bp.route("/status", methods=["GET"])
@jwt_required()
def status():
    ble = current_app.ble_service
    return jsonify(ble.get_status())


@bluetooth_bp.route("/start", methods=["POST"])
@jwt_required()
def start_scan():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    height_cm = data.get("height_cm")
    age = data.get("age")
    is_male = data.get("is_male", True)

    ble = current_app.ble_service
    ble.start_scan(
        patient_id=patient_id,
        height_cm=float(height_cm) if height_cm else None,
        age=int(age) if age else None,
        is_male=bool(is_male),
    )
    logger.info("Bluetooth scan started for patient_id=%s", patient_id)
    return jsonify({"message": "Scan started."})


@bluetooth_bp.route("/stop", methods=["POST"])
@jwt_required()
def stop_scan():
    ble = current_app.ble_service
    ble.stop_scan()
    logger.info("Bluetooth scan stopped.")
    return jsonify({"message": "Scan stopped."})


@bluetooth_bp.route("/latest", methods=["GET"])
@jwt_required()
def latest():
    ble = current_app.ble_service
    data = ble.get_latest_measurement()
    if data is None:
        return jsonify({"error": "No measurement available."}), 404
    return jsonify(data)

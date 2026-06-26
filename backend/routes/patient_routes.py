import io
import logging
from datetime import datetime

import pandas as pd
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required

from models import db, Patient, Measurement

logger = logging.getLogger(__name__)
patient_bp = Blueprint("patients", __name__)


@patient_bp.route("/", methods=["GET"])
@jwt_required()
def list_patients():
    query = request.args.get("q", "").strip()
    active_only = request.args.get("active", "true").lower() == "true"

    patients = Patient.query
    if active_only:
        patients = patients.filter_by(is_active=True)
    if query:
        patients = patients.filter(Patient.name.ilike(f"%{query}%"))

    return jsonify([p.to_dict() for p in patients.order_by(Patient.name).all()])


@patient_bp.route("/", methods=["POST"])
@jwt_required()
def create_patient():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    height_cm = data.get("height_cm")
    age = data.get("age")
    is_male = data.get("is_male", True)
    bale_chat_id = data.get("bale_chat_id")

    if not name or not height_cm or not age:
        return jsonify({"error": "Name, height_cm, and age are required."}), 400

    if bale_chat_id:
        existing = Patient.query.filter_by(bale_chat_id=str(bale_chat_id)).first()
        if existing:
            return jsonify({"error": "This Bale chat ID is already linked to another patient."}), 409

    patient = Patient(
        name=name,
        height_cm=float(height_cm),
        age=int(age),
        is_male=bool(is_male),
        bale_chat_id=str(bale_chat_id) if bale_chat_id else None,
    )
    db.session.add(patient)
    db.session.commit()
    logger.info("New patient registered: %s (ID %d)", name, patient.id)
    return jsonify(patient.to_dict()), 201


@patient_bp.route("/<int:patient_id>", methods=["GET"])
@jwt_required()
def get_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    return jsonify(patient.to_dict(include_measurements=True))


@patient_bp.route("/<int:patient_id>", methods=["PUT"])
@jwt_required()
def update_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    data = request.get_json(silent=True) or {}

    if "name" in data:
        patient.name = data["name"].strip()
    if "height_cm" in data:
        patient.height_cm = float(data["height_cm"])
    if "age" in data:
        patient.age = int(data["age"])
    if "is_male" in data:
        patient.is_male = bool(data["is_male"])
    if "bale_chat_id" in data:
        patient.bale_chat_id = str(data["bale_chat_id"]) if data["bale_chat_id"] else None
    if "is_active" in data:
        patient.is_active = bool(data["is_active"])

    db.session.commit()
    logger.info("Patient %d updated.", patient_id)
    return jsonify(patient.to_dict())


@patient_bp.route("/<int:patient_id>", methods=["DELETE"])
@jwt_required()
def delete_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    patient.is_active = False
    patient.bale_chat_id = None
    db.session.commit()
    logger.info("Patient %d deactivated.", patient_id)
    return jsonify({"message": "Patient deactivated."})


@patient_bp.route("/<int:patient_id>/measurements", methods=["GET"])
@jwt_required()
def get_measurements(patient_id):
    Patient.query.get_or_404(patient_id)
    measurements = (
        Measurement.query.filter_by(patient_id=patient_id)
        .order_by(Measurement.recorded_at)
        .all()
    )
    return jsonify([m.to_dict() for m in measurements])


@patient_bp.route("/<int:patient_id>/measurements", methods=["POST"])
@jwt_required()
def add_measurement(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    data = request.get_json(silent=True) or {}

    weight = data.get("weight")
    if weight is None:
        return jsonify({"error": "Weight is required."}), 400

    def _f(key):
        v = data.get(key)
        return float(v) if v not in (None, "") else None

    def _i(key):
        v = data.get(key)
        return int(v) if v not in (None, "") else None

    # Use directly provided body composition values (manual/OCR) if present,
    # otherwise compute from impedance via the BLE formula.
    direct_fat_pct = data.get("body_fat_pct")
    if direct_fat_pct is not None:
        fat_pct   = float(direct_fat_pct)
        fat_mass  = _f("fat_mass") or round(float(weight) * fat_pct / 100, 2)
        muscle_kg = _f("muscle_mass")
        water_kg  = _f("water_kg")
    else:
        from services.bluetooth_service import body_composition
        metrics = body_composition(
            weight=float(weight),
            impedance=data.get("impedance"),
            height_cm=patient.height_cm,
            age=patient.age,
            is_male=patient.is_male,
        ) or {}
        fat_pct   = metrics.get("body_fat_pct")
        fat_mass  = metrics.get("fat_mass")
        muscle_kg = metrics.get("muscle_mass")
        water_kg  = metrics.get("water_kg")
        water_pct = metrics.get("water_pct")
        # Also populate extended fields from BLE metrics if not already in payload
        for key in ("bmr", "bone_mass", "visceral_fat"):
            if data.get(key) is None and key in metrics:
                data[key] = metrics[key]

    # If water_pct provided but water_kg not, derive water_kg
    if "water_pct" not in locals() or water_pct is None:
        water_pct = _f("water_pct")
    if water_kg is None and water_pct is not None:
        water_kg = round(float(weight) * water_pct / 100, 2)

    input_method = data.get("input_method", "manual")
    if data.get("impedance") and not data.get("body_fat_pct"):
        input_method = "bluetooth"

    measurement = Measurement(
        patient_id=patient_id,
        weight=float(weight),
        fat_mass=round(fat_mass, 2) if fat_mass else None,
        muscle_mass=round(muscle_kg, 2) if muscle_kg else None,
        water_kg=round(water_kg, 2) if water_kg else None,
        body_fat_pct=round(fat_pct, 1) if fat_pct else None,
        notes=data.get("notes"),
        input_method=input_method,
        # Extended fields
        water_pct=round(water_pct, 1) if water_pct else None,
        bmr=_f("bmr"),
        bone_mass=_f("bone_mass"),
        visceral_fat=_f("visceral_fat"),
        protein=_f("protein"),
        skeletal_muscle_mass=_f("skeletal_muscle_mass"),
        subcutaneous_fat=_f("subcutaneous_fat"),
        lean_body_mass=_f("lean_body_mass"),
        body_age=_i("body_age"),
        body_type=data.get("body_type") or None,
    )

    if data.get("recorded_at"):
        try:
            measurement.recorded_at = datetime.fromisoformat(data["recorded_at"])
        except Exception:
            pass

    db.session.add(measurement)
    db.session.commit()
    logger.info("Measurement saved for patient %d: %.2f kg [%s]", patient_id, float(weight), input_method)
    return jsonify(measurement.to_dict()), 201


@patient_bp.route("/<int:patient_id>/measurements/<int:m_id>", methods=["PUT"])
@jwt_required()
def update_measurement(patient_id, m_id):
    Patient.query.get_or_404(patient_id)
    m = Measurement.query.filter_by(id=m_id, patient_id=patient_id).first_or_404()
    data = request.get_json(silent=True) or {}

    def _set_float(field):
        if field in data:
            v = data[field]
            setattr(m, field, float(v) if v not in (None, "") else None)

    def _set_int(field):
        if field in data:
            v = data[field]
            setattr(m, field, int(v) if v not in (None, "") else None)

    if "weight" in data and data["weight"] is not None:
        m.weight = float(data["weight"])

    for field in (
        "body_fat_pct", "fat_mass", "muscle_mass", "water_kg", "water_pct",
        "bmr", "bone_mass", "visceral_fat", "protein",
        "skeletal_muscle_mass", "subcutaneous_fat", "lean_body_mass",
    ):
        _set_float(field)

    _set_int("body_age")

    if "body_type" in data:
        m.body_type = data["body_type"] or None
    if "notes" in data:
        m.notes = data["notes"] or None
    if "recorded_at" in data and data["recorded_at"]:
        try:
            m.recorded_at = datetime.fromisoformat(data["recorded_at"])
        except Exception:
            pass

    db.session.commit()
    logger.info("Measurement %d updated for patient %d.", m_id, patient_id)
    return jsonify(m.to_dict())


@patient_bp.route("/<int:patient_id>/measurements/<int:m_id>", methods=["DELETE"])
@jwt_required()
def delete_measurement(patient_id, m_id):
    Patient.query.get_or_404(patient_id)
    m = Measurement.query.filter_by(id=m_id, patient_id=patient_id).first_or_404()
    db.session.delete(m)
    db.session.commit()
    logger.info("Measurement %d deleted for patient %d.", m_id, patient_id)
    return jsonify({"message": "Measurement deleted."})


@patient_bp.route("/<int:patient_id>/export", methods=["GET"])
@jwt_required()
def export_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    measurements = (
        Measurement.query.filter_by(patient_id=patient_id)
        .order_by(Measurement.recorded_at)
        .all()
    )

    fmt = request.args.get("format", "csv").lower()
    rows = [
        {
            "Date": m.recorded_at.strftime("%Y-%m-%d %H:%M"),
            "Weight (kg)": m.weight,
            "Body Fat (%)": m.body_fat_pct,
            "Fat Mass (kg)": m.fat_mass,
            "Muscle Mass (kg)": m.muscle_mass,
            "Water (kg)": m.water_kg,
            "Notes": m.notes or "",
        }
        for m in measurements
    ]

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    filename = f"{patient.name.replace(' ', '_')}_history"

    if fmt == "excel":
        df.to_excel(buf, index=False)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{filename}.xlsx",
        )
    else:
        df.to_csv(buf, index=False)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{filename}.csv",
        )


@patient_bp.route("/<int:patient_id>/send-profile", methods=["POST"])
@jwt_required()
def send_profile(patient_id):
    from flask import current_app
    from services.bale_service import send_bale_message

    patient = Patient.query.get_or_404(patient_id)
    if not patient.bale_chat_id:
        return jsonify({"error": "This patient has no linked Bale account."}), 400

    token = current_app.config.get("BALE_BOT_TOKEN", "")
    if not token:
        return jsonify({"error": "Bale bot token is not configured."}), 500

    sex = "مرد" if patient.is_male else "زن"
    message = (
        f"سلام {patient.name}! 👋\n\n"
        f"خوش آمدید به برنامه کنترل وزن.\n\n"
        f"مشخصات ثبت‌شده شما:\n"
        f"• نام: {patient.name}\n"
        f"• قد: {int(patient.height_cm)} سانتی‌متر\n"
        f"• سن: {patient.age} سال\n"
        f"• جنسیت: {sex}\n\n"
        f"دکتر شما اطلاعات پروفایل‌تان را ثبت کرد. "
        f"از این پس، گزارش‌های پیشرفت و پیام‌های درمانی از طریق همین بات ارسال خواهد شد. 🌟"
    )

    result = send_bale_message(token, patient.bale_chat_id, message)
    if result:
        logger.info("Profile sent to patient %d via Bale.", patient_id)
        return jsonify({"success": True})
    return jsonify({"error": "Failed to send message via Bale. Check bot token and chat ID."}), 502


@patient_bp.route("/bale-recent-users", methods=["GET"])
@jwt_required()
def bale_recent_users():
    """Return the last 3 unique Bale users who messaged the bot, excluding already-registered patients."""
    from flask import current_app
    import requests as http

    token = current_app.config.get("BALE_BOT_TOKEN", "")
    if not token:
        return jsonify([])

    try:
        resp = http.get(f"https://tapi.bale.ai/bot{token}/getUpdates", timeout=10)
        data = resp.json()
    except Exception:
        logger.exception("Failed to fetch Bale updates.")
        return jsonify([])

    if not data.get("ok"):
        return jsonify([])

    registered_ids = {
        p.bale_chat_id
        for p in Patient.query.filter(Patient.bale_chat_id.isnot(None)).all()
    }

    seen = {}  # chat_id -> first_name, collected newest-first
    for update in reversed(data.get("result", [])):
        msg = update.get("message")
        if not msg:
            continue
        chat_id = str(msg.get("chat", {}).get("id", ""))
        first_name = msg.get("from", {}).get("first_name", "")
        if chat_id and chat_id not in seen and chat_id not in registered_ids:
            seen[chat_id] = first_name
        if len(seen) >= 3:
            break

    return jsonify([{"chat_id": cid, "first_name": name} for cid, name in seen.items()])


@patient_bp.route("/inactive", methods=["GET"])
@jwt_required()
def inactive_patients():
    from datetime import timedelta
    from flask import current_app

    days = current_app.config["SCHEDULER_INACTIVE_DAYS"]
    cutoff = datetime.utcnow() - timedelta(days=days)

    all_patients = Patient.query.filter_by(is_active=True).all()
    inactive = []
    for p in all_patients:
        if p.last_visit is None or p.last_visit < cutoff:
            d = p.to_dict()
            d["days_inactive"] = (
                (datetime.utcnow() - p.last_visit).days if p.last_visit else None
            )
            inactive.append(d)

    return jsonify(inactive)

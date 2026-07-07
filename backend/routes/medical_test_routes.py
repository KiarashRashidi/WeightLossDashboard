import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from models import db, Patient, MedicalTest

logger = logging.getLogger(__name__)
medical_test_bp = Blueprint("medical_tests", __name__)

FLOAT_FIELDS = (
    "fbs", "hba1c", "bun", "creatinine", "alt", "ast", "lipase", "amylase",
    "cholesterol_total", "triglycerides", "hdl", "ldl",
    "vitamin_d", "b12", "calcitonin",
)
TEXT_FIELDS = ("cbc", "liver_gallbladder_ultrasound", "notes")


def _f(data, key):
    v = data.get(key)
    return float(v) if v not in (None, "") else None


@medical_test_bp.route("/<int:patient_id>/medical-tests", methods=["GET"])
@jwt_required()
def get_medical_tests(patient_id):
    Patient.query.get_or_404(patient_id)
    tests = (
        MedicalTest.query.filter_by(patient_id=patient_id)
        .order_by(MedicalTest.recorded_at)
        .all()
    )
    return jsonify([t.to_dict() for t in tests])


@medical_test_bp.route("/<int:patient_id>/medical-tests", methods=["POST"])
@jwt_required()
def add_medical_test(patient_id):
    Patient.query.get_or_404(patient_id)
    data = request.get_json(silent=True) or {}

    test = MedicalTest(
        patient_id=patient_id,
        **{field: _f(data, field) for field in FLOAT_FIELDS},
        **{field: (data.get(field) or None) for field in TEXT_FIELDS},
    )

    if data.get("recorded_at"):
        try:
            test.recorded_at = datetime.fromisoformat(data["recorded_at"])
        except Exception:
            pass

    db.session.add(test)
    db.session.commit()
    logger.info("Medical test saved for patient %d.", patient_id)
    return jsonify(test.to_dict()), 201


@medical_test_bp.route("/<int:patient_id>/medical-tests/<int:t_id>", methods=["PUT"])
@jwt_required()
def update_medical_test(patient_id, t_id):
    Patient.query.get_or_404(patient_id)
    t = MedicalTest.query.filter_by(id=t_id, patient_id=patient_id).first_or_404()
    data = request.get_json(silent=True) or {}

    for field in FLOAT_FIELDS:
        if field in data:
            setattr(t, field, _f(data, field))

    for field in TEXT_FIELDS:
        if field in data:
            setattr(t, field, data[field] or None)

    if "recorded_at" in data and data["recorded_at"]:
        try:
            t.recorded_at = datetime.fromisoformat(data["recorded_at"])
        except Exception:
            pass

    db.session.commit()
    logger.info("Medical test %d updated for patient %d.", t_id, patient_id)
    return jsonify(t.to_dict())


@medical_test_bp.route("/<int:patient_id>/medical-tests/<int:t_id>", methods=["DELETE"])
@jwt_required()
def delete_medical_test(patient_id, t_id):
    Patient.query.get_or_404(patient_id)
    t = MedicalTest.query.filter_by(id=t_id, patient_id=patient_id).first_or_404()
    db.session.delete(t)
    db.session.commit()
    logger.info("Medical test %d deleted for patient %d.", t_id, patient_id)
    return jsonify({"message": "Medical test deleted."})

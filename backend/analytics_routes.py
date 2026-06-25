"""
Simple analytics endpoint that returns pre-computed summary stats
without requiring N+1 patient queries on the frontend.
"""
import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from models import db, Patient, Measurement
from sqlalchemy import func

logger = logging.getLogger(__name__)
analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/summary", methods=["GET"])
@jwt_required()
def summary():
    total = Patient.query.count()
    active = Patient.query.filter_by(is_active=True).count()
    with_bale = Patient.query.filter(Patient.is_active == True, Patient.bale_chat_id.isnot(None)).count()

    cutoff = datetime.utcnow() - timedelta(days=21)
    inactive_count = 0
    for p in Patient.query.filter_by(is_active=True).all():
        if p.last_visit is None or p.last_visit < cutoff:
            inactive_count += 1

    # Average weight loss: per patient with >= 2 measurements
    losses = []
    for p in Patient.query.filter_by(is_active=True).all():
        ms = sorted(p.measurements, key=lambda m: m.recorded_at)
        if len(ms) >= 2:
            losses.append(ms[0].weight - ms[-1].weight)

    avg_loss = round(sum(losses) / len(losses), 1) if losses else None

    # Top 10 patients by weight loss
    top_losers = []
    for p in Patient.query.filter_by(is_active=True).all():
        ms = sorted(p.measurements, key=lambda m: m.recorded_at)
        if len(ms) >= 2:
            loss = ms[0].weight - ms[-1].weight
            top_losers.append({"name": p.name.split()[0], "loss": round(loss, 1), "id": p.id})
    top_losers.sort(key=lambda x: x["loss"], reverse=True)

    return jsonify({
        "total_patients": total,
        "active_patients": active,
        "patients_with_bale": with_bale,
        "inactive_patients": inactive_count,
        "average_weight_loss_kg": avg_loss,
        "top_losers": top_losers[:10],
    })

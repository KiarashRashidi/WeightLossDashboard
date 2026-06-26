from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Doctor(db.Model):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    height_cm = db.Column(db.Float, nullable=False)
    age = db.Column(db.Integer, nullable=False)
    is_male = db.Column(db.Boolean, default=True)
    bale_chat_id = db.Column(db.String(50), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    measurements = db.relationship(
        "Measurement", backref="patient", lazy=True,
        cascade="all, delete-orphan", order_by="Measurement.recorded_at"
    )

    @property
    def last_visit(self):
        if self.measurements:
            return self.measurements[-1].recorded_at
        return None

    def to_dict(self, include_measurements=False):
        data = {
            "id": self.id,
            "name": self.name,
            "height_cm": self.height_cm,
            "age": self.age,
            "is_male": self.is_male,
            "bale_chat_id": self.bale_chat_id,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "last_visit": self.last_visit.isoformat() if self.last_visit else None,
        }
        if include_measurements:
            data["measurements"] = [m.to_dict() for m in self.measurements]
        return data


class Measurement(db.Model):
    __tablename__ = "measurements"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    fat_mass = db.Column(db.Float)
    muscle_mass = db.Column(db.Float)
    water_kg = db.Column(db.Float)
    body_fat_pct = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    # Extended body composition fields (from smart scale screenshots / manual entry)
    water_pct = db.Column(db.Float)
    bmr = db.Column(db.Float)
    bone_mass = db.Column(db.Float)
    visceral_fat = db.Column(db.Float)
    protein = db.Column(db.Float)
    skeletal_muscle_mass = db.Column(db.Float)
    subcutaneous_fat = db.Column(db.Float)
    lean_body_mass = db.Column(db.Float)
    body_age = db.Column(db.Integer)
    body_type = db.Column(db.String(50))
    input_method = db.Column(db.String(20), default="manual")  # bluetooth | ocr | manual

    @property
    def bmi(self):
        try:
            h_m = self.patient.height_cm / 100
            return round(self.weight / (h_m * h_m), 1)
        except Exception:
            return None

    @staticmethod
    def bmi_category(bmi):
        if bmi is None:
            return None
        if bmi < 18.5:
            return "Underweight"
        if bmi < 25.0:
            return "Normal"
        if bmi < 30.0:
            return "Overweight"
        if bmi < 35.0:
            return "Obese I"
        if bmi < 40.0:
            return "Obese II"
        return "Obese III"

    def to_dict(self):
        bmi = self.bmi
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "weight": self.weight,
            "bmi": bmi,
            "bmi_category": self.bmi_category(bmi),
            "fat_mass": self.fat_mass,
            "muscle_mass": self.muscle_mass,
            "water_kg": self.water_kg,
            "body_fat_pct": self.body_fat_pct,
            "recorded_at": self.recorded_at.isoformat(),
            "notes": self.notes,
            # Extended fields
            "water_pct": self.water_pct,
            "bmr": self.bmr,
            "bone_mass": self.bone_mass,
            "visceral_fat": self.visceral_fat,
            "protein": self.protein,
            "skeletal_muscle_mass": self.skeletal_muscle_mass,
            "subcutaneous_fat": self.subcutaneous_fat,
            "lean_body_mass": self.lean_body_mass,
            "body_age": self.body_age,
            "body_type": self.body_type,
            "input_method": self.input_method,
        }


class UnregisteredUser(db.Model):
    __tablename__ = "unregistered_users"

    id = db.Column(db.Integer, primary_key=True)
    bale_chat_id = db.Column(db.String(50), unique=True, nullable=False)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_handled = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "bale_chat_id": self.bale_chat_id,
            "detected_at": self.detected_at.isoformat(),
            "is_handled": self.is_handled,
        }


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)  # 'new_user', 'inactive_patient'
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=True)
    bale_chat_id = db.Column(db.String(50), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    patient = db.relationship("Patient", foreign_keys=[patient_id])

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "bale_chat_id": self.bale_chat_id,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "is_read": self.is_read,
        }

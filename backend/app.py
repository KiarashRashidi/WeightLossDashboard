import logging

from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO

from config import Config
from models import db, Doctor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    JWTManager(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio.init_app(app)

    from routes.auth_routes import auth_bp
    from routes.patient_routes import patient_bp
    from routes.medical_test_routes import medical_test_bp
    from routes.bluetooth_routes import bluetooth_bp
    from routes.messaging_routes import messaging_bp
    from routes.bale_webhook import bale_bp
    from routes.notification_routes import notification_bp
    from routes.ocr_routes import ocr_bp
    from analytics_routes import analytics_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(patient_bp, url_prefix="/api/patients")
    app.register_blueprint(medical_test_bp, url_prefix="/api/patients")
    app.register_blueprint(bluetooth_bp, url_prefix="/api/bluetooth")
    app.register_blueprint(messaging_bp, url_prefix="/api/messaging")
    app.register_blueprint(bale_bp, url_prefix="/api/bale")
    app.register_blueprint(notification_bp, url_prefix="/api/notifications")
    app.register_blueprint(ocr_bp, url_prefix="/api/ocr")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")

    with app.app_context():
        db.create_all()
        _migrate_schema()
        _seed_admin(app)
        _start_scheduler(app)
        _start_bluetooth_service(app)
        _register_bale_webhook(app)

    logger.info("SmartWeigh MedDash backend started.")
    return app


def _migrate_schema():
    """Lightweight in-place migration for new columns on existing SQLite tables
    (db.create_all() only creates missing tables, it never alters existing ones)."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "patients" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("patients")]
        if "target_weight" not in columns:
            db.session.execute(text("ALTER TABLE patients ADD COLUMN target_weight FLOAT"))
            db.session.commit()
            logger.info("Migrated patients table: added target_weight column.")


def _seed_admin(app):
    if Doctor.query.count() == 0:
        doctor = Doctor(username=app.config["ADMIN_USERNAME"])
        doctor.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(doctor)
        db.session.commit()
        logger.info("Default doctor account created: %s", app.config["ADMIN_USERNAME"])


def _start_scheduler(app):
    from services.scheduler_service import start_scheduler
    start_scheduler(app, socketio)


def _register_bale_webhook(app):
    token = app.config.get("BALE_BOT_TOKEN", "")
    webhook_url = app.config.get("BALE_WEBHOOK_URL", "")
    if token and webhook_url:
        from services.bale_service import register_webhook
        register_webhook(token, webhook_url)
    else:
        logger.warning("Bale webhook not registered: BALE_BOT_TOKEN or BALE_WEBHOOK_URL missing.")


def _start_bluetooth_service(app):
    from services.bluetooth_service import BluetoothService
    ble = BluetoothService(socketio)
    app.ble_service = ble
    logger.info("Bluetooth service initialized.")


app = create_app()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)

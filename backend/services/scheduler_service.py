import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def start_scheduler(app, socketio):
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        func=lambda: _check_inactive_patients(app, socketio),
        trigger=CronTrigger(hour=8, minute=0),
        id="inactive_patient_check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started. Inactive patient check runs daily at 08:00 UTC.")
    return scheduler


def _check_inactive_patients(app, socketio):
    with app.app_context():
        try:
            from models import db, Patient, Notification

            inactive_days = app.config["SCHEDULER_INACTIVE_DAYS"]
            cutoff = datetime.utcnow() - timedelta(days=inactive_days)

            patients = Patient.query.filter_by(is_active=True).all()
            new_notifications = 0

            for patient in patients:
                last_visit = patient.last_visit
                if last_visit is not None and last_visit >= cutoff:
                    continue

                days_ago = (
                    (datetime.utcnow() - last_visit).days if last_visit else None
                )
                message = (
                    f"Patient {patient.name} hasn't visited in "
                    f"{days_ago} days." if days_ago else
                    f"Patient {patient.name} has never visited."
                )

                exists = Notification.query.filter_by(
                    type="inactive_patient",
                    patient_id=patient.id,
                    is_read=False,
                ).first()

                if not exists:
                    notif = Notification(
                        type="inactive_patient",
                        patient_id=patient.id,
                        message=message,
                    )
                    db.session.add(notif)
                    db.session.flush()

                    socketio.emit("notification:new", notif.to_dict())
                    new_notifications += 1
                    logger.info("Inactive patient alert: %s", message)

            db.session.commit()
            logger.info(
                "Inactive patient check complete. %d new notifications.", new_notifications
            )

        except Exception:
            logger.exception("Error during inactive patient scheduler check.")

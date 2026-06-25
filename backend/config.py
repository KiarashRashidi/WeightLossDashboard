import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///smartweigh.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-dev-secret-change-in-prod")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)

    GAPGPT_API_KEY = os.getenv("GAPGPT_API_KEY", "")
    BALE_BOT_TOKEN = os.getenv("BALE_BOT_TOKEN", "")
    SCHEDULER_INACTIVE_DAYS = int(os.getenv("SCHEDULER_INACTIVE_DAYS", "21"))

    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "doctor")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")

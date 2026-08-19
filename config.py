import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    
    class Settings(BaseSettings):
        DATA_SOURCE: str = "google_sheet"
        EXCEL_FILE_PATH: str = str(BASE_DIR / "google_sheet.xlsx")
        GOOGLE_SHEET_ID: Optional[str] = None
        GOOGLE_SHEET_NAME: str = "Rides"
        GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = str(BASE_DIR / "service_account.json")
        TWILIO_PROVIDER: str = "mock"
        TWILIO_ACCOUNT_SID: Optional[str] = None
        TWILIO_AUTH_TOKEN: Optional[str] = None
        TWILIO_PHONE_NUMBER: Optional[str] = None
        SERVER_HOST: str = "0.0.0.0"
        SERVER_PORT: int = 8000
        PUBLIC_WEBHOOK_URL: str = "http://localhost:8000"
        REMINDER_LEAD_MINUTES: int = 30
        REMINDER_WINDOW_TOLERANCE_MINUTES: int = 5
        POLL_INTERVAL_SECONDS: int = 60
        TIMEZONE: str = "Asia/Kolkata"

        model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

except Exception:
    try:
        from pydantic import BaseModel
        class Settings(BaseModel):
            DATA_SOURCE: str = os.getenv("DATA_SOURCE", "google_sheet")
            EXCEL_FILE_PATH: str = os.getenv("EXCEL_FILE_PATH", str(BASE_DIR / "google_sheet.xlsx"))
            GOOGLE_SHEET_ID: Optional[str] = os.getenv("GOOGLE_SHEET_ID")
            GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "Rides")
            GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json"))
            TWILIO_PROVIDER: str = os.getenv("TWILIO_PROVIDER", "mock")
            TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID")
            TWILIO_AUTH_TOKEN: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN")
            TWILIO_PHONE_NUMBER: Optional[str] = os.getenv("TWILIO_PHONE_NUMBER")
            SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
            SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
            PUBLIC_WEBHOOK_URL: str = os.getenv("PUBLIC_WEBHOOK_URL", "http://localhost:8000")
            REMINDER_LEAD_MINUTES: int = int(os.getenv("REMINDER_LEAD_MINUTES", "30"))
            REMINDER_WINDOW_TOLERANCE_MINUTES: int = int(os.getenv("REMINDER_WINDOW_TOLERANCE_MINUTES", "5"))
            POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
            TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    except Exception:
        from dataclasses import dataclass
        @dataclass
        class Settings:
            DATA_SOURCE: str = os.getenv("DATA_SOURCE", "google_sheet")
            EXCEL_FILE_PATH: str = os.getenv("EXCEL_FILE_PATH", str(BASE_DIR / "google_sheet.xlsx"))
            GOOGLE_SHEET_ID: Optional[str] = os.getenv("GOOGLE_SHEET_ID")
            GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "Rides")
            GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json"))
            TWILIO_PROVIDER: str = os.getenv("TWILIO_PROVIDER", "mock")
            TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID")
            TWILIO_AUTH_TOKEN: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN")
            TWILIO_PHONE_NUMBER: Optional[str] = os.getenv("TWILIO_PHONE_NUMBER")
            SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
            SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
            PUBLIC_WEBHOOK_URL: str = os.getenv("PUBLIC_WEBHOOK_URL", "http://localhost:8000")
            REMINDER_LEAD_MINUTES: int = int(os.getenv("REMINDER_LEAD_MINUTES", "30"))
            REMINDER_WINDOW_TOLERANCE_MINUTES: int = int(os.getenv("REMINDER_WINDOW_TOLERANCE_MINUTES", "5"))
            POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
            TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")


try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

settings = Settings()

import os
import tempfile
import pytest
from datetime import datetime
from src.models import Ride, RideStatus
from src.sheet_adapter import LocalExcelSheetAdapter
from src.twilio_adapter import generate_reminder_twiml


def test_excel_sheet_adapter_read_write():
    excel_path = "google_sheet.xlsx"
    if os.path.exists(excel_path):
        adapter = LocalExcelSheetAdapter(excel_path)
        rides = adapter.fetch_all_rides()
        assert len(rides) >= 1
        assert rides[0].ride_id.startswith("RIDE-")


def test_generate_reminder_twiml():
    xml = generate_reminder_twiml("John Doe", "JFK Terminal 4", "09:45 AM")
    assert "<Response>" in xml
    assert "<Say" in xml
    assert "John Doe" in xml
    assert "JFK Terminal 4" in xml
    assert "09:45 AM" in xml
    assert "call or message your customer" in xml.lower()

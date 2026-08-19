import os
import tempfile
import pytest
from datetime import datetime
from src.models import Ride, RideStatus
from src.sheet_adapter import CSVSheetAdapter
from src.twilio_adapter import generate_reminder_twiml


def test_csv_sheet_adapter_read_write():
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv") as tmp:
        tmp.write("ride_id,driver_name,driver_phone,pickup_location,scheduled_pickup_time,status,call_sid,call_outcome,last_called_at,notes\n")
        tmp.write("R-99,Test Driver,+15551234567,Test Location,2026-08-19 12:00,Pending,,,,\n")
        tmp_path = tmp.name

    try:
        adapter = CSVSheetAdapter(tmp_path)
        rides = adapter.fetch_all_rides()
        assert len(rides) == 1
        assert rides[0].ride_id == "R-99"
        assert rides[0].driver_name == "Test Driver"
        assert rides[0].status == RideStatus.PENDING

        # Update status
        success = adapter.update_ride_status("R-99", RideStatus.REMINDER_SENT, call_sid="CA_TEST_123", call_outcome="completed")
        assert success is True

        # Re-read file
        updated_rides = adapter.fetch_all_rides()
        assert len(updated_rides) == 1
        assert updated_rides[0].status == RideStatus.REMINDER_SENT
        assert updated_rides[0].call_sid == "CA_TEST_123"
        assert updated_rides[0].call_outcome == "completed"

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_generate_reminder_twiml():
    xml = generate_reminder_twiml("John Doe", "JFK Terminal 4", "09:45 AM")
    assert "<Response>" in xml
    assert "<Say" in xml
    assert "John Doe" in xml
    assert "JFK Terminal 4" in xml
    assert "09:45 AM" in xml
    assert "Call or message your customer" in xml or "call or message your customer" in xml.lower()

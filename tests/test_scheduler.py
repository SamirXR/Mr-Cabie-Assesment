import pytest
from datetime import datetime
from src.models import Ride, RideStatus, CallOutcome
from src.sheet_adapter import MockSheetAdapter
from src.twilio_adapter import MockCallService
from src.scheduler import ReminderScheduler


def test_is_ride_in_window():
    adapter = MockSheetAdapter()
    call_service = MockCallService()
    scheduler = ReminderScheduler(adapter, call_service, lead_minutes=30, tolerance_minutes=5)

    ref_time = datetime(2026, 8, 19, 9, 15)

    # 30 mins away (09:45) -> In Window
    ride_30m = Ride(
        ride_id="R-1",
        driver_name="Alex",
        driver_phone="+14155551111",
        pickup_location="JFK",
        scheduled_pickup_time=datetime(2026, 8, 19, 9, 45),
        status=RideStatus.PENDING,
    )
    assert scheduler.is_ride_in_window(ride_30m, ref_time) is True

    # 15 mins away (09:30) -> Outside Window
    ride_15m = Ride(
        ride_id="R-2",
        driver_name="Bob",
        driver_phone="+14155552222",
        pickup_location="LGA",
        scheduled_pickup_time=datetime(2026, 8, 19, 9, 30),
        status=RideStatus.PENDING,
    )
    assert scheduler.is_ride_in_window(ride_15m, ref_time) is False

    # 60 mins away (10:15) -> Outside Window
    ride_60m = Ride(
        ride_id="R-3",
        driver_name="Charlie",
        driver_phone="+14155553333",
        pickup_location="EWR",
        scheduled_pickup_time=datetime(2026, 8, 19, 10, 15),
        status=RideStatus.PENDING,
    )
    assert scheduler.is_ride_in_window(ride_60m, ref_time) is False


def test_scan_and_trigger_reminders_and_idempotency():
    ref_time = datetime(2026, 8, 19, 9, 15)
    
    ride_eligible = Ride(
        ride_id="R-101",
        driver_name="Marcus Vance",
        driver_phone="+14155552671",
        pickup_location="JFK Airport",
        scheduled_pickup_time=datetime(2026, 8, 19, 9, 45),
        status=RideStatus.PENDING,
    )
    
    ride_already_called = Ride(
        ride_id="R-105",
        driver_name="Robert Chen",
        driver_phone="+14155553344",
        pickup_location="Times Square",
        scheduled_pickup_time=datetime(2026, 8, 19, 9, 45),
        status=RideStatus.REMINDER_SENT,
    )

    adapter = MockSheetAdapter([ride_eligible, ride_already_called])
    call_service = MockCallService()
    scheduler = ReminderScheduler(adapter, call_service, lead_minutes=30, tolerance_minutes=5)

    # First Scan
    logs = scheduler.scan_and_trigger_reminders(reference_time=ref_time)
    
    assert len(logs) == 1
    assert logs[0].ride_id == "R-101"
    assert logs[0].driver_name == "Marcus Vance"
    
    # Verify sheet status updated to Reminder Sent
    all_rides = adapter.fetch_all_rides()
    r101 = next(r for r in all_rides if r.ride_id == "R-101")
    assert r101.status == RideStatus.REMINDER_SENT
    assert r101.call_sid is not None

    # Second Scan (Idempotency check: R-101 is now REMINDER_SENT, so 0 calls should trigger!)
    second_logs = scheduler.scan_and_trigger_reminders(reference_time=ref_time)
    assert len(second_logs) == 0


def test_unanswered_call_logging():
    ref_time = datetime(2026, 8, 19, 9, 15)
    ride_unanswered = Ride(
        ride_id="R-106",
        driver_name="Amira Patel",
        driver_phone="+14155556655",
        pickup_location="Brooklyn",
        scheduled_pickup_time=datetime(2026, 8, 19, 9, 45),
        status=RideStatus.PENDING,
    )

    adapter = MockSheetAdapter([ride_unanswered])
    call_service = MockCallService(default_outcome=CallOutcome.SIMULATED_NO_ANSWER)
    scheduler = ReminderScheduler(adapter, call_service)

    logs = scheduler.scan_and_trigger_reminders(reference_time=ref_time)
    assert len(logs) == 1
    assert logs[0].status == CallOutcome.SIMULATED_NO_ANSWER.value

    # Verify sheet status updated to No Answer
    updated_ride = adapter.fetch_all_rides()[0]
    assert updated_ride.status == RideStatus.NO_ANSWER

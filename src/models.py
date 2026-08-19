from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RideStatus(str, Enum):
    PENDING = "Pending"
    REMINDER_SENT = "Reminder Sent"
    CALLING = "Calling"
    NO_ANSWER = "No Answer"
    FAILED = "Failed"


class CallOutcome(str, Enum):
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    BUSY = "busy"
    NO_ANSWER = "no-answer"
    FAILED = "failed"
    CANCELED = "canceled"
    SIMULATED_ANSWERED = "simulated-answered"
    SIMULATED_NO_ANSWER = "simulated-no-answer"


class Ride(BaseModel):
    ride_id: str
    driver_name: str
    driver_phone: str
    pickup_location: str
    scheduled_pickup_time: datetime
    customer_name: Optional[str] = "Customer"
    customer_phone: Optional[str] = ""
    status: RideStatus = RideStatus.PENDING
    call_sid: Optional[str] = None
    last_called_at: Optional[datetime] = None
    call_outcome: Optional[str] = None
    notes: Optional[str] = ""

    def minutes_until_pickup(self, reference_time: Optional[datetime] = None) -> float:
        if reference_time is None:
            reference_time = datetime.now(self.scheduled_pickup_time.tzinfo)
        diff = self.scheduled_pickup_time - reference_time
        return diff.total_seconds() / 60.0

    def is_eligible_for_reminder(self, lead_minutes: int = 30, tolerance_minutes: int = 5) -> bool:
        if self.status in [RideStatus.REMINDER_SENT, RideStatus.CALLING]:
            return False
        minutes_remaining = self.minutes_until_pickup()
        min_threshold = lead_minutes - tolerance_minutes
        max_threshold = lead_minutes + tolerance_minutes
        return min_threshold <= minutes_remaining <= max_threshold


class CallLog(BaseModel):
    call_sid: str
    ride_id: str
    driver_name: str
    driver_phone: str
    status: str
    timestamp: datetime = Field(default_factory=datetime.now)
    message_played: str
    duration_seconds: Optional[int] = 0
    outcome_details: Optional[str] = ""

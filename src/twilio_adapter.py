import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from src.models import Ride, CallLog, CallOutcome

logger = logging.getLogger(__name__)


def generate_reminder_twiml(driver_name: str, pickup_location: str, pickup_time_str: str) -> str:
    """Generates TwiML voice response instructing driver on mandatory pickup actions."""
    response = VoiceResponse()
    message = (
        f"Hello {driver_name}, this is an urgent automated reminder from Cabie Fleet Management. "
        f"You have a scheduled pickup at {pickup_location} at {pickup_time_str}. "
        f"Please perform two steps immediately: First, call or message your customer to confirm details. "
        f"Second, start heading to the pickup location right away. Thank you and drive safely!"
    )
    response.say(message)
    return str(response)


class BaseCallService(ABC):
    @abstractmethod
    def make_reminder_call(self, ride: Ride, webhook_base_url: Optional[str] = None) -> CallLog:
        pass

    @abstractmethod
    def get_call_logs(self) -> List[CallLog]:
        pass


class MockCallService(BaseCallService):
    """Mock Twilio call service for offline testing and demo dashboards."""

    def __init__(self, default_outcome: CallOutcome = CallOutcome.SIMULATED_ANSWERED):
        self.call_logs: List[CallLog] = []
        self.default_outcome = default_outcome

    def make_reminder_call(self, ride: Ride, webhook_base_url: Optional[str] = None) -> CallLog:
        call_sid = f"CA_MOCK_{uuid.uuid4().hex[:12].upper()}"
        pickup_time_str = ride.scheduled_pickup_time.strftime("%I:%M %p")
        
        twiml_text = (
            f"Hello {ride.driver_name}, this is an automated reminder from Cabie Fleet Management. "
            f"You have a pickup scheduled at {ride.pickup_location} at {pickup_time_str}. "
            f"Please remember to contact your customer and head to the pickup location on time."
        )

        call_log = CallLog(
            call_sid=call_sid,
            ride_id=ride.ride_id,
            driver_name=ride.driver_name,
            driver_phone=ride.driver_phone,
            status=self.default_outcome.value,
            timestamp=datetime.now(),
            message_played=twiml_text,
            duration_seconds=18,
            outcome_details=f"Mock outbound call triggered successfully to {ride.driver_phone}",
        )
        self.call_logs.append(call_log)
        logger.info(f"[MOCK TWILIO CALL] Call SID {call_sid} to {ride.driver_name} ({ride.driver_phone}) - Outcome: {call_log.status}")
        return call_log

    def get_call_logs(self) -> List[CallLog]:
        return self.call_logs


import urllib.parse

class TwilioCallService(BaseCallService):
    """Production Twilio API Integration."""

    def __init__(self, account_sid: str, auth_token: str, from_phone: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_phone = from_phone
        self.client = Client(account_sid, auth_token)
        self.call_logs: List[CallLog] = []

    def make_reminder_call(self, ride: Ride, webhook_base_url: Optional[str] = None) -> CallLog:
        pickup_time_str = ride.scheduled_pickup_time.strftime("%I:%M %p")
        twiml = generate_reminder_twiml(ride.driver_name, ride.pickup_location, pickup_time_str)

        try:
            if webhook_base_url and "localhost" not in webhook_base_url:
                url_target = f"{webhook_base_url.rstrip('/')}/twiml/reminder?driver_name={urllib.parse.quote(ride.driver_name)}"
            else:
                url_target = f"https://twimlets.com/echo?Twiml={urllib.parse.quote(twiml)}"

            call_kwargs = {
                "to": ride.driver_phone,
                "from_": self.from_phone,
                "url": url_target,
            }

            if webhook_base_url:
                call_kwargs["status_callback"] = f"{webhook_base_url}/webhooks/twilio/status"
                call_kwargs["status_callback_event"] = ["initiated", "ringing", "answered", "completed"]
                call_kwargs["status_callback_method"] = "POST"

            call = self.client.calls.create(**call_kwargs)

            call_log = CallLog(
                call_sid=call.sid,
                ride_id=ride.ride_id,
                driver_name=ride.driver_name,
                driver_phone=ride.driver_phone,
                status=call.status,
                timestamp=datetime.now(),
                message_played=twiml,
                outcome_details=f"Twilio Call Created with status {call.status}",
            )
            self.call_logs.append(call_log)
            logger.info(f"[TWILIO API] Outbound Call SID {call.sid} initiated to {ride.driver_phone}")
            return call_log
        except Exception as e:
            logger.error(f"[TWILIO API ERROR] Failed to make call to {ride.driver_phone}: {e}")
            failed_log = CallLog(
                call_sid=f"CA_FAILED_{uuid.uuid4().hex[:8]}",
                ride_id=ride.ride_id,
                driver_name=ride.driver_name,
                driver_phone=ride.driver_phone,
                status=CallOutcome.FAILED.value,
                timestamp=datetime.now(),
                message_played=twiml,
                outcome_details=str(e),
            )
            self.call_logs.append(failed_log)
            return failed_log

    def get_call_logs(self) -> List[CallLog]:
        return self.call_logs


def get_call_service(config) -> BaseCallService:
    """Factory to instantiate configured call service provider."""
    provider = config.TWILIO_PROVIDER.lower()
    if provider == "twilio":
        if not config.TWILIO_ACCOUNT_SID or not config.TWILIO_AUTH_TOKEN or not config.TWILIO_PHONE_NUMBER:
            logger.warning("Twilio credentials missing in config. Falling back to MockCallService.")
            return MockCallService()
        return TwilioCallService(
            account_sid=config.TWILIO_ACCOUNT_SID,
            auth_token=config.TWILIO_AUTH_TOKEN,
            from_phone=config.TWILIO_PHONE_NUMBER,
        )
    return MockCallService()

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from src.models import Ride, RideStatus, CallLog, CallOutcome
from src.sheet_adapter import BaseSheetAdapter
from src.twilio_adapter import BaseCallService

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Core Orchestration Engine that checks scheduled rides, evaluates the 30-minute window,

    triggers calls via Twilio, and records results back in the Sheet/CSV.
    """

    def __init__(
        self,
        sheet_adapter: BaseSheetAdapter,
        call_service: BaseCallService,
        lead_minutes: int = 30,
        tolerance_minutes: int = 5,
        webhook_base_url: Optional[str] = None,
    ):
        self.sheet_adapter = sheet_adapter
        self.call_service = call_service
        self.lead_minutes = lead_minutes
        self.tolerance_minutes = tolerance_minutes
        self.webhook_base_url = webhook_base_url
        self.processed_call_sids: Dict[str, CallLog] = {}

    def is_ride_in_window(self, ride: Ride, reference_time: datetime) -> bool:
        """Evaluates if ride scheduled time falls within [30 - tolerance, 30 + tolerance] minutes from reference_time."""
        diff_minutes = (ride.scheduled_pickup_time - reference_time).total_seconds() / 60.0
        min_threshold = self.lead_minutes - self.tolerance_minutes
        max_threshold = self.lead_minutes + self.tolerance_minutes
        
        logger.debug(
            f"Checking Ride {ride.ride_id} ({ride.driver_name}): "
            f"scheduled={ride.scheduled_pickup_time.strftime('%H:%M')}, "
            f"ref={reference_time.strftime('%H:%M')}, diff={diff_minutes:.1f}m, "
            f"window=[{min_threshold}, {max_threshold}]"
        )
        return min_threshold <= diff_minutes <= max_threshold

    def scan_and_trigger_reminders(self, reference_time: Optional[datetime] = None) -> List[CallLog]:
        """Scans sheet for upcoming rides ~30 minutes away and dispatches automated Twilio calls."""
        if reference_time is None:
            reference_time = datetime.now()

        logger.info(f"Scanning sheet for rides 30 mins from {reference_time.strftime('%Y-%m-%d %H:%M:%S')}...")
        all_rides = self.sheet_adapter.fetch_all_rides()
        triggered_logs = []

        for ride in all_rides:
            # Skip already handled rides (Idempotency Check)
            if ride.status in [RideStatus.REMINDER_SENT, RideStatus.CALLING]:
                logger.info(f"Skipping Ride {ride.ride_id} for {ride.driver_name} - already marked as '{ride.status.value}'.")
                continue

            # Time window check
            if self.is_ride_in_window(ride, reference_time):
                logger.info(
                    f"Match found! Ride {ride.ride_id} for {ride.driver_name} is scheduled at "
                    f"{ride.scheduled_pickup_time.strftime('%H:%M')} (30 mins from {reference_time.strftime('%H:%M')})."
                )
                
                # Mark as Calling immediately to lock row
                self.sheet_adapter.update_ride_status(ride.ride_id, RideStatus.CALLING)
                
                # Make outbound Twilio Call
                call_log = self.call_service.make_reminder_call(ride, self.webhook_base_url)
                self.processed_call_sids[call_log.call_sid] = call_log
                triggered_logs.append(call_log)

                # Update sheet status based on call outcome
                final_status = RideStatus.REMINDER_SENT
                if call_log.status in [CallOutcome.NO_ANSWER.value, CallOutcome.BUSY.value, CallOutcome.SIMULATED_NO_ANSWER.value]:
                    final_status = RideStatus.NO_ANSWER
                elif call_log.status in [CallOutcome.FAILED.value, CallOutcome.CANCELED.value]:
                    final_status = RideStatus.FAILED

                self.sheet_adapter.update_ride_status(
                    ride_id=ride.ride_id,
                    status=final_status,
                    call_sid=call_log.call_sid,
                    call_outcome=call_log.status,
                    notes=f"Reminder call triggered at {reference_time.strftime('%H:%M')}",
                )

        logger.info(f"Scan complete. Triggered {len(triggered_logs)} calls.")
        return triggered_logs

    def trigger_single_ride(self, ride_id: str) -> Optional[CallLog]:
        """Manually trigger a reminder call for a specific ride (used for demo / manual overrides)."""
        all_rides = self.sheet_adapter.fetch_all_rides()
        target_ride = next((r for r in all_rides if r.ride_id == ride_id), None)
        if not target_ride:
            logger.error(f"Ride ID {ride_id} not found.")
            return None

        self.sheet_adapter.update_ride_status(ride_id, RideStatus.CALLING)
        call_log = self.call_service.make_reminder_call(target_ride, self.webhook_base_url)
        self.processed_call_sids[call_log.call_sid] = call_log

        final_status = RideStatus.REMINDER_SENT
        if call_log.status in [CallOutcome.NO_ANSWER.value, CallOutcome.BUSY.value, CallOutcome.SIMULATED_NO_ANSWER.value]:
            final_status = RideStatus.NO_ANSWER
        elif call_log.status in [CallOutcome.FAILED.value, CallOutcome.CANCELED.value]:
            final_status = RideStatus.FAILED

        self.sheet_adapter.update_ride_status(
            ride_id=ride_id,
            status=final_status,
            call_sid=call_log.call_sid,
            call_outcome=call_log.status,
            notes=f"Manual call triggered at {datetime.now().strftime('%H:%M')}",
        )
        return call_log

    def handle_twilio_webhook_callback(self, call_sid: str, call_status: str, duration: int = 0):
        """Processes async status callbacks from Twilio when calls connect or end."""
        logger.info(f"Received Twilio Call Status Callback: SID={call_sid}, Status={call_status}")
        
        # Map Twilio call status to RideStatus
        status_map = {
            "completed": RideStatus.REMINDER_SENT,
            "no-answer": RideStatus.NO_ANSWER,
            "busy": RideStatus.NO_ANSWER,
            "failed": RideStatus.FAILED,
            "canceled": RideStatus.FAILED,
        }

        new_status = status_map.get(call_status.lower(), RideStatus.REMINDER_SENT)
        
        # Find ride associated with call_sid in memory or sheet
        all_rides = self.sheet_adapter.fetch_all_rides()
        matching_ride = next((r for r in all_rides if r.call_sid == call_sid), None)
        
        if matching_ride:
            self.sheet_adapter.update_ride_status(
                ride_id=matching_ride.ride_id,
                status=new_status,
                call_sid=call_sid,
                call_outcome=call_status,
                notes=f"Twilio Callback: {call_status} ({duration}s)",
            )
            logger.info(f"Updated Ride {matching_ride.ride_id} status to '{new_status.value}' via Twilio Webhook.")

import argparse
import logging
import sys
import time
from datetime import datetime, date

from config import settings
from src.sheet_adapter import get_sheet_adapter
from src.twilio_adapter import get_call_service
from src.scheduler import ReminderScheduler

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("cabie_agent")


def run_dashboard(host: str, port: int):
    """Starts FastAPI web dashboard & webhook server using uvicorn."""
    import uvicorn
    logger.info(f"Starting Cabie Driver Reminder Dashboard & Webhook Server at http://{host}:{port}")
    uvicorn.run("src.twiml_server:app", host=host, port=port, reload=True)


def run_scan_once(simulated_time_str: str = None):
    """Executes a single scan cycle for scheduled rides 30 mins away."""
    sheet_adapter = get_sheet_adapter(settings)
    call_service = get_call_service(settings)
    scheduler = ReminderScheduler(
        sheet_adapter=sheet_adapter,
        call_service=call_service,
        lead_minutes=settings.REMINDER_LEAD_MINUTES,
        tolerance_minutes=settings.REMINDER_WINDOW_TOLERANCE_MINUTES,
        webhook_base_url=settings.PUBLIC_WEBHOOK_URL,
    )

    ref_dt = None
    if simulated_time_str:
        parts = simulated_time_str.split(":")
        today = date.today()
        ref_dt = datetime(today.year, today.month, today.day, int(parts[0]), int(parts[1]))

    logger.info("==================================================")
    logger.info(f"CABIE DRIVER REMINDER AGENT — SCANNING (Mode: {settings.TWILIO_PROVIDER.upper()})")
    logger.info("==================================================")
    
    logs = scheduler.scan_and_trigger_reminders(reference_time=ref_dt)
    
    print("\n--- SCAN SUMMARY ---")
    print(f"Total Calls Triggered: {len(logs)}")
    for log in logs:
        print(f" • [{log.status.upper()}] Driver: {log.driver_name} ({log.driver_phone}) | Call SID: {log.call_sid}")
    print("---------------------\n")


def run_daemon(interval_seconds: int = 60):
    """Runs continuous background polling loop checking rides every N seconds."""
    sheet_adapter = get_sheet_adapter(settings)
    call_service = get_call_service(settings)
    scheduler = ReminderScheduler(
        sheet_adapter=sheet_adapter,
        call_service=call_service,
        lead_minutes=settings.REMINDER_LEAD_MINUTES,
        tolerance_minutes=settings.REMINDER_WINDOW_TOLERANCE_MINUTES,
        webhook_base_url=settings.PUBLIC_WEBHOOK_URL,
    )

    logger.info(f"Starting Driver Reminder Agent Daemon (polling every {interval_seconds}s)... Press Ctrl+C to stop.")
    try:
        while True:
            scheduler.scan_and_trigger_reminders()
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user.")


def main():
    parser = argparse.ArgumentParser(description="Cabie Driver Pickup Reminder Agent CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to execute")

    # Command: dashboard
    dash_parser = subparsers.add_parser("dashboard", help="Launch interactive web UI dashboard and webhook server")
    dash_parser.add_argument("--host", default=settings.SERVER_HOST, help="Server host")
    dash_parser.add_argument("--port", type=int, default=settings.SERVER_PORT, help="Server port")

    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Run a single scan for rides ~30 minutes away")
    scan_parser.add_argument("--simulated-time", help="Simulate reference time (HH:MM format, e.g. 09:45)")

    # Command: daemon
    daemon_parser = subparsers.add_parser("daemon", help="Run background daemon polling every interval seconds")
    daemon_parser.add_argument("--interval", type=int, default=settings.POLL_INTERVAL_SECONDS, help="Polling interval in seconds")

    # Command: test-call
    call_parser = subparsers.add_parser("test-call", help="Force trigger a reminder call for a single ride ID")
    call_parser.add_argument("--ride-id", required=True, help="Ride ID to call (e.g. RIDE-101)")

    # Command: reset
    subparsers.add_parser("reset", help="Reset all ride statuses back to Pending in Sheet / CSV")

    args = parser.parse_args()

    if args.command == "dashboard" or args.command is None:
        # Default to running dashboard if no args passed
        host = getattr(args, "host", settings.SERVER_HOST)
        port = getattr(args, "port", settings.SERVER_PORT)
        run_dashboard(host, port)

    elif args.command == "scan":
        run_scan_once(args.simulated_time)

    elif args.command == "daemon":
        run_daemon(args.interval)

    elif args.command == "test-call":
        sheet_adapter = get_sheet_adapter(settings)
        call_service = get_call_service(settings)
        scheduler = ReminderScheduler(sheet_adapter, call_service)
        log = scheduler.trigger_single_ride(args.ride_id)
        if log:
            print(f"Successfully triggered call for Ride {args.ride_id}!")
            print(f"Call SID: {log.call_sid}")
            print(f"Message: {log.message_played}")
        else:
            print(f"Ride ID {args.ride_id} not found.")

    elif args.command == "reset":
        sheet_adapter = get_sheet_adapter(settings)
        sheet_adapter.reset_all_statuses()
        print("All ride statuses reset to 'Pending'.")


if __name__ == "__main__":
    main()

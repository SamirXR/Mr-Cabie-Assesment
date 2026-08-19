import logging
import os
from datetime import datetime, date
from typing import Optional
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import settings
from src.models import Ride, RideStatus, CallOutcome
from src.sheet_adapter import get_sheet_adapter
from src.twilio_adapter import get_call_service, generate_reminder_twiml
from src.scheduler import ReminderScheduler

logger = logging.getLogger("cabie_agent")

app = FastAPI(title="Cabie Driver Reminder Agent API")

# Mount Static Files & Templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_dir = os.path.join(BASE_DIR, "dashboard", "static")
templates_dir = os.path.join(BASE_DIR, "dashboard", "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=templates_dir)

# Initialize Global Components
sheet_adapter = get_sheet_adapter(settings)
call_service = get_call_service(settings)
scheduler = ReminderScheduler(
    sheet_adapter=sheet_adapter,
    call_service=call_service,
    lead_minutes=settings.REMINDER_LEAD_MINUTES,
    tolerance_minutes=settings.REMINDER_WINDOW_TOLERANCE_MINUTES,
    webhook_base_url=settings.PUBLIC_WEBHOOK_URL,
)


class ScanRequest(BaseModel):
    reference_time: Optional[str] = None


class AddRideRequest(BaseModel):
    driver_name: str
    driver_phone: str
    pickup_location: str
    scheduled_pickup_time: str
    customer_name: Optional[str] = "Customer"


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Serves interactive visual dashboard for fleet managers and test evaluators."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/twiml/reminder", response_class=Response)
async def get_reminder_twiml(ride_id: Optional[str] = None):
    """Serves dynamic TwiML XML voice instructions when Twilio executes the outbound call."""
    driver_name = "Driver"
    pickup_location = "Pickup Location"
    pickup_time_str = "scheduled time"

    if ride_id:
        all_rides = sheet_adapter.fetch_all_rides()
        target = next((r for r in all_rides if r.ride_id == ride_id), None)
        if target:
            driver_name = target.driver_name
            pickup_location = target.pickup_location
            pickup_time_str = target.scheduled_pickup_time.strftime("%I:%M %p")

    xml_content = generate_reminder_twiml(driver_name, pickup_location, pickup_time_str)
    return Response(content=xml_content, media_type="application/xml")


@app.post("/webhooks/twilio/status")
async def twilio_status_callback(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: Optional[int] = Form(0),
):
    """Receives asynchronous call status callbacks from Twilio (completed, no-answer, busy, failed)."""
    logger.info(f"Twilio Webhook Callback: SID={CallSid}, Status={CallStatus}, Duration={CallDuration}s")
    scheduler.handle_twilio_webhook_callback(CallSid, CallStatus, CallDuration or 0)
    return {"status": "accepted"}


@app.get("/api/rides")
async def get_rides():
    """Returns list of all scheduled rides from Sheet / CSV."""
    rides = sheet_adapter.fetch_all_rides()
    return rides


@app.post("/api/scan")
async def run_scan(payload: ScanRequest):
    """Triggers 30-minute reminder scan with optional reference_time override."""
    ref_dt = None
    if payload.reference_time:
        try:
            parts = payload.reference_time.split(":")
            today = date.today()
            ref_dt = datetime(today.year, today.month, today.day, int(parts[0]), int(parts[1]))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {e}")

    triggered_logs = scheduler.scan_and_trigger_reminders(reference_time=ref_dt)
    return {
        "status": "success",
        "reference_time": (ref_dt or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "triggered_count": len(triggered_logs),
        "calls": [log.model_dump() for log in triggered_logs],
    }


@app.post("/api/call-ride")
async def call_ride(ride_id: str):
    """Force triggers a reminder call for a specific ride ID."""
    call_log = scheduler.trigger_single_ride(ride_id)
    if not call_log:
        raise HTTPException(status_code=404, detail="Ride ID not found")
    return {"status": "success", "call": call_log.model_dump()}


@app.post("/api/add-ride")
async def add_ride(payload: AddRideRequest):
    """Adds a new ride record for live testing."""
    import uuid

    ride_id = f"RIDE-{uuid.uuid4().hex[:4].upper()}"

    # Parse pickup time
    parts = payload.scheduled_pickup_time.split(":")
    today = date.today()
    scheduled_dt = datetime(today.year, today.month, today.day, int(parts[0]), int(parts[1]))

    ride = Ride(
        ride_id=ride_id,
        driver_name=payload.driver_name,
        driver_phone=payload.driver_phone,
        pickup_location=payload.pickup_location,
        scheduled_pickup_time=scheduled_dt,
        customer_name=payload.customer_name or "Customer",
        status=RideStatus.PENDING,
    )
    success = sheet_adapter.add_ride(ride)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to append ride to sheet")
    return {"status": "success", "ride": ride.model_dump()}


@app.post("/api/reset")
async def reset_demo_data():
    """Resets all ride statuses back to Pending."""
    sheet_adapter.reset_all_statuses()
    return {"status": "success", "message": "All ride statuses reset to Pending."}


@app.get("/api/logs")
async def get_call_logs():
    """Returns recent call history logs."""
    return call_service.get_call_logs()


@app.get("/api/config")
async def get_config():
    """Returns agent system status and mode."""
    return {
        "data_source": settings.DATA_SOURCE,
        "twilio_provider": settings.TWILIO_PROVIDER,
        "reminder_lead_minutes": settings.REMINDER_LEAD_MINUTES,
        "tolerance_minutes": settings.REMINDER_WINDOW_TOLERANCE_MINUTES,
        "public_webhook_url": settings.PUBLIC_WEBHOOK_URL,
    }

import csv
import logging
import os
import threading
from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import List, Optional
from src.models import Ride, RideStatus

logger = logging.getLogger(__name__)


def parse_datetime(dt_str: str) -> datetime:
    """Parses various datetime strings flexibly."""
    dt_str = str(dt_str).strip()

    # Try parsing Excel float timestamp (e.g. 46253.40625)
    try:
        f = float(dt_str)
        if f > 35000:
            from datetime import timedelta
            return datetime(1899, 12, 30) + timedelta(days=f)
    except ValueError:
        pass
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(dt_str, fmt)
            # If format was time-only, default to today's date
            if fmt in ["%H:%M:%S", "%H:%M"]:
                today = date.today()
                parsed = datetime(today.year, today.month, today.day, parsed.hour, parsed.minute, parsed.second)
            return parsed
        except ValueError:
            continue
    raise ValueError(f"Could not parse datetime string: '{dt_str}'")


class BaseSheetAdapter(ABC):
    @abstractmethod
    def fetch_all_rides(self) -> List[Ride]:
        pass

    @abstractmethod
    def update_ride_status(
        self,
        ride_id: str,
        status: RideStatus,
        call_sid: Optional[str] = None,
        call_outcome: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        pass

    @abstractmethod
    def add_ride(self, ride: Ride) -> bool:
        pass

    @abstractmethod
    def reset_all_statuses(self) -> bool:
        pass


class MockSheetAdapter(BaseSheetAdapter):
    """In-memory thread-safe adapter for instant testing and UI demonstration."""

    def __init__(self, initial_rides: Optional[List[Ride]] = None):
        self._lock = threading.RLock()
        if initial_rides:
            self._rides = {r.ride_id: r for r in initial_rides}
        else:
            self._rides = {}

    def fetch_all_rides(self) -> List[Ride]:
        with self._lock:
            return list(self._rides.values())

    def update_ride_status(
        self,
        ride_id: str,
        status: RideStatus,
        call_sid: Optional[str] = None,
        call_outcome: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        with self._lock:
            if ride_id in self._rides:
                ride = self._rides[ride_id]
                ride.status = status
                if call_sid:
                    ride.call_sid = call_sid
                if call_outcome:
                    ride.call_outcome = call_outcome
                if notes is not None:
                    ride.notes = notes
                ride.last_called_at = datetime.now()
                return True
            return False

    def add_ride(self, ride: Ride) -> bool:
        with self._lock:
            self._rides[ride.ride_id] = ride
            return True

    def reset_all_statuses(self) -> bool:
        with self._lock:
            for ride in self._rides.values():
                ride.status = RideStatus.PENDING
                ride.call_sid = None
                ride.call_outcome = None
                ride.last_called_at = None
            return True


class CSVSheetAdapter(BaseSheetAdapter):
    """CSV File based Adapter providing persistent local storage matching Google Sheet schema."""

    def __init__(self, csv_filepath: str):
        self.filepath = csv_filepath
        self._lock = threading.RLock()

    def fetch_all_rides(self) -> List[Ride]:
        with self._lock:
            if not os.path.exists(self.filepath):
                logger.warning(f"CSV file {self.filepath} does not exist.")
                return []

            rides = []
            with open(self.filepath, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader, start=1):
                    try:
                        ride_id = row.get("ride_id") or row.get("Ride ID") or f"RIDE-{idx:03d}"
                        driver_name = row.get("driver_name") or row.get("Driver Name") or ""
                        driver_phone = row.get("driver_phone") or row.get("Driver Phone") or ""
                        pickup_location = row.get("pickup_location") or row.get("Pickup Location") or ""
                        time_str = row.get("scheduled_pickup_time") or row.get("Scheduled Pickup Time") or ""
                        status_str = row.get("status") or row.get("Status") or "Pending"
                        call_sid = row.get("call_sid") or row.get("Call SID") or ""
                        call_outcome = row.get("call_outcome") or row.get("Call Outcome") or ""
                        notes = row.get("notes") or row.get("Notes") or ""

                        if not driver_name or not time_str:
                            continue

                        scheduled_dt = parse_datetime(time_str)

                        try:
                            status_enum = RideStatus(status_str)
                        except ValueError:
                            status_enum = RideStatus.PENDING

                        ride = Ride(
                            ride_id=ride_id,
                            driver_name=driver_name,
                            driver_phone=driver_phone,
                            pickup_location=pickup_location,
                            scheduled_pickup_time=scheduled_dt,
                            status=status_enum,
                            call_sid=call_sid if call_sid else None,
                            call_outcome=call_outcome if call_outcome else None,
                            notes=notes,
                        )
                        rides.append(ride)
                    except Exception as e:
                        logger.error(f"Error parsing CSV row {row}: {e}")
            return rides

    def update_ride_status(
        self,
        ride_id: str,
        status: RideStatus,
        call_sid: Optional[str] = None,
        call_outcome: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        with self._lock:
            if not os.path.exists(self.filepath):
                return False

            rows = []
            updated = False
            fieldnames = []

            with open(self.filepath, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                for idx, row in enumerate(reader, start=1):
                    row_id = row.get("ride_id") or row.get("Ride ID") or f"RIDE-{idx:03d}"
                    if row_id == ride_id:
                        # Normalize column keys
                        status_col = "status" if "status" in row else "Status"
                        sid_col = "call_sid" if "call_sid" in row else "Call SID"
                        outcome_col = "call_outcome" if "call_outcome" in row else "Call Outcome"
                        called_col = "last_called_at" if "last_called_at" in row else "Last Called At"
                        notes_col = "notes" if "notes" in row else "Notes"

                        row[status_col] = status.value
                        if call_sid:
                            row[sid_col] = call_sid
                        if call_outcome:
                            row[outcome_col] = call_outcome
                        if called_col in row:
                            row[called_col] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        if notes is not None and notes_col in row:
                            row[notes_col] = notes
                        updated = True
                    rows.append(row)

            if updated:
                with open(self.filepath, mode="w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

            return updated

    def add_ride(self, ride: Ride) -> bool:
        with self._lock:
            file_exists = os.path.exists(self.filepath)
            fieldnames = [
                "ride_id",
                "driver_name",
                "driver_phone",
                "pickup_location",
                "scheduled_pickup_time",
                "status",
                "call_sid",
                "call_outcome",
                "last_called_at",
                "notes",
            ]
            with open(self.filepath, mode="a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists or os.path.getsize(self.filepath) == 0:
                    writer.writeheader()
                writer.writerow(
                    {
                        "ride_id": ride.ride_id,
                        "driver_name": ride.driver_name,
                        "driver_phone": ride.driver_phone,
                        "pickup_location": ride.pickup_location,
                        "scheduled_pickup_time": ride.scheduled_pickup_time.strftime("%Y-%m-%d %H:%M"),
                        "status": ride.status.value,
                        "call_sid": ride.call_sid or "",
                        "call_outcome": ride.call_outcome or "",
                        "last_called_at": ride.last_called_at.strftime("%Y-%m-%d %H:%M:%S") if ride.last_called_at else "",
                        "notes": ride.notes or "",
                    }
                )
            return True

    def reset_all_statuses(self) -> bool:
        with self._lock:
            if not os.path.exists(self.filepath):
                return False
            rides = self.fetch_all_rides()
            for r in rides:
                r.status = RideStatus.PENDING
                r.call_sid = None
                r.call_outcome = None
                r.last_called_at = None

            fieldnames = [
                "ride_id",
                "driver_name",
                "driver_phone",
                "pickup_location",
                "scheduled_pickup_time",
                "status",
                "call_sid",
                "call_outcome",
                "last_called_at",
                "notes",
            ]
            with open(self.filepath, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in rides:
                    writer.writerow(
                        {
                            "ride_id": r.ride_id,
                            "driver_name": r.driver_name,
                            "driver_phone": r.driver_phone,
                            "pickup_location": r.pickup_location,
                            "scheduled_pickup_time": r.scheduled_pickup_time.strftime("%Y-%m-%d %H:%M"),
                            "status": RideStatus.PENDING.value,
                            "call_sid": "",
                            "call_outcome": "",
                            "last_called_at": "",
                            "notes": r.notes or "",
                        }
                    )
            return True


class GoogleSheetAdapter(BaseSheetAdapter):
    """Google Sheets API Adapter using gspread and service account auth."""

    def __init__(self, sheet_id: str, service_account_file: str, sheet_name: str = "Rides"):
        self.sheet_id = sheet_id
        self.service_account_file = service_account_file
        self.sheet_name = sheet_name
        self._sheet = None

    def _get_worksheet(self):
        if self._sheet is None:
            import gspread
            gc = gspread.service_account(filename=self.service_account_file)
            sh = gc.open_by_key(self.sheet_id)
            self._sheet = sh.worksheet(self.sheet_name)
        return self._sheet

    def fetch_all_rides(self) -> List[Ride]:
        try:
            ws = self._get_worksheet()
            records = ws.get_all_records()
            rides = []
            for idx, row in enumerate(records, start=2):  # Row 1 is header
                ride_id = str(row.get("ride_id") or row.get("Ride ID") or f"RIDE-{idx-1:03d}")
                driver_name = str(row.get("driver_name") or row.get("Driver Name") or "")
                driver_phone = str(row.get("driver_phone") or row.get("Driver Phone") or "")
                pickup_location = str(row.get("pickup_location") or row.get("Pickup Location") or "")
                time_str = str(row.get("scheduled_pickup_time") or row.get("Scheduled Pickup Time") or "")
                status_str = str(row.get("status") or row.get("Status") or "Pending")
                call_sid = str(row.get("call_sid") or row.get("Call SID") or "")
                call_outcome = str(row.get("call_outcome") or row.get("Call Outcome") or "")

                if not driver_name or not time_str:
                    continue

                scheduled_dt = parse_datetime(time_str)
                try:
                    status_enum = RideStatus(status_str)
                except ValueError:
                    status_enum = RideStatus.PENDING

                ride = Ride(
                    ride_id=ride_id,
                    driver_name=driver_name,
                    driver_phone=driver_phone,
                    pickup_location=pickup_location,
                    scheduled_pickup_time=scheduled_dt,
                    status=status_enum,
                    call_sid=call_sid if call_sid else None,
                    call_outcome=call_outcome if call_outcome else None,
                )
                rides.append(ride)
            return rides
        except Exception as e:
            logger.error(f"Failed to fetch rides from Google Sheet: {e}")
            return []

    def update_ride_status(
        self,
        ride_id: str,
        status: RideStatus,
        call_sid: Optional[str] = None,
        call_outcome: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        try:
            ws = self._get_worksheet()
            cell = ws.find(ride_id)
            if not cell:
                logger.warning(f"Ride ID {ride_id} not found in Google Sheet.")
                return False

            row_num = cell.row
            headers = ws.row_values(1)
            
            def get_col_idx(possible_names):
                for name in possible_names:
                    if name in headers:
                        return headers.index(name) + 1
                return None

            status_col = get_col_idx(["status", "Status"])
            sid_col = get_col_idx(["call_sid", "Call SID"])
            outcome_col = get_col_idx(["call_outcome", "Call Outcome"])
            called_col = get_col_idx(["last_called_at", "Last Called At"])

            if status_col:
                ws.update_cell(row_num, status_col, status.value)
            if call_sid and sid_col:
                ws.update_cell(row_num, sid_col, call_sid)
            if call_outcome and outcome_col:
                ws.update_cell(row_num, outcome_col, call_outcome)
            if called_col:
                ws.update_cell(row_num, called_col, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            return True
        except Exception as e:
            logger.error(f"Failed to update ride status in Google Sheet: {e}")
            return False

    def add_ride(self, ride: Ride) -> bool:
        try:
            ws = self._get_worksheet()
            ws.append_row(
                [
                    ride.ride_id,
                    ride.driver_name,
                    ride.driver_phone,
                    ride.pickup_location,
                    ride.scheduled_pickup_time.strftime("%Y-%m-%d %H:%M"),
                    ride.status.value,
                    ride.call_sid or "",
                    ride.call_outcome or "",
                    ride.last_called_at.strftime("%Y-%m-%d %H:%M:%S") if ride.last_called_at else "",
                ]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to add ride to Google Sheet: {e}")
            return False

    def reset_all_statuses(self) -> bool:
        try:
            ws = self._get_worksheet()
            records = ws.get_all_records()
            headers = ws.row_values(1)
            status_col = headers.index("status") + 1 if "status" in headers else (headers.index("Status") + 1 if "Status" in headers else None)
            if status_col:
                for idx in range(2, len(records) + 2):
                    ws.update_cell(idx, status_col, RideStatus.PENDING.value)
            return True
        except Exception as e:
            logger.error(f"Failed to reset Google Sheet: {e}")
            return False


class LocalExcelSheetAdapter(BaseSheetAdapter):
    """Adapter reading directly from downloaded Google Sheet XLSX files."""

    def __init__(self, excel_filepath: str, csv_fallback_path: str):
        self.excel_filepath = excel_filepath
        self.csv_adapter = CSVSheetAdapter(csv_fallback_path)
        self._lock = threading.RLock()
        self._sync_excel_to_csv()

    def _sync_excel_to_csv(self):
        import zipfile, xml.etree.ElementTree as ET
        if not os.path.exists(self.excel_filepath):
            return

        try:
            with zipfile.ZipFile(self.excel_filepath) as z:
                strings = []
                if 'xl/sharedStrings.xml' in z.namelist():
                    tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
                    for elem in tree.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                        strings.append(elem.text or '')
                
                sheet = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                rows = []
                for row in sheet.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
                    row_vals = []
                    for cell in row.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                        t = cell.attrib.get('t')
                        val_elem = cell.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                        val = val_elem.text if val_elem is not None else ''
                        if t == 's' and val != '':
                            val = strings[int(val)]
                        row_vals.append(val)
                    if row_vals:
                        rows.append(row_vals)

            if not rows:
                return

            out_rows = []
            headers = ['ride_id', 'driver_name', 'driver_phone', 'pickup_location', 'scheduled_pickup_time', 'status', 'call_sid', 'call_outcome', 'last_called_at', 'notes']

            for r in rows[1:]:
                if len(r) >= 5:
                    ride_id = r[0]
                    driver_name = r[1]
                    driver_phone = r[2]
                    pickup_location = r[3]
                    time_raw = r[4]
                    
                    # Convert Excel serial date if numeric
                    try:
                        f = float(time_raw)
                        base = datetime(1899, 12, 30)
                        dt = base + datetime.timedelta(days=f)
                        time_str = dt.strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        time_str = str(time_raw)

                    status = r[5] if len(r) > 5 else 'Pending'
                    call_sid = r[6] if len(r) > 6 else ''
                    call_outcome = r[7] if len(r) > 7 else ''
                    notes = r[-1] if len(r) > 8 else ''

                    out_rows.append({
                        'ride_id': ride_id,
                        'driver_name': driver_name,
                        'driver_phone': driver_phone,
                        'pickup_location': pickup_location,
                        'scheduled_pickup_time': time_str,
                        'status': status,
                        'call_sid': call_sid,
                        'call_outcome': call_outcome,
                        'last_called_at': '',
                        'notes': notes
                    })

            with open(self.csv_adapter.filepath, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(out_rows)
            logger.info(f"Synchronized {len(out_rows)} rides from {self.excel_filepath}")
        except Exception as e:
            logger.error(f"Error syncing {self.excel_filepath}: {e}")

    def fetch_all_rides(self) -> List[Ride]:
        with self._lock:
            return self.csv_adapter.fetch_all_rides()

    def update_ride_status(
        self,
        ride_id: str,
        status: RideStatus,
        call_sid: Optional[str] = None,
        call_outcome: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        with self._lock:
            return self.csv_adapter.update_ride_status(
                ride_id=ride_id,
                status=status,
                call_sid=call_sid,
                call_outcome=call_outcome,
                notes=notes,
            )

    def add_ride(self, ride: Ride) -> bool:
        with self._lock:
            return self.csv_adapter.add_ride(ride)

    def reset_all_statuses(self) -> bool:
        with self._lock:
            return self.csv_adapter.reset_all_statuses()


def get_sheet_adapter(config) -> BaseSheetAdapter:
    """Factory to instantiate configured sheet adapter."""
    from config import BASE_DIR
    excel_path = os.path.join(BASE_DIR, "google_sheet.xlsx")
    if os.path.exists(excel_path):
        logger.info(f"Detected Google Sheet excel file at {excel_path}. Loading LocalExcelSheetAdapter.")
        return LocalExcelSheetAdapter(excel_path, config.CSV_FILE_PATH)

    source_type = config.DATA_SOURCE.lower()
    if source_type == "google_sheet":
        if not config.GOOGLE_SHEET_ID or not os.path.exists(config.GOOGLE_SERVICE_ACCOUNT_FILE):
            logger.warning("Google Sheet ID or credentials missing. Falling back to CSV adapter.")
            return CSVSheetAdapter(config.CSV_FILE_PATH)
        return GoogleSheetAdapter(
            sheet_id=config.GOOGLE_SHEET_ID,
            service_account_file=config.GOOGLE_SERVICE_ACCOUNT_FILE,
            sheet_name=config.GOOGLE_SHEET_NAME,
        )
    elif source_type in ["csv", "xlsx", "excel"]:
        return CSVSheetAdapter(config.CSV_FILE_PATH)
    elif source_type == "mock":
        return MockSheetAdapter()
    else:
        raise ValueError(f"Unknown data source type: {config.DATA_SOURCE}")


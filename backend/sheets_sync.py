"""
Google Sheets auto-sync for the Mayor Endorsement CRM.

Exposes schedule_sync() — call it after any city mutation. Internally debounces
so that rapid-fire updates coalesce into one API call (default: 30 s window).

Requires env vars:
  GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON  — full service account JSON string
  GOOGLE_SHEETS_SHEET_ID              — spreadsheet ID from the URL
"""

import json
import os
import threading
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Status display ─────────────────────────────────────────────────────────────

STATUS_LABELS = {
    "no_contact_info":    "No contact info",
    "city_contact_only":  "City contact only",
    "info_requested":     "Info requested",
    "ready_for_outreach": "Ready for outreach",
    "outreach_sent":      "Outreach sent",
    "in_conversation":    "In conversation",
    "call_scheduled":     "Call scheduled",
    "endorsed":           "Endorsed ✓",
    "declined":           "Declined",
    "follow_up":          "Follow-up needed",
    "not_pursuing":       "Not pursuing",
}

STATUS_ORDER = [
    "no_contact_info", "city_contact_only", "info_requested",
    "ready_for_outreach", "outreach_sent", "in_conversation",
    "call_scheduled", "endorsed", "declined", "follow_up", "not_pursuing",
]

# ── Colors (0–1 RGB for the Sheets API) ───────────────────────────────────────

def _rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}

HEADER_BG = _rgb(0xD0, 0xE4, 0xF5)   # #D0E4F5

# Map from human-readable status label → background color
STATUS_BG = {
    "Endorsed ✓":      _rgb(0xD9, 0xEA, 0xD3),  # #D9EAD3 green
    "Declined":        _rgb(0xF4, 0xCC, 0xCC),  # #F4CCCC red
    "Outreach sent":   _rgb(0xCF, 0xE2, 0xF3),  # #CFE2F3 blue
    "In conversation": _rgb(0xCF, 0xE2, 0xF3),
    "Call scheduled":  _rgb(0xCF, 0xE2, 0xF3),
    "Follow-up needed":_rgb(0xFF, 0xF2, 0xCC),  # #FFF2CC yellow
    "No contact info": _rgb(0xEF, 0xEF, 0xEF),  # #EFEFEF gray
    "City contact only":_rgb(0xEF, 0xEF, 0xEF),
}

# Column indices for the main tracker sheet
MAIN_HEADERS = [
    "City", "County", "Population", "Mayor", "Mayor Email", "Mayor Phone",
    "City Email", "City Phone", "Status", "Last Contacted", "Next Step",
    "Wildfire Risk", "Notes",
]
STATUS_COL = 8   # 0-based index of "Status"

# ── Debounce ───────────────────────────────────────────────────────────────────

_timer: threading.Timer | None = None
_lock = threading.Lock()


def schedule_sync(delay: float = 30.0) -> None:
    """Schedule a sync in `delay` seconds. Resets the timer on each call."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(delay, _run_sync)
        _timer.daemon = True
        _timer.start()


def _run_sync() -> None:
    from database import SessionLocal
    db = SessionLocal()
    try:
        sync_to_sheets(db)
    except Exception as exc:
        print(f"[sheets_sync] error: {exc}")
    finally:
        db.close()


# ── Sheets client ──────────────────────────────────────────────────────────────

def _get_service():
    raw = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build("sheets", "v4", credentials=creds, cache_discovery=False)
    except Exception as exc:
        print(f"[sheets_sync] auth error: {exc}")
        return None


def _spreadsheet_id() -> str | None:
    return os.environ.get("GOOGLE_SHEETS_SHEET_ID") or None


# ── Main sync ──────────────────────────────────────────────────────────────────

def sync_to_sheets(db) -> None:
    service = _get_service()
    sid = _spreadsheet_id()
    if not service or not sid:
        return  # not configured — skip silently

    from models import City

    # ── Fetch data ─────────────────────────────────────────────────────────────

    cities = (
        db.query(City)
        .order_by(City.city_name.asc())
        .all()
    )

    # ── Build row data ─────────────────────────────────────────────────────────

    def fmt_date(dt):
        if not dt:
            return ""
        if not hasattr(dt, "strftime"):
            return str(dt)
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"

    main_rows = [MAIN_HEADERS]
    for c in cities:
        mayor = c.mayor or ""
        if c.mayor_needs_verification and mayor:
            mayor += " (unverified)"

        pop = f"{c.population:,}" if c.population else ""
        notes = c.notes or ""
        if len(notes) > 200:
            notes = notes[:197] + "…"

        main_rows.append([
            c.city_name or "",
            c.county or "",
            pop,
            mayor,
            c.mayor_work_email or c.mayor_personal_email or "",
            c.mayor_work_phone or c.mayor_personal_phone or "",
            c.city_email or "",
            c.city_phone or "",
            STATUS_LABELS.get(c.outreach_status, c.outreach_status or ""),
            fmt_date(c.last_contacted),
            c.next_action or "",
            (c.wildfire_risk_tier or "").capitalize() if c.wildfire_risk_tier else "",
            notes,
        ])

    # Summary stats
    total = len(cities)
    endorsed  = sum(1 for c in cities if c.outreach_status == "endorsed")
    declined  = sum(1 for c in cities if c.outreach_status == "declined")
    pending   = sum(1 for c in cities if c.outreach_status in ("outreach_sent", "in_conversation", "call_scheduled"))
    not_yet   = sum(1 for c in cities if c.outreach_status in ("no_contact_info", "city_contact_only", "info_requested", "ready_for_outreach"))
    contacted = total - not_yet
    has_email = sum(1 for c in cities if c.mayor_work_email or c.mayor_personal_email)

    summary_rows = [
        ["Metric", "Value"],
        ["Total cities", total],
        ["Contacted", contacted],
        ["Endorsed", endorsed],
        ["Declined", declined],
        ["Pending (sent / in conv / call)", pending],
        ["Not yet contacted", not_yet],
        ["Mayor email on file", f"{has_email} / {total}"],
        [],
        ["Last synced", datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")],
    ]

    # ── Ensure tabs exist, delete Recent Activity if present ───────────────────

    sheets = service.spreadsheets()
    meta = sheets.get(spreadsheetId=sid).execute()
    sheet_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    setup_reqs = []

    # Delete "Recent Activity" tab if it still exists from a previous sync
    if "Recent Activity" in sheet_ids:
        setup_reqs.append({"deleteSheet": {"sheetId": sheet_ids["Recent Activity"]}})

    for title in ["Mayor Outreach Tracker", "Summary Stats"]:
        if title not in sheet_ids:
            setup_reqs.append({"addSheet": {"properties": {"title": title}}})

    if setup_reqs:
        sheets.batchUpdate(spreadsheetId=sid, body={"requests": setup_reqs}).execute()
        meta = sheets.get(spreadsheetId=sid).execute()
        sheet_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    main_gid    = sheet_ids["Mayor Outreach Tracker"]
    summary_gid = sheet_ids["Summary Stats"]

    # ── Clear old data, then write ─────────────────────────────────────────────

    sheets.values().batchClear(
        spreadsheetId=sid,
        body={"ranges": ["Mayor Outreach Tracker", "Summary Stats"]}
    ).execute()

    sheets.values().batchUpdate(
        spreadsheetId=sid,
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "Mayor Outreach Tracker!A1", "values": main_rows},
                {"range": "Summary Stats!A1",          "values": summary_rows},
            ],
        }
    ).execute()

    # ── Formatting ─────────────────────────────────────────────────────────────

    fmt = []
    data_rows = len(main_rows)

    # Look up per-sheet metadata for cleanup
    sheet_meta = {s["properties"]["sheetId"]: s for s in meta["sheets"]}

    def header_fmt(gid, ncols):
        return {
            "repeatCell": {
                "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": ncols},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": HEADER_BG,
                    "textFormat": {"bold": True, "fontSize": 10},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
            }
        }

    # Freeze row 1 on main sheet
    fmt.append({
        "updateSheetProperties": {
            "properties": {"sheetId": main_gid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Headers
    fmt.append(header_fmt(main_gid, len(MAIN_HEADERS)))
    fmt.append(header_fmt(summary_gid, 2))

    # ── Clean up existing bandings and conditional formats on main sheet ────────

    for br in sheet_meta.get(main_gid, {}).get("bandedRanges", []):
        fmt.append({"deleteBanding": {"bandedRangeId": br["bandedRangeId"]}})

    existing_cf = sheet_meta.get(main_gid, {}).get("conditionalFormats", [])
    for i in range(len(existing_cf) - 1, -1, -1):
        fmt.append({"deleteConditionalFormatRule": {"sheetId": main_gid, "index": i}})

    # ── Alternating row banding (white / very light gray) ──────────────────────

    fmt.append({
        "addBanding": {
            "bandedRange": {
                "range": {
                    "sheetId": main_gid,
                    "startRowIndex": 1,
                    "endRowIndex": data_rows,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(MAIN_HEADERS),
                },
                "rowProperties": {
                    "firstBandColor":  {"red": 1.0,   "green": 1.0,   "blue": 1.0},
                    "secondBandColor": {"red": 0.957, "green": 0.957, "blue": 0.957},
                },
            }
        }
    })

    # ── Whole-row conditional formatting via CUSTOM_FORMULA ─────────────────────
    # Column I (index 8) = Status. Formula anchors the column ($I) but lets row float.

    full_row_range = [{
        "sheetId": main_gid,
        "startRowIndex": 1,
        "endRowIndex": data_rows,
        "startColumnIndex": 0,
        "endColumnIndex": len(MAIN_HEADERS),
    }]

    for label, bg in STATUS_BG.items():
        fmt.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": full_row_range,
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": f'=$I2="{label}"'}],
                        },
                        "format": {"backgroundColor": bg},
                    },
                },
                "index": 0,
            }
        })

    # ── Cell alignment ─────────────────────────────────────────────────────────

    # Center-align: Population(2), Status(8), Last Contacted(9), Wildfire(11)
    for col in [2, 8, 9, 11]:
        fmt.append({
            "repeatCell": {
                "range": {"sheetId": main_gid, "startRowIndex": 1, "endRowIndex": data_rows,
                          "startColumnIndex": col, "endColumnIndex": col + 1},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        })

    # Wrap text in Notes column (12)
    fmt.append({
        "repeatCell": {
            "range": {"sheetId": main_gid, "startRowIndex": 1, "endRowIndex": data_rows,
                      "startColumnIndex": 12, "endColumnIndex": 13},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
            "fields": "userEnteredFormat.wrapStrategy",
        }
    })

    # ── Column widths ──────────────────────────────────────────────────────────

    fmt.append({
        "autoResizeDimensions": {
            "dimensions": {"sheetId": main_gid, "dimension": "COLUMNS",
                           "startIndex": 0, "endIndex": len(MAIN_HEADERS)}
        }
    })
    # Pin minimums: City(0), Mayor(3), Next Step(10), Notes(12)
    for col_idx, px in {0: 160, 3: 160, 10: 200, 12: 280}.items():
        fmt.append({
            "updateDimensionProperties": {
                "range": {"sheetId": main_gid, "dimension": "COLUMNS",
                          "startIndex": col_idx, "endIndex": col_idx + 1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # Auto-resize summary tab
    fmt.append({
        "autoResizeDimensions": {
            "dimensions": {"sheetId": summary_gid, "dimension": "COLUMNS",
                           "startIndex": 0, "endIndex": 2}
        }
    })

    sheets.batchUpdate(spreadsheetId=sid, body={"requests": fmt}).execute()

    print(f"[sheets_sync] synced {len(cities)} cities → Google Sheets")

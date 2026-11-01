# Petrol Station Backend API

## 1. Overview

This API supports daily petrol station operations, including:

- Recording pump meter readings and tank readings.
- Recording POS, cash/bank, credit sales and expenses.
- Calculating fuel movement, expected revenue and profit.
- Retrieving daily reconciliation results.
- Retrieving discrepancy reports.

**Base URL (local development):** `http://127.0.0.1:8000/api/`

## 2. Authentication and authorisation

The API requires authentication.

Authentication currently uses Django REST Framework's `SessionAuthentication`. Users must be logged in and should send their session cookie with requests.

| Role | Permissions |
|---|---|
| Manager | Submit daily entries and read station settings |
| Owner | Read reports and station settings; create new effective-dated settings |
| Authenticated user | View daily results for their assigned station |

Users cannot submit readings for pumps or tanks belonging to another station.

A user without an assigned station cannot use the protected Manager or Owner endpoints.

## 3. Endpoints

### GET `/station/settings/products/`

**Purpose:** Retrieve all effective-dated product selling-price and landing-cost settings for the authenticated user's station.

**Access:** Authenticated Manager or Owner assigned to a station.

### POST `/station/settings/products/`

**Purpose:** Add a new effective-dated product settings version. Existing versions are not edited in place.

**Access:** Owner assigned to a station.

Example request:

```json
{
  "product_type": "PMS",
  "selling_price": "1.50",
  "landing_cost": "1.20",
  "effective_from": "2026-11-01"
}
```

### GET `/station/settings/reconciliation/`

**Purpose:** Retrieve all effective-dated reconciliation settings for the authenticated user's station.

**Access:** Authenticated Manager or Owner assigned to a station.

### POST `/station/settings/reconciliation/`

**Purpose:** Add a new effective-dated reconciliation settings version.

**Access:** Owner assigned to a station.

Example request:

```json
{
  "adjustment_divisor": "20",
  "adjustment_factor": "0.85",
  "physical_tolerance": "120.00",
  "financial_tolerance": "1000.00",
  "adjustment_tolerance": "0.05",
  "effective_from": "2026-11-01"
}
```

`physical_tolerance` (litres) and `financial_tolerance` (naira) are applied per product: how far pump litres may be from the adjusted tank litres, and how far recorded money may be from pump sales, before a day is flagged. `adjustment_tolerance` is stored separately; its validation semantics are not applied until the business rule is confirmed. The API does not allow editing or deleting an existing settings version.

### GET `/daily-entries/`

**Purpose:** List the authenticated manager's saved, resumable drafts for their station. Submitted entries are not included.

**Access:** Authenticated Manager assigned to a station.

### POST `/daily-entries/`

**Purpose:** Create a draft containing a station's daily readings and financial transactions. Drafts can later be retrieved and updated. After uploading evidence photos for every selected pump and tank reading, call `POST /daily-entries/{entry_id}/finalise/` to calculate and persist the reconciliation result.

**Access:** Authenticated Manager assigned to a station.

#### Request body

```json
{
  "entry_date": "2026-10-09",
  "pump_readings": [
    {
      "pump": 1,
      "closing_reading": "1100.00"
    }
  ],
  "tank_readings": [
    {
      "tank": 1,
      "closing_reading": "4900.00",
      "delivered_quantity": "0.00"
    }
  ],
  "financial_transactions": [
    {
      "product_type": "PMS",
      "transaction_type": "POS",
      "amount": "150.00",
      "description": "POS sales"
    },
    {
      "product_type": "PMS",
      "transaction_type": "cash_bank",
      "amount": "6.00",
      "description": "Cash sales"
    },
    {
      "product_type": "PMS",
      "transaction_type": "expense",
      "amount": "5.00",
      "description": "Station expenses"
    }
  ]
}
```

The IDs shown for the pump and tank are examples; use IDs returned by your backend for the authenticated user's station.

Tank `closing_reading` is the litres in the tank (from the dip chart). `delivered_quantity` is optional: litres delivered into that tank on the entry date. Every financial transaction, expenses included, must name its `product_type` (`PMS` or `AGO`).

`GET /station/equipment/` returns each pump and tank with `last_reading` (`entry_date`, `closing_reading`) from the latest official submission, or `null`, so clients can show the previous figure and the litres moved while the manager types.

#### Draft lifecycle endpoints

- `GET /daily-entries/{entry_id}/`: retrieve a manager-owned draft, including readings, transaction rows, notes and evidence counts.
- `PATCH /daily-entries/{entry_id}/`: update a draft. Existing reading records are updated in place for equipment that remains selected, preserving its uploaded evidence. Removing equipment removes its reading and evidence.
- `DELETE /daily-entries/{entry_id}/`: permanently discard a draft and associated records. The frontend must require explicit confirmation before calling this endpoint.

Only the manager who created a draft can retrieve, update or discard it. Entries from another manager or station are not exposed. Submitted entries cannot be edited or deleted through the draft endpoint.

#### Transaction types

- `POS`
- `cash_bank`
- `CREDIT`
- `expense`
- `transfer`
- `shell_deposit`

Supported product types are `PMS` and `AGO`.

#### Successful response

HTTP `201 Created`

The response contains the new draft ID, status, date, notes and reading IDs. Reconciliation results are created only after finalisation.

### POST `/daily-entries/{entry_id}/finalise/`

**Purpose:** Validate evidence, calculate reconciliation and persist the official result atomically.

**Access:** The manager who created the draft, assigned to the same station.

On success, the response includes the entry ID, `submitted` status and a confirmation message. If any required evidence is missing or calculation fails, the entry remains a draft and no partial result is saved.

A saved daily result contains fields such as:

- `station`
- `entry_date`
- `pump_volume`
- `tank_movement`
- `physical_difference`
- `physical_within_tolerance` (nullable for results calculated before this field was introduced)
- `expected_revenue`
- `actual_sales`
- `financial_difference`
- `fuel_cost`
- `gross_profit`
- `expenses`
- `net_profit`
- `calculated_at`

The `station` and `manager` are derived from the authenticated user, not from the request body.

#### Validation and errors

- `400 Bad Request`: Invalid fields, negative amounts, duplicate readings, readings for another station, missing evidence during finalisation, invalid settings, or a duplicate effective date.
- `403 Forbidden`: The user lacks the required Manager role or station assignment.
- `401 Unauthorized`: The request is not authenticated.
- `500 Internal Server Error`: An unexpected calculation failure prevents the submission from completing.

Failed submissions should not leave partial daily-entry records behind.

### GET `/reports/daily-results/`

**Purpose:** Retrieve saved daily reconciliation results.

**Access:** Authenticated user.

#### Successful response

HTTP `200 OK`

Returns a JSON array of daily results belonging to the authenticated user's station.

Example:

```json
[
  {
    "id": 1,
    "station": "Test Station",
    "entry_date": "2026-10-09",
    "pump_volume": "100.00",
    "tank_movement": "100.00",
    "physical_difference": "0.00",
    "expected_revenue": "156.38",
    "actual_sales": "156.00",
    "financial_difference": "0.38",
    "fuel_cost": "100.00",
    "gross_profit": "56.38",
    "expenses": "0.00",
    "net_profit": "56.38",
    "calculated_at": "2026-10-09T10:00:00Z"
  }
]
```

The figures are illustrative, not live data. Decimal values are returned as strings to preserve precision.

### GET `/reports/discrepancies/`

**Purpose:** Retrieve daily results with non-zero physical or financial differences.

**Access:** Authenticated user assigned to a station; results are limited to that user's station.

#### Successful response

HTTP `200 OK`

Returns a JSON array containing discrepancy records for the Owner's station only.

A physical discrepancy exists when the pump volume differs from the tank movement. A financial discrepancy exists when expected revenue differs from recorded sales.

### Admin endpoints

**Access:** staff accounts (`is_staff`, e.g. `omesh-admin`) assigned to a station. `GET /auth/me/` returns `is_admin`.

- `GET /admin/summary/`: counts of the station's records (`submitted_days`, `entries`, `drafts`, `transactions`, `photos`, `deliveries`) and the `clear_all_phrase`.
- `DELETE /admin/days/{YYYY-MM-DD}/`: deletes every entry for that date (the official one, superseded versions and drafts, with readings, money lines, results and photos) plus that day's fuel deliveries. `404` if there is nothing for the date.
- `POST /admin/clear/` with `{"confirm": "DELETE ALL"}`: deletes all of the station's daily records and deliveries. Users, pumps, tanks, prices and checking rules are kept. Any other `confirm` value returns `400`.

## 4. Business rules

### Pump volume

Pump volume is calculated from the current closing meter reading minus the previous closing meter reading for that pump. Only the latest successfully submitted entry for an earlier station date can provide the previous reading; drafts and superseded submissions are ignored. If there is no earlier official reading, the first closing reading establishes the baseline and calculated movement is zero.

### Tank movement

Tank movement = previous closing litres + litres delivered (the reading's `delivered_quantity` plus any `FuelDelivery` records for the date) − current closing litres.

### Per-product reconciliation

These rules follow the station's spreadsheet and are applied to PMS and AGO separately; a day's totals are the sum of the products. Each result carries a `product_results` list with the per-product figures.

- **Physical check:** expected litres = tank movement + (tank movement / adjustment divisor) × adjustment factor. Pump volume is compared with expected litres; within `physical_tolerance` litres is accepted. The divisor (20) and factor (0.85) come from the spreadsheet. The adjustment tolerance (±0.05) is stored but not yet used.
- **Sales value** (`expected_revenue`) = pump volume × selling price.
- **Money recorded** (`actual_sales`) = every transaction for the product: POS, cash/bank, credit, transfer, shell deposit and expenses paid from the takings.
- **Financial difference** = sales value − money recorded (positive means short); within `financial_tolerance` naira is accepted.

### Profit

- Fuel cost = tank movement × applicable landing cost.
- Gross profit = sales value − fuel cost.
- Net profit = gross profit − expenses.

### Historical settings

Product pricing, landing costs and reconciliation settings are selected according to their effective dates.

## 5. Important integration notes

- Send dates in `YYYY-MM-DD` format.
- Send monetary amounts and meter readings as decimal strings.
- Do not send the station ID or manager ID when submitting a daily entry.
- Use the actual pump and tank IDs supplied by the backend.
- The latest successfully submitted entry for a station/date is the official entry for reporting and for future reading baselines. A newer draft does not replace it; a later successful submission for the same date becomes the official version while earlier records remain stored.
- The frontend should display validation errors returned by the API rather than assuming every request succeeds.
- The current API uses session-based authentication; cross-origin frontend integration may require appropriate CSRF and CORS configuration.

## 6. Current scope

This API currently supports daily submissions and saved reconciliation reports. It does not yet document endpoints for creating stations, pumps, tanks, deliveries or configuration settings. Those resources are managed separately at this stage.

## Station controls, saved entries and export

- `GET /api/station/columns/`: station financial column definitions, including hidden columns.
- `POST /api/station/columns/` (owner): `{label, transaction_type}` creates a column. Existing accounting types remain supported.
- `PATCH /api/station/columns/{id}/` (owner): `{active: false|true}` hides/restores; no delete route.
- Financial transaction inputs optionally include `column` (ID). Its station and visibility are validated; the server derives the accounting type. Existing entries may retain hidden columns.
- `GET /api/station/settings/equipment/` (owner): all equipment, including hidden items.
- `POST /api/station/settings/equipment/` (owner): `{kind: "pump"|"tank", label, product_type}`.
- `PATCH /api/station/settings/equipment/{kind}/{id}/` (owner): `{active: false|true}`; no delete route.
- `GET /api/station/equipment/?before=YYYY-MM-DD`: active equipment with the previous official closing readings before that business date.
- `GET /api/saved-entries/?date=YYYY-MM-DD` or `/api/saved-entries/{id}/`: submitted details; managers are restricted to their own station and own entries.
- `PATCH /api/saved-entries/{id}/` (owner): partial daily-entry payload plus the `version` returned by GET. Existing equipment and date are retained; corrections preserve evidence and original manager attribution. The previous snapshot and editor are recorded. Later official days are recalculated in the same database transaction. A stale version returns 409.
- Daily result responses now include `daily_entry` to link a report to its entry.
- `GET /api/admin/export/` (station admin only): downloadable ZIP of station operational data, drafts and superseded submissions, equipment, columns, settings, audit snapshots, CSV tables and photo files. It excludes passwords and sessions. `manifest.json` lists counts and any missing photos; `data.json` uses Django's fixture representation. User IDs/names are in `users.json`. Export is not an automatic import/restore endpoint.

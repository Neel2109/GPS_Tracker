# TrackGuard — Live Device GPS Tracking & Remote Control System

> Secure real-time laptop tracking and remote-control system with live location, device monitoring, location history, and authenticated lock, sleep, restart, and shutdown controls from iPhone, Android, or web.

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Technology](#tech-stack)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Google Maps setup](#google-maps-setup)
- [Pair and run the Windows agent](#pair-and-run-the-windows-agent)
- [Project layout](#project-layout)
- [API reference](#api-endpoints)
- [Security and privacy](#security-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Deployment notes](#deployment-notes)
- [License](#license)

## Overview

TrackGuard is a self-hosted dashboard and device agent for monitoring computers
you own or are authorized to manage. A Windows agent connects outbound to the
TrackGuard server, sends device telemetry and location updates, and receives
authenticated remote power/session commands. The dashboard can be opened from a
desktop or mobile browser.

The repository currently implements a Windows laptop agent. The dashboard can
represent other device types, but phones and watches need their own native
agents before they can provide device-native telemetry or location.

## Architecture

```
                         ┌─────────────────────────┐
                         │   iPhone / Android / PC  │
                         │    React + TypeScript    │
                         │    Dashboard (PWA)       │
                         └────────────┬────────────┘
                                      │ HTTPS / WSS
                                      ▼
                         ┌─────────────────────────┐
                         │     FastAPI Backend      │
                         │  Auth · Devices · WS     │
                         │  Location · Commands     │
                         └────────────┬────────────┘
                                      │ WSS
                                      ▼
                         ┌─────────────────────────┐
                         │    Windows Laptop        │
                         │    Python Agent          │
                         │  Location · Battery      │
                         │  Network · Commands      │
                         └─────────────────────────┘
```

## Device Identification

| Information  | Purpose                                              |
|-------------|------------------------------------------------------|
| Device UUID | Primary device identity                               |
| Device Token| Authentication                                        |
| MAC Address | Local network/interface information                   |
| Local IP    | Local network information                             |
| Public IP   | Network identification + approximate IP geolocation   |
| GPS/OS Loc  | Geographic location tracking                          |
| Battery     | Device monitoring                                     |
| Heartbeat   | Online/offline status                                 |

## Tech Stack

### Frontend
- React 19, Vite 8, TypeScript
- Tailwind CSS v4
- Google Maps JavaScript API (satellite, roadmap, and terrain); Leaflet for location history
- React Router, WebSocket
- PWA-ready

### Backend
- Python, FastAPI, Uvicorn
- SQLAlchemy async persistence with SQLite as the local default; other database
  engines require a matching async driver and deployment configuration
- JWT Authentication, Argon2/Bcrypt
- WebSocket real-time communication

### Windows Agent
- Python background service
- Windows Location Services (reports satellite, Wi-Fi, cellular, or Windows source) with coarse IP-geolocation fallback
- psutil for hardware telemetry
- WebSocket client with exponential backoff

## Requirements

- Windows 10/11 for the packaged agent and its Windows-specific location and
  power commands.
- Python 3.12 for the backend and for building/running the agent from source.
- Node.js and npm for the React dashboard.
- A Google Maps API key for the Google live map. Without one, the dashboard
  displays setup guidance; other location views use Leaflet.
- Windows Location Services enabled on the tracked laptop if Windows-provided
  location is desired. A laptop may have no GPS hardware; Windows may determine
  its position from available Wi-Fi, cellular, or other location sources.

### Location source and accuracy

TrackGuard records the source returned by the device's location provider and the
provider-reported accuracy when available. On Windows, the agent uses Windows
Location Services, which may use built-in GNSS hardware, Wi-Fi, cellular, or
another Windows positioning source depending on the device and system settings.
It falls back to IP geolocation only when Windows cannot provide a fix; IP-based
coordinates are approximate, and no numeric accuracy is claimed for them.

MAC addresses identify network interfaces and IP addresses identify network
connections; neither provides GPS coordinates. The repository currently
includes a Windows agent only. Android, iPhone, and smartwatch GNSS require
separate native agents using Android Fused Location Provider, Apple Core
Location, or the watch's location API before those devices can report their
native location to TrackGuard.

## Quick Start

Use **Python 3.12** for the backend and agent. The pinned Pydantic version in
this project may try to build `pydantic-core` from source on newer Python
versions, which requires the Rust and Visual C++ build toolchains.

Create a Python 3.12 virtual environment once from the project root:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install --upgrade pip
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
.\.venv312\Scripts\python.exe -m pip install -r installer\requirements-build.txt
```

Copy `.env.example` to `.env`, then set a private 6–12 digit `LOCAL_PIN` and a
unique `JWT_SECRET` before starting the app. Do not commit or share these
values. The web dashboard and Android app use `LOCAL_PIN` as their only
interactive sign-in method for the local owner. The owner account is selected
with `LOCAL_USER_EMAIL`; on an empty database, TrackGuard creates that account.
To bootstrap the first platform super-administrator, also set `LOCAL_USER_PHONE`
and `SUPER_ADMIN_PHONE` to the same phone number in E.164 format (for example,
`+14155550123`). The owner signs in directly with the configured local PIN;
phone, SMS, invitation, and authenticator choices are not presented on the
client sign-in screens. Keep the PIN private and restrict the server to a
trusted network because PIN-only sign-in is a single authentication factor.

New users are provisioned by an administrator; self-service registration is
not enabled because authenticator codes do not prove control of a phone number.
Account creation returns a single-use invitation link/token that expires after
48 hours. Share it only through a private channel. The recipient verifies
ownership of the invited phone number by SMS, claims the invitation, and
creates their own authenticator; the setup secret is not sent to the
administrator. Invitations can be reissued, which revokes any unused invite
for that account. New and existing phone-based accounts must verify their
number before activation or sign-in. SMS verification and recovery require the
server's Twilio settings. Verification codes are short-lived, single-use,
hashed in the database, and rate-limited. The authenticator secret is encrypted
in the database using `TOTP_ENCRYPTION_KEY` or, if unset, a key derived from
`JWT_SECRET`; keep that setting stable and back up authenticator access before
reinstalling or moving the server. Codes are single-use per time step, and
failed PIN and code attempts are rate-limited.

After an administrator signs in, the **Admin console** allows account
provisioning, role/status management, authenticator resets, active-session
review/revocation, incident triage, and paged/searchable account, device, and
audit tables. Sensitive account and authenticator actions require the
administrator to have signed in within the last ten minutes. Only a
super-administrator can grant administrator roles or reset another user's
authenticator. The platform device inventory intentionally does not expose
coordinates or location history.
An administrator who needs another account's location must submit a request
with a reason and a 15-minute, 1-hour, or 4-hour duration. The owner approves,
denies, or revokes it from **Location access**. Approved access is read-only,
expires automatically, and every location/history read is audited. Active
grants stream approved live locations to the admin map. Device commands require a separate,
owner-approved **Device control** grant for one selected device; it expires
after 15 minutes, and the administrator must type that device's exact name for
each command. Supported Windows agents allow lock, sleep, restart, shutdown,
and Lost Mode; Android allows Lost Mode only. Arbitrary shell commands, device
transfer, and account-owner changes are not available. Command requests and
results are audited. Existing broad device-control requests are revoked during
upgrade because they do not identify an approved device. The application
automatically creates its tables at startup and adds missing
phone-verification, alert-lifecycle, role, status, phone, and last-login columns
to existing SQLite databases. Existing phone accounts must verify ownership
before their next sign-in; existing accounts become `USER`;
configure the local owner's phone and super-admin phone explicitly to bootstrap
the first administrator. Keep database backups before upgrades.

Local development defaults to `trackguard.db` through SQLite and creates its
schema on startup. For a persistent PostgreSQL deployment, install Docker
Desktop, copy `.env.example` to `.env`, replace every placeholder (especially
`POSTGRES_PASSWORD`, `JWT_SECRET`, and `LOCAL_PIN`), then run:

```powershell
docker compose up --build -d
```

The Docker stack runs the API and built web dashboard on port 8000 and stores
PostgreSQL data in the named `trackguard-postgres` volume. Check
`http://localhost:8000/health` after startup. `docker compose down` preserves
the database volume; do not use `docker compose down -v` unless you intend to
delete the database. SMS verification requires the Twilio settings described
below; without them, activation/sign-in for unverified phone accounts is
blocked rather than treating an unverified number as owned.

Run the backend and frontend together with one command from the project root:

```bash
npm install
npm run dev
```

This starts the backend at `http://localhost:8000` and the dashboard at
`http://localhost:5173`. Keep the terminal open; press Ctrl+C to stop both.
`npm run dev:web` starts only Vite; API requests then require the backend to be
started separately.

### Windows desktop launcher

Build the no-console desktop launcher with:

```powershell
.\.venv312\Scripts\python.exe build_exe.py
```

This creates `dist\tracker.exe`. Double-clicking it starts the server and
agent without opening command windows, then opens the dashboard. TrackGuard
does not register itself to launch at Windows sign-in; open the dashboard by
running the EXE. While it is active, keep TrackGuard visible in the system
tray. Quit from the tray (or confirm Quit in the fallback window) to stop the
server and agent.

The backend API documentation is available at `http://localhost:8000/docs`;
`http://localhost:8000/health` is the health-check endpoint. To build only the
frontend, run `npm run build`. To serve the built frontend and API together,
run `.\.venv312\Scripts\python.exe run.py` after building; use
`.\.venv312\Scripts\python.exe run.py --build` to request a frontend build at
startup. The unified server listens on port 8000 by default. Set a different
port or bind address with `--port` and `--host`.

## Configuration

Create a private `.env` file in the project root. It is deliberately ignored by
Git. `LOCAL_PIN` is the exact server-side PIN used to sign in to the local owner
account; it is not the phone's screen-lock PIN. If PIN verification fails,
check the value privately against the API server's `.env` and restart the API
process after changing it. Do not paste the PIN into chat, logs, or support
requests. The most useful settings are:

| Variable | Purpose |
| --- | --- |
| `LOCAL_PIN` | Required 6–12 digit PIN for local-owner sign-in. |
| `LOCAL_USER_EMAIL` | Selects the local TrackGuard account when the database contains multiple accounts. |
| `LOCAL_USER_NAME` | Display name used when the owner account is created on an empty database. |
| `LOCAL_USER_PHONE` | E.164 phone number assigned to the configured local owner during PIN-based setup. |
| `SUPER_ADMIN_PHONE` | E.164 phone number that bootstraps the local owner as the initial `SUPER_ADMIN`; set it to the same value as `LOCAL_USER_PHONE`. |
| `SECRET_KEY` or `JWT_SECRET` | Secret used to sign authentication tokens. Set a unique, strong value before use. |
| `TOTP_ENCRYPTION_KEY` | Optional independent secret used to encrypt authenticator keys in the database. If omitted, the key is derived from `JWT_SECRET`; keep whichever source you use stable. |
| `TWILIO_ACCOUNT_SID` | Twilio account SID required for phone verification and recovery codes. |
| `TWILIO_AUTH_TOKEN` | Private Twilio API token; required for phone verification and recovery; keep it only in the server environment. |
| `TWILIO_FROM_NUMBER` | Twilio-enabled sender number in E.164 format, required for verification and recovery SMS. |
| `PHONE_RECOVERY_HMAC_KEY` | Private random key of at least 32 characters used to hash phone verification/recovery codes and phone/IP identifiers. |
| `DATABASE_URL` | Async SQLAlchemy URL. Defaults to `sqlite+aiosqlite:///./trackguard.db`; Docker Compose points the app at PostgreSQL using asyncpg. |
| `CORS_ORIGINS` | Comma-separated browser origins allowed by the API. The development defaults allow localhost. |
| `VITE_GOOGLE_MAPS_API_KEY` | Restricted browser key used by the Google Maps frontend. |

Never commit `.env`, credentials, enrollment executables, or device tokens.
Do not use example/default secrets on an internet-reachable server. Treat
location history and network identifiers as sensitive data, and restrict access
to both the server and its database.

### Google Maps setup

The dashboard uses Google Maps and opens in satellite view. In Google Cloud,
enable the Maps JavaScript API, configure billing, and create a browser key
restricted to your development and production referrers. Add the key to the
root `.env` file:

```env
VITE_GOOGLE_MAPS_API_KEY=your-restricted-browser-key
```

Restart Vite after changing `.env`. Without a key, the dashboard displays setup
guidance in the map panel instead of loading third-party map tiles.

### Sign in and manage platform accounts

The web dashboard and Android app expose only PIN sign-in for the local owner.
The PIN is read from `LOCAL_PIN` on the API server. Phone-based invitation,
activation, SMS verification, and authenticator recovery controls are not
available on these sign-in screens. The backend retains the corresponding
account-management endpoints for compatibility; configuring Twilio is still
required for any server-side phone verification or recovery operations.

Users can open **Privacy & data** to export their account data as JSON or
permanently delete location history from their own devices. History is retained
until the owner deletes it; deleting it also removes the points used for trips
and route playback, but does not delete the account or devices. Trip reports
split segments at reporting gaps over 30 minutes and estimate stops from
reported stationary samples lasting at least five minutes.

Use the **Admin console** from an `ADMIN` or `SUPER_ADMIN` account to create and
manage accounts. The first `SUPER_ADMIN` is established by the matching
`LOCAL_USER_PHONE` and `SUPER_ADMIN_PHONE` server settings, never by a client
request. Administrator account and device-inventory views are audited. To view
another account's device location, use the console's reasoned access request;
the owner must approve it and can revoke it at any time. This grant expires
after the selected duration and applies only to location reads, not device
control.

Successful sign-ins create server-tracked sessions. Signing out or revoking a
session invalidates its access and refresh tokens. Existing stateless tokens
issued before session tracking was enabled are no longer accepted; sign in
again after upgrading. The admin incident center exposes incident details
without precise coordinates and records acknowledge/resolve changes in the
audit log.

### Pair and run the Windows agent

The computer running TrackGuard is the **server**; the laptop being monitored
is the **device**. The agent on the device makes an outbound connection to the
server, so you do not enter the device's IP to pair it. After it connects,
TrackGuard displays and lets you search by the device's reported local/public
IP. The device ID remains an internal authentication key.

In the dashboard, choose **Add a device**, enter a display name and type, and
set the TrackGuard server address. Use `http://localhost:8000` only for a device on
the same computer; for another computer on the same network use the server
computer's LAN IP (for example, `http://192.168.1.10:8000`). For a device
outside that network, the server needs a publicly reachable HTTPS address.

Choose **Create installer** and download the generated Windows `.exe`. Transfer
it to the tracked Windows device and double-click it. In the graphical setup
window, click **Install and connect**. The executable includes the Python
runtime and agent dependencies; it enrolls the device, starts the agent in the
background, and adds it to the current Windows user's startup programs so it
starts when you sign in. The tracked device does
not need Python installed, and no terminal command or manual pairing-code
entry is required. Keep the dashboard dialog open until the device is detected;
its local/public IP appears after the first network update. Each generated EXE
contains a one-use enrollment credential, expires after 24 hours, and should
be transferred privately rather than shared.

Ensure Windows Firewall allows inbound TCP connections to port 8000 on the
server and that the device can reach the configured server address. The
Windows EXE builder is installed on the TrackGuard server by the
`installer/requirements-build.txt` setup step. The server does not need the
tracked device's IP to enroll it: the agent connects outward to TrackGuard,
and the dashboard learns the device's IP from the agent's network status.
Pairing by an IP address alone cannot install or authenticate an agent on an
unconfigured device; install the generated EXE on that device once. Afterward,
use its reported IP to find it in the dashboard.

## Project layout

```text
app/                 FastAPI application, persistence, authentication, and API routers
agent/               Windows telemetry and remote-command agent
installer/           Windows graphical installer and installer build requirements
src/                 React/TypeScript dashboard
public/              Frontend static assets and PWA manifest
scripts/dev.mjs      Starts the backend and Vite development server together
run.py               Starts FastAPI and optionally builds the frontend
Dockerfile           Builds the React dashboard and API image
docker-compose.yml   PostgreSQL-backed application deployment
requirements.txt     Python backend dependencies
package.json         Frontend dependencies and npm scripts
```

## Features

- **Live Location** — Real-time device tracking on interactive dark map
- **Location History** — View movement routes with date filtering
- **Trip Segments** — Derive route segments from recorded points, split after 30-minute reporting gaps, and replay the selected route
- **Device Proximity** — Compare the signed-in owner's device pairs using last-reported positions, reported GPS accuracy, a 10-minute freshness limit, and a 5-minute maximum fix-time skew; uncertain or stale fixes are labeled instead of presented as current
- **Possible Device Separation** — Flag a cautious possible-left-behind pattern only when fresh, accuracy-adjusted fixes show meaningful separation and one device reported movement while the other reported stationary
- **Geofences** — Create, enable/disable, and delete circular saved places; show enter/exit alerts after a device reports a crossing
- **Incident Center and SOS** — Persist offline and low-battery incidents alongside SOS/geofence alerts; acknowledge or resolve them, retain status-transition history, and receive live web updates
- **Battery Monitor** — Live battery level with charging status
- **Network Info** — MAC, local IP, public IP, connection type
- **Remote Lock** — Lock Windows session instantly
- **Remote Sleep** — Put device to sleep
- **Remote Restart** — Restart device
- **Remote Shutdown** — Shut down device
- **Lost Mode** — Increased tracking frequency (10s intervals)
- **Device Pairing** — Windows graphical installer; no manual pairing code or terminal
- **Multi-Device** — Manage multiple registered devices; this repository currently includes a Windows agent
- **PWA-ready dashboard** — Add the dashboard to a mobile home screen where supported

## API Endpoints

The API is versioned under `/api` and exposes interactive OpenAPI
documentation at `/docs` while the server is running.

```
POST /api/auth/unlock
POST /api/auth/totp/setup
POST /api/auth/totp/confirm
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me

GET  /api/devices
POST /api/devices/pair/installer
GET  /api/devices/{id}
DELETE /api/devices/{id}

GET  /api/devices/{id}/location
GET  /api/devices/{id}/locations
GET  /api/devices/{id}/trips
GET  /api/devices/{id}/trips/{trip_id}/locations
GET  /api/devices/proximity?threshold_meters=250

GET    /api/geofences
POST   /api/geofences
PATCH  /api/geofences/{id}
DELETE /api/geofences/{id}

GET  /api/alerts
POST /api/alerts/{id}/read
POST /api/alerts/read-all
POST /api/alerts/sos

POST /api/devices/{id}/commands/lock
POST /api/devices/{id}/commands/sleep
POST /api/devices/{id}/commands/restart
POST /api/devices/{id}/commands/shutdown

WS   /ws/device/{device_id}
WS   /ws/dashboard/{user_id}
```

The WebSocket connection is used for device registration/telemetry and
dashboard updates. See the interactive API documentation for request schemas,
authentication requirements, and response shapes.

Trip segments are computed from stored location points and split when the gap
between reports exceeds 30 minutes; distance is the sum of straight-line
distances between reported points, not a map-matched road distance. Geofence
crossings are evaluated when an authorized paired device uploads a location.
The first report initializes inside/outside state without generating an entry
alert. SOS creates an in-app TrackGuard alert only; it does not contact
emergency services, notify external contacts, or guarantee delivery while the
dashboard is disconnected.

## Security and privacy

- Use TrackGuard only to manage devices you own or have explicit authorization
  to monitor. Remote lock, sleep, restart, and shutdown commands affect the
  tracked computer.
- Keep the server behind HTTPS/WSS when accessed outside a trusted local
  network. Do not expose the development server directly to the public internet.
- Configure a strong `SECRET_KEY`/`JWT_SECRET`, a private `LOCAL_PIN`, and
  narrow `CORS_ORIGINS` to the actual dashboard origins.
- Treat each generated installer as a one-use enrollment credential. Transfer
  it privately and delete it once installation is complete.
- The Windows agent stores its registration configuration under the current
  user's `%APPDATA%\TrackGuard` directory. Protect access to that account and
  device.
- Location is provider-dependent. Windows Location Services may return a
  coarse or unavailable position; IP geolocation is approximate and is not
  GPS. MAC addresses and IP addresses are network identifiers, not GPS
  coordinates.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| `npm run dev` cannot find Python | Create `.venv312` as shown above and install `requirements.txt`. The development script searches for `.venv312` and `.venv`. |
| Dashboard cannot reach the API | Confirm the backend is running on port 8000, the Vite proxy is active, and the server firewall allows connections from the tracked device where needed. |
| Device does not appear after installer setup | Keep the pairing dialog open, verify the server URL is reachable from that laptop, and check its `TrackGuard\agent.log` under `%LOCALAPPDATA%`. |
| Agent log shows WebSocket HTTP 403 | The saved device pairing is not present in the server database or the token is no longer accepted. Add/pair this PC again from the dashboard; the agent now stops retrying and records this recovery hint in `logs\agent.log`. |
| Location is missing or approximate | Enable Windows Location Services and grant the relevant permissions. IP fallback is approximate and may not identify the laptop's physical location. |
| Google map does not load | Confirm the Maps JavaScript API and billing are enabled, the browser key is referrer-restricted correctly, and Vite was restarted after changing `.env`. |
| PIN unlock is unavailable | Set `LOCAL_PIN` to 6–12 digits in the server `.env` and restart the backend. The endpoint temporarily rate-limits repeated incorrect attempts. |

## Deployment notes

The recommended development workflow is `npm run dev`; `docker-compose.yml` is
present but refers to `backend/` and `frontend/` build contexts that are not
provided in this repository. It is not a ready-to-run deployment configuration.
Before deploying, configure a production-grade database and secrets, serve
traffic through HTTPS/WSS, restrict network access, and establish a backup and
retention policy for location data.

## License

MIT

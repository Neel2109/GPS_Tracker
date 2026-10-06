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

Set a private 6–12 digit `LOCAL_PIN` in the root `.env` file before starting
the app. Do not commit or share this PIN. If the database contains exactly one
account, the PIN unlocks it; otherwise set `LOCAL_USER_EMAIL` to the account
that owns the devices. On a new empty database, TrackGuard creates a local
owner account automatically. The unlock endpoint limits failed attempts.

Run the backend and frontend together with one command from the project root:

```bash
npm install
npm run dev
```

This starts the backend at `http://localhost:8000` and the dashboard at
`http://localhost:5173`. Keep the terminal open; press Ctrl+C to stop both.
`npm run dev:web` starts only Vite; API requests then require the backend to be
started separately.

The backend API documentation is available at `http://localhost:8000/docs`;
`http://localhost:8000/health` is the health-check endpoint. To build only the
frontend, run `npm run build`. To serve the built frontend and API together,
run `.\.venv312\Scripts\python.exe run.py` after building; use
`.\.venv312\Scripts\python.exe run.py --build` to request a frontend build at
startup. The unified server listens on port 8000 by default. Set a different
port or bind address with `--port` and `--host`.

## Configuration

Create a private `.env` file in the project root. It is deliberately ignored by
Git. The most useful settings are:

| Variable | Purpose |
| --- | --- |
| `LOCAL_PIN` | Required 6–12 digit local dashboard unlock PIN. |
| `LOCAL_USER_EMAIL` | Selects the local TrackGuard account when the database contains multiple accounts. |
| `LOCAL_USER_NAME` | Display name used when the owner account is created on an empty database. |
| `SECRET_KEY` or `JWT_SECRET` | Secret used to sign authentication tokens. Set a unique, strong value before use. |
| `DATABASE_URL` | SQLAlchemy database URL. The application defaults to a local SQLite database named `trackguard.db`. |
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
requirements.txt     Python backend dependencies
package.json         Frontend dependencies and npm scripts
```

## Features

- **Live Location** — Real-time device tracking on interactive dark map
- **Location History** — View movement routes with date filtering
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
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me

GET  /api/devices
POST /api/devices/pair/installer
GET  /api/devices/{id}
DELETE /api/devices/{id}

GET  /api/devices/{id}/location
GET  /api/devices/{id}/locations

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

Neel Patel


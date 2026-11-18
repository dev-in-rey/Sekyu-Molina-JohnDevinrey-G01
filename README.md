# Sekyu: Smart Gate Access and Community Security System — CSIT327

- **Student Name:** John Devinrey A. Molina
- **Section:** G1
- **Course:** CSIT327 (Information Management 2)

---

## Overview

**Sekyu** is a Full-Stack Django web application designed to digitize subdivision guardhouse entry workflows and community security management in accordance with the Software Design Document and the Philippine Data Privacy Act of 2012 (Republic Act No. 10173).

It is powered by **Django Templates + Bootstrap 5 (via CDN)** on the frontend and **PostgreSQL** on the backend.

### Implemented Core Features (Project Development 2 — Vertical Slice)
1. **Household Profile Registration & HOA Standing (`households` app — `/households/`)**
   - **Resident CRUD (`/households/`, `/households/create/`, `/households/<pk>/edit/`, `/households/<pk>/delete/`):** Logged-in residents register and manage their subdivision property units (`block_number`, `lot_number`, `street_name`) linked via `ForeignKey` (`PROTECT`) to `CustomUser` (BR-05).
   - **Database & Business Rule Constraints:** Enforces positive integer block and lot numbers (`block_number > 0 AND lot_number > 0`, BR-06), unique `(block_number, lot_number, street_name)` across the subdivision (BR-04), and prevents deletion if visitor passes or gate logs reference the unit (`ProtectedError`).
   - **HOA Standing Management (`/households/manage/`, `/households/<pk>/status/`):** HOA Administrators view all subdivision households and update `hoa_status` (`GOOD_STANDING`, `DELINQUENT`, `INACTIVE`) to control visitor pass eligibility (BR-13).
   - **Ownership & Role Isolation:** Residents can only view, edit, or delete their own households (HTTP 403 Forbidden otherwise).
2. **Digital Visitor Pass Generation & 4-Digit PIN Guardhouse Validation (`passes` app — `/passes/`)**
   - **Resident Pass CRUD (`/passes/`, `/passes/create/`, `/passes/<pk>/`, `/passes/<pk>/edit/`, `/passes/<pk>/revoke/`, `/passes/<pk>/delete/`):**
     - Verified residents with a household in `GOOD_STANDING` (BR-13) generate time-bound digital visitor passes (`GUEST`, `DELIVERY`, `SERVICE`, `CONTRACTOR`) with an automatically generated 4-digit security PIN (`access_pin`, BR-10) and unique cryptographic token (`qr_token`, BR-11).
     - Enforces `valid_until > valid_from` (BR-09) and valid lifecycle statuses (`PENDING`, `ACTIVE`, `USED`, `EXPIRED`, `REVOKED`, BR-12).
     - Residents can view the high-contrast 4-Digit PIN credential card, edit active/pending passes, revoke passes, or delete unused passes (passes referenced by a `GateAccessLog` are protected against deletion per BR-19).
   - **Guardhouse 4-Digit PIN Validation Kiosk (`/passes/validate/`):**
     - On-duty Security Guards validate incoming visitors by entering the 4-digit PIN via the on-screen keypad or keyboard.
     - Automatically marks passes past `valid_until` as `EXPIRED` (BR-14), transitions single-entry passes to `USED` upon granted clearance (BR-15), and records an immutable `GateAccessLog` (`GRANTED` or `DENIED`, BR-17) linked to the processing guard (`guard_user`, BR-16), `VisitorPass` (BR-19), and destination `Household`.
   - **Gate Access Logs & Exit Tracking (`/passes/logs/`, `/passes/logs/<pk>/exit/`):**
     - Security Guards and HOA Administrators inspect and filter gate entry/exit transactions (`GRANTED`, `DENIED`, `MANUAL_OVERRIDE`).
     - Guards record visitor departure timestamps (`exit_timestamp >= entry_timestamp`, BR-18).

### Implemented Standard Account Features (Project Development 1)
1. **Account Registration (`/accounts/signup/`)**
   - Homeowners/residents can register with `username`, `email`, `first_name`, `last_name`, `phone_number`, and confirmed passwords.
   - Validates required fields, email format, unique username and email (BR-01), and matching passwords.
   - Uses Django's built-in password hashing (`PBKDF2`) — plain-text passwords are never stored.
   - Self-registered users are strictly assigned the `RESIDENT` role (BR-02) with `is_approved=False` pending HOA verification (F-02, BR-13).
   - Displays a dismissible Bootstrap 5 `alert-success` notification upon registration (`SuccessMessageMixin`).
2. **Login & Logout (`/accounts/login/`, `/accounts/logout/`)**
   - Supports signing in using **either Username or Email Address** (`EmailOrUsernameModelBackend`).
   - Displays clear Bootstrap error messages when credentials are invalid.
   - Secure POST logout terminates the user session and redirects to the login page.
   - All internal pages require authentication (`LoginRequiredMixin`). Unauthenticated visitors are redirected to `/accounts/login/`.
3. **Role-Based User Dashboards (`/dashboard/resident/`, `/dashboard/guard/`, `/dashboard/admin/`)**
   - Supports all three SDD roles:
     - `RESIDENT` — Subdivision Resident Portal (view HOA verification standing, community stats, and personal security record).
     - `GUARD` — Guardhouse Security Kiosk (view HOA-verified resident directory for gate clearance).
     - `ADMIN` — HOA Administration Console (approve pending residents, manage active status, and assign `RESIDENT`, `GUARD`, or `ADMIN` roles).
   - Logging in to `/` (`DashboardRedirectView`) automatically routes each user to their role-specific dashboard.
   - Role isolation is strictly enforced via `RoleRequiredMixin`: typing another role's dashboard URL returns **HTTP 403 Forbidden**.
4. **User Profile (`/accounts/profile/` & `/accounts/profile/edit/`)**
   - Logged-in users can view and update their own profile details (`first_name`, `last_name`, `email`, `phone_number`, and `profile_photo` image upload).
   - Locked to `request.user` (`ProfileView` and `ProfileUpdateView`); attempting to view or edit another user's profile ID returns **HTTP 403 Forbidden**.

---

## Steps to Run the Project

### 1. Navigate to the Project Directory
```powershell
cd sekyu\sekyu_project
```

### 2. Create and Activate a Virtual Environment
**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Create the PostgreSQL Database & Configure `.env`
Create the `sekyu_db` database in PostgreSQL (e.g. via `psql` or pgAdmin):
```sql
CREATE DATABASE sekyu_db;
```
Copy `.env.example` to `.env` and fill in your PostgreSQL credentials:
```powershell
Copy-Item .env.example .env
```
Edit `.env`:
```env
DJANGO_SECRET_KEY=your-secure-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
DB_ENGINE=django.db.backends.postgresql
DB_NAME=sekyu_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
```

### 5. Apply Database Migrations
```powershell
python manage.py migrate
```

### 6. (Optional) Create an HOA Administrator Superuser
```powershell
python manage.py createsuperuser
```

### 7. (Optional) Run the Test Suite & Code Coverage
Run all unit/integration tests across `accounts`, `dashboard`, and `sekyu`, and measure Python + Django template coverage:
```powershell
python manage.py test
coverage erase
coverage run manage.py test
coverage report -m
coverage html
```
Open `htmlcov/index.html` in your browser to inspect line-by-line coverage.

### 8. Run the Development Server
```powershell
python manage.py runserver
```
Open your browser and visit: **http://127.0.0.1:8000/**

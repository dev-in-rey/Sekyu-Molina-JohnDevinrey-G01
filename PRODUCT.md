# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Subdivision Residents / Homeowners:** Account holders who register household profiles, maintain personal and emergency contact credentials, and monitor their HOA verification standing (and in future SDD phases, manage vehicles and digital visitor passes).
- **Security Guards:** On-duty gatehouse personnel who verify HOA-cleared subdivision residents for gate dispatch (and in future SDD phases, validate QR/4-digit PIN visitor passes and log walk-in entries).
- **Homeowners Association (HOA) Administrators:** System managers who review and approve pending resident accounts, toggle account active status, and provision/assign `RESIDENT`, `GUARD`, and `ADMIN` roles (and in future SDD phases, audit gate logs and publish community announcements).

## Product Purpose

Sekyu is a Smart Gate Access and Community Security System built to digitize residential subdivision guardhouse workflows in the Philippines. It eliminates paper logbooks and exposed visitor/resident PII by providing role-isolated digital identity, HOA homeowner verification, and fast gatehouse verification workflows compliant with the Philippine Data Privacy Act of 2012 (Republic Act No. 10173).

## Positioning

Unlike generic campus or corporate portals, Sekyu is designed specifically around Philippine residential subdivision gatehouse operations: strict HOA approval gating before resident clearance, instant high-contrast guardhouse lookup, and statutory RA 10173 data-privacy protection.

## Operating Context

- **Current Active Scope (PD1 Accounts & Dashboards + PD2 Households, Visitor Passes & Gate Logs):** Full-stack Django web portal with PostgreSQL (`sekyu_db`), username or email authentication, resident self-registration (`is_approved=False` until HOA review), role-isolated dashboards (`/dashboard/resident/`, `/dashboard/guard/`, `/dashboard/admin/`), self-service profile/photo management (`/accounts/profile/`), subdivision household block/lot registration (`/households/`), 4-digit PIN digital visitor pass generation (`/passes/`), guardhouse 4-digit PIN validation kiosk (`/passes/validate/`), and immutable gate access entry/exit logging (`/passes/logs/`).
- **Planned SDD Modules (Future Phases):** Resident vehicle registry, optical camera QR scanning, manual walk-in visitor fallback form, offline SQLite guard tablet sync cache, HOA community announcements, and automated 24-hour visitor PII redaction.
- **Deployment Context:** Single-subdivision or gated residential community per deployment instance (`Asia/Manila` timezone).

## Capabilities and Constraints

- **Database & Tech Stack:** Full-stack Django (`Django 6.1.3`) with Django templates, Bootstrap 5 (CDN), Bootstrap Icons, and PostgreSQL (`psycopg`). SQLite is strictly disallowed in the final setup.
- **Role-Based Access Control & Security:** Self-registration creates `RESIDENT` accounts only; `GUARD` and `ADMIN` accounts are assigned by HOA Administrators. Cross-role dashboard access and cross-user profile access must return HTTP 403 Forbidden. Passwords use Django's built-in salted hashing, forms enforce CSRF protection, and secrets remain isolated in `.env`.
- **SDD Scope Exclusions:** No physical boom barrier motor/relay control, no CCTV automated license plate recognition (ALPR), no online HOA payment processing, and no native mobile app store binaries (browser-based web/PWA only).

## Brand Commitments

- **Product Name:** Sekyu (`Sekyu · Smart Gate Access`)
- **Compliance Reference:** Republic Act No. 10173 (Philippine Data Privacy Act of 2012)

## Evidence on Hand

- Software Design Document: `../Molina-JohnDevinrey-SDD.md` and `../Molina-JohnDevinrey-SDD.pdf`
- Project documentation and run instructions: `README.md`
- Automated verification suite: `test_rubric.py`

## Product Principles

1. **Verify Before Clearing:** New resident accounts remain pending until verified by an HOA Administrator (BR-13).
2. **Strict Role Isolation:** Residents, Guards, and HOA Admins operate exclusively inside their own role boundaries.
3. **Privacy by Default (RA 10173):** Expose only the minimum personal data needed for each role's operational duty.
4. **Operational Clarity:** Keep forms, status badges, and directories scannable for quick decisions at the guardhouse and HOA desk.
5. **Truthful Surfaces:** Display only currently active, working system capabilities without fabricated data or dead placeholders.

## Accessibility & Inclusion

- **Guardhouse Kiosk Legibility (SDD 1.4 / 1.7):** High-contrast status indicators, clear typography, and fast search/filtering suitable for guardhouse tablet and desktop monitors across day and night shifts.
- **Inclusive Form Feedback:** Explicit field labels, password visibility toggles, accessible alert roles (`role="alert"`), and clear inline validation messages across desktop and mobile viewports.

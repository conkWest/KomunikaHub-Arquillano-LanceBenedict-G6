# KomunikaHub – Community Broadcast & Incident Coordination Portal

Django + PostgreSQL (Supabase) web portal for barangay/HOA communities.
IT317 – G8, Cebu Institute of Technology University.

## Standard features (PD1)
Registration, login/logout, role-based dashboards (Resident / Barangay Staff), user profile with photo.

## Core feature (PD2): Incident Ticketing and Resolution Workflow
Residents report community incidents; barangay staff triage and resolve them.

**Residents**
- File a ticket (title, category, zone, location, description, up to 3 photos)
- Track their own tickets with a timestamped status history and public staff remarks
- Edit a ticket or remove photos while it is Pending and unassigned

**Barangay staff**
- Dispatch panel with filters: status, urgency, zone, category, keyword
- Set urgency, assign or reassign a field team, post internal or public remarks
- Advance status one step at a time: Pending > In Progress > Resolved
  (a team is required to start; a resolution summary is required to resolve)

**Rules enforced** (SDD BR-19 to BR-34): max 5 open tickets per resident, 20-char minimum
description, JPEG/PNG/WebP photos up to 5 MB (max 3), unique ticket number `KH-YYYY-NNNNN`,
forward-only status, one active team per ticket, immutable audit log, closed tickets locked,
residents see only their own tickets and only public remarks.

## Setup
1. `git clone <repo-url> && cd <repo>`
2. `python -m venv venv` and activate it
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your Supabase credentials
5. `python manage.py migrate`
6. `python manage.py seed_demo` (zones, categories, field teams, demo accounts)
7. `python manage.py runserver` then open http://127.0.0.1:8000/

## Tests
`python manage.py test --settings=komunikahub.test_settings`

## Demo accounts (password `Komunika#2026`)
| Role | Username |
|---|---|
| Barangay Staff | staff_demo |
| Resident | resident_demo, resident_demo2 |

## Branching
`main` (stable) <- `develop` <- `feature/*` via Pull Requests.
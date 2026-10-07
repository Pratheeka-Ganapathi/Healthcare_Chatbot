"""Staff portal over real HTTP: admin bootstrap, doctor login, consultation, admin screens."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from clinic_bot.config import Settings
from tests.fakes.staff import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.integration.conftest import LiveServer, query

PORTAL = "http://localhost:5174"
RAO, MEENA = 1, 3


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "admin_email": ADMIN_EMAIL,
            "admin_password": SecretStr(ADMIN_PASSWORD),
            "staff_origins": [PORTAL],
        }
    )


@pytest.fixture
async def http(live_server: LiveServer) -> AsyncIterator[httpx.AsyncClient]:
    base = live_server.url.replace("ws://", "http://").removesuffix("/ws")
    async with httpx.AsyncClient(base_url=base, timeout=30) as client:  # a doc save re-embeds
        yield client


async def sign_in(http: httpx.AsyncClient, email: str, password: str) -> dict[str, str]:
    r = await http.post("/staff/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_admin_creates_a_doctor_who_records_a_consultation(
    live_server: LiveServer, http: httpx.AsyncClient
) -> None:
    admin = await sign_in(http, ADMIN_EMAIL, ADMIN_PASSWORD)
    created = await http.post(
        "/staff/admin/accounts",
        headers=admin,
        json={
            "email": "Rao@CityCare.test",
            "name": "Dr. Rao",
            "password": "rao-pass-1",
            "doctor_id": RAO,
        },
    )
    assert created.status_code == 201 and created.json()["doctor_name"] == "Dr. Rao"
    doctor = await sign_in(http, "rao@citycare.test", "rao-pass-1")

    today: list[dict[str, Any]] = (
        await http.get("/staff/doctor/appointments?scope=today", headers=doctor)
    ).json()
    meena = next(a for a in today if a["patient"]["id"] == MEENA)
    assert meena["status"] == "booked" and meena["start"].endswith("+05:30")

    body = {
        "notes": "Chest clear.",
        "diagnosis": "Viral fever",
        "medication": "Paracetamol",
        "followup_required": True,
        "followup_in_days": 14,
    }
    r = await http.put(
        f"/staff/doctor/appointments/{meena['id']}/consultation", headers=doctor, json=body
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "completed" and detail["has_consultation"]
    assert detail["consultation"]["submitted_by"] == "Dr. Rao"
    assert detail["consultation"]["followup_valid_until"] == "2026-10-20"
    assert detail["patient"]["phone"] and detail["can_record"]
    grants = await query(
        live_server,
        "SELECT valid_until, created_by FROM followup_grants WHERE source_appointment_id = :a",
        a=meena["id"],
    )
    assert [(str(g["valid_until"]), g["created_by"]) for g in grants] == [("2026-10-20", "Dr. Rao")]

    seen_by_admin = await http.get(f"/staff/admin/appointments/{meena['id']}", headers=admin)
    assert seen_by_admin.json()["consultation"]["diagnosis"] == "Viral fever"


async def test_roles_and_tokens_are_enforced(http: httpx.AsyncClient) -> None:
    assert (await http.get("/staff/me")).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert (await http.get("/staff/me", headers=bad)).status_code == 401
    wrong = await http.post("/staff/auth/login", json={"email": ADMIN_EMAIL, "password": "x"})
    assert wrong.status_code == 401 and wrong.json() == {"detail": "Invalid email or password."}

    admin = await sign_in(http, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert (await http.get("/staff/doctor/appointments", headers=admin)).status_code == 403
    me = (await http.get("/staff/me", headers=admin)).json()
    assert me["role"] == "admin" and me["email"] == ADMIN_EMAIL
    assert (await http.post("/staff/auth/logout", headers=admin)).status_code == 204
    assert (await http.get("/staff/me", headers=admin)).status_code == 401


async def test_admin_screens(http: httpx.AsyncClient) -> None:
    admin = await sign_in(http, ADMIN_EMAIL, ADMIN_PASSWORD)
    overview = (await http.get("/staff/admin/overview", headers=admin)).json()
    assert overview["patients"] == 6 and overview["doctors"] == 8

    tables = {t["name"] for t in (await http.get("/staff/admin/tables", headers=admin)).json()}
    assert {"patients", "consultations", "staff_users"} <= tables and "staff_sessions" not in tables
    users = (await http.get("/staff/admin/tables/staff_users", headers=admin)).json()
    assert "password_hash" not in users["columns"] and users["total"] == 1
    assert (await http.get("/staff/admin/tables/staff_sessions", headers=admin)).status_code == 404

    doctors = (await http.get("/staff/admin/doctors", headers=admin)).json()
    rao = next(d for d in doctors if d["id"] == RAO)
    assert rao["fee_rupees"] == 600 and rao["account"] is None
    r = await http.put(
        f"/staff/admin/doctors/{RAO}",
        headers=admin,
        json={"name": "Dr. Rao", "bio": rao["bio"], "fee_rupees": 650, "followup_fee_rupees": 300},
    )
    assert r.json()["fee_rupees"] == 650

    closure = await http.post(
        "/staff/admin/closures", headers=admin, json={"date": "2026-10-12", "reason": "Festival"}
    )
    assert closure.status_code == 201 and closure.json()["date_label"] == "Mon 12 Oct"
    again = await http.post(
        "/staff/admin/closures", headers=admin, json={"date": "2026-10-12", "reason": "Festival"}
    )
    assert again.status_code == 409
    gone = await http.delete(f"/staff/admin/closures/{closure.json()['id']}", headers=admin)
    assert gone.status_code == 204


async def test_clinic_doc_edits_reach_the_faq(
    live_server: LiveServer, http: httpx.AsyncClient
) -> None:
    admin = await sign_in(http, ADMIN_EMAIL, ADMIN_PASSWORD)
    docs = (await http.get("/staff/admin/clinic-docs", headers=admin)).json()
    info = next(d for d in docs if d["name"] == "clinic_info.md")
    edited = info["content"].replace(
        "Two-wheeler parking is available in the building basement.",
        "Free valet parking is available at the main gate.",
    )
    r = await http.put(
        "/staff/admin/clinic-docs/clinic_info.md", headers=admin, json={"content": edited}
    )
    assert r.status_code == 200 and r.json()["updated_by"] == "Clinic admin"
    faq = live_server.container.services.faq
    answer = await faq.answer("Is there parking at the clinic?", health_topics_allowed=False)
    assert any("valet" in p for p in answer.passages)
    no_heading = await http.put(
        "/staff/admin/clinic-docs/clinic_info.md", headers=admin, json={"content": "plain"}
    )
    assert no_heading.status_code == 400


async def test_cors_allows_the_portal(http: httpx.AsyncClient) -> None:
    r = await http.options(
        "/staff/auth/login",
        headers={
            "Origin": PORTAL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == PORTAL

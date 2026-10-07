"""Staff portal HTTP API under ``/staff`` (SPEC 17.5)."""

from __future__ import annotations

from fastapi import APIRouter

from clinic_bot.api.staff import admin, auth, doctor

router = APIRouter(prefix="/staff")
router.include_router(auth.router)
router.include_router(doctor.router)
router.include_router(admin.router)

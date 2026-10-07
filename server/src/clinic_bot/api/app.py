"""FastAPI application factory. ``app`` is what uvicorn serves."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clinic_bot.api import staff
from clinic_bot.api.routes import router
from clinic_bot.api.staff.errors import domain_error_handler
from clinic_bot.config import Settings
from clinic_bot.container import Container, configure_logging
from clinic_bot.domain.errors import DomainError

ContainerFactory = Callable[[Settings], Awaitable[Container]]


def create_app(
    settings: Settings | None = None, factory: ContainerFactory | None = None
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    build = factory or Container.build

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = await build(settings)
        app.state.container = container
        try:
            yield
        finally:
            await container.aclose()

    app = FastAPI(title="City Care Clinic front desk bot", lifespan=lifespan)
    # The widget only reads; the staff portal (its own origin) also writes, with a token.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*settings.allowed_origins, *settings.staff_origins],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(router)
    app.include_router(staff.router)
    return app


app = create_app()

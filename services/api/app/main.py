from fastapi import FastAPI

from app.db.session import Base, engine
from app.prospecting import models  # noqa: F401
from app.prospecting.api.routes import public_router, router
from app.tenancy import service  # noqa: F401

Base.metadata.create_all(engine)
app = FastAPI(title="Nova")
app.include_router(router, prefix="/api/v1")
app.include_router(public_router, prefix="/api/v1")

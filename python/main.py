from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_indexes
from routes.alerts import router as alerts_router
from routes.auth import router as auth_router
from routes.orders import router as orders_router
from routes.products import router as products_router
from routes.users import router as users_router
from seed import seed_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting SGarden API...")
    await init_indexes()
    await seed_data()
    print("SGarden API started successfully")
    yield
    print("Shutting down SGarden API...")


app = FastAPI(
    title="SGarden API",
    description="Inventory Management API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)
app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(users_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)

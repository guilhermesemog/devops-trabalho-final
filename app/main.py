from fastapi import FastAPI

from app.routes import health, tasks

app = FastAPI(title="Task Manager API")
app.include_router(health.router)
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])

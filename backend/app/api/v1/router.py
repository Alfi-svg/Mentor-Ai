"""API v1 Router aggregating all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    actions,
    auth,
    calendar,
    chat,
    health,
    notifications,
    planner,
    schedule,
    tasks,
)

api_router = APIRouter()

# Include health routes
api_router.include_router(health.router, tags=["health"])
# Include authentication and profile routes
api_router.include_router(auth.router)
# Include tasks resource routes
api_router.include_router(tasks.router)
# Include deterministic scheduler routes
api_router.include_router(schedule.router)
# Include natural-language planner routes
api_router.include_router(planner.router)
# Include chat assistant routes
api_router.include_router(chat.router)
# Include two-phase action approval routes
api_router.include_router(actions.router)
# Include calendar integration routes
api_router.include_router(calendar.router)
# Include task deadline notifications routes
api_router.include_router(notifications.router)

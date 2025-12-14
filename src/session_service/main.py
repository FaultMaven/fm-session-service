"""FaultMaven Session Service

Main FastAPI application entry point.
Extracted from FaultMaven monolith - Phase 2 microservice.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from session_service.config import get_settings
from session_service.api.routes import sessions_router
from session_service.infrastructure.redis import get_redis_client, close_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    settings = get_settings()

    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info(f"Environment: {settings.environment}")

    # Initialize Redis
    try:
        redis_client = await get_redis_client()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Session Service")
    await close_redis_client()
    logger.info("Redis connection closed")


# Create FastAPI application
settings = get_settings()
app = FastAPI(
    title="FaultMaven Session Service",
    version=settings.service_version,
    description="Session management service extracted from FaultMaven monolith",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


# Health check endpoint
@app.get("/health")
async def root_health_check():
    """Root health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
        "environment": settings.environment,
    }


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "description": "FaultMaven Session Service",
        "docs": "/docs",
        "health": "/health",
    }


# Include routers
app.include_router(sessions_router)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "session_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

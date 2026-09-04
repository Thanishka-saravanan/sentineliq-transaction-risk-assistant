import os
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="SentinelIQ — Transaction Risk Investigation Assistant",
    description="Fraud desk investigation assistant (Banking Track: PS06)",
    version="1.0.0",
)

# Mount static directory if it exists
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_homepage():
    """Serves the SentinelIQ dashboard homepage."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "project": "SentinelIQ",
        "track_id": "PS06",
        "status": "online",
        "message": "SentinelIQ API is running."
    }


@app.get("/api/health")
async def health_check():
    """Application health and readiness check."""
    return {
        "status": "healthy",
        "project": "SentinelIQ",
        "track_id": "PS06",
        "version": "1.0.0",
        "gemini_api_key_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

"""
VIKMO Dealer Assistant — FastAPI Backend Server.

Endpoints:
- POST /api/chat       — Send a message, get agent response
- POST /api/reset      — Clear session history
- GET  /api/health     — Health check
- GET  /               — Serve frontend
"""

import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VIKMO Dealer Assistant",
    description="RAG-based automotive parts dealer assistant with tool calling",
    version="1.0.0",
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: str
    response: str
    sources: list[str] = []


class ResetRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Lazy import to avoid slow startup when just serving static files
# ---------------------------------------------------------------------------

_agent_module = None


def _get_agent():
    global _agent_module
    if _agent_module is None:
        from assistant import agent as ag
        _agent_module = ag
    return _agent_module


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "VIKMO Dealer Assistant",
        "version": "1.0.0",
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Process a chat message and return the agent's response."""
    try:
        agent = _get_agent()
        result = agent.chat(request.session_id, request.message)
        return ChatResponse(
            session_id=request.session_id,
            response=result["response"],
            sources=result.get("sources", []),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)[:300]}",
        )


@app.post("/api/reset")
async def reset_session(request: ResetRequest):
    """Clear conversation history for a session."""
    agent = _get_agent()
    agent.clear_history(request.session_id)
    return {"status": "ok", "message": "Session history cleared."}


# ---------------------------------------------------------------------------
# Static Files (Frontend)
# ---------------------------------------------------------------------------

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")

if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the frontend HTML."""
        return FileResponse(os.path.join(frontend_dir, "index.html"))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("\n[*] VIKMO Dealer Assistant starting...")
    print("[>] Open http://localhost:8000 in your browser\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

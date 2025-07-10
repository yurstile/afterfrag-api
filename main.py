from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes.auth import router as auth_router
from routes.profile import router as profile_router
from routes.cdn import router as cdn_router
from routes.communities import router as communities_router
from routes.onboarding import router as onboarding_router
from routes.browse import router as browse_router
from routes.posts import router as posts_router
from routes.comments import router as comments_router
from routes.admin import router as admin_router

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://afterfrag.com", "https://app.afterfrag.com"],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Initialize database
init_db()

# Include routers
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(cdn_router)
app.include_router(communities_router)
app.include_router(onboarding_router)
app.include_router(browse_router)
app.include_router(posts_router)
app.include_router(comments_router)
app.include_router(admin_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=21541, reload=True) 
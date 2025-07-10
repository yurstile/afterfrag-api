from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from typing import List
from database import get_db
from schemas.onboarding import OnboardingRequest, OnboardingResponse, AvailableTopicsResponse, AVAILABLE_TOPICS
from auth import verify_token

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """Get current user ID from token"""
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Get user ID from username
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (payload.get("sub"),))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return row[0]

def has_completed_onboarding(user_id: int) -> bool:
    """Check if user has completed onboarding"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_topics WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        return count >= 3

@router.get("/topics", response_model=AvailableTopicsResponse)
def get_available_topics():
    """Get all available topics for onboarding"""
    return AvailableTopicsResponse(
        topics=AVAILABLE_TOPICS,
        total_count=len(AVAILABLE_TOPICS)
    )

@router.get("/status")
def get_onboarding_status(current_user_id: int = Depends(get_current_user_id)):
    """Check if user has completed onboarding"""
    completed = has_completed_onboarding(current_user_id)
    
    if completed:
        # Get user's selected topics
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT topic FROM user_topics WHERE user_id = ? ORDER BY topic", (current_user_id,))
            topics = [row[0] for row in cursor.fetchall()]
        
        return {
            "completed": True,
            "selected_topics": topics,
            "total_topics": len(topics)
        }
    else:
        return {
            "completed": False,
            "selected_topics": [],
            "total_topics": 0
        }

@router.post("/complete", response_model=OnboardingResponse)
def complete_onboarding(
    onboarding_data: OnboardingRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Complete onboarding by selecting topics"""
    # Check if already completed
    if has_completed_onboarding(current_user_id):
        raise HTTPException(status_code=400, detail="Onboarding already completed")
    
    # Save user topics
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Clear any existing topics (in case of retry)
        cursor.execute("DELETE FROM user_topics WHERE user_id = ?", (current_user_id,))
        
        # Insert new topics
        for topic in onboarding_data.topics:
            cursor.execute("""
                INSERT INTO user_topics (user_id, topic)
                VALUES (?, ?)
            """, (current_user_id, topic))
        
        conn.commit()
    
    return OnboardingResponse(
        message="Onboarding completed successfully! You can now browse communities based on your interests.",
        selected_topics=onboarding_data.topics,
        total_topics=len(onboarding_data.topics)
    )

@router.put("/update-topics", response_model=OnboardingResponse)
def update_topics(
    onboarding_data: OnboardingRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """Update user's topic preferences (after onboarding is completed)"""
    # Check if onboarding was completed
    if not has_completed_onboarding(current_user_id):
        raise HTTPException(status_code=400, detail="Must complete onboarding first")
    
    # Update user topics
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Clear existing topics
        cursor.execute("DELETE FROM user_topics WHERE user_id = ?", (current_user_id,))
        
        # Insert new topics
        for topic in onboarding_data.topics:
            cursor.execute("""
                INSERT INTO user_topics (user_id, topic)
                VALUES (?, ?)
            """, (current_user_id, topic))
        
        conn.commit()
    
    return OnboardingResponse(
        message="Topic preferences updated successfully!",
        selected_topics=onboarding_data.topics,
        total_topics=len(onboarding_data.topics)
    ) 
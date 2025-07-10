from pydantic import BaseModel, validator
from typing import Optional, List, Union
from datetime import datetime
from schemas.posts import PostResponse, CommentResponse
from schemas.shared import SocialLink

class ProfileCreate(BaseModel):
    display_name: str
    bio: Optional[str] = None
    social_links: Optional[List[SocialLink]] = []

    @validator('display_name')
    def validate_display_name(cls, v):
        if len(v) < 3:
            raise ValueError('Display name must be at least 3 characters long')
        return v

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    social_links: Optional[List[SocialLink]] = None

    @validator('display_name')
    def validate_display_name(cls, v):
        if v is not None and len(v) < 3:
            raise ValueError('Display name must be at least 3 characters long')
        return v

class ProfileResponse(BaseModel):
    user_id: int
    username: str
    display_name: str
    bio: Optional[str]
    profile_picture_url: Optional[str]
    is_online: bool
    last_online: datetime
    social_links: List[SocialLink]
    created_at: datetime
    updated_at: datetime
    is_admin: bool

class OnlineStatusUpdate(BaseModel):
    is_online: bool 

class RecentActivityItem(BaseModel):
    type: str  # 'post' or 'comment'
    post: Optional[PostResponse] = None
    comment: Optional[CommentResponse] = None
    created_at: str
    group_name: Optional[str] = None
    group_logo_url: Optional[str] = None
    comment_count: Optional[int] = None

class RecentActivityResponse(BaseModel):
    items: List[RecentActivityItem]
    total: int
    page: int
    page_size: int 
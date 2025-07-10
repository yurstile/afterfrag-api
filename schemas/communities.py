from pydantic import BaseModel, validator
from typing import Optional, List, Dict
from datetime import datetime
import json
from schemas.onboarding import AVAILABLE_TOPICS
from schemas.shared import SocialLink, CommunityPostTagResponse

class CommunityCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tags: List[str]
    rules: Optional[List[str]] = None
    social_links: Optional[List[SocialLink]] = None

    @validator('name')
    def validate_name(cls, v):
        if len(v) < 3:
            raise ValueError('Community name must be at least 3 characters long')
        if len(v) > 50:
            raise ValueError('Community name must be at most 50 characters long')
        return v

    @validator('tags')
    def validate_tags(cls, v):
        if not v:
            raise ValueError('At least one tag is required')
        if len(v) > 5:
            raise ValueError('Maximum 5 tags allowed')
        for tag in v:
            if tag not in AVAILABLE_TOPICS:
                raise ValueError(f'Tag "{tag}" is not a valid topic. Please choose from the available topics.')
        return v

    @validator('rules')
    def validate_rules(cls, v):
        if v is not None and len(v) > 15:
            raise ValueError('Maximum 15 rules allowed')
        return v

class CommunityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    rules: Optional[List[str]] = None
    social_links: Optional[List[SocialLink]] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if len(v) < 3:
                raise ValueError('Community name must be at least 3 characters long')
            if len(v) > 50:
                raise ValueError('Community name must be at most 50 characters long')
        return v

    @validator('tags')
    def validate_tags(cls, v):
        if v is not None:
            if not v:
                raise ValueError('At least one tag is required')
            if len(v) > 5:
                raise ValueError('Maximum 5 tags allowed')
            for tag in v:
                if tag not in AVAILABLE_TOPICS:
                    raise ValueError(f'Tag "{tag}" is not a valid topic. Please choose from the available topics.')
        return v

    @validator('rules')
    def validate_rules(cls, v):
        if v is not None and len(v) > 15:
            raise ValueError('Maximum 15 rules allowed')
        return v

class CommunityMember(BaseModel):
    user_id: int
    username: str
    display_name: str
    role: str
    joined_at: datetime
    profile_picture_url: Optional[str] = None

class CommunityResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    tags: List[str]
    owner_id: int
    owner_username: str
    member_count: int
    online_member_count: int
    created_at: datetime
    updated_at: datetime
    banner_picture_url: Optional[str] = None
    group_picture_url: Optional[str] = None
    rules: Optional[List[str]] = None
    social_links: Optional[List[SocialLink]] = None

class CommunityDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    tags: List[str]
    owner_id: int
    owner_username: str
    staff_members: List[CommunityMember]  # Only owners and moderators
    member_count: int  # Total member count
    online_member_count: int  # Online member count
    created_at: datetime
    updated_at: datetime
    banner_picture_url: Optional[str] = None
    group_picture_url: Optional[str] = None
    rules: Optional[List[str]] = None
    social_links: Optional[List[SocialLink]] = None

class CommunityMemberUpdate(BaseModel):
    role: str

    @validator('role')
    def validate_role(cls, v):
        allowed_roles = ['moderator', 'member']
        if v not in allowed_roles:
            raise ValueError(f'Role must be one of: {allowed_roles}')
        return v 

class PostTag(BaseModel):
    name: str
    description: str = ""
    color: str = "#cccccc"  # Optional: for UI 

class CommunityPostTagCreate(BaseModel):
    name: str
    color: str = "#cccccc"

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v) < 1:
            raise ValueError('Tag name cannot be empty')
        if len(v) > 30:
            raise ValueError('Tag name must be at most 30 characters')
        return v

class CommunityPostTagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v or len(v) < 1:
                raise ValueError('Tag name cannot be empty')
            if len(v) > 30:
                raise ValueError('Tag name must be at most 30 characters')
        return v

class CommunityPostTagResponse(BaseModel):
    id: int
    community_id: int
    name: str
    color: str 
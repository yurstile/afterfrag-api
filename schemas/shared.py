from pydantic import BaseModel, validator
from typing import Optional

class SocialLink(BaseModel):
    platform: str
    url: str

    @validator('platform')
    def validate_platform(cls, v):
        allowed_platforms = ['twitter', 'youtube', 'spotify', 'custom', 'discord', 'roblox']
        if v not in allowed_platforms:
            raise ValueError(f'Platform must be one of: {allowed_platforms}')
        return v

class CommunityPostTagResponse(BaseModel):
    id: int
    community_id: int
    name: str
    color: Optional[str] = None 
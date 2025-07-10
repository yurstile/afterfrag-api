from pydantic import BaseModel, validator
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from schemas.shared import CommunityPostTagResponse

class PostMedia(BaseModel):
    file_uuid: str
    file_type: str  # 'image' or 'video'
    file_size: int
    url: Optional[str] = None

class PostCreate(BaseModel):
    title: str
    content: str
    post_tag_ids: List[int] = []
    media: Optional[List[PostMedia]] = []

    @validator('title')
    def validate_title(cls, v):
        if not v or len(v) < 3:
            raise ValueError('Title must be at least 3 characters long')
        if len(v) > 100:
            raise ValueError('Title must be at most 100 characters long')
        return v

    @validator('content')
    def validate_content(cls, v):
        if not v or len(v) < 1:
            raise ValueError('Content cannot be empty')
        if len(v) > 1000:
            raise ValueError('Content must be at most 1000 characters long')
        return v

    @validator('media')
    def validate_media(cls, v):
        if v and len(v) > 5:
            raise ValueError('Maximum 5 media attachments allowed')
        return v

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    post_tag_ids: Optional[List[int]] = None
    media: Optional[List[PostMedia]] = None

class PostResponse(BaseModel):
    id: int
    community_id: int
    user_id: int
    title: str
    content: str
    post_tags: List[CommunityPostTagResponse] = []
    like_count: int
    view_count: int
    created_at: datetime
    updated_at: datetime
    media: List[PostMedia] = []
    author_username: Optional[str] = None
    author_display_name: Optional[str] = None
    author_profile_picture_url: Optional[str] = None

class PostLikeRequest(BaseModel):
    value: int  # 1 for like, -1 for dislike

    @validator('value')
    def validate_value(cls, v):
        if v not in (1, -1):
            raise ValueError('Value must be 1 (like) or -1 (dislike)')
        return v

class CommentMedia(BaseModel):
    file_uuid: str
    file_type: str  # 'image' or 'video'
    file_size: int
    url: Optional[str] = None

class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None
    media: Optional[List[CommentMedia]] = []

    @validator('content')
    def validate_content(cls, v):
        if not v or len(v) < 1:
            raise ValueError('Content cannot be empty')
        if len(v) > 1000:
            raise ValueError('Content must be at most 1000 characters long')
        return v
    @validator('media')
    def validate_media(cls, v):
        if v and len(v) > 5:
            raise ValueError('Maximum 5 media attachments allowed')
        return v

class CommentUpdate(BaseModel):
    content: Optional[str] = None
    media: Optional[List[CommentMedia]] = None

class CommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    content: str
    parent_id: Optional[int] = None
    like_count: int
    created_at: datetime
    updated_at: datetime
    media: List[CommentMedia] = []
    author_username: Optional[str] = None
    author_display_name: Optional[str] = None
    author_profile_picture_url: Optional[str] = None
    children: Optional[List['CommentResponse']] = None

class CommentLikeRequest(BaseModel):
    value: int  # 1 for like, -1 for dislike
    @validator('value')
    def validate_value(cls, v):
        if v not in (1, -1):
            raise ValueError('Value must be 1 (like) or -1 (dislike)')
        return v

class PostResponseWithComments(PostResponse):
    comment_count: int
    comments: Optional[List['CommentResponse']] = None

PostResponseWithComments.model_rebuild()
CommentResponse.model_rebuild() 
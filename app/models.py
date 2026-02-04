"""Pydantic models for API responses."""
from typing import Any, Optional

from pydantic import BaseModel


class AccountOut(BaseModel):
    account_id: int
    platform: str
    handle: str
    display_name: str
    category: Optional[str] = None
    role: Optional[str] = None
    is_enabled: int = 1


class PostOut(BaseModel):
    model_config = {"from_attributes": True}
    
    id: int
    platform: str
    post_id: str
    url: str
    author_handle: str
    author_display_name: str
    category: str
    text: str
    created_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    tagged_account_handle: Optional[str] = None
    tagged_hashtags: Optional[str] = None
    language: Optional[str] = None
    media_json: Optional[str] = None
    metrics_json: Optional[str] = None
    account_id: Optional[int] = None
    like_count: int = 0


class PostListResponse(BaseModel):
    posts: list[PostOut]
    total: int


class LikeUpdateOut(BaseModel):
    post_id: str
    like_count: int

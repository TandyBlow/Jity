"""Schemas for AI-generated scene backgrounds."""

from pydantic import BaseModel, Field


class BackgroundGenerateRequest(BaseModel):
    scene_prompt: str = Field(min_length=1, max_length=4000)
    location: str = Field(default="", max_length=500)


class BackgroundGenerateResponse(BaseModel):
    image_url: str
    cached: bool = False

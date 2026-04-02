from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from google import genai


app = FastAPI(title="Mood Tracker Gemini Backend")


class Constraints(BaseModel):
    tone: str = "Supportive"
    safe_style: list[str] = Field(default_factory=list)
    return_json_only: bool = True
    suggestion_count: int = 4


class UserContext(BaseModel):
    name: str = ""
    mood_emoji: str
    mood_label: str
    energy: int = Field(ge=0, le=100)
    stress: int = Field(ge=0, le=100)
    focus: int = Field(ge=0, le=100)
    motivation: int = Field(ge=0, le=100)
    preferred_suggestion_types: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    task: str
    constraints: Constraints
    user_context: UserContext
    expected_output_schema: dict = Field(default_factory=dict)


class Affirmation(BaseModel):
    title: str
    tags: str
    body: str
    note: str


class GenerateResponse(BaseModel):
    suggestions: list[str] = Field(min_length=4, max_length=4)
    reward: str
    affirmation: Affirmation
    insight: str


def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set on the backend.")
    return genai.Client(api_key=api_key)


def choose_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def build_prompt(req: GenerateRequest) -> str:
    safe_style = ", ".join(req.constraints.safe_style) if req.constraints.safe_style else "supportive"
    name_line = f"User name: {req.user_context.name}." if req.user_context.name else ""
    types = ", ".join(req.user_context.preferred_suggestion_types) or "Productivity, Self-care, Social"

    return f"""
You are generating content for a non-clinical mood tracker and light wellness app.
Stay supportive, practical, emotionally safe, and concise.
Do not diagnose, do not mention therapy, emergencies, disorders, medication, or medical advice.
Avoid guilt, shame, and overpromising.
Write in a {req.constraints.tone.lower()} tone.
Style constraints: {safe_style}.

{name_line}
Mood emoji: {req.user_context.mood_emoji}
Mood label: {req.user_context.mood_label}
Energy: {req.user_context.energy}/100
Stress: {req.user_context.stress}/100
Focus: {req.user_context.focus}/100
Motivation: {req.user_context.motivation}/100
Preferred suggestion types: {types}

Return exactly {req.constraints.suggestion_count} short suggestions.
Each suggestion should be concrete and realistic for today.
Reward should be short and light.
Affirmation should feel encouraging, not cheesy.
Insight should be one short sentence.
Return only valid JSON matching the provided schema.
""".strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    client = get_client()
    model = choose_model()

    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(req),
            config={
                "response_mime_type": "application/json",
                "response_json_schema": GenerateResponse.model_json_schema(),
                "temperature": 0.7,
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini API call failed: {exc}") from exc

    output_text = getattr(response, "text", "")
    if not output_text:
        raise HTTPException(status_code=502, detail="Gemini returned no text output.")

    try:
        data = json.loads(output_text)
        return GenerateResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Invalid Gemini response format: {exc}") from exc

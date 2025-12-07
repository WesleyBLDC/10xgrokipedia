import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from xai_sdk import Client
from xai_sdk.chat import user, system

router = APIRouter()

# MBFC Bias Evaluation Models
BiasRating = Literal[
    "Extreme Left",
    "Left",
    "Left-Center",
    "Least Biased",
    "Right-Center",
    "Right",
    "Extreme Right"
]

FactualRating = Literal[
    "Very High",
    "High",
    "Mostly Factual",
    "Mixed",
    "Low",
    "Very Low"
]


class BreakdownItem(BaseModel):
    score: float = Field(..., description="Score from 0–10 or -10 to +10")
    weight: float = Field(..., description="MBFC weight")
    contribution: float = Field(..., description="score × weight, rounded correctly")


class FactualReportingBreakdown(BaseModel):
    failed_fact_checks: BreakdownItem
    sourcing: BreakdownItem
    transparency: BreakdownItem
    one_sidedness_omission_propaganda: BreakdownItem


class FactualReporting(BaseModel):
    overall_score: float = Field(..., ge=0, le=10, description="Weighted final score")
    rating: FactualRating
    breakdown: FactualReportingBreakdown


class BiasBreakdown(BaseModel):
    economic_system: BreakdownItem
    social_progressive_vs_traditional: BreakdownItem
    straight_news_reporting_balance: BreakdownItem
    editorial_bias: BreakdownItem


class Bias(BaseModel):
    overall_score: float = Field(..., ge=-10, le=10, description="Weighted final score")
    rating: BiasRating
    breakdown: BiasBreakdown


class ArticleEvaluation(BaseModel):
    title: str
    url: str
    factual_reporting: FactualReporting
    bias: Bias


class MBFCResponse(BaseModel):
    article: ArticleEvaluation


class BiasRequest(BaseModel):
    url: str | None = None
    text: str | None = None


SYSTEM_PROMPT = """You are an impartial media analyst who strictly follows the official Media Bias/Fact Check (MBFC) methodology[](https://mediabiasfactcheck.com/methodology/).

When I give you a URL or full article text, perform a complete MBFC-style evaluation and respond as follows:

1. Thoroughly read and analyze the article.

2. Score it using the two official MBFC scales:

   - Factual Reporting: 0–10 (lower = more factual)

   - Bias: −10 (Extreme Left) to +10 (Extreme Right)

3. Write a detailed human-readable analysis with exactly two tables (Factual Reporting + Bias), including clear rationales for every sub-score.

4. At the very end of your response, output ONLY a single valid JSON object (no markdown fences, no extra text) that exactly matches this structure:

{
  "article": {
    "title": "exact article title",
    "url": "URL I provided or 'provided text' if none",
    "factual_reporting": {
      "overall_score": 1.8,
      "rating": "Very High|High|Mostly Factual|Mixed|Low|Very Low",
      "breakdown": {
        "failed_fact_checks": { "score": 0.0, "weight": 0.40, "contribution": 0.0 },
        "sourcing": { "score": 1.5, "weight": 0.25, "contribution": 0.375 },
        "transparency": { "score": 0.5, "weight": 0.25, "contribution": 0.125 },
        "one_sidedness_omission_propaganda": { "score": 5.0, "weight": 0.10, "contribution": 0.5 }
      }
    },
    "bias": {
      "overall_score": -4.2,
      "rating": "Extreme Left|Left|Left-Center|Least Biased|Right-Center|Right|Extreme Right",
      "breakdown": {
        "economic_system": { "score": -2.0, "weight": 0.35, "contribution": -0.7 },
        "social_progressive_vs_traditional": { "score": -7.0, "weight": 0.35, "contribution": -2.45 },
        "straight_news_reporting_balance": { "score": -4.0, "weight": 0.15, "contribution": -0.6 },
        "editorial_bias": { "score": -5.0, "weight": 0.15, "contribution": -0.75 }
      }
    }
  }
}

Use exactly one decimal place for all numbers. The JSON must be the very last thing in your response and must be perfectly parseable by json.loads() in Python. Today is December 06, 2025."""


@router.post("/bias")
async def evaluate_bias(request: BiasRequest) -> MBFCResponse:
    """Evaluate article bias and factual reporting using MBFC methodology via Grok."""
    if not request.url and not request.text:
        raise HTTPException(status_code=400, detail="Either 'url' or 'text' must be provided.")
    
    # Prepare article content
    article_url = request.url or "provided text"
    article_text = request.text or ""
    
    if request.url and not request.text:
        # If only URL is provided, we'll pass it to Grok
        user_message = f"Please evaluate this article URL: {request.url}"
    else:
        # If text is provided, use it
        user_message = f"Please evaluate this article text:\n\n{article_text}"
    
    # Initialize xAI client
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="XAI_API_KEY environment variable is not set"
        )
    
    client = Client(api_key=api_key)
    
    try:
        # Create chat session
        chat = client.chat.create(model="grok-4-fast-reasoning")
        
        # Add system and user messages
        chat.append(system(SYSTEM_PROMPT))
        chat.append(user(user_message))
        
        # Use parse method to get structured output directly as Pydantic model
        response, parsed_response = chat.parse(MBFCResponse)
        
        # Return the parsed response (already validated and structured)
        return parsed_response
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error calling Grok API: {str(e)}"
        )


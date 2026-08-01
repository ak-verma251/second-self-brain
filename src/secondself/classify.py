import os
import json
import time
from dataclasses import dataclass
from dotenv import load_dotenv
from groq import Groq

from secondself.config import PARA_CATEGORIES, LLM_MODEL

@dataclass
class ClassificationResult:
    category: str          # "projects" | "areas" | "resources" | "archives"
    tags: list[str]        # Up to 5 tags
    summary: str           # One-line summary
    suggested_title: str   # Short descriptive title
    confidence: float      # 0.0–1.0

def classify(content: str) -> ClassificationResult:
    """Send content to Groq LLM and get PARA classification."""
    # 1. Load GROQ_API_KEY from .env (python-dotenv)
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment. Please add it to your .env file.")

    client = Groq(api_key=api_key)

    # 2. Build classification prompt
    prompt = f"""You are a personal knowledge management assistant.
Classify the following note using the PARA method:
- Projects: Active goals with deadlines
- Areas: Ongoing responsibilities  
- Resources: Topics of interest / reference material
- Archives: Inactive/completed items

Return JSON:
{{
  "category": "projects|areas|resources|archives",
  "tags": ["tag1", "tag2", "tag3"],
  "summary": "One-line summary of the content",
  "suggested_title": "Short descriptive title",
  "confidence": 0.95
}}
The confidence should be a float between 0.0 and 1.0. Limit tags to maximum 5.

Note content:
---
{content}
---"""

    retries = 1
    # 7. Handle API errors gracefully (retry once, then raise)
    for attempt in range(retries + 1):
        try:
            # 3. Call Groq API with llama3-70b-8192
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )

            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("Received empty response from Groq.")
            
            # 4. Parse JSON response
            data = json.loads(result_text)
            
            category = data.get("category", "").lower()
            tags = data.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            tags = tags[:5]
            summary = data.get("summary", "")
            suggested_title = data.get("suggested_title", "")
            confidence = data.get("confidence", 1.0)
            
            # 5. Validate category is one of PARA_CATEGORIES
            if category not in PARA_CATEGORIES:
                category = "resources"
            
            # 6. Return ClassificationResult
            return ClassificationResult(
                category=category,
                tags=tags,
                summary=summary,
                suggested_title=suggested_title,
                confidence=float(confidence)
            )
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            raise e

def classify_capture(capture: dict) -> ClassificationResult:
    """Classify a raw capture dict."""
    content_dict = capture.get("content", {})
    text_content = ""
    
    if capture.get("type") == "note":
        text_content = content_dict.get("text", "")
    elif capture.get("type") == "url":
        text_content = content_dict.get("text", "")
        url = content_dict.get("url", "")
        if url:
            text_content = f"URL: {url}\n\n{text_content}"
    elif capture.get("type") == "file":
        text_content = content_dict.get("file_content", "")
        if not text_content:
            text_content = f"File Content Description: {content_dict.get('file_path', 'binary file')}"
    else:
        text_content = str(content_dict)

    if not text_content.strip():
        text_content = "Empty content"

    return classify(text_content)

import os
import json
import base64
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ai")

AZURE_VISION_API_URL = os.getenv("AZURE_VISION_API_URL")
AZURE_VISION_API_KEY = os.getenv("AZURE_VISION_API_KEY")

MAX_RETRIES = 3


async def call_azure_vision(image_bytes, prompt: str, mime_type: str = "image/png") -> dict:
    """
    Send image(s) to Azure OpenAI GPT-4o vision and get structured JSON back.
    Accepts a single bytes object or a list of bytes (multi-page).
    Retries up to 3 times on failure.
    """
    # Normalize to list for multi-image support
    if isinstance(image_bytes, list):
        images = image_bytes
    else:
        images = [image_bytes]

    content = [{"type": "text", "text": prompt}]
    total_bytes = 0
    for img in images:
        b64_image = base64.b64encode(img).decode("utf-8")
        total_bytes += len(img)
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{b64_image}",
            },
        })

    payload = {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 1000,
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_VISION_API_KEY,
    }

    logger.info(f"Azure vision call — {len(images)} image(s), {total_bytes} bytes total, mime={mime_type}, url={AZURE_VISION_API_URL}")

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Attempt {attempt + 1}/{MAX_RETRIES}")
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    AZURE_VISION_API_URL,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(f"Raw AI response: {content[:500]}")

                # Strip markdown code fences if present
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()

                parsed = json.loads(content)
                logger.info(f"Parsed AI response: {parsed}")
                return parsed

        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            last_error = e
            continue

    logger.error(f"All {MAX_RETRIES} attempts failed")
    raise last_error

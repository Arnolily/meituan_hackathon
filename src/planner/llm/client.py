from typing import Any, Dict, Optional

from openai import OpenAI


class OpenAICompatibleClient:
    """Thin wrapper over OpenAI-compatible chat endpoints.

    This keeps provider-specific configuration outside planner modules so later
    modules can target Gemini, DeepSeek, or other OpenAI-style APIs by only
    changing `base_url`, `api_key`, and `model`.
    """

    def __init__(self, *, api_key: str, base_url: Optional[str] = None, model: str) -> None:
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return __import__("json").loads(content)


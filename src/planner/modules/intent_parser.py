from typing import Any, Optional, Protocol

from planner.llm.prompts import INTENT_PARSER_SYSTEM_PROMPT, build_intent_parser_user_prompt
from planner.schemas import Intent


class JSONLLMClient(Protocol):
    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> dict[str, Any]:
        ...

def parse_intent(query: str, *, default_city: Optional[str] = None, llm_client: Optional[JSONLLMClient] = None) -> Intent:
    if llm_client is None:
        raise ValueError("Intent parsing requires an LLM client. Configure the API and pass --llm.")
    return llm_parse(query, default_city=default_city, llm_client=llm_client)


def llm_parse(query: str, *, default_city: Optional[str], llm_client: JSONLLMClient) -> Intent:
    payload = llm_client.generate_json(
        system_prompt=INTENT_PARSER_SYSTEM_PROMPT,
        user_prompt=build_intent_parser_user_prompt(query, default_city),
        temperature=0.0,
    )
    intent = Intent.from_llm_payload(payload, raw_query=query)
    if default_city and not intent.city:
        intent = intent.model_copy(update={"city": default_city})
    return intent

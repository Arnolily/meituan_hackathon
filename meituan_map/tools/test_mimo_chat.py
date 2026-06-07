import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from urllib import error, request


DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2-flash"
DEFAULT_SYSTEM_PROMPT = "You are MiMo, a helpful AI assistant."


def load_env_file(env_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
          continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def resolve_config(args: argparse.Namespace) -> Dict[str, str]:
    env_values = load_env_file(Path(args.env_file))
    api_key = (
        args.api_key
        or os.getenv("MIMO_API_KEY")
        or os.getenv("VITE_MIMO_API_KEY")
        or env_values.get("MIMO_API_KEY")
        or env_values.get("VITE_MIMO_API_KEY")
    )
    base_url = (
        args.base_url
        or os.getenv("VITE_MIMO_BASE_URL")
        or env_values.get("VITE_MIMO_BASE_URL")
        or DEFAULT_BASE_URL
    )
    model = args.model or os.getenv("VITE_MIMO_MODEL") or env_values.get("VITE_MIMO_MODEL") or DEFAULT_MODEL

    if not api_key:
        raise RuntimeError("Missing API key. Pass --api-key or configure MIMO_API_KEY / VITE_MIMO_API_KEY.")

    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
    }


def normalize_message_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict))
    return ""


def extract_assistant_text(choice: Dict) -> Tuple[str, str]:
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = normalize_message_content(message.get("content"))
    reasoning = normalize_message_content(message.get("reasoning_content"))
    finish_reason = str(choice.get("finish_reason", ""))
    text = content or reasoning
    if finish_reason == "length" and text:
        text = f"{text}\n\n[finish_reason=length: 输出可能被截断，可提高 --max-completion-tokens]"
    return text, finish_reason


def call_mimo(
    api_key: str,
    base_url: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_completion_tokens: int,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
        "temperature": temperature,
        "top_p": 0.95,
        "stream": False,
        "frequency_penalty": 0,
        "presence_penalty": 0,
    }

    req = request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Unexpected response: {json.dumps(data, ensure_ascii=False)}")

    text, _ = extract_assistant_text(choices[0])
    if not text:
        raise RuntimeError(f"Model returned empty text: {json.dumps(data, ensure_ascii=False)}")
    return text


def interactive_chat(config: Dict[str, str], system_prompt: str, temperature: float, max_completion_tokens: int) -> None:
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    print(f"MiMo chat ready | model={config['model']} | base_url={config['base_url']}")
    print("Type your message. Use /exit to quit, /clear to reset history, /system <prompt> to replace system prompt.")

    while True:
        try:
            user_text = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return

        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            print("Bye.")
            return
        if user_text == "/clear":
            messages = [{"role": "system", "content": system_prompt}]
            print("Conversation history cleared.")
            continue
        if user_text.startswith("/system "):
            system_prompt = user_text[len("/system ") :].strip() or DEFAULT_SYSTEM_PROMPT
            messages = [{"role": "system", "content": system_prompt}]
            print("System prompt updated and conversation history reset.")
            continue

        messages.append({"role": "user", "content": user_text})
        try:
            reply = call_mimo(
                api_key=config["api_key"],
                base_url=config["base_url"],
                model=config["model"],
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
            )
        except RuntimeError as exc:
            print(f"Error> {exc}")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": reply})
        print(f"MiMo> {reply}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone interactive MiMo chat tester.")
    parser.add_argument("--api-key", help="Override API key.")
    parser.add_argument("--base-url", help="Override base URL.")
    parser.add_argument("--model", help="Override model name.")
    parser.add_argument("--system", default=DEFAULT_SYSTEM_PROMPT, help="Initial system prompt.")
    parser.add_argument("--env-file", default=".env.local", help="Path to env file. Default: .env.local")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature.")
    parser.add_argument("--max-completion-tokens", type=int, default=1024, help="Max completion tokens.")
    args = parser.parse_args()

    try:
        config = resolve_config(args)
    except RuntimeError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    interactive_chat(
        config=config,
        system_prompt=args.system,
        temperature=args.temperature,
        max_completion_tokens=args.max_completion_tokens,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

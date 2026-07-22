from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Iterable


class ProbeFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class ProbeConfig:
    provider: str
    base_url: str
    strict_base_url: str
    model: str
    api_key: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "ProbeConfig":
        provider = os.getenv("MODEL_PROVIDER", "deepseek").strip().lower()
        if provider != "deepseek":
            raise ProbeFailure(
                f"MODEL_PROVIDER must be 'deepseek' for this probe, received '{provider or '<empty>'}'."
            )

        base_url = os.getenv("MODEL_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
        strict_base_url = os.getenv(
            "MODEL_STRICT_BASE_URL", f"{base_url}/beta"
        ).strip().rstrip("/")
        model = os.getenv("MODEL_NAME", "deepseek-v4-pro").strip()
        api_key = os.getenv("MODEL_API_KEY", "").strip()
        timeout_raw = os.getenv("MODEL_TIMEOUT_SECONDS", "90").strip()

        if not base_url.startswith("https://"):
            raise ProbeFailure("MODEL_BASE_URL must use HTTPS.")
        if not strict_base_url.startswith("https://"):
            raise ProbeFailure("MODEL_STRICT_BASE_URL must use HTTPS.")
        if not model:
            raise ProbeFailure("MODEL_NAME is required.")
        if not api_key:
            raise ProbeFailure(
                "MODEL_API_KEY is not configured. Set it in the local environment; never paste it into logs or Git."
            )
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ProbeFailure("MODEL_TIMEOUT_SECONDS must be numeric.") from exc
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ProbeFailure("MODEL_TIMEOUT_SECONDS must be greater than 0 and at most 300.")

        return cls(
            provider=provider,
            base_url=base_url,
            strict_base_url=strict_base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )


def redact(text: str, secrets: Iterable[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "<redacted-api-key>", redacted)
    return redacted[:800]


def message_dump(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        value = message.model_dump()
        if isinstance(value, dict):
            return value
    if isinstance(message, dict):
        return message
    return {}


def get_reasoning_content(message: Any) -> str:
    direct = getattr(message, "reasoning_content", None)
    if isinstance(direct, str):
        return direct
    dumped = message_dump(message)
    value = dumped.get("reasoning_content")
    return value if isinstance(value, str) else ""


def get_text_content(message: Any) -> str:
    value = getattr(message, "content", None)
    if isinstance(value, str):
        return value
    dumped = message_dump(message)
    content = dumped.get("content")
    return content if isinstance(content, str) else ""


def completion_metadata(response: Any) -> dict[str, Any]:
    choices = getattr(response, "choices", []) or []
    finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
    return {
        "response_model": getattr(response, "model", None),
        "finish_reason": finish_reason,
    }


def run_probe() -> dict[str, Any]:
    config = ProbeConfig.from_environment()
    structured_flag = os.getenv("MODEL_SUPPORTS_STRUCTURED_OUTPUT", "").strip().lower()
    if structured_flag not in {"1", "true", "yes", "on"}:
        raise ProbeFailure("MODEL_SUPPORTS_STRUCTURED_OUTPUT must be true for Gate 0.")

    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise ProbeFailure(
            "The approved services/api environment is missing the 'openai' package."
        ) from exc

    client = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    strict_client = OpenAI(
        api_key=config.api_key,
        base_url=config.strict_base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
    )

    results: dict[str, Any] = {
        "provider": config.provider,
        "requested_model": config.model,
        "probes": {},
    }

    text_messages = [
        {
            "role": "system",
            "content": "Return a short plain-text acknowledgement for a capability probe.",
        },
        {"role": "user", "content": "Reply with the word READY."},
    ]
    text_response = client.chat.completions.create(
        model=config.model,
        messages=text_messages,
        extra_body={"thinking": {"type": "disabled"}},
        temperature=0,
        max_tokens=128,
    )
    text_message = text_response.choices[0].message
    text_content = get_text_content(text_message)
    empty_content_retry_used = False
    if not text_content.strip():
        empty_content_retry_used = True
        text_response = client.chat.completions.create(
            model=config.model,
            messages=text_messages
            + [{"role": "user", "content": "The previous content was empty. Reply READY now."}],
            extra_body={"thinking": {"type": "disabled"}},
            temperature=0,
            max_tokens=512,
        )
        text_message = text_response.choices[0].message
        text_content = get_text_content(text_message)
    if not text_content.strip():
        metadata = completion_metadata(text_response)
        reasoning_present = bool(get_reasoning_content(text_message).strip())
        raise ProbeFailure(
            "Text probe returned empty content after one retry "
            f"(response_model={metadata['response_model']}, "
            f"finish_reason={metadata['finish_reason']}, reasoning_present={reasoning_present})."
        )
    results["probes"]["text"] = {
        "ok": True,
        "empty_content_retry_used": empty_content_retry_used,
        **completion_metadata(text_response),
    }

    thinking_response = client.chat.completions.create(
        model=config.model,
        messages=[
            {
                "role": "user",
                "content": "Think through 17 multiplied by 19, then give only the final number in content.",
            }
        ],
        extra_body={"thinking": {"type": "enabled"}},
        reasoning_effort="high",
        max_tokens=256,
    )
    thinking_message = thinking_response.choices[0].message
    reasoning_present = bool(get_reasoning_content(thinking_message).strip())
    answer_present = bool(get_text_content(thinking_message).strip())
    if not reasoning_present or not answer_present:
        raise ProbeFailure(
            "Thinking probe did not return both transient reasoning_content and final content."
        )
    # Intentionally discard reasoning_content; it must never enter persistent logs or artifacts.
    results["probes"]["thinking"] = {
        "ok": True,
        "reasoning_present": True,
        "content_present": True,
        **completion_metadata(thinking_response),
    }

    tool_response = strict_client.chat.completions.create(
        model=config.model,
        messages=[
            {
                "role": "user",
                "content": "Call record_probe exactly once with status set to ok.",
            }
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "record_probe",
                    "description": "Record a successful Gate 0 capability probe.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["ok"]}
                        },
                        "required": ["status"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "record_probe"}},
        extra_body={"thinking": {"type": "disabled"}},
        temperature=0,
        max_tokens=128,
    )
    tool_message = tool_response.choices[0].message
    tool_calls = getattr(tool_message, "tool_calls", None) or []
    if len(tool_calls) != 1:
        raise ProbeFailure(f"Strict tool-call probe returned {len(tool_calls)} calls; expected 1.")
    function = getattr(tool_calls[0], "function", None)
    function_name = getattr(function, "name", None)
    arguments_raw = getattr(function, "arguments", "")
    try:
        arguments = json.loads(arguments_raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProbeFailure("Strict tool-call arguments were not valid JSON.") from exc
    if function_name != "record_probe" or arguments != {"status": "ok"}:
        raise ProbeFailure("Strict tool-call output did not match the required schema.")
    tool_content = get_text_content(tool_message)
    results["probes"]["strict_tool_call"] = {
        "ok": True,
        "tool_name": function_name,
        "empty_content_with_tool_call_supported": not bool(tool_content.strip()),
        **completion_metadata(tool_response),
    }

    structured_messages = [
        {
            "role": "system",
            "content": "Return valid JSON only. The JSON schema is: "
            '{"status":"ok","capability":"structured_output"}.',
        },
        {"role": "user", "content": "Return the requested JSON object."},
    ]
    json_response = client.chat.completions.create(
        model=config.model,
        messages=structured_messages,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
        temperature=0,
        max_tokens=128,
    )
    json_message = json_response.choices[0].message
    empty_content_retry_used = False
    json_content = get_text_content(json_message)
    if not json_content.strip():
        empty_content_retry_used = True
        json_response = client.chat.completions.create(
            model=config.model,
            messages=structured_messages
            + [
                {
                    "role": "user",
                    "content": "The previous content was empty. Return the JSON object now.",
                }
            ],
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
            temperature=0,
            max_tokens=128,
        )
        json_message = json_response.choices[0].message
        json_content = get_text_content(json_message)
    try:
        structured = json.loads(json_content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProbeFailure("Structured-output probe returned invalid or empty JSON content.") from exc
    expected = {"status": "ok", "capability": "structured_output"}
    if structured != expected:
        raise ProbeFailure("Structured-output probe returned JSON that failed the expected schema.")
    results["probes"]["structured_output"] = {
        "ok": True,
        "schema_valid": True,
        "empty_content_retry_used": empty_content_retry_used,
        **completion_metadata(json_response),
    }

    return results


def main() -> int:
    try:
        results = run_probe()
    except Exception as exc:  # noqa: BLE001 - probe must fail closed with redacted diagnostics.
        secret = os.getenv("MODEL_API_KEY", "")
        message = redact(str(exc), [secret])
        print(f"DEEPSEEK_MODEL_PROBE_FAILED: {type(exc).__name__}: {message}", file=sys.stderr)
        return 1

    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    print("DEEPSEEK_MODEL_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
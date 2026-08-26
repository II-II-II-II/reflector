"""
Swappable chat backends: local Ollama, AWS Bedrock, or Anthropic direct.
Selected via config.yaml. All three implement the same chat(messages)
interface so the rest of the app never needs to know which is active.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: list[dict] = field(default_factory=list)


class Provider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict] | None = None, tool_executor: dict | None = None) -> ChatResult:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]
        tools/tool_executor: optional Bedrock-style tool specs + {name: callable}
        for providers that support tool use. Not all providers implement this yet."""


def _bedrock_tool_to_ollama(spec: dict) -> dict:
    """Tool specs are defined once in Bedrock's shape (memory_search.py) —
    Ollama's function-calling format is structurally different, so convert
    rather than maintain two copies of the same schema."""
    tool_spec = spec["toolSpec"]
    return {
        "type": "function",
        "function": {
            "name": tool_spec["name"],
            "description": tool_spec["description"],
            "parameters": tool_spec["inputSchema"]["json"],
        },
    }


class OllamaProvider(Provider):
    MAX_TOOL_ITERATIONS = 5

    def __init__(self, model: str, host: str, num_ctx: int):
        import ollama

        self._ollama = ollama
        self._client = ollama.Client(host=host)
        self.model = model
        self.num_ctx = num_ctx

    def chat(self, messages: list[dict], tools: list[dict] | None = None, tool_executor: dict | None = None) -> ChatResult:
        ollama_tools = [_bedrock_tool_to_ollama(t) for t in tools] if tools else None
        conversation = list(messages)
        total_input = 0
        total_output = 0
        tool_call_log = []

        for _ in range(self.MAX_TOOL_ITERATIONS):
            kwargs = {"model": self.model, "messages": conversation, "options": {"num_ctx": self.num_ctx}}
            if ollama_tools:
                kwargs["tools"] = ollama_tools
            response = self._client.chat(**kwargs)
            total_input += getattr(response, "prompt_eval_count", None) or 0
            total_output += getattr(response, "eval_count", None) or 0

            if not response.message.tool_calls:
                return ChatResult(text=response.message.content, input_tokens=total_input, output_tokens=total_output, tool_calls=tool_call_log)

            conversation.append(response.message)
            for tool_call in response.message.tool_calls:
                fn = (tool_executor or {}).get(tool_call.function.name)
                try:
                    result_text = (
                        fn(**tool_call.function.arguments) if fn
                        else f"Error: unknown tool '{tool_call.function.name}'"
                    )
                except Exception as e:
                    result_text = f"Error running tool '{tool_call.function.name}': {type(e).__name__}: {e}"
                tool_call_log.append({"tool": tool_call.function.name, "args": tool_call.function.arguments, "result": result_text})
                conversation.append({"role": "tool", "content": result_text, "tool_name": tool_call.function.name})

        return ChatResult(
            text="(Reached the tool-call limit for this turn without a final answer — try rephrasing.)",
            input_tokens=total_input,
            output_tokens=total_output,
            tool_calls=tool_call_log,
        )


class BedrockProvider(Provider):
    def __init__(self, model_id: str, region: str, profile: str | None = None):
        try:
            import boto3
        except ImportError as e:
            raise RuntimeError(
                "Bedrock provider selected but boto3 isn't installed. Run: pip install boto3"
            ) from e
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self._client = session.client("bedrock-runtime", region_name=region)
        self.model_id = model_id

    MAX_TOOL_ITERATIONS = 5  # safety cap against a runaway tool-calling loop

    def chat(self, messages: list[dict], tools: list[dict] | None = None, tool_executor: dict | None = None) -> ChatResult:
        system = [m["content"] for m in messages if m["role"] == "system"]
        conversation = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        kwargs = {"modelId": self.model_id, "messages": conversation}
        if system:
            kwargs["system"] = [{"text": s} for s in system]
        if tools:
            kwargs["toolConfig"] = {"tools": tools}

        total_input = 0
        total_output = 0
        tool_call_log = []

        for _ in range(self.MAX_TOOL_ITERATIONS):
            response = self._client.converse(**kwargs)
            usage = response.get("usage", {})
            total_input += usage.get("inputTokens", 0) or 0
            total_output += usage.get("outputTokens", 0) or 0

            if response["stopReason"] != "tool_use":
                text = next(
                    (b["text"] for b in response["output"]["message"]["content"] if "text" in b), ""
                )
                return ChatResult(text=text, input_tokens=total_input, output_tokens=total_output, tool_calls=tool_call_log)

            assistant_message = response["output"]["message"]
            conversation.append(assistant_message)

            tool_result_blocks = []
            for block in assistant_message["content"]:
                if "toolUse" not in block:
                    continue
                tool_use = block["toolUse"]
                fn = (tool_executor or {}).get(tool_use["name"])
                try:
                    result_text = fn(**tool_use["input"]) if fn else f"Error: unknown tool '{tool_use['name']}'"
                except Exception as e:
                    result_text = f"Error running tool '{tool_use['name']}': {type(e).__name__}: {e}"
                tool_call_log.append({"tool": tool_use["name"], "args": tool_use["input"], "result": result_text})
                tool_result_blocks.append({
                    "toolResult": {"toolUseId": tool_use["toolUseId"], "content": [{"text": result_text}]}
                })
            conversation.append({"role": "user", "content": tool_result_blocks})
            kwargs["messages"] = conversation

        return ChatResult(
            text="(Reached the tool-call limit for this turn without a final answer — try rephrasing.)",
            input_tokens=total_input,
            output_tokens=total_output,
            tool_calls=tool_call_log,
        )


class AnthropicProvider(Provider):
    def __init__(self, model: str, api_key_env: str):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "Anthropic provider selected but the anthropic package isn't installed. "
                "Run: pip install anthropic"
            ) from e
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Anthropic provider selected but ${api_key_env} is not set in the environment."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict] | None = None, tool_executor: dict | None = None) -> ChatResult:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        conversation = [m for m in messages if m["role"] != "system"]
        response = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system or None,
            messages=conversation,
        )
        return ChatResult(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


def get_provider(config: dict) -> Provider:
    llm_config = config["llm"]
    provider_name = llm_config["provider"]

    if provider_name == "ollama":
        c = llm_config["ollama"]
        return OllamaProvider(model=c["model"], host=c["host"], num_ctx=c["num_ctx"])
    if provider_name == "bedrock":
        c = llm_config["bedrock"]
        return BedrockProvider(model_id=c["model_id"], region=c["region"], profile=c.get("profile"))
    if provider_name == "anthropic":
        c = llm_config["anthropic"]
        return AnthropicProvider(model=c["model"], api_key_env=c["api_key_env"])

    raise ValueError(f"Unknown provider in config.yaml: {provider_name!r}")

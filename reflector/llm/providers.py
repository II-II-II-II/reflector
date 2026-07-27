"""
Swappable chat backends: local Ollama, AWS Bedrock, or Anthropic direct.
Selected via config.yaml. All three implement the same chat(messages)
interface so the rest of the app never needs to know which is active.
"""

import os
from abc import ABC, abstractmethod


class Provider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]"""


class OllamaProvider(Provider):
    def __init__(self, model: str, host: str, num_ctx: int):
        import ollama

        self._ollama = ollama
        self._client = ollama.Client(host=host)
        self.model = model
        self.num_ctx = num_ctx

    def chat(self, messages: list[dict]) -> str:
        response = self._client.chat(
            model=self.model,
            messages=messages,
            options={"num_ctx": self.num_ctx},
        )
        return response.message.content


class BedrockProvider(Provider):
    def __init__(self, model_id: str, region: str):
        try:
            import boto3
        except ImportError as e:
            raise RuntimeError(
                "Bedrock provider selected but boto3 isn't installed. Run: pip install boto3"
            ) from e
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self.model_id = model_id

    def chat(self, messages: list[dict]) -> str:
        system = [m["content"] for m in messages if m["role"] == "system"]
        conversation = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        kwargs = {"modelId": self.model_id, "messages": conversation}
        if system:
            kwargs["system"] = [{"text": s} for s in system]
        response = self._client.converse(**kwargs)
        return response["output"]["message"]["content"][0]["text"]


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

    def chat(self, messages: list[dict]) -> str:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        conversation = [m for m in messages if m["role"] != "system"]
        response = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system or None,
            messages=conversation,
        )
        return response.content[0].text


def get_provider(config: dict) -> Provider:
    llm_config = config["llm"]
    provider_name = llm_config["provider"]

    if provider_name == "ollama":
        c = llm_config["ollama"]
        return OllamaProvider(model=c["model"], host=c["host"], num_ctx=c["num_ctx"])
    if provider_name == "bedrock":
        c = llm_config["bedrock"]
        return BedrockProvider(model_id=c["model_id"], region=c["region"])
    if provider_name == "anthropic":
        c = llm_config["anthropic"]
        return AnthropicProvider(model=c["model"], api_key_env=c["api_key_env"])

    raise ValueError(f"Unknown provider in config.yaml: {provider_name!r}")

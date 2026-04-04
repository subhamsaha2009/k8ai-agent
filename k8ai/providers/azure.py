"""
Azure OpenAI Provider Adapter
Env vars needed:
  AI_PROVIDER=azure
  AI_ENDPOINT    → https://<resource>.openai.azure.com/
  AI_API_KEY     → your Azure OpenAI key
  AI_MODEL       → deployment name (e.g. gpt-4o)
  AI_API_VERSION → e.g. 2024-10-21
"""

import os
import json
from openai import AzureOpenAI
from k8ai.providers.base import BaseProvider, ToolCall


class AzureOpenAIProvider(BaseProvider):

    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=os.getenv("AI_ENDPOINT"),
            api_key=os.getenv("AI_API_KEY"),
            api_version=os.getenv("AI_API_VERSION", "2024-10-21"),
        )
        self.deployment = os.getenv("AI_MODEL", "gpt-4o")

    def get_model_name(self) -> str:
        return f"Azure AI Foundry ({self.deployment})"

    def chat(self, messages: list, tools: list):
        return self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

    def get_content(self, response) -> str | None:
        return response.choices[0].message.content

    def get_tool_calls(self, response) -> list[ToolCall]:
        raw = response.choices[0].message.tool_calls or []
        return [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments),
            )
            for tc in raw
        ]

    def build_assistant_message(self, response) -> dict:
        # OpenAI SDK message object can be appended directly
        return response.choices[0].message

    def build_tool_result(self, tool_call: ToolCall, result: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        }

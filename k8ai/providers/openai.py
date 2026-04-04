"""
OpenAI Direct Provider Adapter

Env vars needed:
  AI_PROVIDER=openai
  AI_API_KEY  → sk-...
  AI_MODEL    → model name (optional, defaults to gpt-4o)

Supported models:
  gpt-4o
  gpt-4o-mini
  gpt-4-turbo
"""

import os
import json
from openai import OpenAI
from k8ai.providers.base import BaseProvider, ToolCall


class OpenAIProvider(BaseProvider):

    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("AI_API_KEY"),
        )
        self.model = os.getenv("AI_MODEL", "gpt-4o")

    def get_model_name(self) -> str:
        return f"OpenAI ({self.model})"

    def chat(self, messages: list, tools: list):
        return self.client.chat.completions.create(
            model=self.model,
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
        return response.choices[0].message

    def build_tool_result(self, tool_call: ToolCall, result: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        }

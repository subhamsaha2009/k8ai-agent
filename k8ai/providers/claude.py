"""
Anthropic Claude Provider Adapter

Env vars needed:
  AI_PROVIDER=claude
  AI_API_KEY  → sk-ant-...
  AI_MODEL    → model name (optional, defaults to claude-opus-4-6)

Supported models:
  claude-opus-4-6
  claude-sonnet-4-6
  claude-haiku-4-5-20251001

Key differences from OpenAI format that this adapter handles:
  1. Tool results go as role="user" with type="tool_result" (not role="tool")
  2. Response content is a list of blocks, not a single message
  3. System prompt is a separate param, not a message in the list
  4. Tool call IDs use field "id" inside content blocks (not tool_calls[].id)
  5. tool_choice format is {"type": "auto"} not just "auto"
"""

import os
import json
import anthropic
from k8ai.providers.base import BaseProvider, ToolCall


class ClaudeProvider(BaseProvider):

    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("AI_API_KEY"),
        )
        self.model = os.getenv("AI_MODEL", "claude-opus-4-6")

    def get_model_name(self) -> str:
        return f"Anthropic Claude ({self.model})"

    def _convert_tools(self, tools: list) -> list:
        """
        Convert OpenAI function calling format to Anthropic tool format.

        OpenAI format:
          {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

        Anthropic format:
          {"name": ..., "description": ..., "input_schema": ...}
        """
        converted = []
        for tool in tools:
            fn = tool["function"]
            converted.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    def _extract_system(self, messages: list) -> tuple[str, list]:
        """
        Claude requires system prompt as a separate parameter.
        Extract it from messages list and return (system_prompt, remaining_messages).
        """
        system = ""
        remaining = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content", "")
            else:
                remaining.append(msg)
        return system, remaining

    def chat(self, messages: list, tools: list):
        system, user_messages = self._extract_system(messages)
        claude_tools = self._convert_tools(tools)

        return self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=user_messages,
            tools=claude_tools,
            tool_choice={"type": "auto"},
        )

    def get_content(self, response) -> str | None:
        """Extract text content from response if present."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return None

    def get_tool_calls(self, response) -> list[ToolCall]:
        """Extract tool_use blocks from Claude response content."""
        return [
            ToolCall(
                id=block.id,
                name=block.name,
                arguments=block.input,  # already a dict in Claude
            )
            for block in response.content
            if block.type == "tool_use"
        ]

    def build_assistant_message(self, response) -> dict:
        """
        Convert Claude response to a message dict for conversation history.
        Claude content is a list of blocks.
        """
        return {
            "role": "assistant",
            "content": response.content,  # list of text/tool_use blocks
        }

    def build_tool_result(self, tool_call: ToolCall, result: str) -> dict:
        """
        Claude tool results must be sent as role="user" with type="tool_result".
        This is the biggest difference from OpenAI format.

        OpenAI: {"role": "tool", "tool_call_id": ..., "content": ...}
        Claude: {"role": "user", "content": [{"type": "tool_result", "tool_use_id": ..., "content": ...}]}
        """
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result,
                }
            ],
        }

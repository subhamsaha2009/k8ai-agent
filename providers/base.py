"""
BaseProvider — the common interface every provider adapter must implement.

agent.py only calls these 3 methods:
  - chat()          → send messages + tools, get response
  - get_tool_calls()→ extract tool calls from response
  - build_tool_result() → format tool result to send back

Every provider translates these into their own SDK format internally.
agent.py never knows which model it is talking to.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    """Unified tool call object — same structure regardless of provider."""
    id: str           # unique ID for this tool call
    name: str         # function name to call
    arguments: dict   # parsed arguments dict


class BaseProvider(ABC):

    @abstractmethod
    def get_model_name(self) -> str:
        """Return display name for welcome screen."""
        pass

    @abstractmethod
    def chat(self, messages: list, tools: list) -> Any:
        """
        Send messages + tools to the model and return the raw response.
        messages: list of dicts in provider-specific format
        tools: list from tools_schema.py (OpenAI function format)
        """
        pass

    @abstractmethod
    def get_content(self, response: Any) -> str | None:
        """Extract the text content from a response (if any)."""
        pass

    @abstractmethod
    def get_tool_calls(self, response: Any) -> list[ToolCall]:
        """Extract list of ToolCall objects from a response."""
        pass

    @abstractmethod
    def build_assistant_message(self, response: Any) -> dict:
        """
        Convert the raw response into a message dict to append
        to the conversation history.
        """
        pass

    @abstractmethod
    def build_tool_result(self, tool_call: ToolCall, result: str) -> dict:
        """
        Format a tool result to append to conversation history.
        Each provider expects a different format for tool results.
        """
        pass

    def has_tool_calls(self, response: Any) -> bool:
        """Return True if response contains tool calls."""
        return len(self.get_tool_calls(response)) > 0

from typing import AsyncIterator, Protocol, Callable, Awaitable

ToolHandler = Callable[[str, dict], Awaitable[dict]]


class ProviderUnavailable(Exception):
    """A sanitized, user-facing provider failure; never contains credentials."""


class IntelligenceProvider(Protocol):
    def register_tools(self, specs: list) -> None: ...
    async def generate(self, text: str, handle_tool_call: ToolHandler) -> str: ...
    def stream(self, text: str, handle_tool_call: ToolHandler) -> AsyncIterator[str]: ...


class SpeechInput(Protocol):
    async def send_audio(self, pcm: bytes, sample_rate: int = 16000) -> None: ...
    async def activity(self, started: bool) -> None: ...


class SpeechOutput(Protocol):
    async def interrupt(self) -> None: ...
    # Audio events contain PCM bytes plus sample_rate, and retain a transcript.
    def events(self) -> AsyncIterator[dict]: ...


class LiveSession(SpeechInput, SpeechOutput, Protocol):
    async def check_health(self) -> None: ...
    async def send_text(self, text: str) -> None: ...
    async def send_tool_result(self, call_id: str, name: str, result: dict) -> None: ...


class LiveProvider(Protocol):
    def start_live_session(self): ...  # async context manager yielding LiveSession


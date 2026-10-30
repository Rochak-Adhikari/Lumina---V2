"""Platform-neutral tool declarations shared by local and cloud composition."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    permission: str = "L0"
    risk: str = "read-only"
    timeout: float = 8
    cancellation: str = "cooperative scan cancellation; cancelled results are never committed"
    idempotent: bool = True

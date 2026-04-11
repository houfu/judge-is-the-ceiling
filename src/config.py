import os
from dataclasses import dataclass


@dataclass
class Config:
    model: str = "qwen2.5:32b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    temperature: float = 0.0
    num_iterations: int = 5
    num_ctx: int = 16384

    @classmethod
    def from_env(cls) -> "Config":
        def _float(key: str, default: float) -> float:
            raw = os.getenv(key)
            if raw is None:
                return default
            try:
                return float(raw)
            except ValueError as exc:
                raise ValueError(f"Invalid {key}={raw!r}; expected float") from exc

        def _int(key: str, default: int) -> int:
            raw = os.getenv(key)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise ValueError(f"Invalid {key}={raw!r}; expected int") from exc

        return cls(
            model=os.getenv("MODEL", "qwen2.5:32b"),
            base_url=os.getenv("BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("API_KEY", "ollama"),
            temperature=_float("TEMPERATURE", 0.0),
            num_iterations=_int("NUM_ITERATIONS", 5),
            num_ctx=_int("NUM_CTX", 16384),
        )


config = Config.from_env()

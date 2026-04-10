import os
from dataclasses import dataclass


@dataclass
class Config:
    model: str = os.getenv("MODEL", "qwen2.5:32b")
    base_url: str = os.getenv("BASE_URL", "http://localhost:11434/v1")
    api_key: str = os.getenv("API_KEY", "ollama")
    temperature: float = float(os.getenv("TEMPERATURE", "0"))
    num_iterations: int = int(os.getenv("NUM_ITERATIONS", "5"))


config = Config()

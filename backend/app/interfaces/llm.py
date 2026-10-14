from typing import Protocol

from app.domain.models import Generation, InferenceConfig


class LLMProvider(Protocol):
    def generate_response(
        self, system: str, user_message: str, context: str, config: InferenceConfig
    ) -> Generation: ...

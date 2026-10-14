from app.domain.models import Generation, InferenceConfig


class OCILLMProvider:
    def generate_response(
        self, system: str, user_message: str, context: str, config: InferenceConfig
    ) -> Generation:
        raise NotImplementedError("Implement OCI Generative AI inference and normalize Generation.")

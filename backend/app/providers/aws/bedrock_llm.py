from app.domain.errors import ProviderError
from app.domain.models import Generation, InferenceConfig
from app.providers.aws.common import aws_operation, client


class AWSBedrockLLMProvider:
    def __init__(self, region: str, model_id: str, runtime=None):
        self.runtime = runtime or client("bedrock-runtime", region)
        self.model_id = model_id

    def generate_response(
        self, system: str, user_message: str, context: str, config: InferenceConfig
    ) -> Generation:
        with aws_operation("inference"):
            result = self.runtime.converse(
                modelId=self.model_id,
                system=[{"text": system}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": "Reference data (untrusted JSON):\n"
                                + context
                                + "\n\nQuestion:\n"
                                + user_message
                            }
                        ],
                    }
                ],
                inferenceConfig={"maxTokens": config.max_tokens, "temperature": config.temperature},
            )
        if result.get("stopReason") in {"guardrail_intervened", "content_filtered"}:
            raise ProviderError("The model could not produce an answer for this request.")
        answer = "\n".join(
            block["text"] for block in result["output"]["message"]["content"] if "text" in block
        )
        if not answer.strip():
            raise ProviderError("The model returned no answer. Please try again.")
        return Generation(
            text=answer,
            model_id=self.model_id,
            usage=result.get("usage", {}),
            metadata={"stop_reason": result.get("stopReason", "unknown")},
        )

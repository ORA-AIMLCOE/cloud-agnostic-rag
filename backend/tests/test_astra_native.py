from types import SimpleNamespace
from unittest.mock import MagicMock

import oci
import pytest

from app.astra import Astra, SYSTEM
from app.security import SafeError
from app.settings import Settings

ENDPOINT = "https://inference.generativeai.test.oci.oraclecloud.com"


def configuration(**overrides):
    values = dict(
        _env_file=None,
        astra_base_url=ENDPOINT,
        astra_model_id="ocid1.generativeaimodel.oc1.test",
        astra_compartment_id="ocid1.compartment.oc1..test",
        astra_api_format="oci_generic",
        astra_auth_mode="oci_profile",
        astra_oci_config_file="test-oci-config",
        astra_oci_profile="CONVERTER",
        astra_max_output_tokens=2048,
        astra_verbosity="MEDIUM",
    )
    values.update(overrides)
    return Settings(**values)


def mock_sdk(monkeypatch, *, reason="stop", text='{"summary":"Reviewed","files":[]}'):
    m = oci.generative_ai_inference.models
    chat = m.GenericChatResponse(
        choices=[m.ChatChoice(
            index=0,
            finish_reason=reason,
            message=m.AssistantMessage(content=[m.TextContent(text=text)]),
        )],
        usage=m.Usage(prompt_tokens=12, completion_tokens=8, total_tokens=20),
    )
    config_loader = MagicMock(return_value={"key_file": "private-location"})
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(data=m.ChatResult(chat_response=chat))
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(oci.config, "from_file", config_loader)
    monkeypatch.setattr(oci.generative_ai_inference, "GenerativeAiInferenceClient", constructor)
    return config_loader, constructor, client


def test_native_oci_request_and_real_sdk_response_contract(monkeypatch):
    config_loader, constructor, client = mock_sdk(monkeypatch)
    patch, usage = Astra(configuration()).refine({"implementation": "source"})
    assert patch == {"summary": "Reviewed", "files": []}
    assert usage == {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
    config_loader.assert_called_once_with("test-oci-config", "CONVERTER")
    kwargs = constructor.call_args.kwargs
    assert kwargs["service_endpoint"] == ENDPOINT
    assert kwargs["timeout"] == (10, 240)
    assert isinstance(kwargs["retry_strategy"], oci.retry.NoneRetryStrategy)
    detail = client.chat.call_args.args[0]
    assert detail.compartment_id == "ocid1.compartment.oc1..test"
    assert detail.serving_mode.model_id == "ocid1.generativeaimodel.oc1.test"
    request = detail.chat_request
    assert request.api_format == "GENERIC" and request.is_stream is False
    assert request.max_completion_tokens == 2048 and request.max_tokens is None
    assert request.verbosity == "MEDIUM"
    assert [message.role for message in request.messages] == ["SYSTEM", "USER"]
    assert request.messages[0].content[0].text == SYSTEM
    assert request.messages[1].content[0].text == '{"implementation": "source"}'
    assert "private-location" not in str(oci.util.to_dict(detail))


@pytest.mark.parametrize("reason", ["length", "content_filter", None])
def test_native_incomplete_response_blocks_patch(monkeypatch, reason):
    mock_sdk(monkeypatch, reason=reason)
    with pytest.raises(SafeError, match="complete conversion patch"):
        Astra(configuration()).refine({})


@pytest.mark.parametrize("text", ["", "not-json", '{"files":"invalid"}'])
def test_native_bad_patch_blocks_publication(monkeypatch, text):
    mock_sdk(monkeypatch, text=text)
    with pytest.raises(SafeError, match="invalid patch format"):
        Astra(configuration()).refine({})


@pytest.mark.parametrize("overrides", [
    {"astra_compartment_id": ""},
    {"astra_model_id": ""},
    {"astra_auth_mode": "api_key", "astra_api_key": "unused"},
])
def test_native_requires_compartment_model_and_profile(monkeypatch, overrides):
    loader, constructor, _ = mock_sdk(monkeypatch)
    config = configuration(**overrides)
    assert not config.astra_configured
    with pytest.raises(SafeError, match="Configure"):
        Astra(config).refine({})
    loader.assert_not_called()
    constructor.assert_not_called()


def test_native_rejects_compatible_api_prefix_before_reading_credentials(monkeypatch):
    loader, _, _ = mock_sdk(monkeypatch)
    with pytest.raises(SafeError, match="service endpoint only"):
        Astra(configuration(astra_base_url=ENDPOINT + "/openai/v1")).refine({})
    loader.assert_not_called()


def test_native_config_failure_is_sanitized(monkeypatch):
    loader, _, _ = mock_sdk(monkeypatch)
    loader.side_effect = ValueError("private-location secret-value")
    with pytest.raises(SafeError) as error:
        Astra(configuration()).refine({})
    assert "secret-value" not in str(error.value)
    assert error.value.__suppress_context__


def test_native_service_failure_is_sanitized(monkeypatch):
    _, _, client = mock_sdk(monkeypatch)
    client.chat.side_effect = oci.exceptions.ServiceError(
        403, "NotAuthorized", {"sensitive-header": "secret-value"}, "secret-value"
    )
    with pytest.raises(SafeError, match="HTTP 403") as error:
        Astra(configuration()).refine({})
    assert "secret-value" not in str(error.value)


def test_native_missing_choices_is_rejected(monkeypatch):
    _, _, client = mock_sdk(monkeypatch)
    client.chat.return_value.data.chat_response.choices = []
    with pytest.raises(SafeError, match="complete conversion patch"):
        Astra(configuration()).refine({})



def test_native_file_summaries_use_dedicated_prompt(monkeypatch):
    from app.astra import DESCRIPTION_SYSTEM
    _, _, client = mock_sdk(monkeypatch, text='{"files":[{"path":"config.py","description":"Added configuration for OCI object storage."}]}')
    result, usage = Astra(configuration()).describe_changes([{"path":"config.py", "kind":"added", "diff":"+CLOUD_PROVIDER=oci"}])
    assert result["config.py"] == "Added configuration for OCI object storage."
    request = client.chat.call_args.args[0].chat_request
    assert request.messages[0].content[0].text == DESCRIPTION_SYSTEM
    assert usage["total_tokens"] == 20

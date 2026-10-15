
import httpx
import pytest

from app.github import GitHub
from app.security import SafeError


@pytest.mark.parametrize("status,headers,expected", [
    (401, {}, "unexpired"),
    (403, {"x-accepted-github-permissions": "contents=read"}, "Contents to Read and write"),
    (403, {"x-accepted-github-permissions": "contents=write", "x-ratelimit-remaining": "0"}, "rate limit"),
    (403, {"x-accepted-github-permissions": "contents=read", "x-github-sso": "required"}, "SSO"),
    (404, {}, "source branch"),
    (429, {}, "rate limit"),
])
def test_github_failure_guidance_never_echoes_response_secrets(status, headers, expected):
    def handler(request):
        return httpx.Response(status, headers=headers, json={"message": "sensitive-token"})
    client = GitHub("https://github.com/owner/repo", "sensitive-token", httpx.MockTransport(handler))
    try:
        with pytest.raises(SafeError, match=expected) as exc:
            client.snapshot("main")
        assert "sensitive-token" not in str(exc.value)
    finally:
        client.close()


def test_connection_timeout_has_actionable_message():
    def handler(request):
        raise httpx.ConnectTimeout("sensitive proxy details", request=request)
    client = GitHub("https://github.com/owner/repo", "token", httpx.MockTransport(handler))
    try:
        with pytest.raises(SafeError, match="timed out") as exc:
            client.snapshot("main")
        assert "sensitive" not in str(exc.value)
    finally:
        client.close()

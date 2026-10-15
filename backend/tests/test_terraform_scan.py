
import pytest

from app.security import SafeError, check_source_secrets, has_secret


@pytest.mark.parametrize("flag", ["true", "false"])
def test_terraform_password_management_flag_is_not_a_credential(flag):
    source = 'resource "aws_db_instance" "rag" {\r\n  manage_master_user_password = ' + flag + '\r\n}\r\n'
    assert not has_secret(source)
    check_source_secrets({"infrastructure/aws/main.tf": source})


@pytest.mark.parametrize("source", [
    "manage_master_user_password = true\nAWS_SECRET_ACCESS_KEY=literal-credential",
    "manage_master_user_password = false\npassword=literal-credential",
    'manage_master_user_password = "literal-credential"',
    "manage_master_user_password = true-with-secret-suffix",
    "password=true",
])
def test_boolean_exception_does_not_hide_credentials(source):
    assert has_secret(source)
    with pytest.raises(SafeError, match="Possible committed credentials"):
        check_source_secrets({"infrastructure/aws/main.tf": source})

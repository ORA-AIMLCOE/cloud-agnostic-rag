import ast
import json

from app.security import SafeError
from app.settings import ROOT
from app.validation import EDITABLE

RECIPE = ROOT / "migration_recipes" / "aws_rag_v1"
PROTECTED = (
    "frontend/",
    "backend/app/api/",
    "backend/app/domain/",
    "backend/app/interfaces/",
    "backend/app/services/",
    "backend/app/workflows/",
    "backend/app/repositories/",
    "backend/app/database/",
    "backend/alembic/",
)
REQUIRED = [
    "backend/app/providers/factory.py",
    "backend/app/core/config.py",
    "backend/app/core/dependencies.py",
    "backend/app/services/pdf_text.py",
    "backend/app/interfaces/llm.py",
    "backend/app/interfaces/storage.py",
    "backend/app/interfaces/ingestion.py",
    "backend/app/interfaces/vector_search.py",
    "backend/app/database/models.py",
    "backend/app/repositories/sqlalchemy_repository.py",
    "backend/tests/test_contracts.py",
    "backend/requirements.lock.txt",
    "frontend/package.json",
    "frontend/package-lock.json",
]


def inspect_source(files):
    missing = [name for name in REQUIRED if name not in files]
    if missing:
        raise SafeError(
            "This repository does not match the supported aws_rag recipe. Missing: " + ", ".join(missing[:5])
        )
    factory = files["backend/app/providers/factory.py"].decode()
    if 'if settings.cloud_provider == "oci":' not in factory or "extension points" not in factory:
        raise SafeError(
            "OCI factory scaffolding differs from the supported baseline. Update the recipe before converting."
        )
    package = json.loads(files["frontend/package.json"])
    if "react" not in package.get("dependencies", {}):
        raise SafeError("Unsupported frontend structure.")
    return {
        "recipe": "aws_rag_v1",
        "components": [
            "S3 object storage",
            "Bedrock generation",
            "Bedrock knowledge base",
            "PostgreSQL history",
        ],
        "protected_files": sum(p.startswith(PROTECTED) for p in files),
        "source_files": len(files),
    }


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise SafeError(
            "Source wiring differs from the supported recipe. No broad rewrite will be attempted."
        )
    return text.replace(before, after, 1)


def generate_recipe(files):
    inspect_source(files)
    changes = {
        p.relative_to(RECIPE / "templates").as_posix(): p.read_text(encoding="utf-8")
        for p in (RECIPE / "templates").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    path = "backend/app/providers/factory.py"
    text = files[path].decode().replace("\r\n", "\n")
    before = """        raise NotImplementedError(
            "OCI adapters are extension points. Implement and contract-test them before enabling OCI."
        )"""
    changes[path] = replace_once(
        text,
        before,
        "        from app.providers.oci.factory import create_oci_providers\n\n        return create_oci_providers()",
    )
    path = "backend/app/core/config.py"
    text = files[path].decode().replace("\r\n", "\n")
    changes[path] = replace_once(
        text,
        '    aws_s3_prefix: str = "documents/"',
        '    object_storage_prefix: str = "documents/"\n    aws_s3_prefix: str = "documents/"',
    )
    changes[path] = replace_once(
        changes[path],
        "    def safe_prefix(self):",
        """    def safe_prefix(self):
        self.object_storage_prefix = self.object_storage_prefix.strip("/") + "/"
        if self.object_storage_prefix == "/" or ".." in self.object_storage_prefix:
            raise ValueError("Use a nonempty dedicated object prefix without '..'.")""",
    )
    path = "backend/app/core/dependencies.py"
    changes[path] = replace_once(
        files[path].decode().replace("\r\n", "\n"),
        "        settings.aws_s3_prefix,",
        '        settings.object_storage_prefix if settings.cloud_provider == "oci" else settings.aws_s3_prefix,',
    )
    changes[path] = replace_once(
        changes[path],
        "        engine, sessions = create_database(settings.database_url)\n        repository = SQLAlchemyRepository(sessions)",
        """        if settings.cloud_provider == "oci":
            from app.providers.oci.database import create_oracle_repository
            engine, repository = create_oracle_repository()
        else:
            engine, sessions = create_database(settings.database_url)
            repository = SQLAlchemyRepository(sessions)""",
    )
    # Oracle persistence is an infrastructure adapter. Source models/repository/migrations stay intact.
    models = files["backend/app/database/models.py"].decode().replace("\r\n", "\n")
    models = models.replace("from sqlalchemy.orm import", "from sqlalchemy.dialects.oracle import TIMESTAMP\nfrom app.providers.oci.database_types import JSONText, EmptyText\nfrom sqlalchemy.orm import")
    models = replace_once(models, "mapped_column(JSON)", "mapped_column(JSONText())")
    models = replace_once(models, "status_message: Mapped[str] = mapped_column(Text)",
                          "status_message: Mapped[str] = mapped_column(EmptyText(), nullable=True)")
    models = models.replace("DateTime(timezone=True)", "TIMESTAMP(timezone=True)")
    models = models.replace(', ondelete="RESTRICT"', "")
    changes["backend/app/providers/oci/database_models.py"] = models
    repository = files["backend/app/repositories/sqlalchemy_repository.py"].decode().replace("\r\n", "\n")
    repository = repository.replace("from app.database.models import", "from app.providers.oci.database_models import")
    repository = repository.replace("class SQLAlchemyRepository:", "class OracleRepository:")
    repository = repository.replace('text("SELECT 1")', 'text("SELECT 1 FROM dual")')
    repository = repository.replace("PostgreSQL SELECT FOR UPDATE", "Oracle SELECT FOR UPDATE")
    changes["backend/app/providers/oci/repository.py"] = repository
    path = "backend/tests/test_contracts.py"
    changes[path] = replace_once(
        files[path].decode().replace("\r\n", "\n"),
        'pytest.raises(NotImplementedError, match="extension points")',
        "pytest.raises(ValueError)",
    )
    # Only the former unimplemented-provider expectation changes; all AWS behavior tests remain.
    changes["backend/requirements-oci.lock.txt"] = (RECIPE / "oci-dependencies.lock.txt").read_text()
    changes[".env.oci.example"] = env_text({}, placeholders=True)
    changes[".gitignore"] = (
        files.get(".gitignore", b"").decode() + "\n# OCI runtime credentials\n.env\nconfig/oci/\n*.pem\nconfig/wallet/\nWallet*.zip\n*.p12\n*.sso\n"
    )
    changes["docs/conversion-report.md"] = (
        "# OCI conversion\n\nRecipe: aws_rag_v1. Core RAG files are preserved.\nSee docs/oci-generated.md for setup and limitations. No deployment or live-cloud verification was performed.\n"
    )
    return {
        path: (
            content.replace("\r\n", "\n").replace("\n", "\r\n")
            if b"\r\n" in files.get(path, b"")
            else content
        )
        for path, content in changes.items()
    }


def model_context(files, changes, target, failure=""):
    # Actual resource IDs, endpoints, credentials, and environment files are excluded.
    sources = {
        p: b.decode()
        for p, b in files.items()
        if p.startswith("backend/app/interfaces/") or p == "backend/app/domain/models.py"
    }
    return {
        "task": "Review and minimally adapt the OCI recipe for this project's provider contracts.",
        "source_interfaces": sources,
        "allowed_files": sorted(EDITABLE),
        "implementation": {p: s for p, s in changes.items() if p.startswith("backend/app/providers/oci/")},
        "target_capabilities": {
            k: target[k]
            for k in (
                "llm_format",
                "llm_serving_mode",
                "embedding_serving_mode",
                "embedding_dimensions",
                "chunk_chars",
                "chunk_overlap",
            )
        },
        "database_contract": "Oracle Autonomous AI Database with native VECTOR(*, FLOAT32), python-oracledb 26.0.1 Thin mode, array(f) vector binds and cosine VECTOR_DISTANCE. No pgvector or PostgreSQL SQL. Metadata and vectors share one application schema. Preserve row-lock retry serialization and index/owner/document filters. Schema and database adapters are deterministic and outside the editable model scope.",
        "sdk_contract": "OCI Python 2.188: native EmbedTextDetails inputs, serving_mode, compartment_id, input_type SEARCH_DOCUMENT/SEARCH_QUERY, output_dimensions optional; data.embeddings. Native chat uses GENERIC or COHERE request and data.chat_response. The generic_astra preset uses GenericChatRequest with max_completion_tokens and verbosity MEDIUM, omitting max_tokens and temperature; generic preserves max_tokens and temperature. Compatible endpoints use configured Responses or Chat Completions API.",
        "validation_failure": failure,
    }


def env_values(target, placeholders=False):
    def value(key, fallback):
        return fallback if placeholders else str(target.get(key, fallback))

    values = {
        "CLOUD_PROVIDER": "oci",
        "OCI_REGION": value("region", "<region>"),
        "OCI_COMPARTMENT_ID": value("compartment_id", "<compartment-ocid>"),
        "OCI_NAMESPACE": value("namespace", "<namespace>"),
        "OCI_BUCKET": value("bucket", "<bucket>"),
        "OBJECT_STORAGE_PREFIX": value("object_prefix", "documents/"),
        "OCI_LLM_MODEL_ID": value("llm_model_id", "<model-or-endpoint-id>"),
        "OCI_LLM_ENDPOINT": value("llm_endpoint", "<oci-service-endpoint>"),
        "OCI_LLM_FORMAT": value("llm_format", "generic"),
        "OCI_LLM_SERVING_MODE": value("llm_serving_mode", "on_demand"),
        "OCI_EMBEDDING_MODEL_ID": value("embedding_model_id", "<embedding-model-or-endpoint-id>"),
        "OCI_EMBEDDING_ENDPOINT": value("embedding_endpoint", "<oci-native-inference-endpoint>"),
        "OCI_EMBEDDING_SERVING_MODE": value("embedding_serving_mode", "on_demand"),
        "OCI_EMBEDDING_DIMENSIONS": value("embedding_dimensions", "1024"),
        "OCI_EMBEDDING_SET_DIMENSIONS": str(target.get("embedding_set_dimensions", False)).lower(),
        "OCI_CHUNK_CHARS": value("chunk_chars", "1800"),
        "OCI_CHUNK_OVERLAP": value("chunk_overlap", "200"),
        "OCI_DB_USER": value("db_user", "<application-user>"),
        "OCI_DB_PASSWORD": value("db_password", "<database-password>"),
        "OCI_DB_DSN": value("db_dsn", "tcps://<host>:1521/<service-name>"),
        "OCI_DB_WALLET_DIR": value("db_wallet_dir", ""),
        "OCI_DB_WALLET_PASSWORD": value("db_wallet_password", ""),
        "OCI_CONFIG_FILE": "config/oci/config"
        if target.get("private_key") and not placeholders
        else "~/.oci/config",
        "OCI_PROFILE": value("oci_profile", "DEFAULT"),
    }
    return values


def env_text(target, placeholders=False):
    values = env_values(target, placeholders)
    # Literal single-quoted dotenv values, with no interpolation or embedded newlines.
    for v in values.values():
        if any(c in v for c in ("\r", "\n", "\x00", "${")):
            raise SafeError(
                "Configuration values cannot contain newlines, null bytes or dotenv interpolation expressions."
            )
    values = {k: v.replace("\\", "\\\\").replace("'", "\\'") for k, v in values.items()}
    return (
        "# Private runtime configuration. Do not commit this file.\n"
        + "\n".join(f"{k}='{v}'" for k, v in values.items())
        + "\n"
    )


def assert_boundaries(files, changes):
    for path, content in changes.items():
        if path.startswith(PROTECTED):
            raise SafeError("A protected core file was modified: " + path)
        if path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as exc:
                raise SafeError("Generated Python did not pass syntax validation.") from exc

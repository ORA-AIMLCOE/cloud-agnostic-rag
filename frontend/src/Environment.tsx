import { useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";

type Preview = {
  aws: Record<string, string>;
  aws_ignored: number;
  oci: Record<string, string> | null;
  masked: string[];
  status: string;
};
function EnvFile({
  title,
  badge,
  values,
  masked = [],
  empty,
}: {
  title: string;
  badge: string;
  values: Record<string, string> | null;
  masked?: string[];
  empty: string;
}) {
  const entries = Object.entries(values ?? {});
  return (
    <article className="env-file">
      <div className="env-file-heading">
        <Icon name="settings" />
        <strong>{title}</strong>
        <span>{badge}</span>
      </div>
      {entries.length ? (
        <div className="env-lines">
          {entries.map(([key, value], index) => (
            <div
              className={`env-line ${masked.includes(key) ? "masked" : ""}`}
              key={key}
            >
              <span className="env-number" aria-hidden="true">
                {index + 1}
              </span>
              <code>
                <span className="env-key">{key}</span>
                <span className="env-equals">=</span>
                <span className="env-value">{JSON.stringify(value)}</span>
              </code>
            </div>
          ))}
        </div>
      ) : (
        <p className="env-empty">{empty}</p>
      )}
    </article>
  );
}
export function Environment({
  jobId,
  status,
}: {
  jobId: string;
  status: string;
}) {
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    api<Preview>(`/jobs/${jobId}/environment`)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((e) => {
        if (!cancelled)
          setError(
            e instanceof Error
              ? e.message
              : "Unable to load environment settings.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, status, attempt]);
  return (
    <section className="environment-panel" aria-label="Environment comparison">
      <div className="environment-heading">
        <div>
          <h2>Environment configuration</h2>
          <p>
            Review the AWS settings from your initial upload and the OCI runtime
            configuration.
          </p>
        </div>
        <span className="preview-label">Credentials masked</span>
      </div>
      <p className="environment-note">
        AWS credentials and unsupported values are discarded at upload. This
        preview shows only retained AWS settings. OCI passwords are masked
        before this page receives them; signing keys are never displayed.
      </p>
      {error ? (
        <div role="alert" className="error">
          <span>{error}</span>
          <button
            className="secondary"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Retry
          </button>
        </div>
      ) : !data ? (
        <p role="status" className="env-empty">
          Loading environment settings...
        </p>
      ) : (
        <>
          <div className="environment-grid">
            <EnvFile
              title="AWS .env"
              badge="Initial upload"
              values={data.aws}
              empty={
                data.status === "expired"
                  ? "The saved AWS configuration has expired."
                  : "No AWS settings were saved with the initial upload for this conversion."
              }
            />
            <EnvFile
              title="OCI .env"
              badge={
                data.status === "completed" ? "Generated" : "Submitted settings"
              }
              values={data.oci}
              masked={data.masked}
              empty={
                data.status === "expired"
                  ? "The saved OCI configuration has expired."
                  : "OCI settings have not been submitted for this conversion."
              }
            />
          </div>
          <div className="environment-footnote">
            <span>
              {Object.keys(data.aws).length} AWS settings shown
              {data.aws_ignored
                ? `; ${data.aws_ignored} other entries discarded`
                : ""}
              .
            </span>
            <span>
              {data.status === "completed"
                ? "Use Private ENV Configuration in Overview for the complete OCI runtime files."
                : "The complete OCI runtime files become available after successful conversion."}
            </span>
          </div>
        </>
      )}
    </section>
  );
}

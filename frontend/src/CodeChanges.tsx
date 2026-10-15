import { useMemo, useState } from "react";
import type { Change } from "./api";
import { Icon } from "./Icon";
import { parseDiff } from "./diff";

export function CodeChanges({
  files,
  compareUrl,
}: {
  files: Change[];
  compareUrl?: string;
}) {
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(files[0]?.path ?? "");
  const visible = files.filter((file) =>
    file.path.toLowerCase().includes(filter.toLowerCase()),
  );
  const change = visible.find((file) => file.path === selected) ?? visible[0];
  const lines = useMemo(() => parseDiff(change?.diff ?? ""), [change?.diff]);
  const totals = files.reduce(
    (sum, file) => ({
      added: sum.added + file.added,
      removed: sum.removed + file.removed,
    }),
    { added: 0, removed: 0 },
  );
  if (!files.length)
    return (
      <div className="empty-panel">
        The code comparison appears after generation and validation.
      </div>
    );
  return (
    <section className="code-review" aria-label="Code comparison">
      <div className="review-toolbar">
        <div>
          <strong>{files.length} changed files</strong>
          <span className="diff-stats">
            <b>+{totals.added}</b>
            <em>-{totals.removed}</em>
          </span>
        </div>
        {compareUrl && (
          <a
            className="review-github"
            href={compareUrl}
            target="_blank"
            rel="noreferrer"
          >
            View on GitHub <Icon name="arrow" />
          </a>
        )}
      </div>
      <div className="diff-layout">
        <nav className="changed-files" aria-label="Changed files">
          <label className="file-filter">
            <Icon name="search" />
            <input
              aria-label="Filter changed files"
              placeholder="Filter files..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </label>
          <div className="file-list">
            {visible.map((file) => {
              const slash = file.path.lastIndexOf("/");
              return (
                <button
                  key={file.path}
                  className={change?.path === file.path ? "selected" : ""}
                  onClick={() => setSelected(file.path)}
                  title={file.path}
                  aria-label={file.path}
                  aria-current={change?.path === file.path ? "true" : undefined}
                >
                  <Icon name="file" />
                  <span className="file-name">
                    <strong>{file.path.slice(slash + 1)}</strong>
                    {slash >= 0 && <small>{file.path.slice(0, slash)}</small>}
                  </span>
                  <span className={`file-kind ${file.kind}`} title={file.kind}>
                    {file.kind === "added"
                      ? "A"
                      : file.kind === "deleted"
                        ? "D"
                        : "M"}
                  </span>
                </button>
              );
            })}
            {!visible.length && <p className="no-files">No matching files.</p>}
          </div>
        </nav>
        {change ? (
          <article className="diff-pane">
            <div className="diff-title">
              <Icon name="file" />
              <strong>{change.path}</strong>
              <span className="diff-stats">
                <b>+{change.added}</b>
                <em>-{change.removed}</em>
              </span>
              <span className="diff-kind">{change.kind}</span>
            </div>
            {change.reason && (
              <div className="change-reason">
                <div className="summary-heading">
                  <strong>Development summary</strong>
                  {change.reason_source === "astra" && (
                    <span>Written by GPT</span>
                  )}
                </div>
                <p>{change.reason}</p>
              </div>
            )}
            <div className="diff-legend">
              <span>Unified diff</span>
              <span>Red: removed from AWS source</span>
              <span>Green: added for OCI</span>
            </div>
            <div
              className="diff-scroll"
              tabIndex={0}
              role="region"
              aria-label={`Diff for ${change.path}`}
              key={change.path}
            >
              <table
                className="diff-table"
                aria-label={`Changes in ${change.path}`}
              >
                <thead className="sr-only">
                  <tr>
                    <th>Source line</th>
                    <th>OCI line</th>
                    <th>Change</th>
                    <th>Code</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => (
                    <tr className={line.kind} key={index}>
                      <td className="line-number">{line.oldLine}</td>
                      <td className="line-number">{line.newLine}</td>
                      <td className="line-sign">
                        {line.kind === "addition"
                          ? "+"
                          : line.kind === "deletion"
                            ? "-"
                            : ""}
                      </td>
                      <td className="line-code">
                        <code>{line.text || " "}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!lines.length && (
              <p className="no-files">
                No textual diff available for this file.
              </p>
            )}
          </article>
        ) : (
          <div className="empty-panel">Try a different file name.</div>
        )}
      </div>
    </section>
  );
}

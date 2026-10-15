export type DiffLine = {
  kind: "addition" | "deletion" | "context" | "hunk" | "note";
  text: string;
  oldLine?: number;
  newLine?: number;
};

export function parseDiff(diff: string): DiffLine[] {
  let oldLine: number | undefined, newLine: number | undefined;
  let inHunk = false;
  const lines: DiffLine[] = [];
  for (const line of diff.split("\n")) {
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
    if (hunk) {
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      inHunk = true;
      lines.push({ kind: "hunk", text: line });
    } else if (
      !inHunk &&
      (line.startsWith("--- ") ||
        line.startsWith("+++ ") ||
        line.startsWith("diff ") ||
        line.startsWith("index "))
    ) {
      continue;
    } else if (line.startsWith("+")) {
      lines.push({ kind: "addition", text: line.slice(1), newLine });
      if (newLine !== undefined) newLine++;
    } else if (line.startsWith("-")) {
      lines.push({ kind: "deletion", text: line.slice(1), oldLine });
      if (oldLine !== undefined) oldLine++;
    } else if (line.startsWith(" ")) {
      lines.push({ kind: "context", text: line.slice(1), oldLine, newLine });
      if (oldLine !== undefined) oldLine++;
      if (newLine !== undefined) newLine++;
    } else if (line) {
      lines.push({ kind: "note", text: line });
    }
  }
  return lines;
}

import { expect, test } from "vitest";
import { parseDiff } from "./diff";

test("unified diffs track source and OCI lines across multiple hunks", () => {
  const lines = parseDiff(
    "--- a/file.py\n+++ b/file.py\n@@ -4,2 +4,3 @@\n context\n-old\n+new\n+extra\n@@ -20 +21 @@\n-last\n+replacement\n",
  );
  expect(
    lines
      .filter((line) => line.kind === "deletion")
      .map((line) => line.oldLine),
  ).toEqual([5, 20]);
  expect(
    lines
      .filter((line) => line.kind === "addition")
      .map((line) => line.newLine),
  ).toEqual([5, 6, 21]);
  expect(lines[1]).toEqual({
    kind: "context",
    text: "context",
    oldLine: 4,
    newLine: 4,
  });
  expect(lines.some((line) => line.text === "++ b/file.py")).toBe(false);
});
test("added files and literal diff-looking code keep correct line numbers", () => {
  const lines = parseDiff(
    "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+++ code\n+second\n\\ No newline at end of file",
  );
  expect(lines[1]).toEqual({ kind: "addition", text: "++ code", newLine: 1 });
  expect(lines[2].newLine).toBe(2);
  expect(lines[3].kind).toBe("note");
});

// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CodeChanges } from "./CodeChanges";

test("vertical file navigator filters files and updates the unified diff", () => {
  render(
    <CodeChanges
      files={[
        {
          path: "backend/settings.py",
          kind: "modified",
          added: 1,
          removed: 1,
          diff: "@@ -1 +1 @@\n-old setting\n+new setting",
        },
        {
          path: "backend/providers/oci/storage.py",
          kind: "added",
          added: 1,
          removed: 0,
          diff: "@@ -0,0 +1 @@\n+storage adapter",
        },
      ]}
    />,
  );
  expect(
    screen.getByRole("table", { name: "Changes in backend/settings.py" }),
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "backend/providers/oci/storage.py" }),
  );
  expect(screen.getByText("storage adapter")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Filter changed files"), {
    target: { value: "settings" },
  });
  expect(
    screen.queryByRole("button", { name: "backend/providers/oci/storage.py" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("new setting")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Filter changed files"), {
    target: { value: "missing" },
  });
  expect(screen.getByText("No matching files.")).toBeInTheDocument();
});

export function Icon({
  name,
}: {
  name:
    | "arrow"
    | "plus"
    | "code"
    | "file"
    | "check"
    | "chevron"
    | "close"
    | "trash"
    | "panel"
    | "storage"
    | "model"
    | "search"
    | "database"
    | "folder"
    | "settings";
}) {
  const paths = {
    panel: "M3 4h18v16H3z M9 4v16 M15 9l-3 3 3 3",
    storage: "M3 5l9-3 9 3-9 3z M3 5v14l9 3 9-3V5 M12 8v14",
    model:
      "M8 5h8a4 4 0 0 1 4 4v7a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V9a4 4 0 0 1 4-4z M12 2v3 M8 10v2 M16 10v2 M9 16h6 M1 10v5 M23 10v5",
    search: "M15 15l6 6 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0 M7 10h6 M10 7v6",
    database:
      "M3 5c0-4 18-4 18 0s-18 4-18 0v14c0 4 18 4 18 0V5 M3 12c0 4 18 4 18 0",
    folder: "M3 6h7l2 3h9v11H3z",
    settings: "M5 3v18 M12 3v18 M19 3v18 M2 8h6 M9 16h6 M16 8h6",
    trash: "M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7",
    arrow: "M4 12h16 M13 5l7 7-7 7",
    plus: "M12 5v14 M5 12h14",
    code: "M8 7l-5 5 5 5 M16 7l5 5-5 5 M14 4l-4 16",
    file: "M14 3H5v18h14V8z M14 3v5h5 M8 12h8 M8 16h5",
    check: "M5 12l4 4L19 6",
    chevron: "M9 5l7 7-7 7",
    close: "M6 6l12 12 M18 6 6 18",
  };
  return (
    <svg
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}

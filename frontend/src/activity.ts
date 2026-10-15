type ActivityLabel = { title: string; description?: string };

const labels: Record<string, ActivityLabel> = {
  "Reading the source branch": {
    title: "Fetch the AWS source code",
    description: "Read a snapshot of the selected GitHub branch.",
  },
  "Repository inspected. Complete the OCI settings.": {
    title: "AWS project structure checked",
    description:
      "The repository is supported. Ready for your OCI configuration.",
  },
  "Preparing OCI adapters and configuration": {
    title: "Prepare OCI service integrations",
    description:
      "Prepare the storage, AI, and database changes while preserving core RAG logic.",
  },
  "Running isolated application and adapter tests": {
    title: "Build and test the converted application",
    description:
      "Run offline build and compatibility checks in an isolated container.",
  },
  "Summarizing file changes with GPT Astra": {
    title: "Explain each file's development changes",
    description: "GPT summarizes the final diff for every changed file.",
  },
  "Creating the OCI commit": {
    title: "Publish the OCI conversion to GitHub",
    description:
      "Commit the validated changes and create a separate OCI branch.",
  },
  "OCI code validated and branch published": {
    title: "OCI branch published successfully",
    description: "Offline checks passed. The new branch is ready for review.",
  },
  "OCI code validated; ready to download": {
    title: "OCI project ready to download",
    description:
      "Offline checks passed. Download the code and Private ENV Configuration.",
  },
  "Offline validation failed. Review test results; no branch was published.": {
    title: "Build or compatibility checks failed",
    description:
      "Review the Validation tab for details. No branch was published.",
  },
};

export function activityLabel(message: string): ActivityLabel {
  const review = /^OCI Astra: adapter review (\d+)$/.exec(message);
  if (review)
    return {
      title: "Review OCI code with GPT",
      description: `Review pass ${review[1]}: check and refine the OCI integration code.`,
    };
  // Preserve diagnostic details for failures and events without a display label.
  return labels[message] ?? { title: message };
}

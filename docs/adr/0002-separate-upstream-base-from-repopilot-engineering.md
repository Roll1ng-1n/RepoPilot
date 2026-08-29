# Separate the upstream base from RepoPilot engineering

The imported `minisweagent` package remains the identifiable upstream base, while an independent `repopilot` package owns RepoPilot's new agent-engineering capabilities. RepoPilot will prefer extension from its own package and modify `minisweagent` only when its interfaces prevent a reasonable extension, keeping such changes minimal and traceable; this avoids both a disruptive upstream rename and an indistinguishable pile of project-specific behavior inside the base package.

# Require native tool calling

RepoPilot V1 requires execution models to provide OpenAI-compatible native tool calling and does not parse actions from Markdown, XML, or free-form text. This deliberately excludes otherwise usable models in exchange for simpler structured tools, argument validation, dispatch, recovery, and trace data.

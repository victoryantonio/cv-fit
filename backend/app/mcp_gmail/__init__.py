"""Gmail MCP helper: read-only alert email access for the backend.

Runs as a stdio subprocess (`python -m app.mcp_gmail`). Two tools, both read-only.
It never talks to LinkedIn and is never handed to an LLM.
"""

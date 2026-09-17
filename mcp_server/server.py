"""
A small MCP (Model Context Protocol) tool server.

It exposes a couple of deliberately simple tools — a calculator and a word
counter — so the RAG agent in ../api can demonstrate calling out to an MCP
server over the network from inside Docker, exactly like it would call a
real external MCP server (GitHub, Slack, a database, etc.) in production.

Run standalone (outside Docker) with:
    python server.py

Inside Docker, this process is the container's ENTRYPOINT — see Dockerfile.
"""

import ast
import operator
import os

from mcp.server.fastmcp import FastMCP

# Host/port are configurable via env vars so the same image behaves correctly
# whether it's run standalone on your laptop or inside a Docker network where
# it must bind to 0.0.0.0 (not 127.0.0.1) to accept connections from other
# containers.
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8100"))

mcp = FastMCP("agent-tools", host=HOST, port=PORT)

# A safe, whitelisted arithmetic evaluator instead of eval() — never eval()
# untrusted input from an LLM or a user, even in a toy project.
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


@mcp.tool()
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression, e.g. '(4 + 5) * 12'."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)
    except Exception as exc:  # noqa: BLE001 - tool errors should surface, not crash
        return f"error: could not evaluate expression ({exc})"


@mcp.tool()
def word_count(text: str) -> str:
    """Count words and characters in a piece of text."""
    words = len(text.split())
    chars = len(text)
    return f"{words} words, {chars} characters"


if __name__ == "__main__":
    # "sse" (Server-Sent Events) is one of MCP's network transports — it lets
    # this tool server run as its own long-lived container that other
    # services reach over HTTP, instead of the "stdio" transport used when an
    # MCP server is spawned as a local subprocess.
    mcp.run(transport="sse")

"""Stream adapters for normalising agent output events into plain text tokens."""

from __future__ import annotations

from typing import Any, AsyncIterator


class StreamAdapter:
    """Adapts DeepAgents / LangGraph stream events to an async iterator of strings.

    The adapter understands several event shapes emitted by
    ``astream_events(version="v2")``:

    * ``on_chat_model_stream`` — incremental LLM token chunks.
    * ``on_chain_stream`` — higher-level chain outputs that may contain text.
    """

    @staticmethod
    async def adapt(stream_events: Any) -> AsyncIterator[str]:
        """Yield text tokens from *stream_events*.

        Parameters
        ----------
        stream_events:
            An async iterable of LangChain/LangGraph v2 stream event dicts.

        Yields
        ------
        str
            Non-empty text fragments suitable for direct display.
        """
        async for event in stream_events:
            kind: str = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue
                text = getattr(chunk, "content", "")
                if isinstance(text, str) and text:
                    yield text
                elif isinstance(text, list):
                    for block in text:
                        if isinstance(block, str) and block:
                            yield block
                        elif isinstance(block, dict) and block.get("type") == "text":
                            t = block.get("text", "")
                            if t:
                                yield t

            elif kind == "on_chain_stream":
                # Some chain outputs surface final text here.
                data = event.get("data", {})
                output = data.get("output") or data.get("chunk")
                if isinstance(output, str) and output:
                    yield output
                elif isinstance(output, dict):
                    # Try common keys
                    for key in ("content", "text", "output"):
                        val = output.get(key, "")
                        if isinstance(val, str) and val:
                            yield val
                            break

"""
Agent module — Groq LLM with tool calling and RAG context injection.

Uses ChatGroq with .bind_tools() for native tool calling.
Falls back to plain LLM if tool calling fails (Llama can generate malformed calls).
"""

import os
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from assistant.retrieval import get_store, search_products
from assistant.tools import ALL_TOOLS, check_stock, find_parts_by_vehicle, create_order
from assistant.prompts import SYSTEM_PROMPT, CONTEXT_TEMPLATE, NO_CONTEXT_TEMPLATE

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_HISTORY = 10


# ---------------------------------------------------------------------------
# Session Store (in-memory)
# ---------------------------------------------------------------------------
_sessions: dict[str, list] = {}


def get_history(session_id: str) -> list:
    if session_id not in _sessions:
        _sessions[session_id] = []
    return _sessions[session_id]


def clear_history(session_id: str) -> None:
    _sessions[session_id] = []


def _trim_history(history: list) -> list:
    max_messages = MAX_HISTORY * 2
    if len(history) > max_messages:
        return history[-max_messages:]
    return history


# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------

_llm_with_tools = None
_llm_plain = None


def _get_llms():
    """Get LLM instances - one with tools, one without."""
    global _llm_with_tools, _llm_plain
    if _llm_with_tools is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found. Set it in your .env file. "
                "Get a free key at https://console.groq.com"
            )

        base_llm = ChatGroq(
            model=GROQ_MODEL,
            api_key=api_key,
            temperature=0.3,
            max_tokens=2048,
        )

        _llm_with_tools = base_llm.bind_tools(ALL_TOOLS)
        _llm_plain = base_llm

    return _llm_with_tools, _llm_plain


# ---------------------------------------------------------------------------
# Tool Dispatcher
# ---------------------------------------------------------------------------

TOOL_MAP = {
    "check_stock": check_stock,
    "find_parts_by_vehicle": find_parts_by_vehicle,
    "create_order": create_order,
}


def _execute_tool(tool_name: str, tool_args: dict) -> str:
    if tool_name not in TOOL_MAP:
        return f"Unknown tool: {tool_name}"
    try:
        result = TOOL_MAP[tool_name].invoke(tool_args)
        return str(result)
    except Exception as e:
        return f"Tool error ({tool_name}): {str(e)}"


# ---------------------------------------------------------------------------
# RAG Context Builder
# ---------------------------------------------------------------------------

def _build_context(query: str) -> tuple[str, list[dict]]:
    """Build RAG context and return (context_string, raw_results)."""
    results = search_products(query, k=5)
    if not results:
        return NO_CONTEXT_TEMPLATE, []
    product_lines = [r["document"] for r in results]
    products_text = "\n\n".join(product_lines)
    return CONTEXT_TEMPLATE.format(products=products_text), results


def _build_messages(system_message: str, history: list, user_message: str) -> list:
    """Build the message list from system prompt, history, and current query."""
    messages = [SystemMessage(content=system_message)]
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=user_message))
    return messages


# ---------------------------------------------------------------------------
# Main Chat Function
# ---------------------------------------------------------------------------

def _invoke_with_retry(llm, messages, max_retries=3, base_delay=5):
    """Invoke LLM with exponential backoff retry for rate limit and transient errors."""
    import time as _time

    for attempt in range(max_retries + 1):
        try:
            response = llm.invoke(messages)
            # Guard against empty responses (Llama on Groq can return blank)
            if (
                response
                and hasattr(response, "content")
                and not response.content
                and not (hasattr(response, "tool_calls") and response.tool_calls)
            ):
                if attempt < max_retries:
                    wait = base_delay * (2 ** attempt)
                    print(f"  [Empty model output, retrying in {wait}s... attempt {attempt+1}/{max_retries}]")
                    _time.sleep(wait)
                    continue
            return response
        except Exception as e:
            err_str = str(e).lower()
            is_retryable = (
                "rate_limit" in err_str
                or "429" in err_str
                or "too many requests" in err_str
                or "rate limit" in err_str
                or "tokens per minute" in err_str
                or "model output" in err_str          # empty output error
                or "cannot both be empty" in err_str  # empty output variant
                or "overloaded" in err_str             # server overloaded
                or "503" in err_str                    # service unavailable
            )
            if is_retryable and attempt < max_retries:
                wait = base_delay * (2 ** attempt)
                reason = "Rate limit" if "rate" in err_str or "429" in err_str else "Transient error"
                print(f"  [{reason}, retrying in {wait}s... attempt {attempt+1}/{max_retries}]")
                _time.sleep(wait)
            else:
                raise


def chat(session_id: str, user_message: str) -> dict:
    """
    Process a user message and return the agent's response.

    Strategy:
    1. Try with tools - if LLM wants a tool, execute it and get final answer
    2. If tool calling fails (Groq 400 error), fall back to plain LLM with RAG context
    3. Always return a text response
    """
    llm_tools, llm_plain = _get_llms()

    # RAG context (also captures results to reuse for source SKUs)
    context, rag_results = _build_context(user_message)
    system_message = SYSTEM_PROMPT.format(context=context)

    # Build messages
    history = get_history(session_id)
    messages = _build_messages(system_message, history, user_message)

    response_text = ""

    try:
        # Step 1: Try LLM with tools
        try:
            ai_response = _invoke_with_retry(llm_tools, messages)
        except Exception as tool_err:
            # Tool calling failed (malformed call, Groq 400, etc.)
            # Fall back to plain LLM — it will answer using RAG context only
            ai_response = _invoke_with_retry(llm_plain, messages)

        # Step 2: If tools were called, execute them
        if hasattr(ai_response, 'tool_calls') and ai_response.tool_calls:
            messages.append(ai_response)

            tool_results_text = []
            for tool_call in ai_response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_result = _execute_tool(tool_name, tool_args)
                tool_results_text.append(tool_result)

                messages.append(ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call["id"],
                ))

            # Now pass the tool results back to the LLM to synthesize the final answer
            try:
                final_response = _invoke_with_retry(llm_tools, messages)
                response_text = final_response.content
            except Exception as synthesis_err:
                print(f"  [Tool synthesis error: {str(synthesis_err)[:200]}]")
                response_text = "\n\n".join(tool_results_text)
        else:
            # No tool calls — direct text response
            response_text = ai_response.content

        # Final safety net
        if not response_text or not response_text.strip():
            response_text = (
                "I can help you with automotive parts! Try asking me to:\n"
                "- Search for specific parts (e.g. 'brake pads for Pulsar 150')\n"
                "- Check stock by SKU (e.g. 'check stock for SKU001')\n"
                "- Find parts for a vehicle (e.g. 'parts for Honda Activa 6G 2022')\n"
                "- Place an order (e.g. 'order for Sharma Motors: 2x SKU001')"
            )

    except Exception as e:
        # Complete fallback — log the error and try plain LLM with a simplified prompt
        print(f"  [Agent error: {str(e)[:200]}]")
        try:
            import time as _time
            _time.sleep(3)  # Brief pause before retry
            # Use a simpler message list to reduce chance of empty output
            fallback_messages = [
                SystemMessage(content=(
                    "You are VIKMO Dealer Assistant. Answer the user's question about "
                    "automotive parts using the context below.\n\n" + context
                )),
                HumanMessage(content=user_message),
            ]
            fallback_response = _invoke_with_retry(
                llm_plain, fallback_messages, max_retries=3, base_delay=3
            )
            response_text = fallback_response.content
        except Exception as fallback_err:
            print(f"  [Fallback also failed: {str(fallback_err)[:200]}]")
            # Use RAG results directly as a last resort
            rag_results = search_products(user_message, k=5)
            if rag_results:
                lines = ["Here are some products from our catalogue that may match your query:\n"]
                for r in rag_results:
                    meta = r.get("metadata", {})
                    lines.append(
                        f"• **{meta.get('product_name', 'N/A')}** (SKU: {meta.get('sku', '?')})\n"
                        f"  Category: {meta.get('category', '?')} | Brand: {meta.get('brand', '?')} | "
                        f"Price: ₹{meta.get('price', '?')} | Stock: {meta.get('stock', '?')} units"
                    )
                lines.append("\nPlease ask about a specific product for more details!")
                response_text = "\n".join(lines)
            else:
                response_text = (
                    "I apologize for the error. Please try a more specific query like:\n"
                    "- 'Show me brake pads for Bajaj Pulsar 150'\n"
                    "- 'Check stock for SKU001'\n"
                    "- 'What parts fit Honda Activa 6G 2022?'"
                )

    # Update session history
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": response_text})
    _sessions[session_id] = _trim_history(history)

    # Source SKUs — reuse the RAG results from earlier (no duplicate search)
    sources = [r["sku"] for r in rag_results[:3]]

    return {
        "response": response_text,
        "sources": sources,
    }


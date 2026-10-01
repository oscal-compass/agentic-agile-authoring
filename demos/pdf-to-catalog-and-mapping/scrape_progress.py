#!/usr/bin/env python3
"""
scrape_progress.py — extract the latest meaningful agent activity and cost from a JSONL log.

Supports both log formats:
  - Claude Code: {"type":"assistant","message":{"content":[...],"usage":{...}}}
  - Bob shell:   {"type":"message","role":"assistant","content":"<token>"}
                 {"type":"result","stats":{"session_costs":0.94,"duration_ms":...}}

Prints one summary line (activity) and optionally a cost line.
Usage:
  scrape_progress.py <logfile>           — print activity line
  scrape_progress.py <logfile> --cost    — print cost summary only
"""
import json, sys, re

# ---------------------------------------------------------------------------
# Model pricing table — USD per million tokens (input, output)
# Source: anthropic.com/pricing (mid-2025 list prices)
# Key is canonical model name after stripping provider prefix (aws/, vertex/)
# ---------------------------------------------------------------------------
MODEL_PRICING = {
    "claude-opus-4-5":   (15.00,  75.00),
    "claude-opus-4-7":   (15.00,  75.00),
    "claude-sonnet-4-5": ( 3.00,  15.00),
    "claude-sonnet-4-7": ( 3.00,  15.00),
    "claude-opus-3":     (15.00,  75.00),
    "claude-sonnet-3-7": ( 3.00,  15.00),
    "claude-sonnet-3-5": ( 3.00,  15.00),
    "claude-haiku-3-5":  ( 0.80,   4.00),
    "claude-haiku-3":    ( 0.25,   1.25),
}

def _model_price(model_str):
    """Return (input_per_M, output_per_M) or None if unknown."""
    if not model_str:
        return None
    bare = model_str.split("/")[-1].lower()
    if bare in MODEL_PRICING:
        return MODEL_PRICING[bare]
    for key, prices in MODEL_PRICING.items():
        if bare.startswith(key) or key.startswith(bare):
            return prices
    return None

def scrape(logfile):
    lines = []
    try:
        with open(logfile, errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return "(waiting for agent to start...)", None
    except Exception as e:
        return f"(log unreadable: {e})", None

    # ---- Bob format: accumulate streamed tokens ----
    bob_buf = ""
    bob_sentences = []
    tool_calls = []

    # ---- Claude format: collect text blocks and tool names ----
    claude_texts = []
    claude_tools = []

    # ---- Cost tracking ----
    # Claude: sum usage across all assistant messages
    claude_input_tokens  = 0
    claude_output_tokens = 0
    claude_cache_read    = 0
    claude_cache_write   = 0
    claude_model         = None
    # Bob: final result record
    bob_cost_usd   = None
    bob_duration_s = None

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue

        t    = obj.get("type", "")
        role = obj.get("role", "")

        # --- Bob token-stream format ---
        if t == "message" and role == "assistant":
            bob_buf += obj.get("content", "")
            while True:
                m = re.search(r"[.!?]\s+|\n\n", bob_buf)
                if not m:
                    break
                sentence = bob_buf[:m.end()].strip()
                if len(sentence) > 15:
                    bob_sentences.append(sentence)
                bob_buf = bob_buf[m.end():]

        elif t == "tool_use":
            inp  = obj.get("input") or {}
            desc = (inp.get("description") or inp.get("command") or "")[:80]
            name = obj.get("name", "")
            if name:
                tool_calls.append(f"{name}: {desc}" if desc else name)

        # Bob final result with cost
        elif t == "result":
            stats = obj.get("stats") or {}
            if "session_costs" in stats:
                bob_cost_usd = float(stats["session_costs"])
            if "duration_ms" in stats:
                bob_duration_s = float(stats["duration_ms"]) / 1000.0

        # --- Claude Code JSONL format ---
        elif t == "assistant":
            msg = obj.get("message") or {}
            # capture model (use first seen; all messages in a session use the same model)
            if not claude_model and msg.get("model"):
                claude_model = msg["model"]
            # accumulate token usage
            usage = msg.get("usage") or {}
            claude_input_tokens  += usage.get("input_tokens", 0)
            claude_output_tokens += usage.get("output_tokens", 0)
            claude_cache_read    += usage.get("cache_read_input_tokens", 0)
            claude_cache_write   += usage.get("cache_creation_input_tokens", 0)
            for blk in msg.get("content") or []:
                if blk.get("type") == "text":
                    txt = blk.get("text", "").strip()
                    if len(txt) > 15:
                        claude_texts.append(txt)
                elif blk.get("type") == "tool_use":
                    inp  = blk.get("input") or {}
                    desc = (inp.get("description") or inp.get("command") or "")[:80]
                    name = blk.get("name", "")
                    if name:
                        claude_tools.append(f"{name}: {desc}" if desc else name)

    # Flush remaining bob buffer
    if bob_buf.strip() and len(bob_buf.strip()) > 15:
        bob_sentences.append(bob_buf.strip())

    # ---- Build cost summary ----
    cost_summary = None
    if bob_cost_usd is not None:
        mins = int(bob_duration_s // 60) if bob_duration_s else 0
        secs = int(bob_duration_s % 60) if bob_duration_s else 0
        cost_summary = f"${bob_cost_usd:.4f}  (bob session_costs; {mins}m{secs:02d}s)"
    elif claude_input_tokens or claude_output_tokens:
        total = claude_input_tokens + claude_output_tokens
        model_label = claude_model.split("/")[-1] if claude_model else "unknown model"
        parts = [f"model {model_label}",
                 f"input {claude_input_tokens:,}  output {claude_output_tokens:,}  total {total:,} tokens"]
        if claude_cache_read or claude_cache_write:
            parts.append(f"cache read {claude_cache_read:,}  write {claude_cache_write:,}")
        prices = _model_price(claude_model)
        if prices:
            in_p, out_p = prices
            est_usd = (claude_input_tokens * in_p + claude_output_tokens * out_p) / 1_000_000
            parts.append(f"~${est_usd:.4f} (${in_p}/${out_p} per M in/out, list price)")
        else:
            parts.append("(price unknown — model not in pricing table)")
        cost_summary = "  |  ".join(parts)

    # ---- Build activity summary ----
    all_texts = bob_sentences + claude_texts
    all_tools = tool_calls + claude_tools

    latest_text = all_texts[-1] if all_texts else ""
    latest_tool = all_tools[-1] if all_tools else ""

    if latest_text:
        activity = re.sub(r"\s+", " ", latest_text)[:100]
    elif latest_tool:
        activity = latest_tool[:100]
    else:
        activity = f"(running — {len(lines)} log lines so far)"

    return activity, cost_summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: scrape_progress.py <logfile> [--cost]")
        sys.exit(1)

    logfile   = sys.argv[1]
    cost_only = "--cost" in sys.argv

    activity, cost = scrape(logfile)

    if cost_only:
        if cost:
            print(cost)
        else:
            print("(no cost data yet — agent may still be running)")
    else:
        print(activity)
        if cost:
            print(f"  cost: {cost}")

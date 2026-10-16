import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent / ".env")

import queries

# Define tools for LLM function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_incidents",
            "description": "Finds active civic grievance incidents grouped by ward and issue type, sorted by registered complaint count. Case-insensitive ward match.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ward": {"type": "string", "description": "Optional ward name filter (e.g., 'Thanisandra')"},
                    "issue_type": {"type": "string", "description": "Optional issue type filter (e.g., 'Solid Waste Management')"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trace_root_cause",
            "description": "Traces Incident -> Ward -> WorkOrder where WorkOrder MAY_CONTRIBUTE_TO the incident's IssueType. Returns work order details, status, project, contractor, affected infrastructure, downstream dependents via DEPENDS_ON*1..3, and causality disclaimer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string", "description": "Incident ID (e.g., 'INC-Thanisandra-SolidWaste')"}
                },
                "required": ["incident_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "what_if_delay",
            "description": "Walks DEPENDS_ON*1..3 from affected infrastructure, finds dependent wards, counts real same-issue complaints in the loaded 14-day window, and computes projected additional complaints from extra delay days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "string", "description": "Work order ID (e.g., 'WO-101')"},
                    "extra_days": {"type": "integer", "description": "Number of extra delay days to simulate (e.g., 14)", "default": 14}
                },
                "required": ["work_order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "evidence_for_incident",
            "description": "Calculates evidence_score (0-95) from transparent rules (complaint count, baseline spike, delayed work order in ward, issue match, dependency chain, YoY volume increase) and returns firing rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string", "description": "Incident ID (e.g., 'INC-001')"}
                },
                "required": ["incident_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trend_for_ward",
            "description": "Returns H1 2024 vs H1 2025 registered complaints per issue type for a ward, with % change, citywide same-issue benchmark, and percentage points vs citywide comparison.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ward_name": {"type": "string", "description": "Ward name (e.g., 'Thanisandra')"}
                },
                "required": ["ward_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "top_rising_issues",
            "description": "Returns ward + issue pairs with the largest % surge in registered complaints from H1 2024 to H1 2025 across Bangalore.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of top rising issues to return (default 5)", "default": 5}
                }
            }
        }
    }
]

SYSTEM_PROMPT = """You are the CivicGraph AI Assistant, specialized in Bangalore municipal grievance intelligence.

CRITICAL INSTRUCTIONS:
1. Grounding: Answer ONLY from tool results. If information is not in tool results, do not invent it.
2. Identifiers & Scores: Always cite specific incident IDs (e.g., INC-Thanisandra-SolidWaste), work order IDs (e.g., WO-101), affected infrastructure, and the split evidence score (e.g., evidence score: 95/95 [Real-data: 40/40, Modeled-link: 55/55]).
3. Terminology & Causality:
   - Always use "is associated with" or "may contribute to". Never say "due to", "caused by", "caused", "proves", "reason", or "ಕಾರಣ".
   - Always refer to "evidence score", never "confidence".
   - State that work orders and infrastructure chains are synthetic models; association is not causation.
   - Do NOT use ward numbers (e.g., never say "Ward 6" or "Ward 123"); refer to wards by their canonical name only (e.g., Thanisandra, Horamavu).
   - Collection routes depend on the transfer station; a work order affects the station, so routes are downstream.
4. Reporting Registrations:
   - Always emphasize that complaint counts represent registered complaints, and that growth in reporting channels may play a role. Do NOT mention specific apps like Sahaaya or WhatsApp.
   - Always label ward complaint totals as "registered complaints in formed incidents".
5. Language Handling:
   - Always formulate your response clearly in English.
"""

def translate_text(text: str, source_code: str = 'kn-IN', target_code: str = 'en-IN') -> Optional[str]:
    """Translates text between Kannada and English using Sarvam AI translation API.
    Splits long multi-paragraph text to ensure reliable translation without payload truncation."""
    sarvam_key = os.getenv("SARVAM_API_KEY")
    if not sarvam_key:
        return None
    url = "https://api.sarvam.ai/translate"
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": sarvam_key
    }
    
    # If text has multiple paragraphs or is long, chunk by paragraphs
    if len(text) > 600 or "\n\n" in text:
        paragraphs = text.split("\n\n")
        translated_chunks = []
        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue
            try:
                payload = {
                    "input": p_clean,
                    "source_language_code": source_code,
                    "target_language_code": target_code,
                    "model": "mayura:v1",
                    "mode": "formal"
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=25)
                if resp.status_code == 200:
                    translated_chunks.append(resp.json().get("translated_text", p_clean))
                else:
                    translated_chunks.append(p_clean)
            except Exception:
                translated_chunks.append(p_clean)
        return "\n\n".join(translated_chunks)
    else:
        try:
            payload = {
                "input": text,
                "source_language_code": source_code,
                "target_language_code": target_code,
                "model": "mayura:v1",
                "mode": "formal"
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                return resp.json().get("translated_text")
        except Exception:
            pass
        return None

def execute_tool(name: str, args: Dict[str, Any]) -> Any:
    """Dispatches tool execution to queries.py."""
    if name == "find_incidents":
        return queries.find_incidents(args.get("ward"), args.get("issue_type"))
    elif name == "trace_root_cause":
        return queries.trace_root_cause(args["incident_id"])
    elif name == "what_if_delay":
        extra = args.get("extra_days", 14)
        return queries.what_if_delay(args["work_order_id"], extra_days=extra)
    elif name == "evidence_for_incident":
        return queries.evidence_for_incident(args["incident_id"])
    elif name == "trend_for_ward":
        return queries.trend_for_ward(args["ward_name"])
    elif name == "top_rising_issues":
        return queries.top_rising_issues(args.get("limit", 5))
    else:
        return {"error": f"Unknown tool: {name}"}

def llm_chat(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Any:
    """Central LLM call wrapper. Tries OpenAI gpt-4o-mini first, falls back seamlessly to Sarvam AI."""
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and not openai_key.startswith("your_"):
        try:
            client = OpenAI(api_key=openai_key)
            kwargs = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": 0.1
            }
            if tools:
                kwargs["tools"] = tools
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message
        except Exception:
            pass

    sarvam_key = os.getenv("SARVAM_API_KEY")
    if sarvam_key:
        client = OpenAI(
            base_url="https://api.sarvam.ai/v1",
            api_key=sarvam_key
        )
        kwargs = {
            "model": "sarvam-105b",
            "messages": messages,
            "max_tokens": 3000,
            "temperature": 0.1
        }
        if tools:
            kwargs["tools"] = tools
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message

    raise RuntimeError("No working LLM provider available.")

def is_kannada_text(text: str) -> bool:
    """Detects if text contains Kannada Unicode characters (U+0C80 to U+0CFF)."""
    return bool(re.search(r'[\u0C80-\u0CFF]', text))

def ask_city(question: str) -> Dict[str, Any]:
    """Answers a civic grievance question using multi-turn tool calling.
    For Kannada questions, translates question to English, runs tool calling,
    then translates English answer back to Kannada (machine translated)."""
    is_kn = is_kannada_text(question)
    search_q = question
    en_translation = ""

    if is_kn:
        translated_q = translate_text(question, source_code="kn-IN", target_code="en-IN")
        if translated_q:
            search_q = translated_q
            en_translation = translated_q

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": search_q}
    ]
    tools_called = []

    en_answer = ""
    for iteration in range(5):
        msg = llm_chat(messages, tools=TOOLS)

        if msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                raw_args = tc.function.arguments
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                tools_called.append({"tool": fn_name, "args": args})

                result = execute_tool(fn_name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)
                })
        else:
            en_answer = msg.content or ""
            break
    else:
        final_msg = llm_chat(messages)
        en_answer = final_msg.content or ""

    kn_answer = ""
    HARDCODED_DISCLAIMER_KN = "ಸಂಬಂಧವು ಕಾರಣವನ್ನು ಸೂಚಿಸುವುದಿಲ್ಲ. ಕಾರ್ಯ ಆದೇಶಗಳು ಮತ್ತು ಮೂಲಸೌಕರ್ಯ ಸರಪಳಿಗಳು ಸಿಂಥೆಟಿಕ್ ಮಾದರಿಗಳು."

    if is_kn:
        # Pre-process text before translation
        prep_text = en_answer.replace("unpolluted baseline", "baseline excluding the spike week")
        prep_text = prep_text.replace("same-issue", "same-category")

        # Strip fixed English disclaimers before translation
        cleaned_for_trans = prep_text
        disclaimer_patterns = [
            r"Work orders and infrastructure chains are synthetic models[;,\.]?\s*association is not causation[\.]?",
            r"work orders and infrastructure chains are synthetic models[;,\.]?\s*association is not causation[\.]?",
            r"This is a synthetic model[\.]?\s*Work orders and infrastructure chains are modeled constructs[;,\.]?\s*association is not causation[\.]?",
            r"Work order is a synthetic model; association is not causation[\.]?",
            r"association is not causation[\.]?",
        ]
        for pat in disclaimer_patterns:
            cleaned_for_trans = re.sub(pat, "", cleaned_for_trans, flags=re.IGNORECASE)
        cleaned_for_trans = cleaned_for_trans.strip()

        kn_body = translate_text(cleaned_for_trans, source_code="en-IN", target_code="kn-IN")
        if kn_body:
            kn_answer = f"{kn_body}\n\n{HARDCODED_DISCLAIMER_KN}"
            final_answer = f"### 🇮🇳 ಕನ್ನಡ ಉತ್ತರ / Kannada Answer\n\n{kn_answer}\n\n---\n### 🇬🇧 English Response\n\n{en_answer}"
        else:
            final_answer = f"[Notice: Kannada machine translation unavailable. Showing English response.]\n\n{en_answer}"
    else:
        final_answer = en_answer

    return {
        "original_question": question,
        "english_translation": en_translation,
        "english_answer": en_answer,
        "kannada_answer": kn_answer,
        "answer": final_answer,
        "tools_called": tools_called,
        "is_kannada": is_kn
    }

def run_agent_turn(chat_history: List[Dict[str, str]]) -> str:
    """Helper for Streamlit UI: runs one conversational turn on the latest user message."""
    latest = next((m["content"] for m in reversed(chat_history) if m.get("role") == "user"), "")
    if not latest:
        return ""
    result = ask_city(latest)
    return result["answer"]

if __name__ == '__main__':
    print("=" * 80)
    print("PHASE B: AGENT CHECK")
    print("=" * 80)

    # 1. English Question Check
    q1 = "Why is Thanisandra's garbage problem rising?"
    print(f"\nUser Question 1: '{q1}'")
    res1 = ask_city(q1)
    print("\nTools Called:")
    for t in res1["tools_called"]:
        print(f"  - {t['tool']}({t['args']})")
    print("\nAgent Answer:\n" + res1["answer"])

    print("\n" + "=" * 80)
    print("TESTING 3 KANNADA QUESTIONS VIA SARVAM TRANSLATION")
    print("=" * 80)

    kannada_questions = [
        "ಥಣಿಸಂದ್ರದಲ್ಲಿ ಕಸದ ಸಮಸ್ಯೆ ಏಕೆ ಹೆಚ್ಚುತ್ತಿದೆ?",
        "ಯಾವ ಕೆಲಸದ ಆದೇಶಗಳು ವಿಳಂಬವಾಗಿವೆ?",
        "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಅತಿ ಹೆಚ್ಚು ದೂರುಗಳು ಬಂದ ವಾರ್ಡ್ ಯಾವುದು?"
    ]

    for idx, q_kn in enumerate(kannada_questions, 1):
        print(f"\n--- Kannada Question {idx} ---")
        print(f"[1. Original Question (Kannada)]:\n{q_kn}\n")
        res = ask_city(q_kn)
        print(f"[2. English Translation of Question]:\n{res['english_translation']}\n")
        print("Tools Called:")
        for t in res["tools_called"]:
            print(f"  - {t['tool']}({t['args']})")
        print(f"\n[3. English Answer]:\n{res['english_answer']}\n")
        print(f"[4. Kannada Answer (Machine Translated)]:\n{res['kannada_answer']}\n")
        print("-" * 70)

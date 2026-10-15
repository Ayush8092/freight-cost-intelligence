"""Answer questions from the pipeline's findings, with optional Groq phrasing."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]


def _select(question: str, findings: pd.DataFrame) -> pd.DataFrame | None:
    q = question.casefold()
    selected = findings.copy()
    cities = {city.casefold() for route in findings["route"].unique() for city in route.split("-")}
    mentioned = {city for city in cities if re.search(rf"\b{re.escape(city)}\b", q)}
    if mentioned:
        selected = selected[selected["route"].apply(lambda route: any(c in route.casefold() for c in mentioned))]
    months = [i for i, month in enumerate(_MONTHS, 1) if re.search(rf"\b{month}\b", q)]
    dates = pd.to_datetime(selected["week_of"])
    if months:
        selected = selected[dates.dt.month.isin(months)]
        dates = pd.to_datetime(selected["week_of"])
    years = [int(year) for year in re.findall(r"\b(20\d{2})\b", q)]
    if years:
        selected = selected[dates.dt.year.isin(years)]
    if not mentioned and not months and not years:
        return None
    return selected


def answer(question: str, findings: pd.DataFrame) -> str:
    """Return matching finding rows without using external knowledge."""
    selected = _select(question, findings)
    if selected is None:
        return "I can answer about routes, months or years in my findings (e.g. 'why did Chennai-Bangalore get pricier in March 2025?')."
    if selected.empty:
        return "None of my findings match that question: no flagged cost rise for those routes and dates."
    lines = []
    for row in selected.itertuples(index=False):
        note = f" (note {row.matched_note_id})" if row.matched_note_id else ""
        lines.append(f"{row.route}, week of {row.week_of}: {row.cost_per_tonne_km} per tonne-km "
                     f"({row.vs_own_history}; {row.vs_similar_routes}). Verdict: {row.flagged}{note}. {row.reason}")
    return "\n".join(lines)


def answer_with_groq(question: str, findings: pd.DataFrame, api_key: str | None = None,
                     model: str | None = None) -> tuple[str, dict]:
    """Use Groq to phrase an answer grounded only in selected pipeline rows."""
    try:
        from dotenv import load_dotenv
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("Groq Q&A needs the optional packages: pip install groq python-dotenv") from exc

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key or key == "put_your_groq_api_key_here":
        raise RuntimeError("Set GROQ_API_KEY in the project .env file before using --groq.")

    selected = _select(question, findings)
    if selected is not None and selected.empty:
        return answer(question, findings), {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0}
    if selected is None:
        selected = findings
    records = selected.to_dict(orient="records")
    prompt = (
        "Answer the user's question using only the supplied FreightLens finding rows. "
        "Do not infer causes that are not present in the reason or invent data. If the rows do not answer it, say so. "
        "Distinguish a statistically flagged increase from whether a context note justifies it. Be concise.\n\n"
        f"Finding rows (JSON):\n{records}\n\nQuestion: {question}"
    )
    client = Groq(api_key=key)
    response = client.chat.completions.create(
        model=model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=500,
    )
    usage = getattr(response, "usage", None)
    usage_log = {
        "model": model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "llm_calls": 1,
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "estimated_cost_usd": None,
        "cost_note": "Not estimated; check current Groq pricing for the selected model.",
    }
    return (response.choices[0].message.content or "The model returned an empty answer."), usage_log

"""Clean Air Window: find the cleanest time to go outside today.

    streamlit run app.py
"""

from __future__ import annotations

import asyncio
import json
import uuid

import acruxcore as acrux
import altair as alt
import pandas as pd
import streamlit as st

from clean_air import config
from clean_air.agent import PlanAnswer, PlanRequest, plan
from clean_air.guidance import find_source
from clean_air.open_meteo import AQI_CATEGORIES

# EPA's own AQI colours, so the chart reads like every AQI map people have seen.
CATEGORY_COLORS = {
    "Good": "#00e400",
    "Moderate": "#ffff00",
    "Unhealthy for Sensitive Groups": "#ff7e00",
    "Unhealthy": "#ff0000",
    "Very Unhealthy": "#8f3f97",
    "Hazardous": "#7e0023",
}
ACTIVITIES = ["walk", "run", "bike ride", "outdoor workout", "kids' play time", "picnic"]
SENSITIVE_GROUPS = ["asthma or lung disease", "heart disease", "child or teenager", "older adult", "outdoor worker"]
TOOL_LABELS = {
    "get_air_and_weather": "Checking today's air quality and weather",
    "search_health_guidance": "Reading the EPA health guidance",
}

st.set_page_config(page_title="Clean Air Window", page_icon="🌿", layout="centered")
st.markdown(
    """
    <style>
      .block-container { max-width: 760px; padding-top: 2.5rem; }
      .verdict { border-left: 8px solid var(--c); background: rgba(127,127,127,.08);
                 border-radius: 10px; padding: 1rem 1.25rem; margin: .5rem 0 1rem; }
      .verdict .when { font-size: 2.1rem; font-weight: 700; line-height: 1.15; }
      .verdict .facts { opacity: .8; margin-top: .35rem; }
      .footnote { font-size: .85rem; opacity: .7; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🌿 Clean Air Window")
st.caption("The cleanest time to go outside today, from the hourly air forecast and the EPA's health guidance.")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

with st.form("plan"):
    city = st.text_input("City", value="Lahore")
    left, right = st.columns(2)
    activity = left.selectbox("Activity", ACTIVITIES)
    duration = right.slider("Minutes", 15, 120, 45, step=15)
    free = st.slider("I'm free between", 0, 24, (15, 21), format="%d:00")
    groups = st.multiselect("Anyone going in an EPA sensitive group? (optional)", SENSITIVE_GROUPS)
    submitted = st.form_submit_button("Find my window", type="primary", width="stretch")


def category_of(aqi: float) -> str:
    return next(name for upper, name in AQI_CATEGORIES if aqi <= upper)


def verdict_html(best: dict, data: dict) -> str:
    color = CATEGORY_COLORS[best["category"]]
    lead = "Go" if best["worst_aqi"] <= 100 else "Best option"
    return f"""
    <div class="verdict" style="--c:{color}">
      <div class="when">{lead} {best['start']} – {best['end']}</div>
      <div class="facts">AQI {best['worst_aqi']} · {best['category']} · {best['temperature_c']}°C ·
        sunset {data['sunset']} · {data['place']}</div>
    </div>"""


def aqi_chart(data: dict, best: dict, free_from: int, free_until: int) -> alt.Chart:
    rows = [{"hour": int(h), "aqi": aqi, "category": category_of(aqi)} for h, aqi in data["hourly_aqi"].items()]
    df = pd.DataFrame(rows)
    df["label"] = df["hour"].map(lambda h: f"{h:02d}:00")
    best_start, best_end = int(best["start"][:2]), int(best["end"][:2]) or 24
    x = alt.X("hour:Q", scale=alt.Scale(domain=[0, 24]), axis=alt.Axis(values=list(range(0, 25, 3)), format="02d", title=None))
    free_band = (
        alt.Chart(pd.DataFrame([{"a": free_from, "b": free_until}]))
        .mark_rect(opacity=0.10, color="#4c78a8")
        .encode(x="a:Q", x2="b:Q")
    )
    bars = (
        alt.Chart(df)
        .mark_bar(width=14, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=x,
            y=alt.Y("aqi:Q", title="U.S. AQI"),
            color=alt.Color(
                "category:N",
                scale=alt.Scale(domain=list(CATEGORY_COLORS), range=list(CATEGORY_COLORS.values())),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            opacity=alt.condition(
                (alt.datum.hour >= best_start) & (alt.datum.hour < best_end), alt.value(1.0), alt.value(0.45)
            ),
            tooltip=[alt.Tooltip("label:N", title="Hour"), "aqi:Q", "category:N"],
        )
    )
    sunset = (
        alt.Chart(pd.DataFrame([{"h": int(data["sunset"][:2]) + int(data["sunset"][3:]) / 60, "t": "sunset"}]))
        .mark_rule(strokeDash=[4, 4], color="#888")
        .encode(x="h:Q")
    )
    return (free_band + bars + sunset).properties(height=230)


def show_plan(result: dict, verdict_slot, chart_slot) -> None:
    """Draw the verdict card and the chart from a get_air_and_weather result."""
    data, best = result["data"], result["data"].get("best_window")
    if not best:
        verdict_slot.warning("Your free time is shorter than the activity. Widen the hours or shorten it.")
        return
    verdict_slot.markdown(verdict_html(best, data), unsafe_allow_html=True)
    chart_slot.altair_chart(aqi_chart(data, best, result["free_from"], result["free_until"]), width="stretch")


def answer_markdown(answer: PlanAnswer) -> str:
    """The model's typed answer as three labelled paragraphs, with the source linked."""
    source = find_source(answer.source_title)
    cite = f"[{source[0]}]({source[1]})" if source else answer.source_title
    return f"**Why this time:** {answer.why}\n\n**For you:** {answer.for_you} *Source: {cite}*\n\n**Tip:** {answer.tip}"


async def run(request: PlanRequest) -> None:
    """Stream one plan into the page and keep it in session state for later reruns."""
    status = st.status("Planning…", expanded=False)
    verdict_slot, chart_slot, text_slot = st.empty(), st.empty(), st.empty()
    result = {"free_from": request.free_from_hour, "free_until": request.free_until_hour, "text": ""}
    async for event in plan(request, session_id=st.session_state.session_id):
        if event.type == "tool_call":
            status.update(label=TOOL_LABELS.get(event.name, event.name) + "…")
            status.write(f"`{event.name}` {event.arguments}")
        elif event.type == "tool_result" and event.name == "get_air_and_weather" and not event.error:
            result["data"] = event.result
            show_plan(result, verdict_slot, chart_slot)
        elif event.type == "content" and not result["text"]:
            # The answer arrives as JSON; show progress, not half-written braces.
            status.update(label="Writing your plan…")
            result["text"] = " "
        elif event.type == "done":
            result["trace_id"] = event.result.trace_id
            result["text"] = answer_markdown(PlanAnswer.model_validate(json.loads(event.result.content)))
            text_slot.markdown(result["text"])
            status.update(label=f"Done in {event.result.iterations} model calls", state="complete")
    st.session_state.result = result


if submitted:
    request = PlanRequest(city, activity, duration, free[0], free[1], groups)
    st.session_state.pop("result", None)
    st.session_state.pop("feedback_sent", None)
    try:
        asyncio.run(run(request))
    except Exception as exc:  # shown to the user, not swallowed
        st.error(f"Could not make a plan: {exc}")
elif (saved := st.session_state.get("result")) and "data" in saved:
    show_plan(saved, st.empty(), st.empty())
    st.markdown(saved["text"])


async def send_feedback(trace_id: str, went: bool) -> None:
    async with acrux.AcruxCore(api_key=config.ACRUXCORE_API_KEY, base_url=config.ACRUXCORE_BASE_URL) as hub:
        await hub.traces.submit_feedback(
            trace_id, rating=1 if went else -1, label="went-outside" if went else "stayed-in", source="end_user"
        )


if trace_id := st.session_state.get("result", {}).get("trace_id"):
    st.divider()
    if st.session_state.get("feedback_sent"):
        st.success("Thanks. That answer is now marked on its trace.")
    else:
        st.write("**Did you go?**")
        yes, no, _ = st.columns([1, 1, 2])
        if yes.button("🌿 I went outside", width="stretch"):
            asyncio.run(send_feedback(trace_id, True))
            st.session_state.feedback_sent = True
            st.rerun()
        if no.button("Stayed in", width="stretch"):
            asyncio.run(send_feedback(trace_id, False))
            st.session_state.feedback_sent = True
            st.rerun()
    st.markdown(
        f'<div class="footnote">Model: {config.CHAT_MODEL} (open weights, via OpenRouter) · '
        f'<a href="{config.ACRUXCORE_DASHBOARD_URL}/traces/{trace_id}" target="_blank">open this trace in AcruxCore</a> · '
        'Air data: <a href="https://open-meteo.com/" target="_blank">Open-Meteo</a> (CC BY 4.0)</div>',
        unsafe_allow_html=True,
    )

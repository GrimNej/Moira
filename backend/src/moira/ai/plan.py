"""PLAN (§8.4, §9.8.4): turn a question into a search plan. Code resolves the time text."""

from moira.ai import prompts
from moira.ai.client import LLM, InputPart
from moira.ai.prompts import escape
from moira.ai.schemas import PlanOutput


async def plan(llm: LLM, question: str, conversation: str, *, user_id: int | None) -> PlanOutput:
    text = (
        f"<question>{escape(question)}</question>\n"
        f"<conversation>\n{conversation or '(none)'}\n</conversation>"
    )
    return await llm.structured(
        prompt=prompts.load("plan"),
        inputs=[InputPart(text=text)],
        schema=PlanOutput,
        effort="minimal",
        max_output_tokens=400,
        timeout_s=20,
        user_id=user_id,
        kind="plan",
    )

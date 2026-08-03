from typing import Any

from app.services.scoring import get_program_requirements
from app.services.visa_finance import get_student_visa_finance


async def get_program_financial_items(program_id: str) -> list[dict[str, Any]] | None:
    """Financial Requirements for one program, straight from GOA-108's visa data.

    Deliberately does not go through /score: that pipeline also fetches the user's
    CV and runs the LLM boost stage (GOA-012), neither of which this needs and both
    of which are slow and costly to trigger just to read currency/pathway data.
    get_student_visa_finance() takes only a country and touches no LLM, so this is a
    thin, read-only join of two already-complete pieces (program -> country ->
    visa_requirements.proof_of_funds) — nothing here is generated, only looked up.

    Returns None if the program itself doesn't exist (caller maps that to 404), or an
    empty list if the program's country has no supported visa data (caller omits the
    Financial Requirements phase entirely rather than rendering nothing under a
    heading -- GOA-035's AC).
    """
    program = await get_program_requirements(program_id)
    if program is None:
        return None
    if not program.country:
        return []
    return await get_student_visa_finance(program.country)

from app.schemas.scoring import UserProfile, ProgramRequirements, GateResult

# Documented reserved gates that we must NOT evaluate in Sprint 2
RESERVED_GATES = ["age", "prerequisites"]


# Academic ladder, low to high. The profile states the degree the candidate
# HOLDS (the wizard's Academic step asks "Select your degree"); a program's
# degree_level states the level the program IS. Admission needs the rung below,
# not the same rung.
_DEGREE_RANK = {
    "diploma": 0,
    "associate": 0,
    "foundation": 0,
    "bachelor": 1,
    "bachelors": 1,
    "bachelor's": 1,
    "bsc": 1,
    "ba": 1,
    "beng": 1,
    "undergraduate": 1,
    "master": 2,
    "masters": 2,
    "master's": 2,
    "msc": 2,
    "ma": 2,
    "meng": 2,
    "mba": 2,
    "graduate": 2,
    "phd": 3,
    "ph.d.": 3,
    "doctorate": 3,
    "doctoral": 3,
}


def degree_rank(value: str | None) -> int | None:
    """Rank a free-text degree level, or None when it is not recognised."""
    if not value or not value.strip():
        return None
    return _DEGREE_RANK.get(value.strip().lower().replace(" ", ""))


def comparable_gpa(
    value: float | None, scale: str, required: float | None
) -> float | None:
    """Put a profile GPA on the same common scale as the catalogue minimum."""
    if value is None or required is None:
        return value
    if scale == "100" and required <= 4.0:
        return value / 25.0
    if scale != "100" and required > 4.0:
        return value * 25.0
    return value


def check_hard_gates(profile: UserProfile, program: ProgramRequirements) -> GateResult:
    if program.min_ects is not None:
        if profile.ects is None or profile.ects < program.min_ects:
            return GateResult(
                passed=False,
                reason=f"Requires {program.min_ects} ECTS",
                gateType="ects",
            )

    if program.degree_level is not None:
        # Prerequisite comparison, not exact equality.
        #
        # This gate used to demand profile.degreeLevel == program.degree_level.
        # The catalogue is entirely 'Master' programmes and the profile holds the
        # degree the candidate has ALREADY EARNED, so every honest applicant --
        # a Bachelor's graduate looking for a Master's, i.e. the product's whole
        # target user -- was hard-blocked from all 12 programmes with "Requires
        # Master degree". Holding a Bachelor's is the normal prerequisite FOR a
        # Master's, not a disqualification from one.
        #
        # Migration 028 documents having hit exactly this and worked around it by
        # seeding the demo profile as degree_level='Master' so the demo would
        # return non-blocked results. That workaround is what this fix removes
        # the need for; the seed stays valid either way (an over-qualified
        # applicant is not blocked).
        #
        # Exact equality also made the comparison string-literal: the frontend
        # sends 'Bachelors'/'Masters' (DEGREE_LEVELS in lib/reference-data.ts)
        # while the catalogue stores 'Master', so it could not have matched even
        # under the old reading. Ranking both sides removes that second trap.
        program_level = degree_rank(program.degree_level)
        holder_level = degree_rank(profile.degreeLevel)

        # An unrecognised value on either side disables the gate rather than
        # blocking: a vocabulary this code has not seen is not evidence that the
        # candidate is unqualified, and silently emptying the results is the
        # worse failure. Genuinely missing profile data is still blocked below.
        if program_level is not None:
            if holder_level is None:
                if profile.degreeLevel is None or not str(profile.degreeLevel).strip():
                    return GateResult(
                        passed=False,
                        reason=f"Requires a {program.degree_level}-level qualification",
                        gateType="degree_level",
                    )
            elif holder_level < program_level - 1:
                return GateResult(
                    passed=False,
                    reason=f"Requires a {program.degree_level}-level qualification",
                    gateType="degree_level",
                )

    if program.required_citizenship is not None:
        if (
            not profile.citizenship
            or profile.citizenship != program.required_citizenship
        ):
            return GateResult(
                passed=False,
                reason=f"Requires {program.required_citizenship} citizenship",
                gateType="citizenship",
            )

    if program.min_ielts is not None and (
        profile.ieltsScore is None or profile.ieltsScore < program.min_ielts
    ):
        return GateResult(
            passed=False,
            reason=f"Requires IELTS {program.min_ielts}",
            gateType="ielts",
        )

    profile_gpa = comparable_gpa(profile.gpa, profile.gpaScale, program.min_gpa)
    if program.min_gpa is not None and (
        profile_gpa is None or profile_gpa < program.min_gpa
    ):
        return GateResult(
            passed=False,
            reason=f"Requires GPA {program.min_gpa}",
            gateType="gpa",
        )

    if program.min_work_experience is not None and (
        profile.workExperienceYears < program.min_work_experience
    ):
        return GateResult(
            passed=False,
            reason=f"Requires {program.min_work_experience} years of work experience",
            gateType="work_experience",
        )

    return GateResult(passed=True, reason=None, gateType=None)

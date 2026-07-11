from app.schemas.scoring import UserProfile, ProgramRequirements, GateResult

# Documented reserved gates that we must NOT evaluate in Sprint 2
RESERVED_GATES = ["age", "prerequisites"]


def check_hard_gates(profile: UserProfile, program: ProgramRequirements) -> GateResult:
    if program.min_ects is not None:
        if profile.ects is None or profile.ects < program.min_ects:
            return GateResult(passed=False, reason=f"Requires {program.min_ects} ECTS", gateType="ects")


    if program.degree_level is not None:
        if profile.degreeLevel != program.degree_level:
            return GateResult(passed=False, reason=f"Requires {program.degree_level} degree", gateType="degree_level")


    if program.required_citizenship is not None:
        if not profile.citizenship or profile.citizenship != program.required_citizenship:
            return GateResult(
                passed=False, 
                reason=f"Requires {program.required_citizenship} citizenship", 
                gateType="citizenship"
            )


    return GateResult(passed=True, reason=None, gateType=None)

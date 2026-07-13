from app.schemas.scoring import UserProfile, ProgramRequirements
from app.services.gates import check_hard_gates


def test_ects_gate_fails():
    profile = UserProfile(userId="1", ects=100)
    program = ProgramRequirements(id="p1", min_ects=120)
    result = check_hard_gates(profile, program)
    assert result.passed is False
    assert result.gateType == "ects"


def test_degree_level_fails():
    profile = UserProfile(userId="1", degreeLevel="Bachelor")
    program = ProgramRequirements(id="p1", degree_level="Master")
    result = check_hard_gates(profile, program)
    assert result.passed is False
    assert result.gateType == "degree_level"


def test_citizenship_fails():
    profile = UserProfile(userId="1", citizenship="US")
    program = ProgramRequirements(id="p1", required_citizenship="EU")
    result = check_hard_gates(profile, program)
    assert result.passed is False
    assert result.gateType == "citizenship"


def test_all_gates_pass():
    profile = UserProfile(userId="1", ects=120, degreeLevel="Master", citizenship="EU")
    program = ProgramRequirements(
        id="p1", min_ects=120, degree_level="Master", required_citizenship="EU"
    )
    result = check_hard_gates(profile, program)
    assert result.passed is True

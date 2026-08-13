from app.schemas.scoring import UserProfile, ProgramRequirements
from app.services.gates import check_hard_gates


def test_ects_gate_fails():
    profile = UserProfile(userId="1", ects=100)
    program = ProgramRequirements(id="p1", min_ects=120)
    result = check_hard_gates(profile, program)
    assert result.passed is False
    assert result.gateType == "ects"


def test_bachelor_holder_is_eligible_for_a_master_program():
    """The rung below is the PREREQUISITE, not a disqualification.

    This asserted the opposite until the degree gate was fixed. Exact equality
    meant a Bachelor's graduate -- the product's entire target user -- was hard
    blocked from all 12 Master's programmes in the catalogue, and migration 028
    had to seed the demo profile as degree_level='Master' to get any non-blocked
    result on screen at all.
    """
    profile = UserProfile(userId="1", degreeLevel="Bachelor")
    program = ProgramRequirements(id="p1", degree_level="Master")
    result = check_hard_gates(profile, program)
    assert result.passed is True


def test_frontend_plural_vocabulary_is_accepted():
    """lib/reference-data.ts sends 'Bachelors'; the catalogue stores 'Master'."""
    profile = UserProfile(userId="1", degreeLevel="Bachelors")
    program = ProgramRequirements(id="p1", degree_level="Master")
    assert check_hard_gates(profile, program).passed is True


def test_degree_level_blocks_the_genuinely_underqualified():
    """Two rungs down is still a real block -- a diploma is not a PhD entry."""
    profile = UserProfile(userId="1", degreeLevel="Diploma")
    program = ProgramRequirements(id="p1", degree_level="PhD")
    result = check_hard_gates(profile, program)
    assert result.passed is False
    assert result.gateType == "degree_level"


def test_missing_degree_level_still_blocks():
    profile = UserProfile(userId="1", degreeLevel=None)
    program = ProgramRequirements(id="p1", degree_level="Master")
    result = check_hard_gates(profile, program)
    assert result.passed is False
    assert result.gateType == "degree_level"


def test_unrecognised_vocabulary_does_not_block():
    """An unknown qualification name is missing knowledge, not missing merit."""
    profile = UserProfile(userId="1", degreeLevel="Licenciatura")
    program = ProgramRequirements(id="p1", degree_level="Master")
    assert check_hard_gates(profile, program).passed is True


def test_overqualified_is_not_blocked():
    profile = UserProfile(userId="1", degreeLevel="PhD")
    program = ProgramRequirements(id="p1", degree_level="Master")
    assert check_hard_gates(profile, program).passed is True


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

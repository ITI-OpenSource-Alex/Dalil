from app.schemas.scoring import UserProfile, ProgramRequirements


def generate_gap_report(profile: UserProfile, program: ProgramRequirements) -> dict:
    """
    Evaluates the profile against the program requirements and returns a dictionary
    of actionable gaps for the user to improve upon.
    """

    gaps = {}

    # IELTS
    if program.min_ielts is not None:
        if profile.ieltsScore is None:
            gaps["ielts"] = {
                "type": "actionable",
                "message": f"Missing IELTS score. Program requires {program.min_ielts}."
            }
        elif profile.ieltsScore < program.min_ielts:
            gaps["ielts"] = {
                "type": "actionable",
                "message": f"IELTS {profile.ieltsScore} is below required {program.min_ielts}."
            }

    # GPA Gap
    if program.min_gpa is not None:
        if profile.gpa is None:
            gaps["gpa"] = {
                "type": "actionable",
                "message": f"Missing GPA. Program requires {program.min_gpa}."
            }
        elif profile.gpaScale == "100" and program.min_gpa <= 4.0:
            pass  # Basic conversion edge case handling skipped for now
        elif profile.gpa < program.min_gpa:
            gaps["gpa"] = {
                "type": "actionable",
                "message": f"GPA {profile.gpa} is below required {program.min_gpa}."
            }

    # Work Experience Gap
    if program.min_work_experience is not None:
        if profile.workExperienceYears < program.min_work_experience:
            gaps["work_experience"] = {
                "type": "actionable",
                "message": f"Requires {program.min_work_experience} years of experience, but you have {profile.workExperienceYears}."
            }

    return gaps

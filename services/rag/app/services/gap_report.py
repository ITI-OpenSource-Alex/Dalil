from app.schemas.scoring import UserProfile, ProgramRequirements
from app.services.gates import comparable_gpa, degree_rank


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
                "message": f"Missing IELTS score. Program requires {program.min_ielts}.",
            }
        elif profile.ieltsScore < program.min_ielts:
            gaps["ielts"] = {
                "type": "actionable",
                "message": f"IELTS {profile.ieltsScore} is below required {program.min_ielts}.",
            }

    # GPA Gap
    if program.min_gpa is not None:
        if profile.gpa is None:
            gaps["gpa"] = {
                "type": "actionable",
                "message": f"Missing GPA. Program requires {program.min_gpa}.",
            }
        elif (
            comparable_gpa(profile.gpa, profile.gpaScale, program.min_gpa)
            < program.min_gpa
        ):
            gaps["gpa"] = {
                "type": "actionable",
                "message": f"GPA {profile.gpa} is below required {program.min_gpa}.",
            }

    # Work Experience Gap
    if program.min_work_experience is not None:
        if profile.workExperienceYears < program.min_work_experience:
            gaps["work_experience"] = {
                "type": "actionable",
                "message": f"Requires {program.min_work_experience} years of experience, but you have {profile.workExperienceYears}.",
            }

    if program.min_ects is not None:
        if profile.ects is None:
            gaps["ects"] = {
                "type": "actionable",
                "message": f"Missing ECTS total. Program requires {program.min_ects} ECTS.",
            }
        elif profile.ects < program.min_ects:
            gaps["ects"] = {
                "type": "actionable",
                "message": f"You have {profile.ects} ECTS; the program requires {program.min_ects}.",
            }

    if program.degree_level:
        programme_rank = degree_rank(program.degree_level)
        holder_rank = degree_rank(profile.degreeLevel)
        if programme_rank is not None and (
            holder_rank is None or holder_rank < programme_rank - 1
        ):
            gaps["degree_level"] = {
                "type": "actionable",
                "message": f"The program requires a qualification suitable for {program.degree_level}-level entry.",
            }

    if (
        program.required_citizenship
        and profile.citizenship != program.required_citizenship
    ):
        gaps["citizenship"] = {
            "type": "eligibility",
            "message": f"The program is restricted to {program.required_citizenship} citizens.",
        }

    return gaps

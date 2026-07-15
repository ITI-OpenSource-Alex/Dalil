from pydantic import BaseModel, Field
from typing import List, Optional


class UserProfile(BaseModel):
    userId: str
    degreeLevel: Optional[str] = None
    gpa: Optional[float] = None
    ieltsScore: Optional[float] = None
    major: Optional[str] = None
    targetCountries: List[str] = Field(default_factory=list)
    fieldOfStudy: Optional[str] = None
    ects: Optional[int] = None
    workExperienceYears: int = 0
    extracurricularsScore: int = 0
    gpaScale: str = "100"
    citizenship: Optional[str] = None


class ProgramRequirements(BaseModel):
    id: str
    min_ects: Optional[int] = None
    degree_level: Optional[str] = None
    required_citizenship: Optional[str] = None
    min_ielts: Optional[float] = None
    min_gpa: Optional[float] = None
    min_work_experience: Optional[int] = None


class GateResult(BaseModel):
    passed: bool
    reason: Optional[str] = None
    gateType: Optional[str] = None


class ScoreRequest(BaseModel):
    userId: str
    programId: str


class MatchRequest(BaseModel):
    userId: str

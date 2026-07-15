from enum import Enum


class ExamType(str, Enum):
    """Supported IELTS exam variants."""

    ACADEMIC = "academic"
    GENERAL = "general"


class SkillArea(str, Enum):
    """Supported IELTS skill areas."""

    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"


class SessionStatus(str, Enum):
    """Lifecycle states for an IELTS exam session."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    SCORED = "scored"

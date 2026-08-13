from enum import StrEnum

from pydantic import BaseModel


class ResourceProvider(StrEnum):
    RODHA = "RODHA"
    TWO_IIM = "2IIM"
    IMS = "IMS"
    VARC1000 = "VARC1000"
    GMAC = "GMAC"
    CAT_PYQ = "CAT_PYQ"
    TIME = "TIME"
    CAREER_LAUNCHER = "CAREER_LAUNCHER"
    USER = "USER"


class ResourcePurpose(StrEnum):
    LEARN = "LEARN"
    PRACTICE = "PRACTICE"
    PYQ = "PYQ"
    REVISION = "REVISION"
    SECTIONAL = "SECTIONAL"
    MOCK = "MOCK"


class ProgressionLevel(StrEnum):
    FOUNDATION = "FOUNDATION"
    INTERMEDIATE = "INTERMEDIATE"
    CAT_LEVEL = "CAT_LEVEL"
    TIMED = "TIMED"
    MIXED = "MIXED"


class CatPriority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TimeFoundationTest(BaseModel):
    id: int | None = None
    test_reference: str
    provider_title: str
    subject: str
    level: str = "FOUNDATION"
    category: str | None = None
    canonical_topic_group: str | None = None
    canonical_topic: str | None = None
    cat_priority: CatPriority = CatPriority.MEDIUM
    cat_core: bool = True
    active: bool = True


class AimcatStatus(StrEnum):
    PAST = "PAST"
    UPCOMING = "UPCOMING"
    AVAILABLE = "AVAILABLE"
    PLANNED = "PLANNED"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    ANALYSIS_DUE = "ANALYSIS_DUE"


class AimcatSchedule(BaseModel):
    id: int | None = None
    provider: str = "TIME"
    series: str = "AIMCAT"
    test_ref: str
    start_date: str
    end_date: str
    preferred_attempt_date: str
    planned_attempt_date: str | None = None
    actual_attempt_date: str | None = None
    status: AimcatStatus = AimcatStatus.UPCOMING
    historical: bool = False
    skipped: bool = False
    converted_to_additional: bool = False
    manual_override: bool = False
    analysis_completed: bool = False
    resolve_completed: bool = False
    mock_id: int | None = None


class StudyResource(BaseModel):
    id: str
    provider: ResourceProvider
    title: str
    description: str = ""
    subject: str
    topic_slug: str | None = None
    type: str
    url: str | None = None
    platform_path: str | None = None
    free: bool = False
    requires_subscription: bool = False
    estimated_minutes: int | None = None
    recommended_question_count: int | None = None
    difficulty: str | None = None
    active: bool = True
    last_verified_at: str | None = None


class TopicResourceMap(BaseModel):
    topic_id: int
    resource_id: str
    purpose: ResourcePurpose
    priority: int = 100
    phase: str | None = None


class UserResourceAccess(BaseModel):
    resource_provider: ResourceProvider
    enabled: bool
    subscription_name: str = ""
    notes: str = ""


class TaskResourceAssignment(BaseModel):
    id: int | None = None
    task_id: int
    resource_id: str
    stage: ResourcePurpose
    stage_order: int = 0
    estimated_minutes: int = 0
    target_count: int = 0
    accuracy_target: float = 0
    selected_reason: str = ""
    manual_override: bool = False
    completed: bool = False
    difficulty: ProgressionLevel = ProgressionLevel.FOUNDATION


class TaskResult(BaseModel):
    task_id: int
    attempted: int = 0
    correct: int = 0
    time_spent: int = 0
    confidence: int = 3
    accuracy: float = 0
    average_time: float = 0
    notes: str = ""
    dilr_solved: bool | None = None
    dilr_sets_solved: int = 0
    dilr_representation: str | None = None
    dilr_selectability: str | None = None
    varc_error_pattern: str | None = None


class TopicPerformanceEvent(BaseModel):
    topic_id: int
    source_type: str
    source_id: int
    occurred_on: str
    attempted: int = 0
    correct: int = 0
    accuracy: float = 0
    time_spent: int = 0
    confidence: int = 3
    difficulty: ProgressionLevel = ProgressionLevel.FOUNDATION


class RevisionSchedule(BaseModel):
    topic_id: int
    due_date: str
    interval_index: int = 0
    status: str = "PENDING"
    source_task_id: int | None = None

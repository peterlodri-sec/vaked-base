from pydantic import BaseModel


class SectionAssignment(BaseModel):
    orchestration_focus: str
    kernel_focus: str
    languages_focus: str
    confident: bool


class CandidateFinding(BaseModel):
    specialist: str = ""
    rfc_id: str = ""
    section_ref: str = ""
    finding_type: str = ""
    description: str = ""
    supporting_quote: str = ""
    severity: str = "minor"
    needs_cross_ref: bool = False
    cross_ref_target: str = ""
    confident: bool = True


class CrossRefAnalysis(BaseModel):
    section_ref: str
    new_findings: list[str]
    confident: bool


class Verdict(BaseModel):
    verdict: str  # "confirmed" | "refuted" | "uncertain"
    refutation_argument: str
    confident: bool


class CoherenceReport(BaseModel):
    executive_summary: str
    confirmed_critical: list[str]
    confirmed_major: list[str]
    uncertain_items: list[str]
    total_candidates: int
    total_confirmed: int
    confident: bool

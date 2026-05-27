from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class DisabilityCategory(str, Enum):
    DYSLEXIA           = "Dyslexia"
    DYSGRAPHIA         = "Dysgraphia"
    DYSCALCULIA        = "Dyscalculia"
    ASD                = "Autism Spectrum Disorder"
    ADHD               = "ADHD"
    VISUAL_IMPAIRMENT  = "Visual Impairment"
    HEARING_IMPAIRMENT = "Hearing Impairment"
    INTELLECTUAL       = "Intellectual Disability"
    CEREBRAL_PALSY     = "Cerebral Palsy"
    SPEECH_LANGUAGE    = "Speech and Language Disability"
    MULTIPLE           = "Multiple Disabilities"
    OTHER              = "Other"


class DisabilitySeverity(str, Enum):
    MILD     = "mild"
    MODERATE = "moderate"
    SEVERE   = "severe"


class StudentInput(BaseModel):
    student_name:         str = Field(..., min_length=2,  max_length=100,
                                      description="Full name of the student")
    age:                  int = Field(..., ge=3, le=25,
                                      description="Student age in years")
    grade:                str = Field(..., max_length=20,
                                      description="Current grade e.g. Grade 4")
    school_name:          str = Field(..., max_length=200,
                                      description="Full school name")
    disability_category:  DisabilityCategory = Field(...,
                                      description="Disability type per RPwD Act 2016")
    disability_severity:  DisabilitySeverity = Field(
                                      DisabilitySeverity.MILD,
                                      description="Severity: mild / moderate / severe")
    raw_notes:            str = Field(..., min_length=50,
                                      description="Teacher observations (min 50 chars)")
    academic_history:     Optional[str] = Field(None,
                                      description="Past academic performance")
    teacher_observations: Optional[str] = Field(None,
                                      description="Classroom behaviour notes")
    parent_concerns:      Optional[str] = Field(None,
                                      description="Parent submitted concerns")

    model_config = {
        "json_schema_extra": {
            "example": {
                "student_name":         "Arjun Sharma",
                "age":                  10,
                "grade":                "Grade 4",
                "school_name":          "Delhi Public School, Bengaluru",
                "disability_category":  "Dyslexia",
                "disability_severity":  "moderate",
                "raw_notes":            (
                    "Arjun struggles with reading and written expression. "
                    "He reverses letters like b/d and p/q. However he excels "
                    "in oral discussions and shows exceptional spatial reasoning."
                ),
                "academic_history":     "Grade 2: 58%, Grade 3: 62%",
                "teacher_observations": "Loses focus during reading. Engaged in group work.",
                "parent_concerns":      "Child gets frustrated with reading at home.",
            }
        }
    }


class IEPResponse(BaseModel):
    iep_id:            str
    student_name:      str
    workflow_status:   str
    compliance_status: str
    pdf_output_path:   Optional[str] = None
    generated_at:      Optional[str] = None
    errors:            List[str]     = []
    message:           str
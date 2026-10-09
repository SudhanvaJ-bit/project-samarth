"""
eval_paper.py
Generates all evaluation data needed for the paper.
Run once — saves results to eval_results.json
"""

import json
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialise ChromaDB retriever before pipeline runs
from rag.retriever import initialize_retriever
initialize_retriever("./rag/documents")

from agents.graph import run_iep_pipeline

# ── 15 test students across 5 disabilities ─────────────

STUDENTS = [
    # DYSLEXIA
    {
        "student_name": "Arjun Sharma", "age": 10, "grade": "Grade 4",
        "school_name": "Delhi Public School, Bengaluru",
        "disability_category": "Dyslexia", "disability_severity": "moderate",
        "raw_notes": "Arjun struggles with reading and written expression. Reverses letters b/d and p/q. Excels in oral discussions, spatial reasoning, and mathematics. Strong verbal memory. Creative and enthusiastic learner.",
        "academic_history": "Grade 3: 62%. Below average English, average Maths.",
        "teacher_observations": "Loses focus during reading. Engaged in group discussions.",
        "parent_concerns": "Gets frustrated with reading homework."
    },
    {
        "student_name": "Priya Iyer", "age": 8, "grade": "Grade 2",
        "school_name": "Kendriya Vidyalaya, Chennai",
        "disability_category": "Dyslexia", "disability_severity": "mild",
        "raw_notes": "Priya has mild difficulty decoding words and spelling. Strong comprehension when text is read aloud. Good at art and creative writing ideas when scribed. Friendly and participates in class discussions.",
        "academic_history": "Grade 1: 70%. Weak in reading fluency.",
        "teacher_observations": "Slow reader but understands content well when heard.",
        "parent_concerns": "Worried about upcoming reading tests."
    },
    {
        "student_name": "Kiran Reddy", "age": 12, "grade": "Grade 6",
        "school_name": "Navodaya Vidyalaya, Hyderabad",
        "disability_category": "Dyslexia", "disability_severity": "severe",
        "raw_notes": "Kiran has severe dyslexia with significant phonological processing difficulties. Cannot decode unfamiliar words. However demonstrates exceptional mathematical reasoning and strong spatial intelligence. Very motivated despite challenges.",
        "academic_history": "Grade 5: 45% overall. Strong in Maths (72%), very weak in languages.",
        "teacher_observations": "Cannot read independently. Requires all text read aloud.",
        "parent_concerns": "Very concerned about secondary school transition."
    },
    # ASD
    {
        "student_name": "Ravi Nair", "age": 9, "grade": "Grade 3",
        "school_name": "VIBGYOR High, Pune",
        "disability_category": "Autism Spectrum Disorder",
        "disability_severity": "mild",
        "raw_notes": "Ravi has difficulty with social interactions and unstructured activities. Prefers routines and gets distressed by sudden changes. Exceptional memory for facts and strong in mathematics and science. Communicates well one-on-one.",
        "academic_history": "Grade 2: 75%. Strong academics, weak social participation.",
        "teacher_observations": "Works best with structured tasks. Sensitive to noise.",
        "parent_concerns": "Social isolation during lunch and recess."
    },
    {
        "student_name": "Anjali Menon", "age": 11, "grade": "Grade 5",
        "school_name": "Amrita Vidyalayam, Kochi",
        "disability_category": "Autism Spectrum Disorder",
        "disability_severity": "moderate",
        "raw_notes": "Anjali has moderate ASD with limited verbal communication. Uses AAC device effectively. Strong visual learner with excellent pattern recognition. Struggles with group work and transitions between activities.",
        "academic_history": "Grade 4: 58%. Strong in visual subjects, weak in language.",
        "teacher_observations": "Communicates via AAC. Meltdowns during unstructured time.",
        "parent_concerns": "Communication skills and peer relationships."
    },
    {
        "student_name": "Dev Pillai", "age": 7, "grade": "Grade 1",
        "school_name": "Ryan International, Mumbai",
        "disability_category": "Autism Spectrum Disorder",
        "disability_severity": "severe",
        "raw_notes": "Dev has severe ASD with minimal verbal communication. Communicates through pictures and gestures. Strong visual-spatial skills. Requires 1:1 support for all classroom activities. Sensory sensitivities to light and sound.",
        "academic_history": "Kindergarten: Participated with full support.",
        "teacher_observations": "Needs constant adult support. Visual schedules essential.",
        "parent_concerns": "Communication, self-care, and classroom inclusion."
    },
    # VISUAL IMPAIRMENT
    {
        "student_name": "Rahul Verma", "age": 14, "grade": "Grade 9",
        "school_name": "Navodaya Vidyalaya, Pune",
        "disability_category": "Visual Impairment",
        "disability_severity": "moderate",
        "raw_notes": "Rahul has low vision and requires large print materials. Academically strong and highly motivated. Excellent in oral work, mathematics, and science. Struggles with standard printed textbooks. Uses magnifier currently.",
        "academic_history": "Grade 8: 78%. Strong across subjects with support.",
        "teacher_observations": "Needs front seating and large print. Very motivated.",
        "parent_concerns": "Board exam accommodations and college admission."
    },
    {
        "student_name": "Meena Krishnan", "age": 10, "grade": "Grade 4",
        "school_name": "Little Flower School, Bengaluru",
        "disability_category": "Visual Impairment",
        "disability_severity": "severe",
        "raw_notes": "Meena is blind and reads Braille. Strong auditory learner with excellent memory. Good at mathematics when using tactile materials. Needs all visual content described or provided in accessible format.",
        "academic_history": "Grade 3: 68%. Consistent performance with Braille materials.",
        "teacher_observations": "Excels when materials are accessible. Socially well-adjusted.",
        "parent_concerns": "Availability of Braille textbooks and assistive devices."
    },
    {
        "student_name": "Suresh Babu", "age": 16, "grade": "Grade 11",
        "school_name": "Government High School, Mysuru",
        "disability_category": "Visual Impairment",
        "disability_severity": "mild",
        "raw_notes": "Suresh has mild visual impairment corrected partially by glasses. Struggles in low-light conditions and with small print. Strong student academically. Preparing for board exams and engineering entrance.",
        "academic_history": "Grade 10: 82%. Top student with appropriate accommodations.",
        "teacher_observations": "Performs well with large print and good lighting.",
        "parent_concerns": "Accommodation support for competitive entrance exams."
    },
    # HEARING IMPAIRMENT
    {
        "student_name": "Kavya Rao", "age": 9, "grade": "Grade 3",
        "school_name": "Spastic Society School, Bengaluru",
        "disability_category": "Hearing Impairment",
        "disability_severity": "moderate",
        "raw_notes": "Kavya has moderate hearing loss and uses hearing aids. Lip-reads effectively. Strong in visual subjects and mathematics. Misses verbal instructions in noisy environments. Benefits from written instructions and FM system.",
        "academic_history": "Grade 2: 65%. Stronger in non-verbal subjects.",
        "teacher_observations": "Misses verbal instructions. Benefits from visual cues.",
        "parent_concerns": "FM system availability and speech therapy continuation."
    },
    {
        "student_name": "Aryan Singh", "age": 13, "grade": "Grade 7",
        "school_name": "Vidya Sagar School, Chennai",
        "disability_category": "Hearing Impairment",
        "disability_severity": "severe",
        "raw_notes": "Aryan is profoundly deaf and communicates using Indian Sign Language. Excellent visual learner and strong in mathematics and art. Requires sign language interpreter for all instruction. Active and enthusiastic learner.",
        "academic_history": "Grade 6: 70% with sign language support.",
        "teacher_observations": "Engaged and motivated with ISL interpreter present.",
        "parent_concerns": "Availability of qualified ISL interpreters."
    },
    # INTELLECTUAL DISABILITY
    {
        "student_name": "Ramesh Kumar", "age": 11, "grade": "Grade 4",
        "school_name": "Akshayanagar Government School, Bengaluru",
        "disability_category": "Intellectual Disability",
        "disability_severity": "mild",
        "raw_notes": "Ramesh has mild intellectual disability. Learns functional reading and mathematics with repetition and concrete materials. Friendly, sociable, and enjoys school. Needs extra time and simplified instructions for all tasks.",
        "academic_history": "Functional literacy level. Strong in practical activities.",
        "teacher_observations": "Responds well to repetition and visual aids.",
        "parent_concerns": "Life skills development and vocational preparation."
    },
    {
        "student_name": "Sunita Devi", "age": 10, "grade": "Grade 3",
        "school_name": "Sarva Shiksha Abhiyan School, Jaipur",
        "disability_category": "Intellectual Disability",
        "disability_severity": "moderate",
        "raw_notes": "Sunita has moderate intellectual disability. Communicates in simple sentences. Recognizes familiar words and numbers up to 20. Strong in music and rhythmic activities. Needs 1:1 support for most academic tasks.",
        "academic_history": "Pre-primary functional level across subjects.",
        "teacher_observations": "Responds to music and routine. Needs constant support.",
        "parent_concerns": "Self-care skills and daily living independence."
    },
    {
        "student_name": "Vikram Joshi", "age": 15, "grade": "Grade 8",
        "school_name": "National Institute for Mentally Handicapped, Secunderabad",
        "disability_category": "Intellectual Disability",
        "disability_severity": "mild",
        "raw_notes": "Vikram has mild intellectual disability with strong social skills. Can read simple texts and do basic arithmetic. Excellent at vocational tasks like assembly and sorting. Preparing for transition to vocational training.",
        "academic_history": "Functional academic skills. Strong in practical workshops.",
        "teacher_observations": "Motivated and hardworking in vocational activities.",
        "parent_concerns": "Vocational training and supported employment pathways."
    },
    # CEREBRAL PALSY
    {
        "student_name": "Pooja Sharma", "age": 12, "grade": "Grade 6",
        "school_name": "Vidyasagar Institute, Mumbai",
        "disability_category": "Cerebral Palsy",
        "disability_severity": "moderate",
        "raw_notes": "Pooja has spastic diplegia affecting lower limbs. Uses wheelchair for mobility. Strong cognitive ability and academic performance. Needs physical accessibility accommodations and assistive technology for writing. Highly motivated learner.",
        "academic_history": "Grade 5: 74%. Strong across subjects with physical support.",
        "teacher_observations": "Excellent student. Needs physical access and writing support.",
        "parent_concerns": "Physical accessibility and assistive technology for writing."
    },
]

NASET_SECTIONS = [
    "background_info", "academic_performance", "social_development",
    "physical_development", "management_needs", "long_term_outcomes",
    "annual_goals", "special_education_services",
    "general_education_participation", "participating_agencies",
    "coordinated_activities", "graduation_info",
    "recommendations_summary", "progress_reporting",
]

results = []

print("="*55)
print("SAMARTH Evaluation — Generating 15 IEPs")
print("="*55)

for i, student in enumerate(STUDENTS):
    print(f"\n[{i+1}/15] {student['student_name']} ({student['disability_category']})")
    start = time.time()

    try:
        state  = run_iep_pipeline(student, iep_id=f"eval-{i+1:02d}")
        elapsed = round(time.time() - start, 1)
        status = str(state.get("workflow_status", ""))
        draft  = state.get("drafted_iep", {})
        comp   = state.get("compliance_report", {})

        sections_complete = sum(
            1 for s in NASET_SECTIONS
            if draft.get(s) and len(str(draft.get(s))) > 50
        )

        result = {
            "student_name":        student["student_name"],
            "disability":          student["disability_category"],
            "severity":            student["disability_severity"],
            "age":                 student["age"],
            "time_seconds":        elapsed,
            "status":              status,
            "compliance_status":   str(comp.get("status", "")),
            "sections_complete":   sections_complete,
            "sections_total":      len(NASET_SECTIONS),
            "mandatory_items":     len(comp.get("mandatory_accommodations", [])),
            "gaps_found":          len(comp.get("identified_gaps", [])),
            "pdf_path":            state.get("pdf_output_path", ""),
            "errors":              state.get("error_log", []),
        }
        results.append(result)

        print(f"  ✅ {elapsed}s | {sections_complete}/14 sections | "
              f"Compliance: {comp.get('status','?')} | "
              f"{len(comp.get('mandatory_items',[]))} mandatory items")

    except Exception as e:
        print(f"  ❌ Failed: {e}")
        results.append({
            "student_name": student["student_name"],
            "disability":   student["disability_category"],
            "status":       "FAILED",
            "error":        str(e),
        })

# ── Save results ──────────────────────────────────────
with open("eval_results.json", "w") as f:
    json.dump(results, f, indent=2)

# ── Print summary table ───────────────────────────────
print("\n" + "="*55)
print("RESULTS SUMMARY")
print("="*55)

successful = [r for r in results if r.get("status","").endswith("COMPLETED")]
times      = [r["time_seconds"] for r in successful]
sections   = [r["sections_complete"] for r in successful]

print(f"\nTotal runs        : {len(results)}")
print(f"Successful        : {len(successful)}/{len(results)}")
print(f"Success rate      : {len(successful)/len(results)*100:.1f}%")
print(f"\nGeneration time:")
print(f"  Mean            : {sum(times)/len(times):.1f}s")
print(f"  Min             : {min(times):.1f}s")
print(f"  Max             : {max(times):.1f}s")
print(f"\nSection completeness:")
print(f"  Mean sections   : {sum(sections)/len(sections):.1f}/14")
print(f"  Full completion : {sum(1 for s in sections if s==14)}/{len(successful)}")

print(f"\nBy disability:")
from collections import defaultdict
by_dis = defaultdict(list)
for r in successful:
    by_dis[r["disability"]].append(r)

for dis, runs in by_dis.items():
    t = [r["time_seconds"] for r in runs]
    s = [r["sections_complete"] for r in runs]
    c = [r["compliance_status"] for r in runs]
    print(f"  {dis[:25]:<25} "
          f"time={sum(t)/len(t):.1f}s "
          f"sections={sum(s)/len(s):.1f}/14 "
          f"compliance={set(c)}")

print(f"\nCompliance breakdown:")
comp_counts = defaultdict(int)
for r in successful:
    comp_counts[r.get("compliance_status","unknown")] += 1
for status, count in comp_counts.items():
    print(f"  {status}: {count}/{len(successful)}")

print(f"\nResults saved to: eval_results.json")
print("="*55)


if __name__ == "__main__":
    pass
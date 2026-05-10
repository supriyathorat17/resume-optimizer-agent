"""
End-to-end test runner for Stages 1-4 of the Resume Optimizer.
Usage:
    python test_run.py --resume data/resume.pdf --jd data/job.txt
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Separators for readability ────────────────────────────────────────────────
W = 70   # line width

def header(title: str):
    print(f"\n{'=' * W}")
    print(f"  {title}")
    print(f"{'=' * W}")

def section(title: str):
    print(f"\n{'-' * W}")
    print(f"  {title}")
    print(f"{'-' * W}")


def run(resume_path: str, jd_path: str):
    from config import config
    from agents.parser import ResumeParser
    from agents.analyzer import JDAnalyzer
    from agents.gap_finder import GapFinder
    from agents.suggester import SuggestionGenerator

    # ── Validate API key ──────────────────────────────────────────────────────
    try:
        config.validate()
    except ValueError as e:
        print(f"\n ERROR: {e}")
        print("  Add your real CLAUDE_API_KEY to the .env file and try again.\n")
        sys.exit(1)

    # =========================================================================
    # STAGE 1 — Parse Resume
    # =========================================================================
    header("STAGE 1 — Parsing Resume")
    print(f"  File: {resume_path}\n")

    parser = ResumeParser()
    resume = parser.parse(resume_path)

    print(f"  Name        : {resume.name}")
    print(f"  Email       : {resume.email}")
    print(f"  Phone       : {resume.phone}")
    print(f"  Location    : {resume.location}")
    print(f"  Summary     : {(resume.summary or '')[:120]}{'...' if resume.summary and len(resume.summary) > 120 else ''}")

    section("Experience")
    for exp in resume.experience:
        print(f"  {exp.role} @ {exp.company}  ({exp.start_date} – {exp.end_date})")
        for b in exp.bullets[:3]:
            print(f"    • {b}")

    section("Education")
    for edu in resume.education:
        print(f"  {edu.degree} in {edu.field or 'N/A'} — {edu.school} ({edu.graduation_date})")
        if edu.gpa:
            print(f"    GPA: {edu.gpa}")

    section("Skills")
    for group in resume.skills:
        print(f"  [{group.category}]  {', '.join(group.items)}")

    section("Projects")
    for proj in resume.projects:
        print(f"  {proj.title}  ({', '.join(proj.tech_stack)})")
        print(f"    {proj.description}")

    if resume.certifications:
        section("Certifications")
        for cert in resume.certifications:
            print(f"  • {cert}")

    # =========================================================================
    # STAGE 2 — Analyze Job Description
    # =========================================================================
    header("STAGE 2 — Analyzing Job Description")
    print(f"  File: {jd_path}\n")

    analyzer = JDAnalyzer()
    jd = analyzer.analyze_file(jd_path)

    print(f"  Title           : {jd.title}")
    print(f"  Company         : {jd.company}")
    print(f"  Location        : {jd.location}")
    print(f"  Seniority       : {jd.seniority_level}")
    print(f"  Employment Type : {jd.employment_type}")

    section("Hard Skills Required")
    print(f"  {', '.join(jd.hard_skills) or '(none identified)'}")

    section("Soft Skills Required")
    print(f"  {', '.join(jd.soft_skills) or '(none identified)'}")

    section("Must-Have Experience")
    for exp in jd.must_have_experience:
        print(f"  • {exp}")

    section("Nice to Have")
    print(f"  {', '.join(jd.nice_to_have) or '(none)'}")

    section("ATS Keywords")
    print(f"  {', '.join(jd.keywords[:30])}")
    if len(jd.keywords) > 30:
        print(f"  ... and {len(jd.keywords) - 30} more")

    # =========================================================================
    # STAGE 3 — Find Gaps
    # =========================================================================
    header("STAGE 3 — Gap Analysis")

    finder = GapFinder()
    gaps = finder.find_gaps(resume, jd)

    if not gaps:
        print("\n  No significant gaps found — strong match!")
    else:
        print(f"\n  Found {len(gaps)} gaps:\n")
        for i, gap in enumerate(gaps, 1):
            bar = "█" * int(gap.impact_on_fit / 10) + "░" * (10 - int(gap.impact_on_fit / 10))
            print(f"  {i:2}. [{gap.severity.upper():<8}] {gap.skill}")
            print(f"      Impact : {bar} {gap.impact_on_fit:.0f}/100")
            print(f"      Type   : {gap.type}")
            print(f"      Reason : {gap.reason}")
            print()

    # =========================================================================
    # STAGE 4 — Generate Suggestions
    # =========================================================================
    header("STAGE 4 — Resume Suggestions")

    suggester = SuggestionGenerator()
    suggestions = suggester.generate(resume, gaps)

    if not suggestions:
        print("\n  No suggestions generated.")
    else:
        print(f"\n  {len(suggestions)} suggestions (highest priority first):\n")
        for i, s in enumerate(suggestions, 1):
            stars = "★" * s.priority + "☆" * (10 - s.priority)
            print(f"  ┌─ #{i}  Priority: {stars}  ({s.priority}/10)")
            print(f"  │  Gap     : {s.gap}")
            print(f"  │  Section : {s.section.upper()}")
            print(f"  │")
            print(f"  │  SUGGESTED REVISION:")
            # Word-wrap long revisions at 60 chars
            words = s.suggested_revision.split()
            line, lines = [], []
            for word in words:
                if sum(len(w) + 1 for w in line) + len(word) > 60:
                    lines.append(" ".join(line))
                    line = [word]
                else:
                    line.append(word)
            if line:
                lines.append(" ".join(line))
            for ln in lines:
                print(f"  │    {ln}")
            print(f"  │")
            print(f"  │  WHY: {s.reasoning}")
            print(f"  └{'─' * 65}")
            print()

    # =========================================================================
    # Summary
    # =========================================================================
    header("SUMMARY")
    print(f"  Resume          : {resume.name}")
    print(f"  Target Role     : {jd.title} @ {jd.company}")
    print(f"  Gaps Found      : {len(gaps)}")
    if gaps:
        critical = sum(1 for g in gaps if g.severity == "critical")
        high     = sum(1 for g in gaps if g.severity == "high")
        medium   = sum(1 for g in gaps if g.severity == "medium")
        low      = sum(1 for g in gaps if g.severity == "low")
        print(f"  Severity        : {critical} critical  {high} high  {medium} medium  {low} low")
    print(f"  Suggestions     : {len(suggestions)}")
    if suggestions:
        avg = sum(s.priority for s in suggestions) / len(suggestions)
        print(f"  Avg Priority    : {avg:.1f} / 10")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resume Optimizer — Stages 1-4 test run")
    parser.add_argument("--resume", required=True, help="Path to resume (PDF or DOCX)")
    parser.add_argument("--jd",     required=True, help="Path to job description (TXT or PDF)")
    args = parser.parse_args()

    if not os.path.exists(args.resume):
        print(f"\n ERROR: Resume file not found: {args.resume}\n")
        sys.exit(1)
    if not os.path.exists(args.jd):
        print(f"\n ERROR: JD file not found: {args.jd}\n")
        sys.exit(1)

    run(args.resume, args.jd)

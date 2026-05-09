# Resume Optimizer Agent

An AI-powered multi-agent system that analyzes resumes against job descriptions, identifies gaps, and generates targeted suggestions to improve ATS scores and interview chances.

## Architecture

The system is composed of specialized agents orchestrated by a central coordinator:

- **ResumeParser** — Extracts structured data from PDF/DOCX resumes
- **JDAnalyzer** — Parses job descriptions to identify required skills, keywords, and qualifications
- **GapFinder** — Compares resume content against JD requirements to surface missing elements
- **SuggestionGenerator** — Uses Claude to produce actionable rewrite suggestions
- **Validator** — Scores the optimized resume and checks ATS threshold compliance

## Project Structure

```
resume_optimizer/
├── src/
│   ├── agents/         # Specialized agent classes
│   ├── apis/           # External API clients (Claude, Resume Worded)
│   ├── utils/          # Shared helpers
│   ├── storage/        # SQLite persistence layer
│   ├── config.py       # Environment configuration
│   ├── models.py       # Pydantic data models
│   ├── orchestrator.py # Agent coordination logic
│   └── main.py         # CLI entry point
├── data/               # Input resumes and job descriptions
├── output/             # Optimized resume output files
├── logs/               # Application logs
├── .env                # Environment variables (not committed)
└── requirements.txt
```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in your API keys
```

## Usage

```bash
python src/main.py --resume data/my_resume.pdf --jd data/job_description.txt
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `CLAUDE_API_KEY` | Anthropic API key | — |
| `RESUME_WORDED_API_KEY` | Resume Worded API key | — |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `MAX_ITERATIONS` | Max optimization loops | `3` |
| `ATS_SCORE_THRESHOLD` | Target ATS score (0–100) | `85` |

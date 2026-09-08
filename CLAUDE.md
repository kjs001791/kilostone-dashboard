# KiloStone Dashboard - Claude Development Guide

## Project Overview
KiloStone Dashboard is a management system for cargo truck driving records. It processes messy manual data through a Gemini API-based pipeline and visualizes fuel efficiency and driving metrics.

## Tech Stack
- **Frontend**: Streamlit (Transitioning to a modern web stack planned)
- **Backend/Logic**: Python 3.12
- **Database**: MariaDB 10.6
- **AI**: Google Gemini 2.0 Flash (via `google-generativeai`)
- **Infrastructure**: Docker Compose, AWS EC2, GitHub Actions

## Commands

### Environment Setup
```bash
# Create and activate venv
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### Running the App (Streamlit)
```bash
# Locally
streamlit run app/main.py

# Via Docker
docker compose up -d --build
```

### Data Pipeline (CLI)
```bash
# Full pipeline (Steps 1-3)
python scripts/run_pipeline.py --input data/raw/driving_log.xlsx

# Skip AI (Steps 1-2 only)
python scripts/run_pipeline.py --input data/raw/driving_log.xlsx --skip-ai

# Approve and load (Steps 4-5)
python scripts/run_pipeline.py --approve data/staging/cleaning_proposal_xxx.csv
```

### DB Initialization
```bash
python scripts/db_initializer.py
```

## Coding Guidelines
- **Modular Structure**: Keep logic in `app/services/` and UI in `app/views/` or `app/components/`.
- **Naming**: Follow PEP 8 (snake_case for functions/variables, PascalCase for classes).
- **Types**: Use Python type hints for better clarity and IDE support.
- **Error Handling**: Use explicit try-except blocks, especially for DB and API calls.
- **Environment Variables**: Use `.env` for secrets (DB creds, Gemini API key). Do not commit `.env`.
- **Streamlit**: Use the custom CSS and components defined in `app/styles.py` and `app/components/`.

## Directory Structure
- `app/`: Core application logic (Streamlit).
- `scripts/`: Data cleaning pipeline and utility scripts.
- `data/`: Raw, staging, and processed data files.
- `assets/`: UI assets like icons and logos.

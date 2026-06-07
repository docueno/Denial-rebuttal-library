# Clinical Validation Appeal Library

Local Streamlit app for managing a SQLite-backed clinical validation denial rebuttal library.
The app imports `codex_rebuttal_library.csv` with these exact columns:

- `diagnosis_code`
- `diagnosis_name`
- `denial_rationale`
- `rebuttal_category`
- `reusable_rebuttal`
- `supporting_criteria`
- `key_clinical_indicators`
- `appeal_type`
- `source_basis`
- `search_terms`

## Run

```bash
python3 -m pip install -r requirements.txt
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false python3 -m streamlit run app.py --server.headless true
```

The database is created at `denial_rebuttals.sqlite3` on first run and populated from `codex_rebuttal_library.csv`.

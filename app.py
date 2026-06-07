from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "denial_rebuttals.sqlite3"
CSV_PATH = APP_DIR / "codex_rebuttal_library.csv"

TABLE_NAME = "rebuttals"
CSV_COLUMNS = [
    "diagnosis_code",
    "diagnosis_name",
    "denial_rationale",
    "rebuttal_category",
    "reusable_rebuttal",
    "supporting_criteria",
    "key_clinical_indicators",
    "appeal_type",
    "source_basis",
    "search_terms",
]
FIELDS = CSV_COLUMNS
SEARCH_FIELDS = [
    "diagnosis_code",
    "diagnosis_name",
    "denial_rationale",
    "reusable_rebuttal",
    "key_clinical_indicators",
    "search_terms",
]
FILTER_FIELDS = ["diagnosis_code", "rebuttal_category", "appeal_type"]
LONG_TEXT_FIELDS = {
    "denial_rationale",
    "reusable_rebuttal",
    "supporting_criteria",
    "key_clinical_indicators",
    "source_basis",
    "search_terms",
}


def quote_identifier(identifier: str) -> str:
    return f'"{identifier}"'


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_identifier(TABLE_NAME)})").fetchall()
    return [row["name"] for row in rows]


def create_table(conn: sqlite3.Connection) -> None:
    field_sql = ",\n                ".join(
        f"{quote_identifier(field)} TEXT NOT NULL DEFAULT ''" for field in FIELDS
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {quote_identifier(TABLE_NAME)} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {field_sql},
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def import_csv(conn: sqlite3.Connection) -> int:
    if not CSV_PATH.exists():
        return 0

    with CSV_PATH.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError(
                "CSV headers must match exactly: " + ", ".join(CSV_COLUMNS)
            )
        rows = [{field: (row.get(field) or "").strip() for field in FIELDS} for row in reader]

    if not rows:
        return 0

    now = datetime.utcnow().isoformat(timespec="seconds")
    placeholders = ", ".join(["?"] * len(FIELDS))
    conn.executemany(
        f"""
        INSERT INTO {quote_identifier(TABLE_NAME)}
            ({", ".join(quote_identifier(field) for field in FIELDS)}, created_at, updated_at)
        VALUES ({placeholders}, ?, ?)
        """,
        [tuple(row[field] for field in FIELDS) + (now, now) for row in rows],
    )
    return len(rows)


def init_db() -> None:
    with closing(get_connection()) as conn:
        current_columns = table_columns(conn)
        expected_columns = ["id", *FIELDS, "created_at", "updated_at"]
        if current_columns and current_columns != expected_columns:
            conn.execute(f"DROP TABLE {quote_identifier(TABLE_NAME)}")

        create_table(conn)
        total = conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(TABLE_NAME)}").fetchone()[0]
        if total == 0:
            import_csv(conn)
        conn.commit()


def fetch_options(field: str) -> list[str]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT {quote_identifier(field)}
            FROM {quote_identifier(TABLE_NAME)}
            WHERE TRIM({quote_identifier(field)}) != ''
            ORDER BY {quote_identifier(field)}
            """
        ).fetchall()
    return [row[0] for row in rows]


def search_records(
    query: str,
    diagnosis_code: str,
    rebuttal_category: str,
    appeal_type: str,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[str] = []

    if query:
        like = f"%{query}%"
        clauses.append(
            "(" + " OR ".join([f"{quote_identifier(field)} LIKE ?" for field in SEARCH_FIELDS]) + ")"
        )
        params.extend([like] * len(SEARCH_FIELDS))

    filters = {
        "diagnosis_code": diagnosis_code,
        "rebuttal_category": rebuttal_category,
        "appeal_type": appeal_type,
    }
    for field, value in filters.items():
        if value != "All":
            clauses.append(f"{quote_identifier(field)} = ?")
            params.append(value)

    sql = f"SELECT * FROM {quote_identifier(TABLE_NAME)}"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += (
        f" ORDER BY {quote_identifier('diagnosis_code')} ASC, "
        f"{quote_identifier('rebuttal_category')} ASC, updated_at DESC"
    )

    with closing(get_connection()) as conn:
        return conn.execute(sql, params).fetchall()


def upsert_record(record_id: int | None, values: dict[str, str]) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with closing(get_connection()) as conn:
        if record_id:
            assignments = ", ".join([f"{quote_identifier(field)} = ?" for field in FIELDS])
            conn.execute(
                f"""
                UPDATE {quote_identifier(TABLE_NAME)}
                SET {assignments}, updated_at = ?
                WHERE id = ?
                """,
                tuple(values[field] for field in FIELDS) + (now, record_id),
            )
        else:
            conn.execute(
                f"""
                INSERT INTO {quote_identifier(TABLE_NAME)}
                    ({", ".join(quote_identifier(field) for field in FIELDS)}, created_at, updated_at)
                VALUES ({", ".join(["?"] * len(FIELDS))}, ?, ?)
                """,
                tuple(values[field] for field in FIELDS) + (now, now),
            )
        conn.commit()


def delete_record(record_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute(f"DELETE FROM {quote_identifier(TABLE_NAME)} WHERE id = ?", (record_id,))
        conn.commit()


def copy_button(text: str, key: str) -> None:
    safe_text = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    components.html(
        f"""
        <button id="copy-{key}" style="
            border: 1px solid #cbd5e1;
            background: #ffffff;
            border-radius: 6px;
            color: #0f172a;
            cursor: pointer;
            font: 14px system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            padding: 8px 12px;
            width: 100%;
        ">Copy reusable_rebuttal</button>
        <script>
        const button = document.getElementById("copy-{key}");
        button.addEventListener("click", async () => {{
            await navigator.clipboard.writeText(`{safe_text}`);
            button.textContent = "Copied";
            setTimeout(() => button.textContent = "Copy reusable_rebuttal", 1400);
        }});
        </script>
        """,
        height=44,
    )


def validate(values: dict[str, str]) -> list[str]:
    missing = [field for field in FIELDS if not values[field].strip()]
    return [f"{field} is required." for field in missing]


def record_form(record: sqlite3.Row | None = None) -> None:
    form_key = f"record-form-{record['id'] if record else 'new'}"
    with st.form(form_key, clear_on_submit=record is None):
        values: dict[str, str] = {}
        cols = st.columns(2)
        for index, field in enumerate(FIELDS):
            default = record[field] if record else ""
            container = st if field in LONG_TEXT_FIELDS else cols[index % 2]
            if field in LONG_TEXT_FIELDS:
                values[field] = container.text_area(field, value=default, height=110)
            else:
                values[field] = container.text_input(field, value=default)

        submitted = st.form_submit_button("Save entry", type="primary")
        if submitted:
            errors = validate(values)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                upsert_record(record["id"] if record else None, values)
                st.success("Entry saved.")
                st.session_state["editing_id"] = None
                st.rerun()


def render_record(record: sqlite3.Row) -> None:
    title = f"{record['diagnosis_code']} - {record['diagnosis_name']}"
    with st.container(border=True):
        top = st.columns([1.25, 1, 1, 0.75])
        top[0].subheader(title)
        top[1].metric("rebuttal_category", record["rebuttal_category"])
        top[2].metric("appeal_type", record["appeal_type"])
        top[3].caption(f"Updated {record['updated_at']}")

        st.markdown(f"**denial_rationale:** {record['denial_rationale']}")
        st.markdown("**reusable_rebuttal**")
        st.write(record["reusable_rebuttal"])

        with st.expander("Supporting detail"):
            st.markdown("**supporting_criteria**")
            st.write(record["supporting_criteria"])
            st.markdown("**key_clinical_indicators**")
            st.write(record["key_clinical_indicators"])
            st.markdown("**source_basis**")
            st.write(record["source_basis"])
            st.markdown("**search_terms**")
            st.write(record["search_terms"])

        actions = st.columns([1.2, 1, 1, 3.8])
        with actions[0]:
            copy_button(record["reusable_rebuttal"], str(record["id"]))
        if actions[1].button("Edit", key=f"edit-{record['id']}"):
            st.session_state["editing_id"] = record["id"]
            st.rerun()
        if actions[2].button("Delete", key=f"delete-{record['id']}", type="secondary"):
            st.session_state["confirm_delete_id"] = record["id"]
            st.rerun()

        if st.session_state.get("confirm_delete_id") == record["id"]:
            st.warning(f"Delete {title}? This cannot be undone.")
            confirm_cols = st.columns([1, 1, 5])
            if confirm_cols[0].button("Confirm", key=f"confirm-{record['id']}", type="primary"):
                delete_record(record["id"])
                st.session_state["confirm_delete_id"] = None
                st.rerun()
            if confirm_cols[1].button("Cancel", key=f"cancel-{record['id']}"):
                st.session_state["confirm_delete_id"] = None
                st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Clinical Validation Appeal Library",
        page_icon="CV",
        layout="wide",
    )
    init_db()

    st.title("Clinical Validation Appeal Library")
    st.caption("SQLite library imported from codex_rebuttal_library.csv.")

    if "editing_id" not in st.session_state:
        st.session_state["editing_id"] = None

    with st.sidebar:
        st.header("Search")
        query = st.text_input(
            "Keyword search",
            placeholder="Search diagnosis, rationale, rebuttal, indicators, terms...",
        )

        diagnosis_code = st.selectbox("diagnosis_code", ["All"] + fetch_options("diagnosis_code"))
        rebuttal_category = st.selectbox(
            "rebuttal_category",
            ["All"] + fetch_options("rebuttal_category"),
        )
        appeal_type = st.selectbox("appeal_type", ["All"] + fetch_options("appeal_type"))

        st.divider()
        st.header("Add Entry")
        record_form()

    records = search_records(
        query.strip(),
        diagnosis_code,
        rebuttal_category,
        appeal_type,
    )
    st.write(f"{len(records)} entr{'y' if len(records) == 1 else 'ies'} found")

    editing_id = st.session_state.get("editing_id")
    if editing_id:
        selected = next((record for record in records if record["id"] == editing_id), None)
        if selected is None:
            with closing(get_connection()) as conn:
                selected = conn.execute(
                    f"SELECT * FROM {quote_identifier(TABLE_NAME)} WHERE id = ?",
                    (editing_id,),
                ).fetchone()
        if selected:
            st.subheader("Edit Entry")
            record_form(selected)
            st.divider()

    for record in records:
        render_record(record)

    if not records:
        st.info("No records match the current filters. Add a new entry from the sidebar.")


if __name__ == "__main__":
    main()

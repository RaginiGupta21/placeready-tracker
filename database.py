"""
database.py - everything that reads or writes the SQLite database.

SQLite keeps all data in ONE file (placement.db) next to this script.
It ships with Python, so there is nothing to install.

Tables:
  students            one row per student (their latest skill ratings)
  weekly_logs         one row every time a student submits (powers the line chart)
  ats_scans           reserved for ATS scan history (not written to yet)
  industry_benchmarks the skill level each target role expects
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

# Build the database path from THIS file's location, so the app works no matter
# which folder you start it from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "placement.db")


# ----------------------------------------------------------
# INDUSTRY BENCHMARKS - the ONLY place target roles are defined.
# Each row: role name, then the skill level (1-5) the role expects, in this order:
#   Python, SQL, DSA, Excel, PowerBI, ML, Communication, Aptitude, Statistics, Domain
# To add a role, add one line here and restart. The profile form dropdown is
# built from this table automatically.
# NOTE: these numbers are illustrative values chosen by the author. They are
# not the result of a statistical study. Edit them to suit your own research.
# ----------------------------------------------------------
BENCHMARKS = [
    ("Data Analyst",       4, 4, 2, 3, 4, 2, 3, 3, 4, 3),
    ("Data Scientist",     5, 4, 3, 3, 3, 5, 3, 4, 5, 4),
    ("Business Analyst",   2, 3, 1, 4, 3, 1, 4, 4, 3, 4),
    ("Data Engineer",      4, 4, 4, 2, 2, 3, 3, 3, 3, 3),
    ("Software Developer", 4, 3, 5, 2, 1, 2, 3, 4, 2, 2),
    ("ML Engineer",        5, 3, 4, 2, 2, 5, 3, 3, 5, 4),
]


@contextmanager
def db():
    """
    Open the database, hand it to the caller, then ALWAYS close it.
    - If the code inside the `with` block finishes normally, changes are saved.
    - If it raises an error, changes are rolled back (nothing half-saved).
    row_factory lets us read columns by name, like row["name"].
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the tables (if missing) and load the role benchmarks. Safe to run on every start."""
    with db() as conn:

        # ---- students: ONE row per person ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                branch          TEXT,
                year            TEXT,
                target_role     TEXT,
                python          INTEGER DEFAULT 1,
                sql             INTEGER DEFAULT 1,
                dsa             INTEGER DEFAULT 1,
                excel           INTEGER DEFAULT 1,
                powerbi         INTEGER DEFAULT 1,
                ml              INTEGER DEFAULT 1,
                communication   INTEGER DEFAULT 1,
                aptitude        INTEGER DEFAULT 1,
                statistics      INTEGER DEFAULT 1,
                domain          INTEGER DEFAULT 1,
                problems        INTEGER DEFAULT 0,
                mocks           INTEGER DEFAULT 0,
                projects        INTEGER DEFAULT 0,
                courses         INTEGER DEFAULT 0,
                readiness_score REAL    DEFAULT 0,
                created_date    TEXT    DEFAULT CURRENT_DATE
            )
        """)

        # ---- weekly_logs: a new row EVERY submission (this is the time-series data) ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id      INTEGER NOT NULL,
                log_date        TEXT,
                python          INTEGER,
                sql             INTEGER,
                dsa             INTEGER,
                excel           INTEGER,
                powerbi         INTEGER,
                ml              INTEGER,
                communication   INTEGER,
                aptitude        INTEGER,
                statistics      INTEGER,
                domain          INTEGER,
                problems        INTEGER,
                mocks           INTEGER,
                projects        INTEGER,
                courses         INTEGER,
                readiness_score REAL,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)

        # ---- ats_scans: table exists for future use; the ATS scanner runs in the
        # browser and does not save to this table yet ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ats_scans (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id       INTEGER NOT NULL,
                scan_date        TEXT    DEFAULT CURRENT_DATE,
                job_title        TEXT,
                company_name     TEXT,
                ats_score        REAL,
                matched_keywords TEXT,
                missing_keywords TEXT,
                resume_version   INTEGER DEFAULT 1,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)

        # ---- industry_benchmarks: what each role expects ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS industry_benchmarks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                role_name     TEXT UNIQUE NOT NULL,
                python_req    INTEGER DEFAULT 3,
                sql_req       INTEGER DEFAULT 3,
                dsa_req       INTEGER DEFAULT 3,
                excel_req     INTEGER DEFAULT 2,
                powerbi_req   INTEGER DEFAULT 2,
                ml_req        INTEGER DEFAULT 2,
                comm_req      INTEGER DEFAULT 3,
                aptitude_req  INTEGER DEFAULT 3,
                stats_req     INTEGER DEFAULT 3,
                domain_req    INTEGER DEFAULT 3
            )
        """)

        # Load BENCHMARKS. "ON CONFLICT ... DO UPDATE" means: if the role already
        # exists, update its numbers. So editing BENCHMARKS and restarting is enough,
        # you do NOT need to delete placement.db any more.
        conn.executemany("""
            INSERT INTO industry_benchmarks
                (role_name, python_req, sql_req, dsa_req, excel_req, powerbi_req,
                 ml_req, comm_req, aptitude_req, stats_req, domain_req)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(role_name) DO UPDATE SET
                python_req   = excluded.python_req,
                sql_req      = excluded.sql_req,
                dsa_req      = excluded.dsa_req,
                excel_req    = excluded.excel_req,
                powerbi_req  = excluded.powerbi_req,
                ml_req       = excluded.ml_req,
                comm_req     = excluded.comm_req,
                aptitude_req = excluded.aptitude_req,
                stats_req    = excluded.stats_req,
                domain_req   = excluded.domain_req
        """, BENCHMARKS)

        # Database-level guard against duplicate students (same name, any capitalisation).
        # If an OLD placement.db already contains duplicates this cannot be created,
        # so we print a clear message instead of crashing.
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_students_name "
                "ON students(name COLLATE NOCASE)"
            )
        except sqlite3.IntegrityError:
            print("WARNING: placement.db already contains duplicate student names.")
            print("         Stop the app, delete placement.db, and start again for a clean database.")


def save_profile(data):
    """
    Save a submitted profile and return the student's id.

    - First time this name is seen  -> INSERT a new student row.
    - Name already exists           -> UPDATE that same row (no duplicate student).
    - Either way                    -> add ONE row to weekly_logs, so the line chart
                                       gets a new point every submission.
    """
    with db() as conn:
        # Look for an existing student with this name (ignoring upper/lower case).
        row = conn.execute(
            "SELECT id FROM students WHERE name = ? COLLATE NOCASE", (data["name"],)
        ).fetchone()

        if row:
            student_id = row["id"]
            conn.execute("""
                UPDATE students SET
                    branch = :branch, year = :year, target_role = :target_role,
                    python = :python, sql = :sql, dsa = :dsa, excel = :excel,
                    powerbi = :powerbi, ml = :ml, communication = :communication,
                    aptitude = :aptitude, statistics = :statistics, domain = :domain,
                    problems = :problems, mocks = :mocks, projects = :projects,
                    courses = :courses, readiness_score = :readiness_score
                WHERE id = :id
            """, {**data, "id": student_id})
        else:
            cursor = conn.execute("""
                INSERT INTO students
                    (name, branch, year, target_role,
                     python, sql, dsa, excel, powerbi, ml,
                     communication, aptitude, statistics, domain,
                     problems, mocks, projects, courses, readiness_score)
                VALUES
                    (:name, :branch, :year, :target_role,
                     :python, :sql, :dsa, :excel, :powerbi, :ml,
                     :communication, :aptitude, :statistics, :domain,
                     :problems, :mocks, :projects, :courses, :readiness_score)
            """, data)
            student_id = cursor.lastrowid

        # Always add a history row (this is what makes the time series).
        conn.execute("""
            INSERT INTO weekly_logs
                (student_id, log_date,
                 python, sql, dsa, excel, powerbi, ml,
                 communication, aptitude, statistics, domain,
                 problems, mocks, projects, courses, readiness_score)
            VALUES
                (:student_id, :log_date,
                 :python, :sql, :dsa, :excel, :powerbi, :ml,
                 :communication, :aptitude, :statistics, :domain,
                 :problems, :mocks, :projects, :courses, :readiness_score)
        """, {
            **data,
            "student_id": student_id,
            "log_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    return student_id


def get_student(student_id):
    """One student as a dictionary, or None if the id does not exist."""
    with db() as conn:
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return dict(row) if row else None


def get_history(student_id):
    """All score snapshots for one student, oldest first (the time series)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT log_date, readiness_score FROM weekly_logs "
            "WHERE student_id = ? ORDER BY id ASC",
            (student_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_students():
    """Every student, best score first (ties sorted by name). Used by the admin page."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM students ORDER BY readiness_score DESC, name ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_benchmark(role_name):
    """The skill levels one role expects, or None if the role does not exist."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM industry_benchmarks WHERE role_name = ?", (role_name,)
        ).fetchone()
    return dict(row) if row else None


def get_roles():
    """All role names, A to Z. The profile form dropdown is built from this."""
    with db() as conn:
        rows = conn.execute(
            "SELECT role_name FROM industry_benchmarks ORDER BY role_name"
        ).fetchall()
    return [r["role_name"] for r in rows]

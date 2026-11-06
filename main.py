"""
main.py - the entry point of PlaceReady (FastAPI).

Run it with:   python main.py
Then open:     http://127.0.0.1:8000

What this file does:
  - creates the web app
  - connects the CSS folder (static/) and the HTML folder (templates/)
  - defines the ROUTES: each route is a URL the browser can visit, plus the
    Python function that runs when it does.

  @app.get(...)   -> the browser is just opening a page
  @app.post(...)  -> the browser is submitting a form
"""

import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import analytics   # score formula, gap analysis, priority actions
import database    # everything that touches placement.db

# Folders are located relative to THIS file, so the app starts correctly even if
# you launch it from a different directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts (code before `yield`) and once when it stops."""
    database.init_db()          # create tables + load role benchmarks
    print("PlaceReady is running. API docs: http://127.0.0.1:8000/docs")
    yield


app = FastAPI(
    title="PlaceReady - Placement Readiness Tracker",
    description="Placement readiness score, skill-gap analysis and ATS resume scanner.",
    version="1.0.0",
    lifespan=lifespan,
)

# Anything requested under /static/... is served from the static/ folder (our CSS).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Jinja2 fills Python values into the HTML files in templates/.
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ----------------------------------------------------------
# PAGE ROUTES
# ----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """Skill form. The role dropdown is built from the benchmarks in the database."""
    return templates.TemplateResponse(
        request, "profile.html", {"roles": database.get_roles()}
    )


@app.post("/submit-profile")
async def submit_profile(
    # Every form field is declared as a function parameter. FastAPI reads it from
    # the submitted form, converts it to the right type, and checks the limits.
    # If a value is missing or out of range, FastAPI answers with a 422 error and
    # this function body never runs.
    name:        str = Form(..., min_length=1, max_length=60),
    branch:      str = Form(..., min_length=1, max_length=60),
    year:        str = Form(..., min_length=1, max_length=20),
    target_role: str = Form(..., min_length=1, max_length=60),
    # skill sliders: whole numbers from 1 to 5
    python:        int = Form(1, ge=1, le=5),
    sql:           int = Form(1, ge=1, le=5),
    dsa:           int = Form(1, ge=1, le=5),
    excel:         int = Form(1, ge=1, le=5),
    powerbi:       int = Form(1, ge=1, le=5),
    ml:            int = Form(1, ge=1, le=5),
    communication: int = Form(1, ge=1, le=5),
    aptitude:      int = Form(1, ge=1, le=5),
    statistics:    int = Form(1, ge=1, le=5),
    domain:        int = Form(1, ge=1, le=5),
    # weekly activity: zero or more
    problems: int = Form(0, ge=0, le=1000),
    mocks:    int = Form(0, ge=0, le=100),
    projects: int = Form(0, ge=0, le=100),
    courses:  int = Form(0, ge=0, le=100),
):
    """Receive the profile form, score it, save it, then show the dashboard."""

    # Tidy the name: trim and collapse repeated spaces ("  Ragini   Gupta " -> "Ragini Gupta").
    clean_name = " ".join(name.split())
    if not clean_name:
        raise HTTPException(status_code=400, detail="Name cannot be blank.")

    # The role must exist in the benchmarks table.
    if database.get_benchmark(target_role) is None:
        raise HTTPException(status_code=400, detail=f"Unknown target role: {target_role}")

    data = {
        "name": clean_name, "branch": branch.strip(), "year": year, "target_role": target_role,
        "python": python, "sql": sql, "dsa": dsa, "excel": excel, "powerbi": powerbi,
        "ml": ml, "communication": communication, "aptitude": aptitude,
        "statistics": statistics, "domain": domain,
        "problems": problems, "mocks": mocks, "projects": projects, "courses": courses,
    }

    data["readiness_score"] = analytics.calculate_readiness(data)   # analytics.py
    student_id = database.save_profile(data)                        # database.py

    # 303 = "now go and GET this other URL". It stops a refresh from re-submitting the form.
    return RedirectResponse(url=f"/dashboard/{student_id}", status_code=303)


@app.get("/dashboard/{student_id}", response_class=HTMLResponse)
async def dashboard(request: Request, student_id: int):
    """One student's results. {student_id} comes from the URL, e.g. /dashboard/3."""
    student = database.get_student(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")

    history = database.get_history(student_id)          # for the line chart
    gap_data = analytics.get_skill_gaps(student)        # your skills vs the role benchmark
    priority = analytics.get_priority_actions(gap_data)

    return templates.TemplateResponse(request, "dashboard.html", {
        "student": student,
        "history": history,
        "gap_data": gap_data,
        "priority": priority,
        # Chart.js is JavaScript, so we hand it the data as JSON text.
        # (These contain only skill names, numbers and dates - never user-typed text.)
        "gap_json": json.dumps(gap_data),
        "history_json": json.dumps(history),
    })


@app.get("/ats", response_class=HTMLResponse)
async def ats_page(request: Request):
    """ATS scanner page. The scanning itself runs in the browser (see ats.html)."""
    return templates.TemplateResponse(request, "ats.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    """Placement-cell view: every student, best first, with colour-coded skills."""
    students = database.get_all_students()

    # For each student, compare four key skills with THEIR OWN target role's benchmark.
    benchmarks = {}
    for s in students:
        role = s["target_role"]
        if role not in benchmarks:
            benchmarks[role] = database.get_benchmark(role) or {}
        bm = benchmarks[role]
        s["status"] = {
            "python":        analytics.skill_status(s["python"],        bm.get("python_req", 3)),
            "sql":           analytics.skill_status(s["sql"],           bm.get("sql_req", 3)),
            "dsa":           analytics.skill_status(s["dsa"],           bm.get("dsa_req", 3)),
            "communication": analytics.skill_status(s["communication"], bm.get("comm_req", 3)),
        }

    return templates.TemplateResponse(request, "admin.html", {"students": students})


# ----------------------------------------------------------
# JSON API ROUTES (return data, not a web page)
# Returning a Python dict is enough: FastAPI turns it into JSON automatically.
# Try them at http://127.0.0.1:8000/docs
# ----------------------------------------------------------

@app.get("/api/student/{student_id}")
async def get_student_api(student_id: int):
    student = database.get_student(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")

    gap_data = analytics.get_skill_gaps(student)
    return {
        "student": student,
        "gap_data": gap_data,
        "priority": analytics.get_priority_actions(gap_data),
        "risk": analytics.get_risk_label(student["readiness_score"]),
    }


@app.get("/api/benchmark/{role_name}")
async def get_benchmark_api(role_name: str):
    benchmark = database.get_benchmark(role_name)
    if benchmark is None:
        raise HTTPException(status_code=404, detail=f"No benchmark found for role: {role_name}")
    return benchmark


# ----------------------------------------------------------
# Start the server when you run:  python main.py
# reload=True restarts the server automatically whenever you save a file (development only).
# ----------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

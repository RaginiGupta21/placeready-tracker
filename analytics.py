"""
analytics.py - The BRAIN of the project

This file does all the smart calculations:
1. Works out your readiness score (are you ready for placement?)
2. Finds your skill gaps (what are you missing vs what companies want?)
3. Creates your priority action list (what should you fix first this week?)

Think of this file like a teacher who looks at your marks
and tells you exactly what to study next.
"""

import database


# ─────────────────────────────────────────────────────────
# THE 10 SKILLS WE TRACK
# ─────────────────────────────────────────────────────────

# These are the internal names used in the database
SKILLS = [
    'python', 'sql', 'dsa', 'excel',
    'powerbi', 'ml', 'communication',
    'aptitude', 'statistics', 'domain'
]

# These are the display names shown on charts and in the app
SKILL_LABELS = {
    'python':        'Python',
    'sql':           'SQL',
    'dsa':           'DSA',
    'excel':         'Excel',
    'powerbi':       'Power BI',
    'ml':            'ML Basics',
    'communication': 'Communication',
    'aptitude':      'Aptitude',
    'statistics':    'Statistics',
    'domain':        'Domain Knowledge'
}


# ─────────────────────────────────────────────────────────
# FUNCTION 1: calculate_readiness()
#
# This turns your skill ratings into ONE score out of 100.
#
# FORMULA:
#   SKILL SCORE   = 60 points maximum (based on your skill ratings)
#   ACTIVITY SCORE = 40 points maximum (based on what you actually DO)
#
# Why two parts?
# Because knowing things is not enough.
# You also need to practise. A student who has never done a
# mock interview is not ready - even if their skills are good.
# ─────────────────────────────────────────────────────────

def calculate_readiness(data):
    """
    Takes the student's form data as input.
    Returns a single number between 0 and 100.
    """

    # PART 1: Add up all 10 skill ratings
    # Each skill is rated 1 to 5.
    # If all 10 skills are rated 5, the total is 50 (maximum).
    # If all 10 skills are rated 1, the total is 10 (minimum).
    skill_total = (
        data.get('python',        1) +
        data.get('sql',           1) +
        data.get('dsa',           1) +
        data.get('excel',         1) +
        data.get('powerbi',       1) +
        data.get('ml',            1) +
        data.get('communication', 1) +
        data.get('aptitude',      1) +
        data.get('statistics',    1) +
        data.get('domain',        1)
    )

    # Convert skill total to a score out of 60.
    # We subtract 10 (the minimum) so the range starts at 0.
    # We divide by 40 (the gap between min=10 and max=50).
    # Then multiply by 60 to get a score out of 60.
    # Example: all skills at 3 → (30-10)/40 × 60 = 30 points
    skill_score = ((skill_total - 10) / 40) * 60

    # PART 2: Activity score - what did you DO this week?
    # Cap each activity so students cannot game the score
    # by entering impossibly large numbers.
    problems = min(data.get('problems', 0), 10)   # max 10 problems
    mocks    = min(data.get('mocks',    0),  3)   # max 3 mocks
    projects = min(data.get('projects', 0),  1)   # max 1 project
    courses  = min(data.get('courses',  0),  1)   # max 1 course

    activity_score = (
        (problems / 10) * 15 +    # up to 15 points for problems
        (mocks    /  3) * 15 +    # up to 15 points for mocks
        projects        *  5 +    # 5 points if you added a project
        courses         *  5      # 5 points if you completed a course
    )

    # Add both parts and round to one decimal place
    total = round(skill_score + activity_score, 1)

    # Make sure the score never goes above 100
    return min(total, 100)


# ─────────────────────────────────────────────────────────
# FUNCTION 2: get_risk_label()
#
# Turns the score number into a human-friendly label.
# Below 40 = Critical (red).
# 40 to 70 = Warning (yellow).
# Above 70 = Ready (green).
# ─────────────────────────────────────────────────────────

def get_risk_label(score):
    """
    Takes a score (0 to 100).
    Returns a label and colour.
    """
    if score >= 70:
        return {'label': 'Ready',    'color': '#22C55E', 'bg': '#F0FDF4'}
    elif score >= 40:
        return {'label': 'Warning',  'color': '#F59E0B', 'bg': '#FFFBEB'}
    else:
        return {'label': 'Critical', 'color': '#EF4444', 'bg': '#FFF1F2'}



# ─────────────────────────────────────────────────────────
# HELPER: skill_status()
# ONE rule used everywhere (dashboard AND admin page):
#   gap = required - yours
#   gap <= 0  -> "good"      (you meet or beat the requirement)
#   gap == 1  -> "warning"   (one level short)
#   gap >= 2  -> "critical"  (two or more levels short)
# ─────────────────────────────────────────────────────────

def skill_status(your_score, required):
    gap = required - your_score
    if gap <= 0:
        return "good"
    if gap == 1:
        return "warning"
    return "critical"

# ─────────────────────────────────────────────────────────
# FUNCTION 3: get_skill_gaps()
#
# This is the DATA MINING part of the project.
# It compares your skill ratings against what companies
# actually require for your target role.
#
# Gap = required score MINUS your score.
# If the gap is positive, you need to improve.
# If the gap is zero or negative, you already meet the requirement.
# ─────────────────────────────────────────────────────────

def get_skill_gaps(student):
    """
    Takes a student dictionary.
    Returns a list of gaps - one per skill, always in the same skill order
    (so the radar chart looks the same for every student).
    Each gap tells you: your score, required score, and status.
    """

    # Get the target role (default to Data Analyst if not set)
    role      = student.get('target_role', 'Data Analyst')

    # Get the industry benchmark for this role from the database
    benchmark = database.get_benchmark(role)

    # If no benchmark found, use safe defaults
    if not benchmark:
        benchmark = {}

    # Map each skill to its required level from the benchmark table
    bench_map = {
        'python':        benchmark.get('python_req',   3),
        'sql':           benchmark.get('sql_req',      3),
        'dsa':           benchmark.get('dsa_req',      3),
        'excel':         benchmark.get('excel_req',    2),
        'powerbi':       benchmark.get('powerbi_req',  2),
        'ml':            benchmark.get('ml_req',       2),
        'communication': benchmark.get('comm_req',     3),
        'aptitude':      benchmark.get('aptitude_req', 3),
        'statistics':    benchmark.get('stats_req',    3),
        'domain':        benchmark.get('domain_req',   3),
    }

    gaps = []

    # Loop through all 10 skills one by one
    for skill in SKILLS:

        your_score = student.get(skill, 1)        # what YOU rated
        required   = bench_map.get(skill, 3)       # what the company wants
        gap        = required - your_score          # the difference

        # Classify the gap (same rule the admin page uses)
        status = skill_status(your_score, required)

        gaps.append({
            'skill':      skill,
            'label':      SKILL_LABELS[skill],
            'your_score': your_score,
            'required':   required,
            'gap':        gap,
            'status':     status,
        })

    return gaps


# ─────────────────────────────────────────────────────────
# FUNCTION 4: get_priority_actions()
#
# Takes the gap list and turns it into specific advice.
# Each action says: which skill, how big the gap is,
# and what to DO about it this week.
# ─────────────────────────────────────────────────────────

# This dictionary maps each skill to a specific, actionable tip.
# These are shown in the Priority Actions section of the dashboard.
ACTION_TIPS = {
    'python': (
        "Practice 10 Python problems on HackerRank daily. "
        "Focus on data structures, file handling, and Pandas library. "
        "freeCodeCamp's Python course on YouTube is free and excellent."
    ),
    'sql': (
        "Solve SQL problems on LeetCode or HackerRank. "
        "Focus on JOINs, GROUP BY, subqueries, and window functions. "
        "W3Schools SQL tutorial is a great free starting point."
    ),
    'dsa': (
        "Study Data Structures (Arrays, Linked Lists, Trees) and "
        "Algorithms (Sorting, Searching) on GeeksforGeeks. "
        "Try 2 problems per day - consistency matters more than speed."
    ),
    'excel': (
        "Complete Microsoft Excel free course on Coursera (audit free). "
        "Practice VLOOKUP, pivot tables, and charts with real datasets. "
        "These skills appear in nearly every Data Analyst job description."
    ),
    'powerbi': (
        "Build 2 dashboards using free datasets from Kaggle. "
        "Follow Microsoft Learn's free Power BI learning path. "
        "This directly supports your OE subject this semester."
    ),
    'ml': (
        "Start with linear regression and logistic regression concepts. "
        "Andrew Ng's ML course on Coursera is free to audit. "
        "For Data Scientist roles, this skill carries very high weight."
    ),
    'communication': (
        "Do 1 mock interview per week - record yourself on your phone. "
        "Practice explaining your projects in 2 minutes without notes. "
        "Strong communication is often the deciding factor in final rounds."
    ),
    'aptitude': (
        "Practice 15 aptitude questions daily on IndiaBix. "
        "Focus on quantitative reasoning and logical puzzles. "
        "Most companies use aptitude tests as the first elimination round."
    ),
    'statistics': (
        "Study mean, median, mode, standard deviation, and probability "
        "distributions on Khan Academy (completely free). "
        "Statistics is the foundation of every Data Scientist role."
    ),
    'domain': (
        "Read 2 data science articles per week on Towards Data Science. "
        "Follow industry news on LinkedIn and subscribe to DataTalks.Club. "
        "Domain knowledge shows interviewers you are serious about the field."
    ),
}


def get_priority_actions(gaps):
    """
    Takes the gaps list from get_skill_gaps().
    Returns the top 5 actions sorted by urgency.
    Only includes skills that actually need improvement (gap > 0).
    """
    actions = []

    # Biggest gap first (Python's sort keeps ties in their original order)
    for gap_item in sorted(gaps, key=lambda g: g['gap'], reverse=True):
        # Only show skills that need improvement
        if gap_item['gap'] > 0:
            actions.append({
                'skill':   gap_item['label'],
                'gap':     gap_item['gap'],
                'from':    gap_item['your_score'],
                'to':      gap_item['required'],
                'tip':     ACTION_TIPS.get(gap_item['skill'], 'Practice this skill regularly.'),
                'urgency': gap_item['status'],
            })

    # Return only the top 5 most urgent
    return actions[:5]

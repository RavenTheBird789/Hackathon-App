"""NCAT Aggie Event Hub - main file for app"""
import calendar
import datetime as dt
import json
import math
import os
import urllib.request
from datetime import date

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
def DATA(name):
    """Look in ./data first, then next to this file (works with either layout)."""
    in_data = os.path.join(BASE, "data", name)
    return in_data if os.path.exists(in_data) else os.path.join(BASE, name)
URGENT_DAYS = 7

MAJORS = {
    "Engineering": ["Comp Sci", "Electrical", "Mechanical", "Civil", "Chemical", "Bioengineering", "Industrial"],
    "Science & Technology": ["Biology", "Chemistry", "Physics", "Mathematics", "Information Technology"],
    "Business": ["Accounting", "Business Administration", "Marketing", "Economics"],
    "Arts, Humanities & Social Sciences": ["English", "History", "Political Science", "Psychology", "Sociology", "Journalism & Media", "Music"],
    "Education": ["Elementary Education", "Special Education"],
    "Health & Human Sciences": ["Nursing", "Public Health", "Kinesiology"],
    "Agriculture": ["Agricultural Science", "Animal Science", "Food Science"],
}
ALL_MAJORS = [m for group in MAJORS.values() for m in group]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")


# ---------- data loading ----------
def load_hosts():
    """host.txt -> {host: importance level}"""
    hosts = {}
    with open(DATA("host.txt")) as f:
        f.readline()  # header
        for line in f:
            if line.strip():
                name, level = line.strip().split(",")
                hosts[name] = int(level)
    return hosts


class Task:
    def __init__(self, id: int, name: str, date: str, desc: str, location: str,
                 host: str, tags: list, mode: str = "In-Person",
                 distance: str = "", majors: list = None,
                 lat: float = None, lon: float = None):
        self.id = id
        self.task_name = name
        self.task_date = dt.date.fromisoformat(date)
        self.task_desc = desc
        self.task_location = location
        self.task_host = host
        self.task_tags = tags
        self.mode = mode
        self.distance = distance
        self.majors = majors or ["All Majors"]
        self.lat, self.lon = lat, lon
        self.approx = False
        self.maps_url = ""

    def days_until(self, current: date = None) -> int:
        return (self.task_date - (current or date.today())).days

    def time_til(self, current: date = None) -> str:
        """Human readable time until this task is due."""
        d = self.days_until(current)
        if d < 0:
            return "Past"
        if d == 0:
            return "Today"
        return "Tomorrow" if d == 1 else f"In {d} days"

    def is_urgent(self, current: date = None) -> bool:
        return 0 <= self.days_until(current) <= URGENT_DAYS

    def has_tag(self, tag: str) -> bool:
        return tag.lower() in (t.lower() for t in self.task_tags)

    def matches_major(self, major: str) -> bool:
        return "All Majors" in self.majors or major in self.majors or major == "Undecided"

    def get_importance(self, major: str = "Undecided") -> int:
        """Host level (host.txt) + 3 if due this week + 2 if it fits the user's major."""
        score = load_hosts().get(self.task_host, 0)
        if self.is_urgent():
            score += 3
        if major in self.majors:
            score += 2
        return score


def load_events():
    events = []
    with open(DATA("gen_events.txt" if os.path.exists(DATA("gen_events.txt")) else "events.txt")) as f:
        f.readline()
        for line in f:
            if not line.strip():
                continue
            p = line.rstrip("\n").split("|")
            i, name, d, desc, loc, host, mode, dist, tags, majors = p[:10]
            lat = float(p[10]) if len(p) > 11 and p[10] and p[11] else None
            lon = float(p[11]) if lat is not None else None
            events.append(Task(int(i), name, d, desc, loc, host,
                               [t for t in tags.split(";") if t], mode, dist,
                               [m for m in majors.split(";") if m], lat, lon))
    return events


# ---------- accounts ----------
def load_users():
    users = {}
    path = DATA("usernames.txt")
    if not os.path.exists(path):  # create it on first run
        with open(path, "w") as f:
            f.write("username|password_hash|role|major\n")
    with open(path) as f:
        f.readline()
        for line in f:
            if line.strip():
                u, h, role, major = line.rstrip("\n").split("|")
                users[u] = {"hash": h, "role": role, "major": major}
    return users


def save_users(users):
    with open(DATA("usernames.txt"), "w") as f:
        f.write("username|password_hash|role|major\n")
        for u, d in users.items():
            f.write(f"{u}|{d['hash']}|{d['role']}|{d['major']}\n")


def ensure_admin():
    users = load_users()
    if "admin" not in users:
        users["admin"] = {"hash": generate_password_hash("admin123"), "role": "admin", "major": "Comp Sci"}
        save_users(users)
        print("Created default admin (admin / admin123) - change this password!")


def current_user():
    """Returns dict for logged-in user, or a Guest by default."""
    name = session.get("user")
    users = load_users()
    if name in users:
        return {"name": name, **users[name]}
    return {"name": "Guest", "role": "guest", "major": "Undecided"}


# ---------- location ----------
def get_location():
    """User's lat/lon. Uses a saved/precise location if present, else ipwho.is (cached in session)."""
    if "loc" in session:
        return session["loc"]
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    local = ip in ("", "127.0.0.1", "::1") or ip.startswith(("192.168.", "10.", "172."))
    try:  # blank IP = ipwho.is uses the caller's public IP (right for local testing)
        with urllib.request.urlopen("https://ipwho.is/" + ("" if local else ip), timeout=3) as r:
            d = json.load(r)
        if d.get("success"):
            session["loc"] = {"lat": d["latitude"], "lon": d["longitude"], "src": "ip"}
            return session["loc"]
    except Exception:
        pass
    return None


def miles_between(lat1, lon1, lat2, lon2):
    """Great-circle (haversine) distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def attach_distance(events):
    """Fill in 'mi away' and a Google Maps directions link for events that have coordinates."""
    loc = get_location()
    for e in events:
        if e.lat is None:
            continue
        dest = f"{e.lat},{e.lon}"
        url = f"https://www.google.com/maps/dir/?api=1&destination={dest}&travelmode=walking"
        if loc:
            e.distance = f"{miles_between(loc['lat'], loc['lon'], e.lat, e.lon):.1f}"
            e.approx = loc.get("src") == "ip"
            url += f"&origin={loc['lat']},{loc['lon']}"
        e.maps_url = url
    return events


# ---------- logic ----------
def search(events, query):
    """Substring match on name and tags."""
    q = query.strip().lower()
    if not q:
        return events
    return [e for e in events if q in e.task_name.lower()
            or any(q in t.lower() for t in e.task_tags)]


def sort_events(events, major):
    """Most important first, then soonest."""
    return sorted(events, key=lambda e: (-e.get_importance(major), e.task_date))


def deadline(current, event_date):
    """Days between today and an event; 'urgent' (red dot + notification) if within a week."""
    diff = (event_date - current).days
    return diff, 0 <= diff <= URGENT_DAYS


def notify(events, current):
    """Colorful NCAT-themed notifications for upcoming events."""
    notes = []
    for e in events:
        diff, urgent = deadline(current, e.task_date)
        if urgent:
            notes.append({"color": "red" if diff <= 1 else "gold",
                          "text": f"{e.task_name} - {e.time_til(current).lower()} at {e.task_location}"})
    return notes


def today(current: str) -> int:
    """Day of month from a yyyy-mm-dd string."""
    return int(current[8:])


def build_calendar(year, month, events, current):
    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        row = []
        for d in week:
            if d == 0:
                row.append(None)
                continue
            day = date(year, month, d)
            todays = [e for e in events if e.task_date == day]
            row.append({"n": d, "iso": day.isoformat(), "today": day == current,
                        "dots": min(len(todays), 3),
                        "urgent": any(deadline(current, e.task_date)[1] for e in todays)})
        weeks.append(row)
    return weeks


def shift_month(year, month, delta):
    m = month - 1 + delta
    return year + m // 12, m % 12 + 1


# ---------- routes ----------
@app.route("/")
def home():
    cur = date.today()
    user = current_user()
    try:
        y, m = map(int, request.args.get("m", f"{cur.year}-{cur.month}").split("-"))
        date(y, m, 1)
    except ValueError:
        y, m = cur.year, cur.month

    all_events = attach_distance([e for e in load_events() if e.days_until(cur) >= 0])
    events = search(all_events, request.args.get("q", ""))
    tag, day = request.args.get("tag", ""), request.args.get("day", "")
    if tag:
        events = [e for e in events if e.has_tag(tag)]
    if day:
        events = [e for e in events if e.task_date.isoformat() == day]
    if request.args.get("major"):
        events = [e for e in events if e.matches_major(user["major"])]
    if request.args.get("urgent"):
        events = [e for e in events if e.is_urgent(cur)]

    py, pm = shift_month(y, m, -1)
    ny, nm = shift_month(y, m, 1)
    return render_template("page.html", page="home", user=user, events=events,
                           weeks=build_calendar(y, m, all_events, cur),
                           month_name=f"{calendar.month_name[m]} {y}",
                           prev=f"{py}-{pm}", next=f"{ny}-{nm}", cur_month=f"{y}-{m}",
                           args=request.args, bookmarks=session.get("bookmarks", []),
                           tags=sorted({t for e in all_events for t in e.task_tags}),
                           sorted_events=sort_events(events, user["major"]))


@app.route("/location", methods=["POST"])
def set_location():
    """Precise location from the browser's GPS (more accurate than IP)."""
    try:
        d = request.get_json()
        session["loc"] = {"lat": float(d["lat"]), "lon": float(d["lon"]), "src": "gps"}
        return jsonify(ok=True)
    except (TypeError, ValueError, KeyError):
        return jsonify(ok=False), 400


@app.route("/bookmark/<int:eid>", methods=["POST"])
def bookmark(eid):
    marks = session.get("bookmarks", [])
    marks.remove(eid) if eid in marks else marks.append(eid)
    session["bookmarks"] = marks
    return redirect(request.referrer or url_for("home"))


@app.route("/bookmarks")
def bookmarks():
    marks = session.get("bookmarks", [])
    events = attach_distance([e for e in load_events() if e.id in marks])
    return render_template("page.html", page="bookmarks", user=current_user(),
                           events=events, bookmarks=marks)


@app.route("/notifications")
def notifications():
    cur = date.today()
    events = sorted(load_events(), key=lambda e: e.task_date)
    return render_template("page.html", page="notifications", user=current_user(),
                           notes=notify(events, cur))


@app.route("/profile")
def profile():
    user = current_user()
    users = load_users() if user["role"] == "admin" else {}
    return render_template("page.html", page="profile", user=user, users=users, majors=MAJORS)


@app.route("/register", methods=["POST"])
def register():
    """Create an account. Guest by default until someone registers."""
    u, p = request.form["username"].strip(), request.form["password"]
    users = load_users()
    if not u or not p or "|" in u or u in users:
        flash("Pick a different username and enter a password.")
    else:
        users[u] = {"hash": generate_password_hash(p), "role": "user",
                    "major": request.form.get("major") if request.form.get("major") in ALL_MAJORS else "Undecided"}
        save_users(users)
        session["user"] = u
    return redirect(url_for("profile"))


@app.route("/login", methods=["POST"])
def login():
    u, p = request.form["username"].strip(), request.form["password"]
    users = load_users()
    if u in users and check_password_hash(users[u]["hash"], p):
        session["user"] = u
    else:
        flash("Wrong username or password.")
    return redirect(url_for("profile"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))


@app.route("/admin/<action>/<name>", methods=["POST"])
def admin(action, name):
    """Admin-only: delete accounts or reset passwords."""
    if current_user()["role"] != "admin":
        return redirect(url_for("home"))
    users = load_users()
    if name in users and name != "admin":
        if action == "delete":
            del users[name]
        elif action == "reset" and request.form.get("password"):
            users[name]["hash"] = generate_password_hash(request.form["password"])
        save_users(users)
    return redirect(url_for("profile"))


ensure_admin()

if __name__ == "__main__":
    print(date.today())
    app.run(debug=True)

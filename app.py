from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

# Compatibility helper for Python 2/3 differences
try:
    unicode  # noqa: F401
except NameError:
    unicode = str

# Base path for the JSON data file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "courses.json")

# Allowed statuses
ALLOWED_STATUSES = {"Not Started", "In Progress", "Completed"}

# Initialize Flask app
app = Flask(__name__)

# --------- Helper utilities (data I/O, validation) ---------

def ensure_data_file():
    """
    Ensure the data directory and courses.json exist.
    If not, create an empty list in the file.
    """
    dirpath = BASE_DIR
    if not os.path.exists(dirpath):
        try:
            os.makedirs(dirpath)
        except Exception:
            pass

    if not os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "w") as f:
                json.dump([], f)
        except Exception:
            pass

def load_courses():
    """
    Load and return the list of courses from the JSON file.
    Returns an empty list if the file is empty or invalid.
    """
    ensure_data_file()
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        # Propagate error to caller to handle gracefully
        raise

def save_courses(courses):
    """
    Persist the provided courses list to the JSON file.
    """
    ensure_data_file()
    with open(DATA_FILE, "w") as f:
        json.dump(courses, f, indent=2)

def get_next_id(courses):
    """
    Compute the next ID to use (auto-increment).
    """
    if not courses:
        return 1
    return max(course.get("id", 0) for course in courses) + 1

def get_course_by_id(courses, cid):
    """
    Find a course by ID. Return the course dict or None if not found.
    """
    for c in courses:
        if c.get("id") == cid:
            return c
    return None

def is_valid_date(date_str):
    """
    Validate that date_str is in YYYY-MM-DD format.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except Exception:
        return False

def validate_course(data, require_all=False):
    """
    Validate course data.
    If require_all is True, all fields must be present and valid.
    Returns a list of error messages (empty if valid).
    """
    errors = []

    # name
    if require_all or "name" in data:
        name = data.get("name")
        if not isinstance(name, (str, unicode)) or not name.strip():
            errors.append("name is required and must be a non-empty string")

    # description
    if require_all or "description" in data:
        desc = data.get("description")
        if not isinstance(desc, (str, unicode)) or not desc.strip():
            errors.append("description is required and must be a non-empty string")

    # target_date
    if require_all or "target_date" in data:
        td = data.get("target_date")
        if not isinstance(td, (str, unicode)) or not is_valid_date(td):
            errors.append("target_date is required and must be in format YYYY-MM-DD")

    # status
    if require_all or "status" in data:
        st = data.get("status")
        if not isinstance(st, (str, unicode)) or st not in ALLOWED_STATUSES:
            errors.append("status is required and must be one of: Not Started, In Progress, Completed")

    return errors

# Ensure the data file exists at startup
ensure_data_file()

# --------- Routes (CRUD) ---------

@app.route("/api/courses", methods=["POST"])
def create_course():
    """
    Create a new course.
    Expects JSON body with: name, description, target_date, status
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        data = None

    if not isinstance(data, dict):
        data = {}

    errors = validate_course(data, require_all=True)
    if errors:
        return jsonify({"errors": errors}), 400

    try:
        courses = load_courses()
    except Exception:
        return jsonify({"error": "Failed to read data file"}), 500

    new_id = get_next_id(courses)
    course = {
        "id": new_id,
        "name": data["name"].strip(),
        "description": data["description"].strip(),
        "target_date": data["target_date"],
        "status": data["status"],
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")  # UTC timestamp
    }

    courses.append(course)

    try:
        save_courses(courses)
    except Exception:
        return jsonify({"error": "Failed to write data file"}), 500

    return jsonify(course), 201

@app.route("/api/courses", methods=["GET"])
def get_all_courses():
    """
    Retrieve all courses.
    """
    try:
        courses = load_courses()
    except Exception:
        return jsonify({"error": "Failed to read data file"}), 500

    return jsonify(courses), 200

# Path-based fetch: GET/PUT/DELETE /api/courses/<id>
@app.route('/api/courses/<int:course_id>', methods=['GET', 'PUT', 'DELETE'])
def course(course_id):
    try:
        courses = load_courses()
    except Exception:
        return jsonify({"error": "Failed to read data file"}), 500

    if request.method == 'GET':
        course = next((c for c in courses if c['id'] == course_id), None)
        if course:
            return jsonify(course)
        else:
            return jsonify({'error': 'Course not found'}), 404

    elif request.method == 'PUT':
        data = request.get_json()
        course = next((c for c in courses if c['id'] == course_id), None)
        if course:
            course.update(data)
            try:
                save_courses(courses)
            except Exception:
                return jsonify({"error": "Failed to write data file"}), 500
            return jsonify(course)
        else:
            return jsonify({'error': 'Course not found'}), 404

    elif request.method == 'DELETE':
        course = next((c for c in courses if c['id'] == course_id), None)
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        courses = [c for c in courses if c['id'] != course_id]

        try:
            save_courses(courses)
        except Exception:
            return jsonify({"error": "Failed to write data file"}), 500

        return jsonify({"message": "Course deleted"}), 200

# Fallback: also support query parameter style GET /api/courses/?id=1
@app.route("/api/courses/", methods=["GET"])
def get_course_by_query():
    """
    Retrieve a single course by ID via query parameter: /api/courses/?id=2
    """
    id_param = request.args.get("id")
    if id_param is None:
        return jsonify({"error": "Missing required query parameter: id"}), 400
    try:
        cid = int(id_param)
    except Exception:
        return jsonify({"error": "id must be an integer"}), 400

    try:
        courses = load_courses()
    except Exception:
        return jsonify({"error": "Failed to read data file"}), 500

    course = get_course_by_id(courses, cid)
    if not course:
        return jsonify({"error": "Course not found"}), 404
    return jsonify(course), 200

@app.route("/api/courses/", methods=["PUT"])
def update_course():
    """
    Full update of a course (all fields required).
    Expects JSON body with: id, name, description, target_date, status
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        data = None

    if not isinstance(data, dict):
        data = {}

    if "id" not in data:
        return jsonify({"error": "Missing required field: id"}), 400

    errors = validate_course(data, require_all=True)
    if errors:
        return jsonify({"errors": errors}), 400

    try:
        courses = load_courses()
    except Exception:
        return jsonify({"error": "Failed to read data file"}), 500

    cid = data["id"]
    course = get_course_by_id(courses, cid)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    # Update fields
    course.update({
        "name": data["name"].strip(),
        "description": data["description"].strip(),
        "target_date": data["target_date"],
        "status": data["status"]
    })

    try:
        save_courses(courses)
    except Exception:
        return jsonify({"error": "Failed to write data file"}), 500

    return jsonify(course), 200

@app.route("/api/courses/", methods=["DELETE"])
def delete_course():
    """
    Delete a course by ID (id must be provided in JSON body).
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        data = None

    if not isinstance(data, dict) or "id" not in data:
        return jsonify({"error": "Missing required field: id"}), 400

    try:
        courses = load_courses()
    except Exception:
        return jsonify({"error": "Failed to read data file"}), 500

    cid = data["id"]
    course = get_course_by_id(courses, cid)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    courses = [c for c in courses if c.get("id") != cid]

    try:
        save_courses(courses)
    except Exception:
        return jsonify({"error": "Failed to write data file"}), 500

    return jsonify({"message": "Course deleted"}), 200

@app.route("/api/courses/stats", methods=["GET"])
def course_stats():
    """
    Return statistics about courses:
    - Total number of courses
    - Number of courses by status
    """
    try:
        courses = load_courses()
    except Exception:
        return jsonify({"error": "Failed to read data file"}), 500

    total = len(courses)

    stats = {
        "total_courses": total,
        "status_counts": {
            "Not Started": 0,
            "In Progress": 0,
            "Completed": 0
        }
    }

    for course in courses:
        status = course.get("status")
        if status in stats["status_counts"]:
            stats["status_counts"][status] += 1

    return jsonify(stats), 200

# --------- Run the app ---------

if __name__ == "__main__":
    app.run(debug=True)

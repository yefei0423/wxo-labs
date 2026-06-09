# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
"""
async_app.py — Flask REST API for WxO Asynchronous Tool Example
...
"""

import time
import uuid
from datetime import datetime

import requests

import threading

from flask import Flask, request, jsonify


app = Flask(__name__)

# ── In-memory job tracker ──────────────────────────────────────────────
jobs = {}

def process_background_job(job_id, job_name, duration, callback_url=None):
    """Background thread: simulates work, updates job tracker, optionally fires callback."""
    print(f"[Thread] Starting simulated long job '{job_name}' ({job_id}) for {duration} seconds...")
    jobs[job_id]["status"] = "Running"
    jobs[job_id]["started_at"] = datetime.now().isoformat()

    time.sleep(duration)

    end_time = datetime.now()
    jobs[job_id]["status"] = "Success"
    jobs[job_id]["completed_at"] = end_time.isoformat()
    jobs[job_id]["time_taken"] = f"{duration:.2f} seconds"
    jobs[job_id]["records_processed"] = duration * 42
    jobs[job_id]["message"] = f"Background job '{job_name}' is officially complete!"

    print(f"[Thread] Job {job_id} finished.")

    # If a callbackUrl was provided (OpenAPI async pattern), POST results back
    if callback_url:
        payload = {k: v for k, v in jobs[job_id].items()}
        try:
            headers = {"Content-Type": "application/json"}
            response = requests.post(callback_url, json=payload, headers=headers)
            print(f"[Thread] Callback response status: {response.status_code}")
            print(f"[Thread] Callback response body: {response.text}")
        except Exception as e:
            print(f"[Thread] Error sending callback: {e}")


# ── Endpoint: Start a job (returns immediately) ───────────────────────
@app.route('/start-job', methods=['POST'])
def start_job():
    data = request.json or {}
    job_name = data.get('job_name', 'Unknown Task')
    duration = data.get('duration', 10)

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "job_name": job_name,
        "status": "Queued",
        "duration": duration,
        "started_at": None,
        "completed_at": None,
        "time_taken": None,
        "records_processed": None,
        "message": f"Job '{job_name}' has been queued."
    }

    # Fire and forget in a background thread
    t = threading.Thread(target=process_background_job, args=(job_id, job_name, duration))
    t.daemon = True
    t.start()

    print(f"\n[API] Started job {job_id}: '{job_name}' for {duration}s")
    return jsonify({
        "job_id": job_id,
        "status": "Queued",
        "message": f"Job '{job_name}' has been started! Use job ID '{job_id}' to check its status."
    }), 200


# ── Endpoint: Check job status ────────────────────────────────────────
@app.route('/job-status/<job_id>', methods=['GET'])
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": f"No job found with ID '{job_id}'."}), 404
    return jsonify(job), 200


# ── Endpoint: List all jobs ───────────────────────────────────────────
@app.route('/jobs', methods=['GET'])
def list_jobs():
    return jsonify(list(jobs.values())), 200


# ── Legacy: OpenAPI callback-based endpoint (kept for reference) ──────
@app.route('/long-task', methods=['POST'])
def handle_long_task():
    data = request.json or {}
    job_name = data.get('job_name', 'Unknown Task')
    duration = data.get('duration', 10)

    callback_url = request.headers.get('callbackUrl') or request.headers.get('callbackurl')

    print(f"\n[API] Received request for Job: {job_name}, Duration: {duration}")
    print(f"[API] Callback URI provided: {callback_url}")

    if not callback_url:
        return jsonify({"error": "Missing callbackUrl header."}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "job_name": job_name,
        "status": "Queued",
        "duration": duration,
        "started_at": None,
        "completed_at": None,
        "time_taken": None,
        "records_processed": None,
        "message": f"Job '{job_name}' has been queued."
    }

    t = threading.Thread(target=process_background_job, args=(job_id, job_name, duration, callback_url))
    t.daemon = True
    t.start()

    return jsonify({
        "status": "accepted",
        "description": "The job has been accepted and is processing in the background."
    }), 202


@app.route('/', methods=['GET'])
def health():
    return jsonify({"status": "running", "description": "wxo-async-test server is up."}), 200

if __name__ == '__main__':
    print("Starting Flask server on port 5055...")
    app.run(host='0.0.0.0', port=5055, debug=True)

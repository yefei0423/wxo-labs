# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
"""
async_tools.py — WxO Python Tools for Non-Blocking Background Jobs
...
"""

import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool

# ── IMPORTANT: Update this URL to your live ngrok/public URL ──────────
BASE_URL = "https://your-ngrok-url.ngrok-free.app"


@tool
def start_background_job(job_name: str, duration: int = 10) -> str:
    """Starts a long-running background job. Returns immediately with a Job ID.
    The user can continue chatting and check back later using check_job_status.

    Args:
        job_name (str): A descriptive name for the background job.
        duration (int): How many seconds the job should run (default 10).

    Returns:
        str: A message confirming the job was started, including the Job ID.
    """
    try:
        resp = requests.post(
            f"{BASE_URL}/start-job",
            json={"job_name": job_name, "duration": duration},
            timeout=10
        )
        data = resp.json()
        job_id = data.get("job_id", "unknown")
        return (
            f"✅ Background job started!\n"
            f"- **Job Name:** {job_name}\n"
            f"- **Job ID:** {job_id}\n"
            f"- **Duration:** ~{duration} seconds\n\n"
            f"You can keep chatting! When you want to check if it's done, "
            f"just ask me: \"Check job status for {job_id}\""
        )
    except Exception as e:
        return f"❌ Failed to start background job: {e}"


@tool
def check_job_status(job_id: str) -> str:
    """Checks the current status of a previously started background job.

    Args:
        job_id (str): The Job ID returned when the job was started.

    Returns:
        str: The current status and details of the job.
    """
    try:
        resp = requests.get(f"{BASE_URL}/job-status/{job_id}", timeout=10)
        if resp.status_code == 404:
            return f"❌ No job found with ID '{job_id}'. Please check the ID and try again."

        data = resp.json()
        status = data.get("status", "Unknown")

        if status in ("Queued", "Running"):
            return (
                f"⏳ Job **{job_id}** is still **{status}**...\n"
                f"- **Job Name:** {data.get('job_name')}\n"
                f"Check back in a moment!"
            )
        else:
            return (
                f"🎉 Job **{job_id}** is **complete!**\n\n"
                f"- **Job Name:** {data.get('job_name')}\n"
                f"- **Message:** {data.get('message')}\n"
                f"- **Records Processed:** {data.get('records_processed')}\n"
                f"- **Started At:** {data.get('started_at')}\n"
                f"- **Completed At:** {data.get('completed_at')}\n"
                f"- **Time Taken:** {data.get('time_taken')}"
            )
    except Exception as e:
        return f"❌ Error checking job status: {e}"

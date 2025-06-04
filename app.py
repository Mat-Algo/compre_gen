import os
import json
import logging
import boto3
import hashlib
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from pydub.utils import which
from pydub import AudioSegment
from dotenv import load_dotenv
from google import genai
import google.auth
import google.auth.transport.requests
import requests
import os

# Load environment variables from .env file if present
load_dotenv(override=True)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

os.environ["PATH"] += os.pathsep + "/usr/bin"
AudioSegment.converter = which("ffmpeg")
stage = "test"

# Import your pipeline functions from gen.py
from gen import (
    generate_outline,
    generate_code,
    write_temp,
    render_voiceover_scene,
)
# Configure logging
logging.basicConfig(level=logging.INFO)

# S3 configuration (using S3 exclusively)
S3_BUCKET = os.getenv("S3_BUCKET")  # e.g., "compre_gen"
if not S3_BUCKET:
    raise Exception("S3_BUCKET environment variable must be configured.")

# Create FastAPI app instance.
# Using the stage name as part of the root path (optional)
app = FastAPI(root_path=f"/{stage}" if stage else "")

# Set up CORS (adjust allowed origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

###############################################################################
# Data Models for Incoming Requests
###############################################################################
class VideoGenerationRequest(BaseModel):
    question: str
    user_answer: str

class MCQReviewRequest(BaseModel):
    question: str
    selected_option: str
    expected_answer: str

def upload_prompt_to_s3(prompt: str, s3_key: str):
    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=prompt.encode("utf-8"),
        ContentType="text/plain"
    )
    return s3_key


def trigger_cloud_run_job(job_name, region, project_id, prompt_s3_key):
    # Obtain fresh access token
    credentials, _ = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())
    token = credentials.token

    url = (
        f"https://run.googleapis.com/v2/projects/{project_id}"
        f"/locations/{region}/jobs/{job_name}:run"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # Use the v2 'overrides' schema to inject your prompt as an arg
    body = {
        "overrides": {
            "containerOverrides": [
                {
                    "args": [prompt_s3_key]
                }
            ]
        }
    }

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code == 200:
        logging.info("Cloud Run Job triggered successfully")
    else:
        logging.error(f"Failed to trigger Cloud Run Job: {resp.text}")
        resp.raise_for_status()



###############################################################################
# Utility Functions
###############################################################################
def generate_video_key(prompt: str) -> str:
    """
    Generate a deterministic key (16 hex characters) based on the given prompt.
    This serves as a unique filename component.
    """
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]

def upload_file_to_s3(local_path: str, s3_key: str) -> str:
    """
    Upload the file at local_path to the S3 bucket using s3_key.
    Returns the public URL of the uploaded file.    
    """
    s3_client = boto3.client("s3")
    s3_client.upload_file(local_path, S3_BUCKET, s3_key)
    public_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"
    return public_url

###############################################################################
# Helper Functions for Reference Retrieval (unchanged)
###############################################################################
def get_youtube_references(prompt: str, n: int = 3) -> list:
    """
    Use the YouTube Data API to fetch relevant videos for the given prompt.
    Returns a list of dicts with 'title' and 'url'.
    """
    search_query = prompt
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&maxResults={n}&q={requests.utils.quote(search_query)}"
        f"&key={YOUTUBE_API_KEY}&type=video"
    )

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        results = []

        for item in data.get("items", []):
            video_id = item["id"].get("videoId")
            title = item["snippet"]["title"]
            if video_id:
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                results.append({"title": title, "url": video_url})

        return results
    except Exception as e:
        logging.error("Error fetching YouTube videos: %s", e)
        return [{"title": "No videos found", "url": ""}]

def get_article_references(prompt: str, n: int = 2) -> list:
    article_prompt = (
        f"Provide {n} educational article or resource URLs that best explains the topic in: {prompt}. "
        "Prefer academic sources, educational websites, or reputable publications. "
        "Return as a JSON array of objects with 'title' and 'url' fields."
    )
    response = client.models.generate_content(model="gemini-2.0-flash", contents=article_prompt)
    raw = response.text.strip()
    try:
        return json.loads(raw)
    except Exception:
        urls = [u.strip() for u in raw.splitlines() if u.startswith("http")]
        return [{"title": f"Reference Article {i+1}", "url": url} for i, url in enumerate(urls)]

###############################################################################
# Background Task Functions (S3-only)
###############################################################################
def background_video_generation(topic: str) -> tuple:
    try:
        logging.info("Generating video for topic: %s", topic)
        outline = generate_outline(topic)
        code = generate_code(topic, outline)
        py_file, uid = write_temp(code)
        rendered_path = render_voiceover_scene(py_file, uid)

        
        video_key = generate_video_key(topic)
        video_filename = f"{video_key}.mp4"

        video_url = upload_file_to_s3(rendered_path, video_filename)
        try:
            os.remove(py_file)
        except Exception as cleanup_err:
            logging.warning("Failed to delete temp file %s: %s", py_file, cleanup_err)
        
        return video_key, video_url
    except Exception as e:
        logging.error("Error generating video: %s", e, exc_info=True)
        return None, None

# def background_mcq_review(topic: str, question: str) -> tuple:
#     """
#     Generates an MCQ review video.
#     Uses S3 exclusively to store both the video and a JSON response with reference links.
#     Returns a tuple: (video_key, video_url)
#     """
#     try:
#         logging.info("Generating MCQ review video for topic: %s", topic)
#         outline = generate_outline(topic)
#         code = generate_code(topic, outline)
#         py_file, uid = write_temp(code)
#         rendered_path = render_voiceover_scene(py_file, uid)

        
#         video_key = generate_video_key(topic)
#         video_filename = f"{video_key}.mp4"
        
#         if S3_BUCKET:
#             video_url = upload_file_to_s3(rendered_path, video_filename)
#             logging.info("MCQ review video uploaded to S3: %s", video_url)
#         else:
#             raise Exception("S3_BUCKET is not configured.")
        
#         youtube_refs = get_youtube_references(question)
#         article_refs = get_article_references(question)
#         video_title = f"Explanation: {question[:50]}{'...' if len(question) > 50 else ''}"
#         response = {
#             "resources": {
#                 "video": {"title": video_title, "url": video_url},
#                 "ref_videos": youtube_refs,
#                 "ref_articles": article_refs
#             }
#         }
        
#         json_key = f"{video_key}.json"
#         s3_client = boto3.client("s3")
#         s3_client.put_object(
#             Bucket=S3_BUCKET,
#             Key=json_key,
#             Body=json.dumps(response).encode("utf-8"),
#             ContentType="application/json"
#         )
#         logging.info("JSON response uploaded to S3 under key %s", json_key)
        
#         try:
#             os.remove(py_file)
#         except Exception as cleanup_err:
#             logging.warning("Failed to delete temp file %s: %s", py_file, cleanup_err)
        
#         return video_key, video_url
#     except Exception as e:
#         logging.error("Error generating MCQ review video: %s", e, exc_info=True)
#         return None, None

###############################################################################
# API Endpoints
###############################################################################
@app.post("/generate_video")
async def generate_video(request_data: VideoGenerationRequest, background_tasks: BackgroundTasks):
    """
    Triggers video generation for a given question.
    Returns a message with the computed video key and status endpoint for polling.
    """
    question = request_data.question
    user_ans = request_data.user_answer
    prompt = (
        f"Here's a question: \"{question}\".\n"
        f"The user answered: \"{user_ans}\".\n\n"
        "Generate a short explanatory video script that:\n"
        "1️⃣ Explains the expected answer in detail.\n"
        "2️⃣ Points out where the user's answer is missing or incorrect.\n"
        "3️⃣ Provides clear guidance on how to improve."
    )
    video_key = generate_video_key(prompt)
    prompt_s3_key = f"prompts/{video_key}.txt"
    upload_prompt_to_s3(prompt, prompt_s3_key)
    trigger_cloud_run_job(
        job_name="my-worker-job",
        region="us-central1",
        project_id="gen-lang-client-0755469978",
        prompt_s3_key=prompt_s3_key
    )
    youtube_refs = get_youtube_references(question)
    article_refs = get_article_references(question)
    return JSONResponse(content={
        "resources": {
            "video": {
                "status_endpoint": f"/status/video/{video_key}"
            },
            "ref_videos": youtube_refs,
            "ref_articles": article_refs
        }
    }, status_code=202)

@app.get("/status/video/{video_key}")
async def video_status(video_key: str):
    s3_client = boto3.client("s3")
    json_key = f"{video_key}.json"
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=json_key)
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=json_key)
        response_content = obj["Body"].read().decode("utf-8")
        response_data = json.loads(response_content)
        return JSONResponse(content=response_data, status_code=200)
    except s3_client.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            return JSONResponse(content={"status": "processing"}, status_code=202)
        else:
            return JSONResponse(content={"error": "Error accessing S3", "details": str(e)}, status_code=500)

@app.post("/review/mcq")
async def review_mcq(request_data: MCQReviewRequest, background_tasks: BackgroundTasks):
    """
    Triggers MCQ review video generation.
    Returns reference links immediately and indicates the status endpoint for polling.
    """
    question = request_data.question
    user_ans = request_data.selected_option
    correct_ans = request_data.expected_answer
    prompt = (
        f"Here's a multiple-choice question: \"{question}\".\n"
        f"The user selected answer: \"{user_ans}\".\n"
        f"The correct answer is: \"{correct_ans}\".\n\n"
        "Generate a short explanatory video script that:\n"
        "1️⃣ Explains why the correct answer is right.\n"
        "2️⃣ If the user's answer is wrong, explains the misconception or error.\n"
        "3️⃣ Provides key concepts to remember for similar questions."
    )
    video_key = generate_video_key(prompt)
    prompt_s3_key = f"prompts/{video_key}.txt"
    upload_prompt_to_s3(prompt, prompt_s3_key)
    
    trigger_cloud_run_job(
        job_name="my-worker-job",
        region="us-central1",
        project_id="gen-lang-client-0755469978",
        prompt_s3_key=prompt_s3_key
    )
    youtube_refs = get_youtube_references(question)
    article_refs = get_article_references(question)
    return JSONResponse(content={
        "resources": {
            "video": {
                "title": f"Explanation: {question[:50]}{'...' if len(question) > 50 else ''}",
                "status_endpoint": f"/status/mcq/{video_key}"
            },
            "ref_videos": youtube_refs,
            "ref_articles": article_refs
        }
    }, status_code=202)

@app.get("/status/mcq/{video_key}")
async def mcq_status(video_key: str):
    """
    Polling endpoint to check for a JSON response stored in S3 with key <video_key>.json.
    Returns the JSON data if available, otherwise a processing status.
    """
    s3_client = boto3.client("s3")
    json_key = f"{video_key}.json"
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=json_key)
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=json_key)
        response_content = obj["Body"].read().decode("utf-8")
        response_data = json.loads(response_content)
        return JSONResponse(content=response_data, status_code=200)
    except s3_client.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            return JSONResponse(content={"status": "processing"}, status_code=202)
        else:
            return JSONResponse(content={"error": "Error accessing S3", "details": str(e)}, status_code=500)

###############################################################################
# Optional: HTML Client for Testing
###############################################################################
@app.get("/", response_class=HTMLResponse)
async def index():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Video Generation App</title>
    </head>
    <body>
        <h1>Video Generation App</h1>
        <form id="videoForm">
            <label for="question">Question:</label>
            <input type="text" id="question" name="question" required><br>
            <label for="user_answer">User Answer:</label>
            <input type="text" id="user_answer" name="user_answer" required><br>
            <button type="submit">Generate Video</button>
        </form>
        <div id="response"></div>
        <script>
        document.getElementById("videoForm").addEventListener("submit", async function(e) {
            e.preventDefault();
            const question = document.getElementById("question").value;
            const user_answer = document.getElementById("user_answer").value;
            const responseDiv = document.getElementById("response");
            const res = await fetch("/generate_video", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({question, user_answer})
            });
            const data = await res.json();
            responseDiv.innerText = JSON.stringify(data, null, 2);
        });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

###############################################################################
# Run the Application Locally (for testing)
###############################################################################
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

# # Create a Lambda handler for the FastAPI app.
# from mangum import Mangum
# handler = Mangum(app)

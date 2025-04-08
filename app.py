import os
import json
import shutil
import logging
import boto3
import hashlib
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file, if present
load_dotenv(override=True)

# Import your existing functions from gen.py
from gen import (
    generate_voiceover_manim_code,
    write_manim_file,
    render_voiceover_scene,
    client,
    extract_code,
)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Local video directory (in case S3 is not used)
VIDEO_DIR = os.getenv("VIDEO_DIR", "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# S3 configuration (if set, files will be uploaded to S3/CDN)
S3_BUCKET = os.getenv("S3_BUCKET")  # e.g., "my-video-bucket"
# AWS credentials (set via environment: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION)

# Create FastAPI app instance
app = FastAPI()

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

###############################################################################
# Utility Functions
###############################################################################
def generate_video_key(prompt: str) -> str:
    """
    Generate a deterministic key (16 hex characters) based on the given prompt.
    This helps produce the same file name for the same question and answer.
    """
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]

def upload_file_to_s3(local_path: str, s3_key: str) -> str:
    """
    Upload the file at local_path to the S3 bucket under s3_key.
    Returns the public URL of the uploaded file.
    """
    s3_client = boto3.client("s3")
    s3_client.upload_file(local_path, S3_BUCKET, s3_key)
    public_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"
    return public_url

###############################################################################
# Helper Functions for Reference Retrieval (same as before)
###############################################################################
def get_youtube_references(prompt: str, n: int = 3) -> list:
    youtube_prompt = (
        f"Provide {n} YouTube video URLs that best explain the topic in: {prompt}. "
        "Return as a JSON array of objects with 'title' and 'url' fields."
    )
    response = client.models.generate_content(model="gemini-2.0-flash", contents=youtube_prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        parsed = json.loads(raw)
        logging.info("Parsed YouTube references: %s", parsed)
        return parsed
    except Exception as e:
        logging.error("Error parsing YouTube JSON: %s", e)
        urls = [u.strip() for u in raw.splitlines() if u.strip().startswith("http")]
        fallback = [{"title": f"Reference Video {i+1}", "url": url} for i, url in enumerate(urls)]
        return fallback

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
# Background Task Functions
###############################################################################
def background_video_generation(topic: str) -> tuple:
    """
    Generates a video from the Manim voiceover pipeline.
    The video file is given a deterministic file name (using generate_video_key).
    If S3 is configured, the file is uploaded and the public URL is returned;
    otherwise, it is saved locally.
    Returns a tuple: (video_key, video_url)
    """
    try:
        logging.info("Generating video for topic: %s", topic)
        # Generate the video code and file using your existing pipeline
        code = generate_voiceover_manim_code(topic)
        py_file, _ = write_manim_file(code)
        rendered_path = render_voiceover_scene(py_file)
        
        # Use a deterministic key (for the given prompt) for naming
        video_key = generate_video_key(topic)
        video_filename = f"{video_key}.mp4"
        
        if S3_BUCKET:
            video_url = upload_file_to_s3(rendered_path, video_filename)
            logging.info("Video uploaded to S3: %s", video_url)
        else:
            local_dest = os.path.join(VIDEO_DIR, video_filename)
            shutil.copy(rendered_path, local_dest)
            video_url = f"/videos/{video_filename}"
            logging.info("Video stored locally at: %s", video_url)
        
        # Cleanup temporary files and folders
        try:
            os.remove(py_file)
        except Exception as cleanup_err:
            logging.warning("Failed to delete temp file %s: %s", py_file, cleanup_err)
        folder_path = "media"
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logging.info("Temporary media folder deleted.")
        
        return video_key, video_url
    except Exception as e:
        logging.error("Error generating video: %s", e)
        return None, None

def background_mcq_review(topic: str, question: str) -> tuple:
    """
    Similar to background_video_generation, but for MCQ review.
    Generates a deterministic video key for the review video.
    Also writes a JSON file locally (for polling) if not using S3.
    Returns a tuple: (video_key, video_url)
    """
    try:
        logging.info("Generating MCQ review video for topic: %s", topic)
        code = generate_voiceover_manim_code(topic)
        py_file, _ = write_manim_file(code)
        rendered_path = render_voiceover_scene(py_file)
        
        video_key = generate_video_key(topic)
        video_filename = f"{video_key}.mp4"
        
        if S3_BUCKET:
            video_url = upload_file_to_s3(rendered_path, video_filename)
            logging.info("MCQ review video uploaded to S3: %s", video_url)
        else:
            local_dest = os.path.join(VIDEO_DIR, video_filename)
            shutil.copy(rendered_path, local_dest)
            video_url = f"/videos/{video_filename}"
            logging.info("MCQ review video stored locally at: %s", video_url)
        
        # Get reference links
        youtube_refs = get_youtube_references(question)
        article_refs = get_article_references(question)
        video_title = f"Explanation: {question[:50]}{'...' if len(question) > 50 else ''}"
        response = {
            "resources": {
                "video": {"title": video_title, "url": video_url},
                "ref_videos": youtube_refs,
                "ref_articles": article_refs
            }
        }
        # Save response locally for polling if not on S3
        response_file = os.path.join(VIDEO_DIR, f"{video_key}.json")
        with open(response_file, "w") as f:
            json.dump(response, f)
        
        # Cleanup temporary files
        try:
            os.remove(py_file)
        except Exception as cleanup_err:
            logging.warning("Failed to delete temp file %s: %s", py_file, cleanup_err)
        folder_path = "media"
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logging.info("Temporary media folder deleted.")
        
        return video_key, video_url
    except Exception as e:
        logging.error("Error generating MCQ review video: %s", e)
        return None, None

###############################################################################
# API Endpoints
###############################################################################
@app.post("/generate_video")
async def generate_video(request_data: VideoGenerationRequest, background_tasks: BackgroundTasks):
    """
    Endpoint to trigger video generation for a given question.
    Uses a deterministic file name so the video URL uniquely corresponds to
    that question (and answer). The endpoint returns immediately while the
    video is processed in the background.
    """
    question = request_data.question
    user_ans = request_data.user_answer
    
    # Build a detailed prompt for generating the video script.
    # (You can adjust the prompt contents as needed.)
    prompt = (
        f"Here's a question: \"{question}\".\n"
        f"The user answered: \"{user_ans}\".\n\n"
        "Generate a short explanatory video script that:\n"
        "1️⃣ Explains the expected answer in detail.\n"
        "2️⃣ Points out where the user's answer is missing or incorrect.\n"
        "3️⃣ Provides clear guidance on how to improve."
    )
    # Schedule the video generation task in the background.
    background_tasks.add_task(background_video_generation, prompt)
    # Return a message; the actual URL will be available once generation is complete.
    return JSONResponse(content={"message": "Video generation started for this question"}, status_code=202)

@app.post("/review/mcq")
async def review_mcq(request_data: MCQReviewRequest, background_tasks: BackgroundTasks):
    """
    Endpoint to trigger MCQ review video generation.
    Returns reference links immediately while the video is processed in the background.
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
    youtube_refs = get_youtube_references(question)
    article_refs = get_article_references(question)
    
    background_tasks.add_task(background_mcq_review, prompt, question)
    
    # Create a placeholder key for status checking (if using local polling)
    temp_key = "pending-" + str(hash(question + user_ans + correct_ans))[:8]
    response = {
        "resources": {
            "video": {
                "title": f"Explanation: {question[:50]}{'...' if len(question) > 50 else ''}",
                "url": f"/status/mcq/{temp_key}"
            },
            "ref_videos": youtube_refs,
            "ref_articles": article_refs
        }
    }
    return JSONResponse(content=response, status_code=202)

@app.get("/videos/{filename}")
async def serve_video(filename: str):
    """
    Serves locally stored video files.
    (This endpoint is used only if S3 storage is not configured.)
    """
    file_path = os.path.join(VIDEO_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        raise HTTPException(status_code=404, detail="Video not found")

@app.get("/status/mcq/{video_key}")
async def mcq_status(video_key: str):
    """
    Polling endpoint to check the status of an MCQ review video.
    If the JSON response file for that video exists (when not using S3), return it.
    """
    video_path = os.path.join(VIDEO_DIR, f"{video_key}.mp4")
    response_path = os.path.join(VIDEO_DIR, f"{video_key}.json")
    
    if os.path.exists(video_path) and os.path.exists(response_path):
        with open(response_path, "r") as f:
            response = json.load(f)
        return JSONResponse(content=response, status_code=200)
    elif os.path.exists(video_path):
        return JSONResponse(
            content={"resources": {"video": {"title": "Explanation Video", "url": f"/videos/{video_key}.mp4"}}},
            status_code=200
        )
    else:
        return JSONResponse(content={"status": "processing"}, status_code=202)

###############################################################################
# Optional: Simple HTML Client for Testing
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
# Run the Application (for local testing)
###############################################################################
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

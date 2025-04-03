import os
import asyncio
from quart import Quart, request, jsonify, send_from_directory
from quart_cors import cors
from dotenv import load_dotenv
import shutil
import json
from gen import (
    generate_voiceover_manim_code,
    write_manim_file,
    render_voiceover_scene,
    client,
    extract_code,
)

load_dotenv(override=True)
VIDEO_DIR = os.getenv("VIDEO_DIR", "videos")

app = Quart(__name__, static_folder=VIDEO_DIR)
app = cors(app, allow_origin="*")

def get_youtube_references(prompt: str, n: int = 3) -> list[dict]:
    """Ask LLM for n YouTube URLs relevant to the prompt and return with titles."""
    youtube_prompt = (
        f"Provide {n} YouTube video URLs that best explain: {prompt}. "
        "Return as a JSON array of objects with 'title' and 'url' fields."
    )
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=youtube_prompt
    )
    raw = resp.text.strip()
    try:
        # Try to parse as JSON
        return json.loads(raw)
    except Exception:
        # Fallback to parsing lines and creating basic objects
        urls = [u.strip() for u in raw.splitlines() if u.startswith("http")]
        return [{"title": f"Reference Video {i+1}", "url": url} for i, url in enumerate(urls)]

def get_article_references(prompt: str, n: int = 2) -> list[dict]:
    """Ask LLM for n article URLs relevant to the prompt and return with titles."""
    article_prompt = (
        f"Provide {n} educational article or resource URLs that best explain: {prompt}. "
        "Prefer academic sources, educational websites, or reputable publications. "
        "Return as a JSON array of objects with 'title' and 'url' fields."
    )
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=article_prompt
    )
    raw = resp.text.strip()
    try:
        # Try to parse as JSON
        return json.loads(raw)
    except Exception:
        # Fallback to parsing lines and creating basic objects
        urls = [u.strip() for u in raw.splitlines() if u.startswith("http")]
        return [{"title": f"Reference Article {i+1}", "url": url} for i, url in enumerate(urls)]

async def background_mcq_review(topic, question):
    """Process MCQ review in the background."""
    try:
        code = generate_voiceover_manim_code(topic)
        py_file, uuid_slug = write_manim_file(code)
        rendered_path = render_voiceover_scene(py_file)

        os.makedirs(VIDEO_DIR, exist_ok=True)
        short_name = f"{uuid_slug}.mp4"
        dest = os.path.join(VIDEO_DIR, short_name)
        shutil.copy(rendered_path, dest)

        # Get video references
        youtube_refs = get_youtube_references(question)
        article_refs = get_article_references(question)

        # Generate video title based on the question
        video_title = f"Explanation: {question[:50]}..." if len(question) > 50 else f"Explanation: {question}"
        
        # Prepare response object
        response = {
            "resources": {
                "video": {
                    "title": video_title,
                    "url": f"/videos/{short_name}"
                },
                "ref_videos": youtube_refs,
                "ref_articles": article_refs
            }
        }

        # Save response to a file so it can be retrieved later
        response_file = os.path.join(VIDEO_DIR, f"{uuid_slug}.json")
        with open(response_file, 'w') as f:
            json.dump(response, f)

        # Cleanup
        try:
            os.remove(py_file)
        except Exception as cleanup_err:
            print(f"Warning: Failed to delete temp file {py_file}: {cleanup_err}")

        folder_path = "media"
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            print("Folder deleted successfully.")
        else:
            print("Folder does not exist.")

        print(f"Video generated: videos/{short_name}")
        return uuid_slug
    except Exception as e:
        print(f"Error generating MCQ review: {e}")
        return None

@app.route("/generate_video", methods=["POST"])
async def generate_video():
    """Legacy endpoint for generating explanation videos."""
    data = await request.get_json(force=True)
    question = data["question"]
    user_ans = data["user_answer"]

    # Build a detailed prompt that instructs the AI to explain the expected answer,
    # highlight differences with the user answer, and suggest improvements.
    topic = (
        f"Here's a question: \"{question}\".\n"
        f"The user answered: \"{user_ans}\".\n\n"
        "Generate a short explanatory video script that:\n"
        "1️⃣ Explains the expected answer in detail.\n"
        "2️⃣ Points out where the user's answer is missing or incorrect.\n"
        "3️⃣ Provides clear guidance on how to improve to reach the expected answer."
    )

    # Start the task but don't wait for it
    task = asyncio.create_task(background_video_generation(topic))
    
    # Return immediate response
    return jsonify({"message": "Video is being generated"}), 202

@app.route("/review/mcq", methods=["POST"])
async def review_mcq():
    """Handle MCQ review requests and start background processing."""
    try:
        data = await request.get_json(force=True)
        
        # Validate required fields
        if not all(k in data for k in ["question", "selected_option", "expected_answer"]):
            return jsonify({"error": "Missing required fields"}), 400
        
        question = data["question"]
        user_ans = data["selected_option"]
        correct_ans = data["expected_answer"]

        # Build a prompt for MCQ review that compares user answer to correct answer
        topic = (
            f"Here's a multiple-choice question: \"{question}\".\n"
            f"The user selected answer: \"{user_ans}\".\n"
            f"The correct answer is: \"{correct_ans}\".\n\n"
            "Generate a short explanatory video script that:\n"
            "1️⃣ Explains why the correct answer is right.\n"
            "2️⃣ If the user's answer is wrong, explain the misconception or error.\n"
            "3️⃣ Provide key concepts to remember for similar questions in the future."
        )

        # Get references first (these are faster operations)
        youtube_refs = get_youtube_references(question)
        article_refs = get_article_references(question)
        
        # Start the longer video generation process in background
        task = asyncio.create_task(background_mcq_review(topic, question))
        
        # Generate a placeholder UUID for now - we'll use this to check status later
        # The actual UUID will be generated in the background task
        temp_uuid = "pending-" + str(hash(question + user_ans + correct_ans))[:8]
        
        # Return immediate response with references but placeholder for video
        response = {
            "resources": {
                "video": {
                    "title": f"Explanation: {question[:50]}..." if len(question) > 50 else f"Explanation: {question}",
                    "url": f"/status/mcq/{temp_uuid}"  # Client should poll this endpoint
                },
                "ref_videos": youtube_refs,
                "ref_articles": article_refs
            }
        }
        
        return jsonify(response), 202  # 202 Accepted indicates processing has begun
            
    except Exception as e:
        print(f"Error in review_mcq endpoint: {e}")
        return jsonify({"error": str(e)}), 500

async def background_video_generation(topic):
    """Process video generation in the background without blocking."""
    try:
        code = generate_voiceover_manim_code(topic)
        py_file, uuid_slug = write_manim_file(code)
        rendered_path = render_voiceover_scene(py_file)

        os.makedirs(VIDEO_DIR, exist_ok=True)
        short_name = f"{uuid_slug}.mp4"              
        dest = os.path.join(VIDEO_DIR, short_name)
        shutil.copy(rendered_path, dest)

        # Cleanup temporary files
        try:
            os.remove(py_file)
        except Exception as cleanup_err:
            print(f"Warning: Failed to delete temp file {py_file}: {cleanup_err}")

        folder_path = "media"
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            print("Folder deleted successfully.")
        else:
            print("Folder does not exist.")

        print(f"Video generated: videos/{short_name}")
        return uuid_slug
    except Exception as e:
        print(f"Error generating video: {e}")
        return None
@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)

@app.route("/status/mcq/<uuid_slug>", methods=["GET"])
async def mcq_status(uuid_slug):
    """Check if the MCQ review video is ready and return its details."""
    video_path = os.path.join(VIDEO_DIR, f"{uuid_slug}.mp4")
    response_path = os.path.join(VIDEO_DIR, f"{uuid_slug}.json")
    
    if os.path.exists(video_path) and os.path.exists(response_path):
        # Video is ready, return the stored response
        with open(response_path, 'r') as f:
            response = json.load(f)
        return jsonify(response), 200
    elif os.path.exists(video_path):
        # Video exists but response file is missing - generate a minimal response
        return jsonify({
            "resources": {
                "video": {
                    "title": "Explanation Video",
                    "url": f"/videos/{uuid_slug}.mp4"
                }
            }
        }), 200
    else:
        # Video is still being generated
        return jsonify({"status": "processing"}), 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
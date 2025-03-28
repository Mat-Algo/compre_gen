import os
import asyncio
from quart import Quart, request, jsonify, send_from_directory
from dotenv import load_dotenv
import shutil
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

# def get_youtube_references(prompt: str, n: int = 3) -> list[str]:
#     """Ask Gemini for n YouTube URLs relevant to the prompt."""
#     youtube_prompt = (
#         f"Provide {n} YouTube video URLs that best explain: {prompt}. "
#         "Return as a JSON array of strings only."
#     )
#     resp = client.models.generate_content(
#         model="gemini-2.0-flash",
#         contents=youtube_prompt
#     )
#     raw = resp.text.strip()
#     try:
#         # Gemini should return JSON array; fallback to parsing lines
#         return extract_code(raw)
#     except Exception:
#         return [u.strip() for u in raw.splitlines() if u.startswith("http")]

async def background_video_generation(topic):
    try:
        code = generate_voiceover_manim_code(topic)

        # ← UPDATED: unpack (py_file, uuid_slug)
        py_file, uuid_slug = write_manim_file(code)

        rendered_path = render_voiceover_scene(py_file)

        os.makedirs(VIDEO_DIR, exist_ok=True)
        short_name = f"{uuid_slug}.mp4"              # ← use UUID
        dest = os.path.join(VIDEO_DIR, short_name)
        shutil.copy(rendered_path, dest)

        # youtube_refs = get_youtube_references(topic)
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
    except Exception as e:
        print(f"Error generating video: {e}")

@app.route("/generate_video", methods=["POST"])
async def generate_video():
    data = await request.get_json(force=True)
    question = data["question"]
    user_ans = data["user_answer"]

    # Build a detailed prompt that instructs the AI to explain the expected answer,
    # highlight differences with the user answer, and suggest improvements.
    topic = (
        f"Here’s a question: “{question}”.\n"
        f"The user answered: “{user_ans}”.\n\n"
        "Generate a short explanatory video script that:\n"
        "1️⃣ Explains the expected answer in detail.\n"
        "2️⃣ Points out where the user's answer is missing or incorrect.\n"
        "3️⃣ Provides clear guidance on how to improve to reach the expected answer."
    )

    # Run video generation in the background to avoid timeout issues.
    asyncio.create_task(background_video_generation(topic))
    
    return jsonify({"message": "Video is being generated"}), 200

@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

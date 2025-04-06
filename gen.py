import os
import re
import subprocess
import logging
import glob
from dotenv import load_dotenv
import re
import uuid
load_dotenv(override=True)

###############################################################################
# Logging Setup
###############################################################################
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

###############################################################################
# Environment Variables
###############################################################################
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

ELEVENLABS_API_KEY = os.getenv("ELEVEN_API_KEY")
if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY not found in environment variables.")

###############################################################################
# Import the Gemini Client
###############################################################################
try:
    from google import genai
except ImportError:
    raise ImportError("Please install the google-genai library or verify it's in the environment.")

client = genai.Client(api_key=GEMINI_API_KEY)

###############################################################################
# 1) Identify Weak Topics
###############################################################################
def identify_weak_topics() -> list:
    topics = [
        "Explain the advanced integration",
    ]
    logging.info("Identified weak topics: %s", topics)
    return topics

# def sanitize_filename(topic: str) -> str:
#     return re.sub(r'[^\w\-_]', '_', topic)

def extract_code(raw_output: str) -> str:
    pattern = r"```python\s*(.*?)```"
    match = re.search(pattern, raw_output, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        return raw_output.strip()

def validate_code(code: str):
    try:
        compile(code, "<string>", "exec")
    except SyntaxError as se:
        logging.error("Generated code has syntax errors: %s", se)
        raise ValueError("Invalid Python code generated.") from se

def generate_voiceover_manim_code(topic: str, max_attempts=5) -> str:
    """
    Uses Gemini to generate a Manim code snippet that uses:
      - from manim_voiceover import VoiceoverScene
      - from manim_voiceover.services.elevenlabs import ElevenLabsService
    to produce a short, self-contained demonstration about the 'topic' with spoken narration.

    Returns valid, syntax-checked Python code as a string.
    """
    base_prompt = f"""
You are an expert educator and Manim developer. Generate a complete, executable Manim script explaining the topic in detail in a visually understadable way: '{topic}'.
Use the plugin "manim-voiceover" with the ElevenLabsService for narration. The code must:

1) Import:
   from manim_voiceover import VoiceoverScene
   from manim_voiceover.services.elevenlabs import ElevenLabsService
   from manim import *

2) Have exactly ONE Scene subclass that inherits from VoiceoverScene, e.g. class TopicVoiceoverScene(VoiceoverScene):

3) In construct(), set the TTS service with:
   self.set_speech_service(ElevenLabsService(voice_id="21m00Tcm4TlvDq8ikWAM"))
   (You may omit 'voice_id' if you prefer.)

4) Provide multiple 'with self.voiceover(text="..."):' blocks, each containing some animations and text relevant to '{topic}'.

5) Show some textual Mobjects on screen (e.g. Text(...) or MathTex(...)) related to the key ideas, and ensure each voiceover block times with or references that visual.

6) Make sure the code is valid Python, uses standard manim-voiceover usage, and does not rely on placeholders or unimported references.

7) Use animations like Write, Create, Transform, LaggedStartMap, ShowCreation, FadeIn/Out, and context animations.

Output ONLY the Python code in triple backticks.

WARNING: 
    - Whenever using the Code class in Manim to display code snippets, avoid passing code= as a keyword argument. Instead, pass the code string as a positional argument. For example, replace:
      Code(code=some_code_str, language="cpp")
      with:
      Code(some_code_str, language="cpp")
      This prevents the error: TypeError: Code.__init__() got an unexpected keyword argument 'code'. Always check the constructor definition of the Code class if in doubt, or use help(Code) to verify the parameters for the current Manim version.
    - When using Manim's Code class, do not pass font_size as an argument—it is not supported. Instead, control the visual size of the code block using .scale(value). For example, replace:
      Code(..., font_size=20)
      with:
      code = Code(...); code.scale(0.6)
      This avoids the TypeError: unexpected keyword argument 'font_size'.
    - Make sure there is no overlap between frames and writings and eveeruthing is inside the frame.
    """.strip()

    prompt = base_prompt
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        logging.info(f"Requesting voiceover scene code from Gemini for topic='{topic}', attempt={attempt}...")
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        raw_output = resp.text.strip()

        manim_code = extract_code(raw_output)
        logging.info("Generated code:\n%s", manim_code)

        if not manim_code:
            prompt += "\nNo code was returned. Please provide valid Python code in a code block."
            continue

        # Quick syntax check
        try:
            validate_code(manim_code)
            return manim_code
        except ValueError:
            prompt += "\nYour last code had a syntax error. Please fix it."

    raise ValueError(f"Failed to generate valid Manim voiceover code for topic '{topic}' after {max_attempts} attempts.")

import uuid

def write_manim_file(code: str) -> tuple[str, str]:
    """
    Saves the given Manim code to a .py file whose name is a random UUID.
    Returns (python_filename, base_uuid) so you can use base_uuid for the video name later.
    """
    base_uuid = uuid.uuid4().hex
    filename = f"{base_uuid}.py"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    logging.info("Saved Manim code to %s", filename)
    return filename, base_uuid


def render_voiceover_scene(py_file: str):
    import re
    
    # 1) Search the file for the scene name
    with open(py_file, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'class\s+(\w+)\(VoiceoverScene\):', content)
    if not match:
        raise ValueError("Could not find a 'class ___(VoiceoverScene):' in the generated code.")

    scene_name = match.group(1)
    logging.info(f"Detected voiceover scene name: {scene_name}")

    # 2) Use -v DEBUG for maximum verbosity, remove -p and -q flags
    #    so it doesn't try to open a video preview or suppress logs.
    cmd = [
        "manim",
        "-v", "DEBUG",            # Maximum verbosity for debugging
        py_file,
        scene_name,
        "--disable_caching"       # Force re-render so TTS is actually called
    ]
    logging.info("Running Manim command: %s", " ".join(cmd))


    result = subprocess.run(cmd, check=True)


    potential_file = f"{scene_name}.mp4"
    if not os.path.exists(potential_file):
        possible = glob.glob(
            os.path.join("media", "videos", "**", f"{scene_name}.mp4"),
            recursive=True
        )
        if possible:
            potential_file = possible[0]
        else:
            raise FileNotFoundError(
                f"Could not locate the rendered '{scene_name}.mp4' after manim-voiceover run."
            )

    logging.info(f"Rendered voiceover video: {potential_file}")
    return potential_file


def main():
    topics = identify_weak_topics()

    for topic in topics:
        logging.info("Processing topic: %s", topic)
        try:
            # 1) Generate Manim code (VoiceoverScene) from Gemini
            code = generate_voiceover_manim_code(topic)
            # 2) Write to a file
            py_file = write_manim_file(code, topic)
            # 3) Render the scene with manim-voiceover
            final_video = render_voiceover_scene(py_file)
            logging.info("Final video with embedded ElevenLabs voiceover: %s", final_video)

        except Exception as e:
            logging.error("Failed to produce voiceover scene for topic '%s': %s", topic, e)

if __name__ == "__main__":
    main()

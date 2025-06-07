import os
import re
import subprocess
import glob
import logging
import uuid
import traceback
from dotenv import load_dotenv
from google import genai
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
import textwrap
# import psutil, os

# def log_memory_usage(note=""):
#     process = psutil.Process(os.getpid())
#     mem = process.memory_info().rss / (1024 * 1024)  # in MB
#     logging.info(f"[MEMORY] {note}: {mem:.2f} MB")

# ── Load environment ─────────────────────────────────────────────────────
load_dotenv(override=True)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")

# ── API KEYS ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVEN_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENV")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "manim-api-kb")
if not GEMINI_API_KEY:
    raise EnvironmentError("GEMINI_API_KEY missing")
if not ELEVENLABS_API_KEY:
    raise EnvironmentError("ELEVENLABS_API_KEY missing")
if not PINECONE_API_KEY:
    raise EnvironmentError("PINECONE_API_KEY missing")

# ── Initialize clients ───────────────────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)

# ── Build or connect to Pinecone index ──────────────────────────────────
if PINECONE_INDEX not in pc.list_indexes().names():
    pc.create_index(name=PINECONE_INDEX, spec=ServerlessSpec(cloud="aws", region=PINECONE_ENV),dimension=384)
index = pc.Index(PINECONE_INDEX)
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# ── Upload KB to Pinecone ─────────────────────────────────────────────────
KB_SOURCE = "/Users/mat/Desktop/Proj/Solutioon/kb.txt"
def load_kb(path: str):
    entries = []
    if os.path.isdir(path):
        # split each file into sections by top-level headings
        for md in glob.glob(os.path.join(path, "*.md")):
            text = open(md, encoding="utf-8").read()
            parts = re.split(r"(?m)^##\s+", text)
            for part in parts[1:]:
                lines = part.splitlines()
                title = lines[0].strip()
                body = "\n".join(lines[1:]).strip()
                entries.append((f"{os.path.basename(md)}::{title}", body))
    elif os.path.isfile(path):
        # read entire file as one entry
        text = open(path, encoding="utf-8").read()
        entries.append((os.path.basename(path), text))
    else:
        raise FileNotFoundError(f"KB_SOURCE not found: {path}")
    return entries



# batch upsert embeddings with normalization
import numpy as np

def normalize(v: list[float]) -> list[float]:
    arr = np.array(v, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return (arr / norm).tolist() if norm > 0 else v

if os.path.exists(KB_SOURCE):
    logging.info("Loading KB entries from %s", KB_SOURCE)
    entries = load_kb(KB_SOURCE)
    logging.info("Found %d KB entries", len(entries))

    existing = set(index.fetch(ids=[key for key, _ in entries]).vectors.keys())
    to_upload = [(key, body) for key, body in entries if key not in existing]
    if not to_upload:
        logging.info("No new KB entries to upload.")
    else:
        batch_size = 50
        for i in range(0, len(to_upload), batch_size):
            batch = to_upload[i : i + batch_size]
            texts = [body for _, body in batch]
            ids = [key for key, _ in batch]
            embs = embed_model.encode(texts, convert_to_numpy=True)
            vecs = [normalize(embs[j]) for j in range(len(ids))]
            vectors = [(ids[j], vecs[j]) for j in range(len(ids))]
            index.upsert(vectors=vectors)
        logging.info("Uploaded KB to Pinecone index '%s'", PINECONE_INDEX)
else:
    logging.warning("KB_SOURCE not found: %s. Skipping KB upload.", KB_SOURCE)


def normalize(v: list[float]) -> list[float]:
    arr = np.array(v, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return (arr / norm).tolist() if norm > 0 else v


def retrieve_sections(query: str, top_k: int = 20):
    q_emb = embed_model.encode([query], convert_to_numpy=True)[0]
    q_emb = normalize(q_emb)
    res = index.query(vector=q_emb, top_k=top_k)
    matches = res.matches if hasattr(res, 'matches') else res['results'][0]['matches']
    return [m.id for m in matches]



# ── Outline generation ─────────────────────────────────────────────────────
def ask_gemini(prompt: str) -> str:
    resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return resp.text or ""

def generate_outline(topic: str) -> str:
    ids = retrieve_sections(topic, top_k=3)
    kb_block = "\n\n".join(f"### {id}" for id in ids)
    prompt = f"""
Below are Manim documentation section relevant to “{topic}”:

{kb_block}

**Step 1:** List, in bullet form, the exact Manim classes, methods, and snippets you’ll need to build a VoiceoverScene that explains “{topic}. Make sure that you extract the full code with its methods so that u can use it properly and not run into error like this for example :AttributeError: 'Camera' object has no attribute 'frame'
"""
    outline = ask_gemini(prompt)
    logging.info("Outline for '%s':\n%s", topic, outline)
    return outline.strip()

# ── Code generation ──────────────────────────────────────────────────────
def extract_code(markdown: str) -> str:
    m = re.search(r"```python\s*(.*?)```", markdown, re.DOTALL)
    return m.group(1).strip() if m else markdown.strip()

def generate_code(topic: str, outline: str, max_attempts: int = 3) -> str:
    ids = retrieve_sections(topic, top_k=3)
    kb_block = "\n\n".join(f"### {{id}}" for id in ids)
    base_prompt = f'''
```text
You are an expert Manim and Python developer, tasked with creating educational animations.
Your primary goal is to generate a complete, executable Manim script that explains the specified '{topic}' in detail, ensuring it is visually understandable and engaging.

The script MUST use the "manim-voiceover" plugin with the ElevenLabsService for narration.

**Core Requirements & Setup:**

1.  **Imports:** The script MUST begin with these exact imports:
    ```python
    from manim_voiceover import VoiceoverScene
    from manim_voiceover.services.elevenlabs import ElevenLabsService
    from manim import *
    # If Color class is used for custom colors, ensure it's available.
    # from manim import Color # Typically covered by 'from manim import *' but be defensive
    ```

2.  **Scene Class:**
    *   There MUST be **exactly ONE** Scene subclass in the script.
    *   This class MUST inherit from `VoiceoverScene`. Example: `class TopicVoiceoverScene(VoiceoverScene):`
    *   **CRITICAL - NO OVERLAP:** Ensure that Mobjects (text, shapes, etc.) from one part of the animation DO NOT visually overlap with Mobjects from a subsequent part, unless explicitly intended for a specific transitional effect. Writings and visuals should never obscure each other unintentionally. See "Overlap Prevention" section for detailed strategies.

3.  **Voiceover Service Initialization:**
    *   Inside the `construct()` method, set the Text-To-Speech (TTS) service using:
        ```python
        self.set_speech_service(ElevenLabsService(voice_id="21m00Tcm4TlvDq8ikWAM"))
        # You may omit 'voice_id' if you prefer the default ElevenLabs voice.
        ```

4.  **Voiceover Blocks & Content Synchronization:**
    *   Provide multiple `with self.voiceover(text="..."):` blocks.
    *   Each voiceover block MUST contain Manim animations (`self.play(...)`, `self.wait(...)`) and Mobject creations/manipulations that are directly relevant to the narrated text for that block.
    *   Display textual Mobjects (e.g., `Text(...)`, `MathTex(...)`) on screen that highlight key ideas. Each voiceover narration should clearly correspond to, or reference, the visuals being animated or displayed at that moment.

5.  **Animation Style:**
    *   Employ a variety of animations to keep the visual engaging, such as `Write`, `Create`, `Transform`, `ReplacementTransform`, `LaggedStartMap`, `ShowCreation`, `FadeIn`, `FadeOut`, `MoveAlongPath`, `Indicate`, and context manager animations (e.g., `self.camera.frame.animate`).
    *   Aim for smooth, 3Blue1Brown-style fluid animations. Use `lag_ratio` in `LaggedStart` or `AnimationGroup` for staggered effects where appropriate.

6.  **Code Validity:**
    *   The generated Python code MUST be fully executable without errors.
    *   It MUST use standard `manim-voiceover` usage patterns.
    *   It MUST NOT rely on placeholders (other than `{topic}` which you will fill), undefined variables, or unimported references.

**CRITICAL - Overlap Prevention & Scene Management:**

This is a non-negotiable requirement. Visual clarity is paramount.

*   **MANDATORY STAGE CLEARING:** Before introducing any new major section or set of Mobjects that would occupy the same space as previous ones, you **MUST** clear the stage of previously displayed objects.
    *   Use `self.play(FadeOut(mobject1, mobject2, ...))` to remove specific objects.
    *   Use `self.remove(mobject1, mobject2, ...)` for instant removal if no animation is needed (usually followed by a `self.wait` or subsequent animation).
    *   Use `self.clear()` to remove *all* Mobjects from the scene. This is suitable for complete transitions between distinct parts of the explanation.
*   **Repositioning:** If Mobjects are intended to remain on screen with new ones, ensure new Mobjects are placed in non-overlapping areas. Use Manim's positioning tools (`.to_edge()`, `.next_to()`, `.shift()`, `VGroup(...).arrange()`).
*   **Layout Safety:**
    *   Strictly ensure all Mobjects remain within the standard camera frame (approximately X: [-7, 7], Y: [-4, 4] for a 16:9 aspect ratio, adjust for camera width/height). Use `.scale()`, `.scale_to_fit_width(config.frame_width - 1)`, `.scale_to_fit_height(config.frame_height - 1)` carefully.
    *   If text or `MathTex` becomes too wide, scale it down. Example: `my_text.scale_to_fit_width(13)` (leaving some margin from frame edges).
    *   Use `VGroup(...).arrange(DOWN)` or `arrange_in_grid` for organizing multiple Mobjects neatly.

**Specific Manim Class Usage Rules:**

*   **`Code` Class (for displaying code snippets):**
    *   **WARNING:** When instantiating the `Code` class, pass the code string as a **positional argument**.
        *   Correct: `my_code_object = Code(your_code_string, language="python")`
        *   **INCORRECT:** `Code(code=your_code_string, language="python")` (This will cause `TypeError: Code.init() got an unexpected keyword argument 'code'`).
    *   **WARNING:** Do **NOT** pass `font_size` as a keyword argument to the `Code` class constructor. It is not supported and will cause a `TypeError`.
        *   Instead, control the visual size by calling `.scale()` on the `Code` object *after* instantiation.
        *   Correct: `my_code_object = Code(your_code_string, language="python"); my_code_object.scale(0.6)`
        *   **INCORRECT:** `Code(your_code_string, language="python", font_size=20)`

**Code Quality & Robustness (CRITICAL):**

1.  **Color Handling:**
    *   **Priority:** Use Manim's predefined color constants (e.g., `BLUE`, `RED`, `GREEN`, `YELLOW_C`, `TEAL_E`) whenever possible. These are available via `from manim import *`.
    *   **Custom Colors:** If defining custom colors, you MUST use the `ManimColor` class (or `Color` if aliased): `MY_CUSTOM_COLOR = ManimColor("#RRGGBB")`. Do not assume `Color` is defined unless explicitly handled by imports.
    *   **`interpolate_color`:** If using `interpolate_color(color1, color2, alpha)`, ensure `color1` and `color2` are valid ManimColor objects (either predefined constants like `BLUE` or objects created via `ManimColor(...)`), NOT raw hex strings. `alpha` must be a float.
    *   **Color Reference (Manim Constants & Hex Values):**
        *   BLACK: `#000000`
        *   WHITE: `#FFFFFF`
        *   DARKER_GRAY / DARKER_GREY: `#222222`
        *   DARK_GRAY / DARK_GREY: `#444444`
        *   GRAY / GREY: `#888888` (GRAY_C)
        *   LIGHT_GRAY / LIGHT_GREY / GRAY_B / GREY_B: `#BBBBBB`
        *   LIGHTER_GRAY / LIGHTER_GREY / GRAY_A / GREY_A: `#DDDDDD`
        *   BLUE: `#58C4DD` (BLUE_C)
        *   GREEN: `#83C167` (GREEN_C)
        *   RED: `#FC6255` (RED_C)
        *   YELLOW: `#FFFF00` (YELLOW_C)
        *   PURPLE: `#9A72AC` (PURPLE_C)
        *   ORANGE: `#FF862F`
        *   PINK: `#D147BD`
        *   TEAL: `#5CD0B3` (TEAL_C)
        *   GOLD: `#F0AC5F` (GOLD_C)
        *   MAROON: `#C55F73` (MAROON_C)
        *   (And their A, B, D, E variants as per original prompt)

2.  **Object & Variable Handling:**
    *   Ensure all variables (especially Mobjects) are defined *before* they are used in animations (`self.play(...)`), added to groups (`VGroup(...)`), or referenced by other operations. Check for typos diligently.
    *   When using `Transform` or `ReplacementTransform`, ensure the source and target Mobjects are valid and compatible. `ReplacementTransform` is often safer for changes in structure.
    *   Verify that methods are called on the correct object types (e.g., `.scale()` on Mobjects, `.set_value()` on `DecimalNumber`). Avoid `AttributeError`.
    *   **Updaters:** Clear updaters (e.g., `mobject.clear_updaters()`) *before* fading out Mobjects that have them, especially if they reference other Mobjects that might also be fading. This prevents errors or lingering computations.

3.  **Positioning Best Practices:**
    *   **Relative Positioning:** Use `.next_to(other_mobject, direction, buff=...)` extensively.
    *   **Alignment:** Use `.align_to(other_mobject, direction)` or `Mobject.align_to(other_mobject_or_point, direction)`.
    *   **`VGroup` for Layout:** Use `VGroup(...).arrange(direction, buff=..., aligned_edge=...)` for grouping and laying out multiple Mobjects.
    *   **Updaters for Dynamic Positioning:** Use `.add_updater(lambda m: m.next_to(...))` for Mobjects that need to follow others or change position dynamically. Remember to clear these updaters if the Mobject or its target is removed.
    *   **Explicit References:** ALWAYS position Mobjects relative to named Mobject variables you have created (e.g., `formula.next_to(title, DOWN)`).
    *   **AVOID `self.mobjects_last_animation`:** DO NOT attempt to position objects relative to `self.mobjects_last_animation` or similar internal/deprecated scene attributes. This is a common source of `AttributeError` and unreliable behavior. See "Error Prevention" section.

4.  **Instruction for Simulated Vertical Scrolling (If content exceeds screen height):**
    *   **Group All Vertically Arranged Content:** Place all sections intended to appear sequentially into a single main `VGroup`, let's call it `scroll_group`.
    *   **Initial Placement:** Position the first section (e.g., `problem_group`) normally (e.g., below a main title). Add it to `scroll_group`. Keep track of the bottom-most element currently positioned (e.g., `last_element_in_scroll = problem_group`).
    *   **Position Subsequent Sections:** For each new section (e.g., `property_section`):
        1.  Create the Mobjects for that section.
        2.  Arrange them vertically within their own `VGroup` (e.g., `property_section_group = VGroup(property_title, property_formula).arrange(DOWN, buff=...)`).
        3.  Position this new section `VGroup` relative to the previous one: `property_section_group.next_to(last_element_in_scroll, DOWN, buff=LARGE_BUFF)` (e.g., `LARGE_BUFF = 1.0` or more to ensure it starts off-screen or significantly below).
        4.  Add the new section `VGroup` to the main `scroll_group`.
        5.  Update `last_element_in_scroll = property_section_group`.
    *   **Animate the Scroll:** When it's time to reveal the new section:
        1.  Calculate the vertical shift distance needed to move `scroll_group` upwards so the top of the new section (e.g., `property_section_group`) aligns with a desired screen position (e.g., just below the main title, or screen center).
        2.  Animate using: `self.play(scroll_group.animate.shift(UP * shift_distance))`
        3.  Optionally, `FadeOut` elements from much earlier sections that are now far off-screen upwards to keep Mobject count manageable.
    *   **Repeat:** Repeat steps for subsequent sections.
    *   **Final Centering (Optional):** For the final result, you might perform one last scroll/shift animation to center the final answer.

5.  **Animation Robustness:**
    *   Prefer standard, reliable animations: `Create`, `Write`, `FadeIn`, `FadeOut`, `Transform`, `ReplacementTransform`, `MoveAlongPath`, `Indicate`.
    *   If using `GrowArrow`, be mindful of arguments. `Create(Arrow(...))` can be a simpler alternative.
    *   Ensure all arguments passed to `self.play(...)` are valid `Animation` instances or Mobject update methods (e.g., `mobject.animate.shift(...)`). Avoid passing plain Mobjects directly unless using state-setting animations like `FadeIn` where appropriate.

**Error Prevention & Best Practices (Focus on `AttributeError: ... object has no attribute 'mobjects_last_animation'`):**

*   **Why the Error Occurs:** This error means you tried to access an attribute (like `mobjects_last_animation`) that doesn't exist on the Scene object (`self`) or is not intended for public use in positioning. Relying on such internal state is unstable.
*   **How to Avoid This Consistently:**
    1.  **Use Explicit Mobject Variables:** Every Mobject you create and intend to interact with later (position something relative to it, transform it, fade it out) MUST be assigned to a Python variable.
        *   Correct: `my_formula = MathTex(...)`, `my_square = Square(...)`
        *   Incorrect (for later reference): `self.play(Write(MathTex(...)))` and then trying to refer to this `MathTex` implicitly.
    2.  **Position Relative to Named Mobjects:** ALWAYS use positioning methods like `.next_to()`, `.align_to()`, `.shift()` by referencing other named Mobject variables.
        *   Correct: `label.next_to(my_formula, DOWN, buff=0.5)`, `equation2.align_to(my_equation1, LEFT)`
        *   **INCORRECT AND WILL CAUSE ERRORS:** `label.next_to(self.mobjects_last_animation, ...)` or `equation2.align_to(self, ...)`.
    3.  **`VGroup` for Related Layouts:** For multiple items that need structured layout (e.g., list of definitions, equations), put them in a `VGroup` and use its `.arrange()` method. Then position the entire `VGroup`.
        *   Example:
            ```python
            summary_part1 = Text("Part 1 Summary")
            summary_part2 = Text("Part 2 Summary")
            summary_group = VGroup(summary_part1, summary_part2).arrange(DOWN, buff=0.5, aligned_edge=LEFT)
            summary_group.next_to(main_title, DOWN, buff=1.0)
            self.play(Write(summary_group))
            ```
    4.  **Avoid Implicit State Reliance:** Do not write code that depends on Manim's internal scene graph state after an animation if you don't have an explicit variable handle to the Mobject(s) you need.

**Mathematical Clarity (`MathTex`):**

*   Format LaTeX clearly. Use `aligned` environments for multi-line equations where appropriate (`r"""\begin{{aligned}} ... \end{{aligned}}"""`).
*   Break down complex formulas visually if it aids understanding.
*   When defining a `MathTex` object by passing multiple distinct strings (e.g., `eq = MathTex("E", "=", "m", "c^2")`), each string becomes a directly accessible sub-mobject using standard list indexing (e.g., `eq[0]` is "E", `eq[2]` is "m"). This is more reliable than searching by TeX string content.

**Pacing:**

*   Include short `self.wait(...)` calls (e.g., `self.wait(0.5)` or `self.wait(1)`) after significant animations or explanations to allow viewer comprehension. The voiceover timing itself, within `with self.voiceover(...):` blocks, will naturally dictate much of the pacing.

**MANDATORY - Safe Scene Exit:**

At the very end of the `construct` method, include this exact block to prevent rendering artifacts or errors on exit:
```python
        # Final clean up to ensure smooth exit
        all_mobjects_on_screen = self.mobjects # Get all mobjects currently in the scene
        if all_mobjects_on_screen:
            # Clear updaters from all mobjects
            for mob in all_mobjects_on_screen:
                mob.clear_updaters()
            
            # Fade out all mobjects
            self.play(*[FadeOut(mob) for mob in all_mobjects_on_screen])
        
        self.wait(0.5) # Short pause before scene truly ends
```

**General Constraints:**

*   **No PNGs:** Do NOT use any PNG images or attempt to load external image files. The animation must be generated purely from Manim code.
*   **Manim Documentation Snippets:** You may refer to the following Manim documentation snippets if they are relevant to the `{topic}`:
    ```
    {kb_block}
    ```

**Verification Mindset Before Outputting:**

Mentally review the generated code, specifically checking for:
*   **No Overlap:** Are objects cleared or positioned to prevent overlap between different explanation segments?
*   **NameErrors:** Are all classes, functions, and color constants defined or imported?
*   **TypeErrors:** Are function/method arguments of the correct type (e.g., `ManimColor` vs. `str` for `interpolate_color`, correct `Code` class instantiation)?
*   **AttributeErrors:** Does the object have the method being called (e.g., avoiding `self.mobjects_last_animation`)?
*   **Manim API Adherence:** Is the code using Manim and `manim-voiceover` APIs correctly?
*   **Completeness:** Is the explanation of `{topic}` detailed and visually supported?
*   **All Requirements Met:** Have all instructions in this prompt been followed?

VERY IMPORTANT:
- MAKE VERY VERY SURE “Before introducing any new major content, you MUST clear the stage of all previously written objects using self.play(FadeOut(...)), self.remove(...), or  self.clear() — no leftover elements are allowed unless explicitly intended to stay.”
- When you show a new object after explaining an old one makes sure not to overlap the old one, either movie it to the side or top or just remove it..NEVER OVERLAP
- Also make sure that the objects or text NEVER goes out of frame


**Output Format:**

*   Output **ONLY** the raw Python code for the Manim script.
*   The code MUST be enclosed in a single triple backtick block (e.g., ```python ... ```).
*   Provide NO explanations, introductions, summaries, or any other text before or after the code block. Just the code.
```
'''

    prompt = base_prompt
    for attempt in range(1, max_attempts+1):
        raw = ask_gemini(prompt)
        code = extract_code(raw)
        try:
            compile(code, '<string>', 'exec')
            return code
        except SyntaxError:
            err = traceback.format_exc()
            logging.warning("Syntax error on attempt %d:\n%s", attempt, err)
            prompt = base_prompt + f"\nPrevious code raised SyntaxError:\n{err}\nPlease correct and resend."
    raise RuntimeError(f"Failed to generate code for '{topic}' after {max_attempts} attempts.")

# ── Manim rendering ───────────────────────────────────────────────────────
def write_temp(code: str):
    uid = uuid.uuid4().hex
    fname = f"{uid}.py"
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(code)
    return fname, uid

def render_voiceover_scene(py_file: str, base_uuid: str) -> str:
    """
    Renders the Manim Voiceover scene from the given file.
    Returns the path to the rendered video file.
    """
    # 1) Extract scene name
    content = open(py_file, "r", encoding="utf-8").read()
    match = re.search(r'class\s+(\w+)\s*\(\s*VoiceoverScene\s*\):', content)
    if not match:
        raise ValueError(f"No VoiceoverScene subclass found in {py_file}")
    scene = match.group(1)

    # 2) Render with --media_dir to our output folder
    output_dir = f"{base_uuid}_output"
    cmd = [
    "manim",
    "-pql",                       # low preview quality
    "--fps", "15",                # cut frames per second in half
    "--resolution", "640,360",    # lower resolution
    py_file,
    scene,
    "--media_dir", output_dir     # keep media outputs
]

    logging.info("Running Manim command: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
    except subprocess.CalledProcessError as e:
        logging.error("STDOUT:\n%s", e.stdout)
        logging.error("STDERR:\n%s", e.stderr)
        raise


    # 3) Look for the mp4 in that folder
    # Manim will write: <output_dir>/videos/<quality>/<scene>.mp4
    pattern = os.path.join(output_dir, "videos", "*", f"{scene}.mp4")
    files = glob.glob(pattern)
    if not files:
        # fallback to any .mp4 under output_dir
        files = glob.glob(os.path.join(output_dir, "**", f"{scene}.mp4"), recursive=True)
    if not files:
        raise FileNotFoundError(
            f"Could not locate rendered video '{scene}.mp4' under '{output_dir}'"
        )
    # return the first (and usually only) match
    return sorted(files)[0]



# ── Main flow ────────────────────────────────────────────────────────────
def main():
    topics = ["explain how water ias formed in chemisty"]
    for topic in topics:
        logging.info("--- Topic: %s ---", topic)
        # log_memory_usage("Start of topic")

        outline = generate_outline(topic)
        # log_memory_usage("After generating outline")

        code = generate_code(topic, outline)
        # log_memory_usage("After generating code")

        logging.info("Code for '%s':\n%s", topic, code)
        py_file, uid = write_temp(code)
        # log_memory_usage("After writing temp file")

        try:
            video = render_voiceover_scene(py_file, uid)
            # log_memory_usage("After rendering video")
            logging.info("Video saved: %s", video)
        except Exception as e:
            logging.error("Render failed: %s", e)
        finally:
            if os.path.exists(py_file):
                os.remove(py_file)
                # log_memory_usage("After cleaning up temp file")

if __name__ == '__main__':
    main()
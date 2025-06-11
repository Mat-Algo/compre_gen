# 🎥 Compre‑gen

**Compre‑gen** is a serverless platform for auto‑generating short, educational explanation videos from user‑submitted questions. It leverages:

* **Manim + manim‑voiceover** for animated scenes
* **ElevenLabs** for high‑quality TTS narration
* **Google Gemini API** for AI‑driven script generation
* **Pinecone** as a knowledge‑base vector store
* **FastAPI + AWS S3 + Google Cloud Run** for scalable, asynchronous processing

---

## 🚀 Key Features

* **AI‑powered script & outline**

  * Uses Gemini 2.0 Flash to craft detailed video outlines and narration
* **Automated voiceover scenes**

  * Generates Manim scenes with synchronized ElevenLabs narration
* **Knowledge retrieval**

  * Indexes reference docs in Pinecone for context‑aware outlines
* **Cloud‑native workflow**

  * FastAPI endpoints trigger Cloud Run jobs and S3 storage
* **Background rendering**

  * UUID‑tracked tasks with polling endpoints for status updates
* **Reference suggestions**

  * Fetches curated YouTube videos and articles per topic

---

## 📦 Tech Stack

| Component            | Technology                           | Role                                |
| -------------------- | ------------------------------------ | ----------------------------------- |
| **API Framework**    | FastAPI ⚡                            | HTTP endpoints, background tasks    |
| **Scene Generation** | Manim + manim-voiceover              | Animated video rendering            |
| **TTS Service**      | ElevenLabs 🎙️                       | Voice narration                     |
| **AI Model**         | Google Gemini API 🤖                 | Script & outline generation         |
| **Vector DB**        | Pinecone 🌲                          | KB indexing & retrieval             |
| **Embedding**        | Sentence-Transformers (`all-MiniLM`) | Query & doc embeddings              |
| **Storage**          | AWS S3 ☁️                            | Prompt, video, JSON upload/download |
| **Job Runner**       | Google Cloud Run Job 🚀              | Offloads Manim renders              |
| **Authentication**   | dotenv                               | Secure API keys & env variables     |

---

## 🔧 Installation

1. **Clone the repo**

   ```bash
   git clone https://github.com/your-org/compre-gen.git
   cd compre-gen
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables** (create a `.env` file)

   ```env
   # AI keys
   GEMINI_API_KEY=...            # Google Gemini API
   ELEVENLABS_API_KEY=...        # ElevenLabs TTS
   PINECONE_API_KEY=...          # Pinecone
   PINECONE_ENV=us‑west1         # Pinecone environment
   PINECONE_INDEX=manim-api-kb   # Index name

   # AWS & cloud
   S3_BUCKET=compre-gen-vid      # S3 bucket for assets
   YOUTUBE_API_KEY=...           # YouTube Data API

   # GCP settings
   GCLOUD_PROJECT=...            # GCP project ID
   GCLOUD_REGION=us-central1     # Cloud Run region
   ```

4. **Configure Google credentials**

   ```bash
   gcloud auth application-default login
   ```

---

## 🚀 Running Locally

```bash
# Start the FastAPI app
uvicorn app:app --host 0.0.0.0 --port 8000
```

* **POST** `/generate_video` to submit a question + answer
* **GET**  `/status/video/{video_key}` to poll for results

---

## 🗂️ Code Structure

* **gen.py**

  * Loads and indexes KB entries into Pinecone
  * Generates outlines & code via Gemini
  * Writes temp scripts and invokes Manim renders

* **app.py**

  * FastAPI app with endpoints for video & MCQ review
  * Triggers Cloud Run jobs, handles S3 I/O
  * Fetches YouTube & article references

* **worker.py**

  * Entry point for Cloud Run Job
  * Downloads prompt, runs `background_video_generation`
  * Uploads render & JSON response to S3

---

## 📄 Usage

1. Call **`/generate_video`** with JSON:

   ```json
   {
     "question": "Explain Maxwell's equations",
     "user_answer": "They describe electromagnetism"
   }
   ```
2. Receive a **202 Accepted** with `status_endpoint`.
3. Poll **`/status/video/{video_key}`** until video & resources are returned.
4. Access **video URL** and **reference links**.

---

## Contributing

Feel free to open issues or submit PRs. Please adhere to existing code style and include relevant tests.

---

## License

MIT license

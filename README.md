# 🎥 Compre_gen

This project generates **short educational explanation videos** using [Manim](https://docs.manim.community/), [ElevenLabs](https://www.elevenlabs.io/), and Google's [Gemini](https://ai.google.dev/gemini-api/docs/overview) via a Quart API. It converts MCQ questions into voice-narrated Manim animations and also suggests helpful YouTube videos and articles for further learning.

---

## 🚀 Features

- 🎙️ Auto-generated voiceovers with **ElevenLabs**
- 📽️ Scene animations with **Manim + manim-voiceover**
- 🤖 AI-generated explanations using **Gemini (Gemini 2.0 Flash model)**
- 🌐 Reference retrieval (YouTube + articles)
- 🔁 Background video rendering with UUID-based tracking
- 📡 REST API with **Quart** and **CORS**

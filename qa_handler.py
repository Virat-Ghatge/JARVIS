#!/usr/bin/env python3
"""
Q&A Handler for JARVIS
Uses Groq's free API (Llama 3.1) to answer factual and conversational questions.
Local cache prevents redundant API calls.

Gemini is NOT used here — reserved strictly for NLP/command classification in core.py.
Priority: Cache → Groq (Llama 3.1) → "Couldn't find" response
"""

import json
import os
import re
import time

CACHE_FILE = os.path.join(os.path.dirname(__file__), "qa_cache.json")
CACHE_TTL = 86400  # 24 hours

# Question starters that trigger this handler
QUESTION_STARTERS = [
    'who is', 'who was', 'who are', 'who were',
    'who invented', 'who created', 'who founded', 'who wrote', 'who made',
    'what is', 'what are', 'what was', 'what were', 'what does', 'what did',
    'where is', 'where are', 'where was',
    'when is', 'when was', 'when did', 'when were',
    'how does', 'how did', 'how do', 'how was',
    'why is', 'why was', 'why did', 'why are',
    'define ', 'tell me about', 'explain ',
]

# Groq model to use — llama-3.1-8b-instant is fastest with 14,400 req/day free
GROQ_MODEL = "llama-3.1-8b-instant"

# Weighted usage ratio — out of every (GROQ_WEIGHT + GEMINI_WEIGHT) questions:
#   GROQ_WEIGHT   turns use Groq   (14,400 req/day free)
#   GEMINI_WEIGHT turns use Gemini (~1,000 req/day reserved for Q&A)
# Adjust these if you hit rate limits on either side.
GROQ_WEIGHT   = 8  # 8 out of every 9 questions go to Groq
GEMINI_WEIGHT = 1  # 1 out of every 9 questions goes to Gemini
_CYCLE = GROQ_WEIGHT + GEMINI_WEIGHT  # full cycle length = 9

# JARVIS persona prompt for Groq
SYSTEM_PROMPT = (
    "You are JARVIS, the AI assistant of Tony Stark. "
    "Answer questions concisely in 1-2 sentences. "
    "Be formal, intelligent, and always address the user as 'sir'. "
    "Do not use markdown, bullet points, or headers — plain spoken language only."
)

# Try to import Groq SDK
try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False


class QAHandler:
    """Answers questions via Groq (Llama 3.1) with local caching."""

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.cache = self._load_cache()
        self.groq_client = self._init_groq()
        self._turn = 0  # Increments each question; odd=Groq first, even=Gemini first

    # ------------------------------------------------------------------ #
    #  GROQ INIT                                                           #
    # ------------------------------------------------------------------ #

    def _init_groq(self):
        """Initialize Groq client if SDK and key are available."""
        api_key = os.getenv('GROQ_API_KEY')

        if not GROQ_SDK_AVAILABLE:
            print("[QA] Groq SDK not installed — run: pip install groq")
            return None
        if not api_key:
            print("[QA] GROQ_API_KEY not set in .env — Q&A via Groq disabled")
            return None

        try:
            client = Groq(api_key=api_key)
            print("[✓] Groq Q&A Engine ready (llama-3.1-8b-instant)")
            return client
        except Exception as e:
            print(f"[QA] Groq init failed: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  CACHE                                                               #
    # ------------------------------------------------------------------ #

    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"[QA Cache] Save failed: {e}")

    def _get_cached(self, key):
        entry = self.cache.get(key.lower().strip())
        if entry:
            if time.time() - entry['timestamp'] < CACHE_TTL:
                return entry['answer']
            del self.cache[key.lower().strip()]
        return None

    def _set_cache(self, key, answer):
        self.cache[key.lower().strip()] = {
            'answer': answer,
            'timestamp': time.time()
        }
        self._save_cache()

    # ------------------------------------------------------------------ #
    #  QUESTION DETECTION                                                  #
    # ------------------------------------------------------------------ #

    def is_question(self, command):
        """Return True if command looks like a factual/conversational question."""
        cmd = command.lower().strip()
        return any(cmd.startswith(s) for s in QUESTION_STARTERS)

    def extract_query(self, command):
        """Strip filler words and return the core query."""
        query = command.lower().strip().rstrip('?')
        for filler in ['jarvis ', 'hey jarvis ', 'please ', 'can you ', 'could you ']:
            if query.startswith(filler):
                query = query[len(filler):]
        return query.strip()

    # ------------------------------------------------------------------ #
    #  GROQ ANSWER                                                         #
    # ------------------------------------------------------------------ #

    def _ask_groq(self, query):
        """Send query to Groq (Llama 3.1) and return answer string or None."""
        if not self.groq_client:
            return None

        try:
            response = self.groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": query},
                ],
                temperature=0.3,
                max_tokens=150,
            )
            answer = response.choices[0].message.content.strip()
            answer = re.sub(r'\*+', '', answer)
            answer = re.sub(r'#+\s*', '', answer)
            return answer if answer else None

        except Exception as e:
            print(f"[QA] Groq error: {e}")
            return None

    def _ask_gemini(self, query):
        """Send query to Gemini and return answer string or None."""
        if not hasattr(self.jarvis, 'genai_client') or not self.jarvis.ai_model:
            return None

        try:
            prompt = (
                "You are JARVIS, Tony Stark's AI. Answer the question below concisely "
                "in 1-2 sentences. Be formal, address the user as 'sir'. "
                "Plain text only — no markdown, no bullet points.\n\n"
                f"Question: {query}\nAnswer:"
            )
            response = self.jarvis.genai_client.models.generate_content(
                model=self.jarvis.ai_model,
                contents=prompt,
                config={'temperature': 0.3, 'max_output_tokens': 150}
            )
            answer = response.text.strip()
            answer = re.sub(r'\*+', '', answer)
            answer = re.sub(r'#+\s*', '', answer)
            return answer if answer else None

        except Exception as e:
            print(f"[QA] Gemini error: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  MAIN ENTRY POINT                                                    #
    # ------------------------------------------------------------------ #

    def answer_question(self, command):
        """
        Route: Cache → Alternating (Groq ↔ Gemini) → Web search fallback.
        Odd turns: Groq primary, Gemini fallback.
        Even turns: Gemini primary, Groq fallback.
        """
        query = self.extract_query(command)
        if not query:
            self.jarvis.speak("Could you please repeat the question, sir?")
            return True

        print(f"[QA] Query: '{query}'")

        # 1. Cache
        cached = self._get_cached(query)
        if cached:
            print("[Source] Cache")
            self.jarvis.speak(cached)
            return True

        # 2. Weighted LLM selection: Groq 4 out of every 5 turns, Gemini 1 out of 5
        self._turn += 1
        use_groq = (self._turn % _CYCLE) < GROQ_WEIGHT

        if use_groq:
            primary_name,  primary_fn  = "Groq",   self._ask_groq
            fallback_name, fallback_fn = "Gemini", self._ask_gemini
        else:
            primary_name,  primary_fn  = "Gemini", self._ask_gemini
            fallback_name, fallback_fn = "Groq",   self._ask_groq

        print(f"[QA] Turn {self._turn} (cycle pos {self._turn % _CYCLE}) → {primary_name} primary")
        answer = primary_fn(query)

        if answer:
            print(f"[Source] {primary_name}")
            self._set_cache(query, answer)
            self.jarvis.speak(answer)
            return True

        # Primary failed — try the other LLM
        print(f"[QA] {primary_name} had no answer — trying {fallback_name}")
        answer = fallback_fn(query)

        if answer:
            print(f"[Source] {fallback_name} (fallback)")
            self._set_cache(query, answer)
            self.jarvis.speak(answer)
            return True

        # Both LLMs failed — open browser
        print(f"[QA] Both LLMs failed — falling back to web search")
        self.jarvis.speak("I couldn't find a direct answer, sir. Let me search the web for that.")
        self.jarvis.web_handler.web_search(f"search {query}")
        return True

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

try:
    from config.settings import QA_CACHE_FILE
    CACHE_FILE = str(QA_CACHE_FILE)
except Exception:
    CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qa_cache.json")
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

try:
    from config.settings import GROQ_MODEL, GEMINI_MODEL
except ImportError:
    GROQ_MODEL = "qwen/qwen3.8-27b"
    GEMINI_MODEL = "gemini-2.5-flash"

# Primary & fallback Groq models
GROQ_MODELS_POOL = [GROQ_MODEL, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "allam-2-7b"]

# JARVIS persona prompt for Groq
SYSTEM_PROMPT = (
    "You are JARVIS, the highly advanced AI assistant of Tony Stark. "
    "Your personality is formal, intelligent, and distinctly British. "
    "You possess a dry wit and occasionally use subtle sarcasm or dry humor. "
    "Always address the user as 'sir'. "
    "You are proactive—if you have extra relevant context, volunteer it by saying 'By the way, sir...' "
    "Keep answers concise (1-2 sentences) but full of character. "
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
            print(f"[OK] Groq Q&A Engine ready ({GROQ_MODEL})")
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
        """Send query to Groq and return answer string or None."""
        if not self.groq_client:
            return None

        # Try models from pool for maximum resilience
        for model_name in GROQ_MODELS_POOL:
            try:
                response = self.groq_client.chat.completions.create(
                    model=model_name,
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
                if answer:
                    return answer
            except Exception as e:
                err_str = str(e).lower()
                if "model_not_found" in err_str or "does not exist" in err_str:
                    continue  # Try next model in pool
                elif "429" in err_str or "rate limit" in err_str:
                    raise  # Let caller catch rate limit and switch to Gemini
                print(f"[QA] Groq error ({model_name}): {e}")

        return None

    def _ask_gemini(self, query):
        """Send query to Gemini and return answer string or None."""
        if not hasattr(self.jarvis, 'genai_client') or not self.jarvis.ai_model:
            return None

        gemini_models = [self.jarvis.ai_model, "gemini-2.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]
        for g_model in [m for m in gemini_models if m]:
            try:
                prompt = (
                    "You are JARVIS, Tony Stark's AI. Answer the question below concisely "
                    "in 1-2 sentences. Be formal, address the user as 'sir'. "
                    "Plain text only — no markdown, no bullet points.\n\n"
                    f"Question: {query}\nAnswer:"
                )
                response = self.jarvis.genai_client.models.generate_content(
                    model=g_model,
                    contents=prompt,
                    config={'temperature': 0.3, 'max_output_tokens': 150}
                )
                answer = response.text.strip()
                answer = re.sub(r'\*+', '', answer)
                answer = re.sub(r'#+\s*', '', answer)
                if answer:
                    return answer
            except Exception as e:
                err_str = str(e).lower()
                if "not found" in err_str or "404" in err_str:
                    continue
                print(f"[QA] Gemini error ({g_model}): {e}")

        return None

    # ------------------------------------------------------------------ #
    def _is_rate_limited(self, error):
        """Return True if the error is a rate-limit / quota error."""
        msg = str(error).lower()
        return any(k in msg for k in ('429', 'rate limit', 'rate_limit', 'quota', 'resource_exhausted'))

    def answer_question(self, command):
        """
        Route: Cache → Groq (primary) → Gemini (only on Groq rate-limit) → Web search.
        Gemini is never called unless Groq hits its daily/minute quota.
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

        # 2. Groq — always primary
        groq_rate_limited = False
        try:
            answer = self._ask_groq(query)
            if answer:
                print(f"[Source] Groq")
                self._set_cache(query, answer)
                self.jarvis.speak(answer)
                return True
        except Exception as e:
            if self._is_rate_limited(e):
                print("[QA] Groq rate limit hit — switching to Gemini")
                groq_rate_limited = True
            else:
                print(f"[QA] Groq error: {e}")

        # 3. Gemini — only if Groq is rate-limited
        if groq_rate_limited:
            try:
                answer = self._ask_gemini(query)
                if answer:
                    print("[Source] Gemini (Groq rate-limited)")
                    self._set_cache(query, answer)
                    self.jarvis.speak(answer)
                    return True
            except Exception as e:
                print(f"[QA] Gemini error: {e}")

        # 4. Both failed — open browser
        print("[QA] LLMs unavailable — falling back to web search")
        self.jarvis.speak("I couldn't find a direct answer, sir. Let me search the web for that.")
        self.jarvis.web_handler.web_search(f"search {query}")
        return True

import re
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

import numpy as np

from config.settings import INTENT_MODEL_PATH, INTENT_VOCAB_PATH

DEFAULT_INTENTS: List[str] = [
    "music.play",
    "music.control",
    "alarm.set",
    "alarm.cancel",
    "alarm.list",
    "system.volume",
    "system.brightness",
    "system.status",
    "app.open",
    "meeting.join",
    "meeting.schedule",
    "meeting.leave",
    "web.search",
    "date_time.get",
    "qa_chat",
]


@dataclass
class IntentResult:
    """
    Structured outcome of an intent classification and slot extraction pass.
    Supports both object attribute access (.intent, .confidence, .slots)
    and dict-like access (['intent'], .get('intent')) for maximum engine compatibility.
    """
    intent: str
    confidence: float
    slots: Dict[str, Any] = field(default_factory=dict)
    raw_query: str = ""

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.slots.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.slots.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(float(self.confidence), 4),
            "slots": dict(self.slots),
            "raw_query": self.raw_query,
        }


def extract_features(text: str, char_ngram: int = 3) -> List[str]:
    """Extract word tokens and character n-grams matching the model tokenizer."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\s]", " ", text.lower()).strip()
    words = [w for w in cleaned.split() if w]
    feats: List[str] = []
    for w in words:
        feats.append(w)
        if len(w) >= char_ngram:
            padded = f"<{w}>"
            for i in range(len(padded) - char_ngram + 1):
                feats.append(padded[i:i + char_ngram])
    return feats


class IntentClassifier:
    """
    Ultra-low latency (<5ms) ONNX CPU Intent Classifier for JARVIS.
    Maps voice and text utterances to 15 core intents with slot extraction.
    Includes an immediate graceful fallback to pattern classification if ONNX model is not yet compiled.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        vocab_path: Optional[Path] = None,
    ) -> None:
        self.model_path: Path = Path(model_path or INTENT_MODEL_PATH)
        self.vocab_path: Path = Path(vocab_path or INTENT_VOCAB_PATH)

        self.vocab: Dict[str, int] = {"<pad>": 0, "<unk>": 1}
        self.intents: List[str] = list(DEFAULT_INTENTS)
        self.max_seq_len: int = 32
        self.char_ngram: int = 3
        self.slots_config: Dict[str, List[str]] = {}

        self.session: Optional[Any] = None
        self.is_onnx_ready: bool = False

        self._load_vocab()
        self._init_session()

    def _load_vocab(self) -> None:
        """Load vocabulary and intents config from JSON file if present."""
        if self.vocab_path.exists():
            try:
                with open(self.vocab_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.vocab = data.get("vocab", self.vocab)
                self.intents = data.get("intents", self.intents)
                self.max_seq_len = int(data.get("max_seq_len", 32))
                self.char_ngram = int(data.get("char_ngram", 3))
                self.slots_config = data.get("slots_config", {})
            except Exception as e:
                print(f"[IntentClassifier] Warning: Could not read vocab file: {e}")

    def _init_session(self) -> None:
        """Initialize onnxruntime InferenceSession on CPU."""
        if not self.model_path.exists():
            self.is_onnx_ready = False
            return

        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.intra_op_num_threads = 2
            opts.inter_op_num_threads = 1
            opts.log_severity_level = 3
            self.session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self.is_onnx_ready = True
        except Exception as e:
            print(f"[IntentClassifier] ONNX Runtime initialization note: {e}")
            self.session = None
            self.is_onnx_ready = False

    def tokenize(self, text: str) -> np.ndarray:
        """Encodes query into token ID sequence padded to max_seq_len."""
        feats = extract_features(text, char_ngram=self.char_ngram)
        ids = [self.vocab.get(f, 1) for f in feats][:self.max_seq_len]
        if len(ids) < self.max_seq_len:
            ids = ids + [0] * (self.max_seq_len - len(ids))
        return np.array([ids], dtype=np.int64)

    def classify(self, query: str) -> IntentResult:
        """
        Classifies user query, returning IntentResult with intent, confidence, and extracted slots.
        Inference takes <5ms on CPU with ONNX Runtime, with zero crash risk via regex fallback.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            return IntentResult(
                intent="qa_chat",
                confidence=1.0,
                slots={},
                raw_query="",
            )

        # High-confidence phrase overrides before ONNX inference
        low = clean_query.lower()
        if re.search(r"\b(what meetings|my meetings|upcoming meetings|list meetings|any meetings|check meetings|calendar meetings)\b", low):
            return IntentResult(
                intent="meeting.schedule",
                confidence=0.98,
                slots=self.extract_slots("meeting.schedule", clean_query),
                raw_query=clean_query,
            )

        # 1. Try ONNX inference if model is compiled
        if self.is_onnx_ready and self.session is not None:
            try:
                input_ids = self.tokenize(clean_query)
                outputs = self.session.run(None, {"input_ids": input_ids})
                logits = outputs[0][0]  # shape: [num_classes]

                # Softmax over logits
                shift_logits = logits - np.max(logits)
                exps = np.exp(shift_logits)
                probs = exps / np.sum(exps)

                best_idx = int(np.argmax(probs))
                confidence = float(probs[best_idx])
                intent = self.intents[best_idx] if best_idx < len(self.intents) else "qa_chat"

                # Extract slots for classified intent
                slots = self.extract_slots(intent, clean_query)
                return IntentResult(
                    intent=intent,
                    confidence=confidence,
                    slots=slots,
                    raw_query=clean_query,
                )
            except Exception:
                pass

        # 2. Graceful fast fallback: Pattern & Regex Classifier
        fallback_intent, fallback_conf = self._pattern_classify(clean_query)
        fallback_slots = self.extract_slots(fallback_intent, clean_query)
        return IntentResult(
            intent=fallback_intent,
            confidence=fallback_conf,
            slots=fallback_slots,
            raw_query=clean_query,
        )

    def _pattern_classify(self, query: str) -> Tuple[str, float]:
        """
        Rule-based pattern matching fallback guaranteeing JARVIS functions
        even before ONNX model compilation.
        """
        low = query.lower().strip()

        # Music playback vs control
        if re.match(r"^(?:pause|resume|continue|stop playback|skip|next track|next song|previous track|previous song|mute music|unmute player)\b", low):
            return "music.control", 0.95
        if low.startswith("play ") or "put on " in low or low.startswith("stream ") or "listen to " in low:
            return "music.play", 0.95

        # Alarms & Timers
        if re.search(r"\b(cancel all alarms|cancel my .* alarm|cancel the alarm|delete alarm|turn off .*alarm)\b", low):
            return "alarm.cancel", 0.95
        if re.search(r"\b(list my alarms|show my alarms|what alarms are set|check my alarms|do i have any alarms)\b", low):
            return "alarm.list", 0.95
        if re.search(r"\b(set an alarm|set alarm|wake me up at|set a timer|start a timer|timer for)\b", low):
            return "alarm.set", 0.95

        # System volume & brightness
        if re.search(r"\b(volume up|volume down|turn up volume|lower volume|mute audio|unmute sound|set volume)\b", low):
            return "system.volume", 0.95
        if re.search(r"\b(brightness up|brightness down|dim screen|dim the screen|make screen brighter|set brightness)\b", low):
            return "system.brightness", 0.95

        # System status / diagnostics
        if re.search(r"\b(system status|cpu usage|check cpu|ram utilization|memory status|battery percentage|check battery|system diagnostics|specs)\b", low):
            return "system.status", 0.95

        # Application Launch
        if re.match(r"^(?:open|launch|start)\s+[a-zA-Z0-9_\-.\s]{2,25}$", low) and not any(k in low for k in ("meeting", "call", "http", "zoom")):
            return "app.open", 0.95

        # Meeting controls
        if re.search(r"\b(leave meeting|leave the meeting|leave call|hang up|end call|drop off call)\b", low):
            return "meeting.leave", 0.95
        if re.search(r"\b(schedule meeting|schedule a meeting|book meeting|create meeting|set up a call|what meetings|my meetings|upcoming meetings|list meetings|any meetings|check meetings|calendar meetings)\b", low):
            return "meeting.schedule", 0.98
        if re.search(r"\b(join meeting|join the call|meet\.google\.com|teams\.microsoft\.com|zoom\.us)\b", low):
            return "meeting.join", 0.95

        # Web Search
        if re.search(r"\b(search the web for|search online for|search the internet for|google |look up online)\b", low):
            return "web.search", 0.95

        # Date & Time
        if re.search(r"\b(what time is it|current time|tell me the time|what is today's date|today's date|current date|which year is it|what year)\b", low):
            return "date_time.get", 0.95

        # Default conversational / QA
        return "qa_chat", 0.85

    def extract_slots(self, intent: str, query: str) -> Dict[str, Any]:
        """
        Extracts intent-specific slots such as song name, alarm time, volume level,
        app name, search query, or meeting URL.
        """
        low = query.lower().strip()
        slots: Dict[str, Any] = {}

        if intent == "music.play":
            # Extract platform if specified
            platform = "youtube"
            for plat in ("spotify", "youtube", "apple music", "soundcloud", "amazon music"):
                if f"on {plat}" in low:
                    platform = plat
                    low = low.replace(f"on {plat}", "").strip()
                    break

            # Extract artist if "by <artist>"
            artist = None
            by_match = re.search(r"\bby\s+([a-zA-Z0-9\s]+)$", low)
            if by_match:
                artist = by_match.group(1).strip()
                low = low[:by_match.start()].strip()

            # Clean leading command verbs to isolate song title
            song = re.sub(r"^(?:jarvis\s+|hey jarvis\s+|please\s+)?(?:play|put on|stream|listen to)\s+(?:some\s+|the\s+|track\s+)?", "", low).strip()
            # Clean trailing politeness
            song = re.sub(r"\s+(?:please|for me|right now|thanks)$", "", song).strip()
            slots["song"] = song or "music"
            slots["platform"] = platform
            if artist:
                slots["artist"] = artist

        elif intent == "music.control":
            action = "pause"
            for act in ("pause", "resume", "stop", "next", "skip", "previous", "mute", "unmute", "replay"):
                if act in low:
                    action = "next" if act == "skip" else act
                    break
            slots["action"] = action

        elif intent == "alarm.set":
            # Check timer duration
            timer_m = re.search(r"(\d+)\s*(minute|min|second|sec|hour|hr)s?", low)
            if timer_m and ("timer" in low or "in " in low):
                qty = int(timer_m.group(1))
                unit = timer_m.group(2)
                mins = qty * 60 if unit.startswith("hour") or unit.startswith("hr") else (max(1, qty // 60) if unit.startswith("sec") else qty)
                slots["duration_minutes"] = mins
                slots["label"] = "timer"

            # Check clock time: e.g. 7:30 am, 8 pm, 6:00
            time_m = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", low)
            if time_m:
                raw_t = time_m.group(1).strip()
                slots["time"] = raw_t
                if "am" in raw_t:
                    slots["period"] = "am"
                elif "pm" in raw_t:
                    slots["period"] = "pm"
                slots.setdefault("label", "alarm")

        elif intent == "alarm.cancel":
            slots["all"] = bool("all" in low)
            time_m = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", low)
            if time_m:
                slots["time"] = time_m.group(1).strip()

        elif intent == "alarm.list":
            slots["list_active"] = True

        elif intent == "system.volume":
            lvl_m = re.search(r"(\d{1,3})\s*(?:%|percent)?", low)
            if lvl_m:
                slots["level"] = min(100, max(0, int(lvl_m.group(1))))
                slots["action"] = "set"
            elif "up" in low or "increase" in low or "raise" in low:
                slots["action"] = "up"
            elif "down" in low or "lower" in low or "decrease" in low:
                slots["action"] = "down"
            elif "unmute" in low:
                slots["action"] = "unmute"
            elif "mute" in low:
                slots["action"] = "mute"
            elif "max" in low:
                slots["level"] = 100
                slots["action"] = "set"

        elif intent == "system.brightness":
            lvl_m = re.search(r"(\d{1,3})\s*(?:%|percent)?", low)
            if lvl_m:
                slots["level"] = min(100, max(0, int(lvl_m.group(1))))
                slots["action"] = "set"
            elif "up" in low or "brighter" in low or "increase" in low:
                slots["action"] = "up"
            elif "down" in low or "dim" in low or "lower" in low or "decrease" in low:
                slots["action"] = "down"
            elif "max" in low:
                slots["level"] = 100
                slots["action"] = "set"

        elif intent == "system.status":
            if "cpu" in low:
                slots["metric"] = "cpu"
            elif "ram" in low or "memory" in low:
                slots["metric"] = "ram"
            elif "battery" in low:
                slots["metric"] = "battery"
            else:
                slots["metric"] = "all"

        elif intent == "app.open":
            app = re.sub(r"^(?:jarvis\s+|hey jarvis\s+|please\s+)?(?:open|launch|start|run)\s+(?:the\s+)?(?:application\s+|app\s+|program\s+)?", "", low).strip()
            app = re.sub(r"\s+(?:please|for me|app|application)$", "", app).strip()
            slots["app_name"] = app or "application"

        elif intent == "meeting.join":
            url_m = re.search(r"(https?://[^\s]+)", query)
            if url_m:
                slots["url"] = url_m.group(1).strip()
            if "google" in low or "meet" in low:
                slots["platform"] = "google meet"
            elif "teams" in low:
                slots["platform"] = "teams"
            elif "zoom" in low:
                slots["platform"] = "zoom"

        elif intent == "meeting.schedule":
            t_m = re.search(r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", low)
            if t_m:
                slots["time"] = t_m.group(1).strip()
            for day in ("tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "next week"):
                if day in low:
                    slots["date"] = day
                    break
            with_m = re.search(r"with\s+([a-zA-Z\s]+?)(?:\s+(?:tomorrow|today|at|on)|\s*$)", query, re.IGNORECASE)
            if with_m:
                slots["participants"] = with_m.group(1).strip()
            slots["title"] = "Scheduled Meeting"

        elif intent == "meeting.leave":
            slots["action"] = "leave"

        elif intent == "web.search":
            q = re.sub(r"^(?:jarvis\s+|hey jarvis\s+|please\s+)?(?:search\s+(?:the\s+web\s+|online\s+|the\s+internet\s+)?for|google|look\s+up\s+online|find\s+information\s+(?:on|about)|search\s+for)\s+", "", low).strip()
            q = re.sub(r"\s+(?:please|for me|online)$", "", q).strip()
            slots["query"] = q or query

        elif intent == "date_time.get":
            if "time" in low:
                slots["type"] = "time"
            elif "year" in low:
                slots["type"] = "year"
            else:
                slots["type"] = "date"

        elif intent == "qa_chat":
            slots["query"] = query

        return slots


import os
import re
import json
import random
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set, Optional

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
ONNX_MODEL_PATH = MODELS_DIR / "intent_model.onnx"
VOCAB_PATH = MODELS_DIR / "intent_vocab.json"

INTENTS: List[str] = [
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

SLOTS_CONFIG: Dict[str, List[str]] = {
    "music.play": ["song", "platform", "artist"],
    "music.control": ["action"],
    "alarm.set": ["time", "period", "label", "duration_minutes"],
    "alarm.cancel": ["time", "all"],
    "alarm.list": [],
    "system.volume": ["level", "action"],
    "system.brightness": ["level", "action"],
    "system.status": ["metric"],
    "app.open": ["app_name"],
    "meeting.join": ["url", "platform"],
    "meeting.schedule": ["title", "time", "date", "participants"],
    "meeting.leave": ["action"],
    "web.search": ["query"],
    "date_time.get": ["type"],
    "qa_chat": ["query"],
}

ARTISTS: List[str] = [
    "Taylor Swift", "The Weeknd", "Daft Punk", "Hans Zimmer", "Queen",
    "Adele", "Drake", "Ed Sheeran", "Coldplay", "Eminem", "Pink Floyd",
    "Billie Eilish", "Kendrick Lamar", "Michael Jackson", "Beethoven",
    "Mozart", "AC/DC", "Imagine Dragons", "Post Malone", "BTS",
    "Lady Gaga", "Linkin Park", "Bruno Mars", "Dua Lipa", "Kavinsky"
]

SONGS: List[str] = [
    "Bohemian Rhapsody", "Blinding Lights", "Interstellar Soundtrack",
    "Shape of You", "Starboy", "Hotel California", "Stay", "Believer",
    "Rolling in the Deep", "Smells Like Teen Spirit", "Fix You", "Despacito",
    "Bad Guy", "Levitating", "Sunflower", "Clair de Lune", "Canon in D",
    "Thunderstruck", "Lose Yourself", "Fly Me to the Moon", "Nightcall",
    "Midnight City", "Get Lucky", "Viva La Vida", "Time"
]

GENRES: List[str] = [
    "jazz", "lo-fi beats", "classical music", "rock", "hip hop",
    "electronic music", "acoustic indie", "pop music", "ambient sound",
    "blues", "synthwave", "chillout", "instrumental piano", "techno"
]

PLATFORMS: List[str] = ["Spotify", "YouTube", "Apple Music", "Soundcloud", "Amazon Music"]

APPS: List[str] = [
    "Chrome", "Google Chrome", "Firefox", "Visual Studio Code", "VS Code",
    "Notepad", "Calculator", "Spotify", "Discord", "Terminal", "PowerShell",
    "Task Manager", "Settings", "Steam", "Slack", "Excel", "Word",
    "PowerPoint", "Obsidian", "VLC", "Docker Desktop", "Git Bash"
]

TIMES: List[str] = [
    "6:00 am", "6:30 am", "7:00 am", "7:15 am", "7:30 am", "8:00 am",
    "8:30 am", "9:00 am", "9:30 am", "10:00 am", "1:00 pm", "2:30 pm",
    "5:00 pm", "6:00 pm", "7:30 pm", "9:00 pm", "10:00 pm", "11:30 pm",
    "6 am", "7 am", "8 am", "9 pm", "6:45", "7:20", "8:10"
]

DURATIONS: List[str] = [
    "5 minutes", "10 minutes", "15 minutes", "20 minutes", "25 minutes",
    "30 minutes", "45 minutes", "1 hour", "90 seconds", "2 hours"
]

LEVELS: List[str] = ["10", "20", "25", "30", "40", "50", "60", "70", "75", "80", "90", "100"]

MEETING_LINKS: List[str] = [
    "https://meet.google.com/abc-defg-hij",
    "https://meet.google.com/xyz-uvwx-rst",
    "https://teams.microsoft.com/l/meetup-join/19%3ameeting",
    "https://teams.microsoft.com/l/meetup-join/987654321",
    "https://zoom.us/j/1234567890",
    "https://zoom.us/j/9876543210"
]

MEETING_TITLES: List[str] = [
    "team sync", "weekly standup", "sprint retrospective", "project review",
    "architecture sync", "client demo", "1 on 1 review", "planning session",
    "board presentation", "budget review", "technical interview", "design sync"
]

WEB_QUERIES: List[str] = [
    "quantum computing advances 2025", "latest generative AI models",
    "how does nuclear fusion work", "best practices for python async programming",
    "history of the roman empire", "space telescope discoveries",
    "renewable energy statistics", "fastest supercomputers in the world",
    "crispr gene editing breakthrough", "mars rover latest findings",
    "how to bake artisan sourdough", "photosynthesis light reaction",
    "black hole event horizon physics", "rust memory management vs c++",
    "global economic trends 2026", "deep sea exploration discoveries"
]

QA_QUESTIONS: List[str] = [
    "who was albert einstein", "explain general relativity in simple terms",
    "what is the capital of australia", "how does a jet engine operate",
    "who wrote the tragedy of macbeth", "what is photosynthesis",
    "explain the difference between tcp and udp", "how do vaccines work",
    "what is dark matter in astronomy", "can you write a haiku about rain",
    "tell me an interesting science fact", "who invented the telephone",
    "what are the laws of thermodynamics", "how does an airplane generate lift",
    "explain quantum entanglement simply", "what is the boiling point of water"
]

PREFIXES: List[str] = [
    "", "", "", "jarvis ", "hey jarvis ", "ok jarvis ", "please ",
    "can you ", "could you ", "would you ", "i want you to ", "kindly "
]

POSTFIXES: List[str] = [
    "", "", "", " please", " for me", " right now", " immediately",
    " thanks", " jarvis", " sir"
]


def generate_synthetic_dataset(min_samples_per_intent: int = 400) -> List[Tuple[str, str]]:
    """
    Generates a rich, synthetic dataset of 6,000+ utterances covering all 15 JARVIS intents.
    Includes template expansion, variable substitution, and natural language noise injection.
    """
    random.seed(42)
    dataset: List[Tuple[str, str]] = []

    def make_phrase(core: str) -> str:
        p = random.choice(PREFIXES)
        s = random.choice(POSTFIXES)
        res = f"{p}{core}{s}".strip().lower()
        res = re.sub(r"\s+", " ", res)
        return res

    for intent in INTENTS:
        samples: Set[str] = set()

        if intent == "music.play":
            while len(samples) < min_samples_per_intent:
                song = random.choice(SONGS)
                artist = random.choice(ARTISTS)
                genre = random.choice(GENRES)
                plat = random.choice(PLATFORMS)
                templates = [
                    f"play {song}",
                    f"play {song} by {artist}",
                    f"play {song} on {plat}",
                    f"play {song} by {artist} on {plat}",
                    f"put on {song}",
                    f"put on some {genre}",
                    f"put on {genre} music",
                    f"play some {genre}",
                    f"listen to {artist}",
                    f"listen to {song}",
                    f"start playing {song}",
                    f"start playing {genre}",
                    f"stream {song} on {plat}",
                    f"queue up {song}",
                    f"spin some {genre}",
                    f"play track {song}",
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "music.control":
            while len(samples) < min_samples_per_intent:
                verbs = [
                    "pause the music", "pause playback", "pause song", "pause audio",
                    "resume music", "resume playback", "continue playing", "unpause music",
                    "stop the music", "stop playback", "stop song", "turn off music",
                    "next track", "next song", "skip this track", "skip to next song",
                    "previous track", "previous song", "go back to previous track",
                    "restart track", "replay this song", "mute music", "unmute player"
                ]
                samples.add(make_phrase(random.choice(verbs)))

        elif intent == "alarm.set":
            while len(samples) < min_samples_per_intent:
                t = random.choice(TIMES)
                d = random.choice(DURATIONS)
                label = random.choice(["wake up", "workout", "meeting", "call", "cook", "standup"])
                templates = [
                    f"set an alarm for {t}",
                    f"set alarm at {t}",
                    f"set alarm for {t} tomorrow",
                    f"wake me up at {t}",
                    f"create an alarm for {t}",
                    f"set a morning alarm at {t}",
                    f"set a timer for {d}",
                    f"start a timer for {d}",
                    f"start timer {d}",
                    f"timer {d}",
                    f"set an alarm at {t} called {label}",
                    f"alarm at {t} for {label}",
                    f"schedule wake up at {t}",
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "alarm.cancel":
            while len(samples) < min_samples_per_intent:
                t = random.choice(TIMES)
                templates = [
                    f"cancel my {t} alarm",
                    f"cancel the alarm for {t}",
                    f"cancel all alarms",
                    f"cancel all my alarms",
                    f"delete alarm for {t}",
                    f"delete all active alarms",
                    f"turn off the alarm",
                    f"turn off all alarms",
                    f"disable alarm at {t}",
                    f"remove the {t} wake up call",
                    f"stop the alarm",
                    f"clear all alarms",
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "alarm.list":
            while len(samples) < min_samples_per_intent:
                templates = [
                    "list my alarms", "list all alarms", "show my alarms", "show all alarms",
                    "what alarms are set", "what alarms do i have", "check my alarms",
                    "do i have any alarms set", "view active alarms", "display alarms",
                    "what timers are running", "list active timers", "show scheduled alarms"
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "system.volume":
            while len(samples) < min_samples_per_intent:
                lvl = random.choice(LEVELS)
                templates = [
                    "volume up", "turn up the volume", "increase volume", "raise the volume",
                    "volume down", "turn down the volume", "decrease volume", "lower sound",
                    f"set volume to {lvl}%", f"set volume to {lvl} percent", f"volume {lvl}",
                    f"adjust volume to {lvl}%", f"change volume to {lvl}",
                    "mute audio", "mute sound", "mute system", "mute volume",
                    "unmute audio", "unmute sound", "unmute system volume", "restore volume",
                    "max volume", "set volume to maximum", "set volume to 100%"
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "system.brightness":
            while len(samples) < min_samples_per_intent:
                lvl = random.choice(LEVELS)
                templates = [
                    "increase brightness", "turn up screen brightness", "make screen brighter",
                    "brightness up", "boost brightness", "higher brightness",
                    "decrease brightness", "dim the screen", "turn down screen brightness",
                    "brightness down", "lower display brightness", "make screen dimmer",
                    f"set brightness to {lvl}%", f"set brightness to {lvl} percent", f"brightness {lvl}",
                    f"display brightness {lvl}%", f"adjust brightness to {lvl}",
                    "max brightness", "set screen to 100% brightness", "dim monitor"
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "system.status":
            while len(samples) < min_samples_per_intent:
                templates = [
                    "check system status", "system status", "run system diagnostics",
                    "system diagnostics", "how is cpu usage", "cpu load", "check cpu",
                    "how much ram is used", "ram utilization", "memory status",
                    "check battery level", "how is battery", "battery percentage",
                    "check hardware specs", "system health check", "telemetry status",
                    "show system stats", "how is the computer running", "performance overview"
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "app.open":
            while len(samples) < min_samples_per_intent:
                app = random.choice(APPS)
                templates = [
                    f"open {app}",
                    f"launch {app}",
                    f"start {app}",
                    f"open application {app}",
                    f"launch program {app}",
                    f"start up {app}",
                    f"bring up {app}",
                    f"open the {app} app",
                    f"run {app}",
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "meeting.join":
            while len(samples) < min_samples_per_intent:
                link = random.choice(MEETING_LINKS)
                plat = random.choice(["Google Meet", "Microsoft Teams", "Zoom"])
                templates = [
                    f"join meeting {link}",
                    f"join the call {link}",
                    f"join {plat} meeting {link}",
                    f"connect to meeting {link}",
                    f"enter meeting {link}",
                    f"join my upcoming meeting",
                    f"join the {plat} call",
                    f"jump into the meeting",
                    f"enter the conference call",
                    f"open meeting link {link}",
                    f"join scheduled call",
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "meeting.schedule":
            while len(samples) < min_samples_per_intent:
                title = random.choice(MEETING_TITLES)
                t = random.choice(TIMES)
                day = random.choice(["tomorrow", "on monday", "on friday", "next week", "today"])
                person = random.choice(["Alex", "Sarah", "the team", "David", "Elena", "Marcus"])
                templates = [
                    f"schedule a meeting for {title} {day} at {t}",
                    f"schedule {title} with {person} {day} at {t}",
                    f"book a meeting {day} at {t}",
                    f"create a meeting for {title} at {t}",
                    f"set up a call with {person} {day} at {t}",
                    f"calendar a meeting called {title} for {t}",
                    f"schedule sync with {person} at {t}",
                    "what meetings do i have today",
                    "what meetings do i have",
                    "my meetings for today",
                    "list my meetings",
                    "show my upcoming meetings",
                    "check my meetings",
                    "what is on my calendar",
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "meeting.leave":
            while len(samples) < min_samples_per_intent:
                templates = [
                    "leave the meeting", "leave call", "leave this meeting",
                    "disconnect from meeting", "hang up the call", "hang up call",
                    "end call", "end the meeting", "drop off call", "drop from meeting",
                    "exit zoom", "disconnect conference", "leave google meet"
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "web.search":
            while len(samples) < min_samples_per_intent:
                q = random.choice(WEB_QUERIES)
                templates = [
                    f"search the web for {q}",
                    f"search online for {q}",
                    f"google {q}",
                    f"look up online {q}",
                    f"search the internet for {q}",
                    f"find information on {q}",
                    f"search for {q}",
                    f"browse online for {q}",
                    f"query web for {q}",
                    f"look up {q} on the web",
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "date_time.get":
            while len(samples) < min_samples_per_intent:
                templates = [
                    "what time is it", "what is the current time", "tell me the time",
                    "time please", "current time", "what time do you have",
                    "what date is today", "what is today's date", "tell me today's date",
                    "what is the date", "today's date", "what day is it today",
                    "which day is it", "what year is it", "current year", "which year is this"
                ]
                samples.add(make_phrase(random.choice(templates)))

        elif intent == "qa_chat":
            while len(samples) < min_samples_per_intent:
                q = random.choice(QA_QUESTIONS)
                chit_chat = [
                    "hello", "hi jarvis", "hey how are you", "good morning",
                    "good afternoon", "who created you", "tell me a joke",
                    "can you help me with a question", "what can you do",
                    "what are your capabilities", "how smart are you"
                ]
                templates = [
                    q,
                    f"can you tell me {q}",
                    f"jarvis {q}",
                    random.choice(chit_chat),
                ]
                samples.add(make_phrase(random.choice(templates)))

        for s in samples:
            dataset.append((s, intent))

    random.shuffle(dataset)
    return dataset


class Tokenizer:
    """
    Subword word + character n-gram tokenizer designed for fast low-latency CPU embedding models.
    """
    def __init__(self, char_ngram: int = 3, max_seq_len: int = 32) -> None:
        self.char_ngram: int = char_ngram
        self.max_seq_len: int = max_seq_len
        self.vocab: Dict[str, int] = {"<pad>": 0, "<unk>": 1}

    def extract_features(self, text: str) -> List[str]:
        cleaned = re.sub(r"[^a-zA-Z0-9_\s]", " ", text.lower()).strip()
        words = [w for w in cleaned.split() if w]
        feats: List[str] = []
        for w in words:
            feats.append(w)
            # Character n-grams for typo and subword invariance
            if len(w) >= self.char_ngram:
                padded = f"<{w}>"
                for i in range(len(padded) - self.char_ngram + 1):
                    feats.append(padded[i:i + self.char_ngram])
        return feats

    def fit(self, texts: List[str], max_vocab_size: int = 6000) -> None:
        counts: Dict[str, int] = {}
        for t in texts:
            feats = self.extract_features(t)
            for f in feats:
                counts[f] = counts.get(f, 0) + 1

        # Keep tokens with frequency >= 2, sorted by frequency
        sorted_tokens = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        for token, cnt in sorted_tokens:
            if len(self.vocab) >= max_vocab_size:
                break
            if cnt >= 2 and token not in self.vocab:
                self.vocab[token] = len(self.vocab)

    def encode(self, text: str) -> List[int]:
        feats = self.extract_features(text)
        ids = [self.vocab.get(f, 1) for f in feats][:self.max_seq_len]
        if len(ids) < self.max_seq_len:
            ids = ids + [0] * (self.max_seq_len - len(ids))
        return ids


class UtteranceDataset(Dataset):
    def __init__(self, data: List[Tuple[str, str]], tokenizer: Tokenizer, intent_to_idx: Dict[str, int]) -> None:
        self.data: List[Tuple[str, str]] = data
        self.tokenizer: Tokenizer = tokenizer
        self.intent_to_idx: Dict[str, int] = intent_to_idx

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        text, intent = self.data[idx]
        ids = self.tokenizer.encode(text)
        label = self.intent_to_idx[intent]
        return torch.tensor(ids, dtype=torch.long), torch.tensor(label, dtype=torch.long)


class IntentNN(nn.Module):
    """
    Lightweight PyTorch neural net for sub-millisecond ONNX CPU inference.
    Combines word+char embeddings with masked average and max pooling into an MLP.
    """
    def __init__(self, vocab_size: int, embed_dim: int, hidden_dim: int, num_classes: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.fc1 = nn.Linear(embed_dim * 2, hidden_dim)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.15)
        self.fc2 = nn.Linear(hidden_dim, num_classes)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        # input_ids: [batch_size, seq_len]
        emb = self.embedding(input_ids)  # [batch_size, seq_len, embed_dim]

        # Padding mask for mean pooling
        mask = (input_ids != 0).unsqueeze(-1).float()  # [batch_size, seq_len, 1]
        sum_pool = torch.sum(emb * mask, dim=1)  # [batch_size, embed_dim]
        lengths = torch.clamp(torch.sum(mask, dim=1), min=1.0)
        mean_pool = sum_pool / lengths

        # Max pooling with padded positions masked out
        emb_masked = emb + (1.0 - mask) * -1e9
        max_pool, _ = torch.max(emb_masked, dim=1)

        feat = torch.cat([mean_pool, max_pool], dim=1)  # [batch_size, embed_dim * 2]
        h = self.relu(self.fc1(feat))
        h = self.dropout(h)
        logits = self.fc2(h)
        return logits


def train_intent_model(
    epochs: int = 15,
    batch_size: int = 64,
    learning_rate: float = 0.003,
    embed_dim: int = 64,
    hidden_dim: int = 64,
) -> float:
    print("=" * 65)
    print("  JARVIS 3.0 Fast Neural Intent Classifier Training Pipeline")
    print("=" * 65)

    print("\n[1/5] Generating synthetic dataset across 15 JARVIS intents...")
    dataset = generate_synthetic_dataset(min_samples_per_intent=420)
    print(f"Generated {len(dataset)} balanced utterances covering all intents.")

    # Split train and validation
    random.shuffle(dataset)
    split_idx = int(len(dataset) * 0.85)
    train_data = dataset[:split_idx]
    val_data = dataset[split_idx:]
    print(f"Dataset split: {len(train_data)} train samples, {len(val_data)} validation samples.")

    print("\n[2/5] Building vocabulary (word + character 3-grams)...")
    tokenizer = Tokenizer(char_ngram=3, max_seq_len=32)
    tokenizer.fit([t for t, _ in train_data], max_vocab_size=6000)
    print(f"Vocabulary size: {len(tokenizer.vocab)} tokens.")

    intent_to_idx = {intent: i for i, intent in enumerate(INTENTS)}
    train_ds = UtteranceDataset(train_data, tokenizer, intent_to_idx)
    val_ds = UtteranceDataset(val_data, tokenizer, intent_to_idx)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    print("\n[3/5] Initializing Neural Network...")
    device = torch.device("cpu")
    model = IntentNN(
        vocab_size=len(tokenizer.vocab),
        embed_dim=embed_dim,
        hidden_dim=hidden_dim,
        num_classes=len(INTENTS),
    ).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    print(f"\n[4/5] Training for {epochs} epochs with AdamW & CrossEntropyLoss...")
    best_acc = 0.0
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        correct_train = 0
        total_train = 0

        for x_batch, y_batch in train_loader:
            x_batch, y_batch = x_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            logits = model(x_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * len(y_batch)
            preds = torch.argmax(logits, dim=1)
            correct_train += (preds == y_batch).sum().item()
            total_train += len(y_batch)

        scheduler.step()

        # Validation
        model.eval()
        val_loss = 0.0
        correct_val = 0
        total_val = 0

        with torch.no_grad():
            for x_val, y_val in val_loader:
                x_val, y_val = x_val.to(device), y_val.to(device)
                logits_val = model(x_val)
                loss_v = criterion(logits_val, y_val)
                val_loss += loss_v.item() * len(y_val)
                preds_val = torch.argmax(logits_val, dim=1)
                correct_val += (preds_val == y_val).sum().item()
                total_val += len(y_val)

        train_acc = correct_train / max(1, total_train)
        val_acc = correct_val / max(1, total_val)
        if val_acc > best_acc:
            best_acc = val_acc

        print(
            f"Epoch {epoch:02d}/{epochs:02d} | "
            f"Train Loss: {train_loss / total_train:.4f} - Train Acc: {train_acc * 100:.2f}% | "
            f"Val Loss: {val_loss / total_val:.4f} - Val Acc: {val_acc * 100:.2f}%"
        )

    elapsed = time.time() - t0
    print(f"\nTraining completed in {elapsed:.2f}s! Best Validation Accuracy: {best_acc * 100:.2f}%.")

    print("\n[5/5] Exporting ONNX model and saving vocabulary metadata...")
    model.eval()
    dummy_input = torch.zeros((1, tokenizer.max_seq_len), dtype=torch.long)
    torch.onnx.export(
        model,
        dummy_input,
        str(ONNX_MODEL_PATH),
        input_names=["input_ids"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size"},
            "logits": {0: "batch_size"},
        },
        opset_version=14,
    )
    print(f"Exported ONNX model -> {ONNX_MODEL_PATH}")

    vocab_payload: Dict[str, Any] = {
        "vocab": tokenizer.vocab,
        "intents": INTENTS,
        "max_seq_len": tokenizer.max_seq_len,
        "char_ngram": tokenizer.char_ngram,
        "slots_config": SLOTS_CONFIG,
    }
    with open(VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(vocab_payload, f, indent=2)
    print(f"Saved vocabulary & slots config -> {VOCAB_PATH}")

    return best_acc


def main() -> None:
    train_intent_model()


if __name__ == "__main__":
    main()


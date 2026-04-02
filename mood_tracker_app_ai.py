"""
Mood Tracker App with optional AI-powered suggestions.

What is new in this version:
- Optional AI generation for suggestions, affirmations, and insights
- Safe fallback to the original rule-based engine when AI is off or fails
- AI settings stored in the local SQLite database
- Uses only Python standard library modules

How AI works:
1. Turn on "Use AI" in Preferences.
2. Provide an API URL and API key.
3. The app sends the current mood snapshot to that endpoint.
4. The endpoint must return JSON shaped like:
   {
     "suggestions": ["...", "...", "...", "..."],
     "reward": "...",
     "affirmation": {
       "title": "Affirmation for 🙂",
       "tags": "Encouragement • Tone: Supportive",
       "body": "...",
       "note": "..."
     },
     "insight": "..."
   }

Notes:
- This app expects a generic JSON API so you can connect it to your own backend,
  FastAPI service, or an OpenAI-compatible wrapper.
- If the API call fails, the app automatically falls back to rule-based content.
"""

from __future__ import annotations

import json
import random
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
import tkinter as tk
from tkinter import messagebox, ttk


DB_PATH = Path(__file__).with_name("mood_tracker.db")


@dataclass
class Snapshot:
    mood: str
    energy: int
    stress: int
    focus: int
    motivation: int


class Database:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._seed_defaults()

    def _create_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mood_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                mood TEXT NOT NULL,
                energy INTEGER NOT NULL,
                stress INTEGER NOT NULL,
                focus INTEGER NOT NULL,
                motivation INTEGER NOT NULL,
                suggestion_mode TEXT NOT NULL,
                generation_source TEXT NOT NULL DEFAULT 'Rule-based',
                suggestions_json TEXT NOT NULL,
                reward_json TEXT NOT NULL,
                affirmation_json TEXT NOT NULL,
                insight_json TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        columns = {
            row[1] for row in cur.execute("PRAGMA table_info(mood_entries)").fetchall()
        }
        if "generation_source" not in columns:
            cur.execute(
                "ALTER TABLE mood_entries ADD COLUMN generation_source TEXT NOT NULL DEFAULT 'Rule-based'"
            )

        self.conn.commit()

    def _seed_defaults(self) -> None:
        defaults = {
            "tone": "Supportive",
            "suggestion_types": json.dumps(["Productivity", "Self-care", "Social"]),
            "notifications": "Off",
            "user_name": "",
            "use_ai": "0",
            "ai_api_url": "",
            "ai_api_key": "",
            "ai_model": "mood-support-v1",
        }
        cur = self.conn.cursor()
        for key, value in defaults.items():
            cur.execute(
                "INSERT OR IGNORE INTO preferences (key, value) VALUES (?, ?)",
                (key, value),
            )
        self.conn.commit()

    def get_pref(self, key: str, default: str = "") -> str:
        cur = self.conn.cursor()
        row = cur.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_pref(self, key: str, value: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO preferences (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def save_entry(
        self,
        snapshot: Snapshot,
        suggestion_mode: str,
        generation_source: str,
        suggestions: list[str],
        reward: str,
        affirmation: dict[str, str],
        insight: str,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO mood_entries (
                created_at, mood, energy, stress, focus, motivation,
                suggestion_mode, generation_source, suggestions_json, reward_json,
                affirmation_json, insight_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                snapshot.mood,
                snapshot.energy,
                snapshot.stress,
                snapshot.focus,
                snapshot.motivation,
                suggestion_mode,
                generation_source,
                json.dumps(suggestions),
                json.dumps(reward),
                json.dumps(affirmation),
                json.dumps(insight),
            ),
        )
        self.conn.commit()

    def get_recent_entries(self, limit: int = 20) -> list[sqlite3.Row]:
        cur = self.conn.cursor()
        return cur.execute(
            "SELECT * FROM mood_entries ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def get_latest_entry(self) -> sqlite3.Row | None:
        cur = self.conn.cursor()
        return cur.execute(
            "SELECT * FROM mood_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()


class RuleBasedEngine:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.mood_labels = {
            "😀": "Cheerful",
            "🙂": "Okay",
            "😌": "Calm",
            "😴": "Tired",
            "😣": "Stressed",
            "🤯": "Overwhelmed",
            "😕": "Low",
        }
        self.suggestions = {
            "restore": [
                "Drink water and take 5 slow breaths",
                "Do one tiny task for 3 minutes",
                "Step away from your screen for a short reset",
                "Pick one must-do and let the rest wait",
                "Put on calming music for 10 minutes",
                "Write a quick brain-dump to reduce mental clutter",
            ],
            "balanced": [
                "Choose 1 priority task and 1 easy win",
                "Reply to one message you have been postponing",
                "Tidy your workspace for 5 minutes",
                "Block 20 minutes for focused work",
                "Take a short walk before starting your next task",
                "Review your plan and remove one unnecessary item",
            ],
            "productive": [
                "Start with your highest-impact task",
                "Use a 25-minute focus sprint",
                "Outline a small goal you can finish today",
                "Batch similar tasks together",
                "Make visible progress on a creative or school project",
                "Plan tomorrow while your energy is still high",
            ],
        }
        self.rewards = {
            "restore": [
                "Watch one favorite video guilt-free",
                "Make tea or your favorite drink",
                "Take a warm shower after your task",
                "Spend 10 minutes doing nothing on purpose",
            ],
            "balanced": [
                "Listen to a playlist you like",
                "Take a relaxed snack break",
                "Buy yourself a small treat later",
                "Enjoy 15 minutes of a hobby",
            ],
            "productive": [
                "Celebrate with a longer break",
                "Mark your win in a journal",
                "Share your progress with a friend",
                "Unlock an episode, game, or fun activity after your task",
            ],
        }
        self.affirmations = {
            "Supportive": [
                "You do not have to do everything today to make today meaningful.",
                "Progress still counts when it is gentle.",
                "You are allowed to make your plan fit your energy.",
                "Small steps are still real steps.",
            ],
            "Playful": [
                "Tiny wins still deserve main-character energy.",
                "You can be kind to yourself and still make progress.",
                "Today is a great day for a low-pressure victory lap.",
                "Your brain is doing its best — give it a friendly side quest.",
            ],
            "Direct": [
                "Pick one thing. Finish it. That is enough.",
                "Protect your energy and use it on what matters most.",
                "A realistic plan beats a perfect plan.",
                "Momentum starts with one action.",
            ],
        }
        self.insights = [
            "Short resets can improve focus more than forcing longer effort.",
            "Lower-energy days often benefit from smaller, visible wins.",
            "Stress can narrow attention, so simpler plans usually work better.",
            "Self-compassion is linked with better recovery after setbacks.",
            "Motivation often follows action, not the other way around.",
            "Mood-aware planning can reduce burnout by matching effort to energy.",
        ]

    def derive_mode(self, s: Snapshot) -> str:
        low_energy = s.energy <= 35
        high_stress = s.stress >= 70
        high_focus = s.focus >= 65
        high_motivation = s.motivation >= 65

        if high_stress or low_energy or s.mood in {"😣", "🤯", "😴", "😕"}:
            return "Restore"
        if high_focus and high_motivation and s.energy >= 55 and s.stress <= 55:
            return "Productive"
        return "Balanced"

    def _bucket(self, mode: str) -> str:
        return {"Restore": "restore", "Balanced": "balanced", "Productive": "productive"}[mode]

    def generate(self, s: Snapshot) -> dict[str, object]:
        mode = self.derive_mode(s)
        bucket = self._bucket(mode)
        tone = self.db.get_pref("tone", "Supportive")
        mood_name = self.mood_labels.get(s.mood, "your current mood")
        return {
            "mode": mode,
            "generation_source": "Rule-based",
            "suggestions": random.sample(self.suggestions[bucket], k=4),
            "reward": random.choice(self.rewards[bucket]),
            "affirmation": {
                "title": f"Affirmation for {s.mood}",
                "tags": f"Encouragement • Tone: {tone}",
                "body": random.choice(self.affirmations.get(tone, self.affirmations["Supportive"])),
                "note": f"You checked in as {mood_name.lower()}. You've got this.",
            },
            "insight": random.choice(self.insights),
        }


class AIContentClient:
    def __init__(self, db: Database, fallback_engine: RuleBasedEngine) -> None:
        self.db = db
        self.fallback_engine = fallback_engine
        self.mood_labels = fallback_engine.mood_labels

    def is_enabled(self) -> bool:
        return self.db.get_pref("use_ai", "0") == "1"

    def _safe_mode(self, snapshot: Snapshot) -> str:
        return self.fallback_engine.derive_mode(snapshot)

    def _build_payload(self, snapshot: Snapshot) -> dict[str, object]:
        tone = self.db.get_pref("tone", "Supportive")
        suggestion_types = json.loads(
            self.db.get_pref("suggestion_types", '["Productivity", "Self-care", "Social"]')
        )
        user_name = self.db.get_pref("user_name", "").strip()
        mood_name = self.mood_labels.get(snapshot.mood, "Unknown")

        return {
            "model": self.db.get_pref("ai_model", "mood-support-v1"),
            "task": "Generate short, supportive wellness/productivity content for a non-clinical mood tracker app.",
            "constraints": {
                "tone": tone,
                "safe_style": [
                    "non-medical",
                    "non-diagnostic",
                    "practical",
                    "encouraging",
                    "short",
                ],
                "return_json_only": True,
                "suggestion_count": 4,
            },
            "user_context": {
                "name": user_name,
                "mood_emoji": snapshot.mood,
                "mood_label": mood_name,
                "energy": snapshot.energy,
                "stress": snapshot.stress,
                "focus": snapshot.focus,
                "motivation": snapshot.motivation,
                "preferred_suggestion_types": suggestion_types,
            },
            "expected_output_schema": {
                "suggestions": ["string", "string", "string", "string"],
                "reward": "string",
                "affirmation": {
                    "title": "string",
                    "tags": "string",
                    "body": "string",
                    "note": "string",
                },
                "insight": "string",
            },
        }

    def _post_json(self, url: str, api_key: str, payload: dict[str, object]) -> dict[str, object]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    def _validate_ai_result(self, data: dict[str, object], snapshot: Snapshot) -> dict[str, object]:
        suggestions = data.get("suggestions")
        reward = data.get("reward")
        affirmation = data.get("affirmation")
        insight = data.get("insight")

        if not isinstance(suggestions, list) or len(suggestions) < 1:
            raise ValueError("AI result missing suggestions list")
        clean_suggestions = [str(item).strip() for item in suggestions if str(item).strip()][:4]
        while len(clean_suggestions) < 4:
            clean_suggestions.append("Take one small step that feels manageable right now.")

        if not isinstance(affirmation, dict):
            raise ValueError("AI result missing affirmation object")

        return {
            "mode": self._safe_mode(snapshot),
            "generation_source": "AI",
            "suggestions": clean_suggestions,
            "reward": str(reward or "Take a short guilt-free break after your next step.").strip(),
            "affirmation": {
                "title": str(affirmation.get("title") or f"Affirmation for {snapshot.mood}").strip(),
                "tags": str(affirmation.get("tags") or f"Encouragement • Tone: {self.db.get_pref('tone', 'Supportive')}").strip(),
                "body": str(affirmation.get("body") or "You can take this one small step at a time.").strip(),
                "note": str(affirmation.get("note") or "A gentle plan still counts as progress.").strip(),
            },
            "insight": str(insight or "Small, realistic actions often help momentum return.").strip(),
        }

    def generate(self, snapshot: Snapshot) -> dict[str, object]:
        if not self.is_enabled():
            return self.fallback_engine.generate(snapshot)

        url = self.db.get_pref("ai_api_url", "").strip()
        key = self.db.get_pref("ai_api_key", "").strip()
        if not url:
            return self.fallback_engine.generate(snapshot)

        payload = self._build_payload(snapshot)
        try:
            response_data = self._post_json(url, key, payload)
            return self._validate_ai_result(response_data, snapshot)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
            return self.fallback_engine.generate(snapshot)


class BaseScreen(ttk.Frame):
    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, padding=18)
        self.app = app

    def on_show(self) -> None:
        pass


class HomeScreen(BaseScreen):
    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="Home", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="A quick, judgment-free way to plan your day around how you feel.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 16))

        top = ttk.Frame(self)
        top.pack(fill="x")

        left = ttk.LabelFrame(top, text="Overview", padding=16)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(
            left,
            text=(
                "This prototype supports mood check-in, suggestions, affirmations, "
                "insights, history, preferences, and optional AI generation."
            ),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        buttons = ttk.Frame(left)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Start check-in", command=lambda: app.show_screen("checkin")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="AI setup tips", command=self.show_ai_help).pack(side="left")

        right = ttk.LabelFrame(top, text="Current snapshot", padding=16)
        right.pack(side="left", fill="both")
        self.snapshot_label = ttk.Label(right, text="", justify="left")
        self.snapshot_label.pack(anchor="w")

    def show_ai_help(self) -> None:
        messagebox.showinfo(
            "AI setup",
            "To use AI, open Preferences and turn on 'Use AI for content'.\n\n"
            "Then provide:\n"
            "• API URL\n"
            "• API Key\n"
            "• Model name\n\n"
            "If the AI call fails, the app automatically falls back to the rule-based engine.",
        )

    def on_show(self) -> None:
        latest = self.app.db.get_latest_entry()
        if not latest:
            self.snapshot_label.configure(text="No check-in yet. Complete one to see your latest snapshot.")
            return
        self.snapshot_label.configure(
            text=(
                f"Mood: {latest['mood']}\n"
                f"Energy: {latest['energy']}\n"
                f"Stress: {latest['stress']}\n"
                f"Focus: {latest['focus']}\n"
                f"Motivation: {latest['motivation']}\n"
                f"Mode: {latest['suggestion_mode']}\n"
                f"Source: {latest['generation_source']}"
            )
        )


class CheckInScreen(BaseScreen):
    EMOJIS = ["😀", "🙂", "😌", "😴", "😣", "🤯", "😕"]

    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="Mood Check-In", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Choose an emoji and rate your current state.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))

        mood_frame = ttk.LabelFrame(self, text="How do you feel?", padding=14)
        mood_frame.pack(fill="x", pady=(0, 12))
        self.selected_mood = tk.StringVar(value="🙂")
        for emoji in self.EMOJIS:
            ttk.Radiobutton(mood_frame, text=emoji, variable=self.selected_mood, value=emoji).pack(side="left", padx=8)

        self.scales: dict[str, tk.IntVar] = {}
        scale_wrap = ttk.LabelFrame(self, text="Sliders", padding=14)
        scale_wrap.pack(fill="x")
        for label, default in [("Energy", 50), ("Stress", 50), ("Focus", 50), ("Motivation", 50)]:
            row = ttk.Frame(scale_wrap)
            row.pack(fill="x", pady=8)
            ttk.Label(row, text=label, width=12).pack(side="left")
            var = tk.IntVar(value=default)
            self.scales[label.lower()] = var
            tk.Scale(
                row,
                from_=0,
                to=100,
                orient="horizontal",
                variable=var,
                length=380,
                resolution=1,
                highlightthickness=0,
            ).pack(side="left", fill="x", expand=True)
            ttk.Label(row, textvariable=var, width=4).pack(side="left", padx=(8, 0))

        actions = ttk.Frame(self)
        actions.pack(anchor="w", pady=16)
        ttk.Button(actions, text="Generate plan", command=self.generate_plan).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Reset", command=self.reset_form).pack(side="left")

    def reset_form(self) -> None:
        self.selected_mood.set("🙂")
        for var in self.scales.values():
            var.set(50)

    def generate_plan(self) -> None:
        snapshot = Snapshot(
            mood=self.selected_mood.get(),
            energy=self.scales["energy"].get(),
            stress=self.scales["stress"].get(),
            focus=self.scales["focus"].get(),
            motivation=self.scales["motivation"].get(),
        )
        result = self.app.content_engine.generate(snapshot)
        self.app.current_snapshot = snapshot
        self.app.current_result = result
        self.app.db.save_entry(
            snapshot=snapshot,
            suggestion_mode=str(result["mode"]),
            generation_source=str(result.get("generation_source", "Rule-based")),
            suggestions=list(result["suggestions"]),
            reward=str(result["reward"]),
            affirmation=dict(result["affirmation"]),
            insight=str(result["insight"]),
        )
        self.app.refresh_header(snapshot)
        self.app.show_screen("suggestions")


class SuggestionsScreen(BaseScreen):
    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="Today's Suggestions", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Personalized ideas based on your check-in.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        self.mode_label = ttk.Label(self, text="", style="Section.TLabel")
        self.mode_label.pack(anchor="w", pady=(0, 10))
        self.source_label = ttk.Label(self, text="", style="Muted.TLabel")
        self.source_label.pack(anchor="w", pady=(0, 10))
        self.listbox = tk.Listbox(self, height=8, width=80)
        self.listbox.pack(fill="x", pady=(0, 12))
        self.reward_label = ttk.Label(self, text="", wraplength=760, justify="left")
        self.reward_label.pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(self)
        actions.pack(anchor="w")
        ttk.Button(actions, text="View affirmation", command=lambda: app.show_screen("affirmations")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="View insight", command=lambda: app.show_screen("insights")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="New check-in", command=lambda: app.show_screen("checkin")).pack(side="left")

    def on_show(self) -> None:
        result = self.app.current_result
        if not result:
            self.mode_label.configure(text="No plan yet. Complete a mood check-in first.")
            self.source_label.configure(text="")
            self.listbox.delete(0, tk.END)
            self.reward_label.configure(text="")
            return
        self.mode_label.configure(text=f"Recommended mode: {result['mode']}")
        self.source_label.configure(text=f"Generated by: {result.get('generation_source', 'Rule-based')}")
        self.listbox.delete(0, tk.END)
        for idx, item in enumerate(result["suggestions"], start=1):
            self.listbox.insert(tk.END, f"{idx}. {item}")
        self.reward_label.configure(text=f"Reward idea: {result['reward']}")


class AffirmationsScreen(BaseScreen):
    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="Affirmations", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Encouragement tailored to how you feel.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        card = ttk.LabelFrame(self, text="Affirmation", padding=16)
        card.pack(fill="x")
        self.tags_label = ttk.Label(card, text="", style="Muted.TLabel")
        self.tags_label.pack(anchor="w")
        self.body_label = ttk.Label(card, text="", wraplength=760, justify="left", style="BodyBold.TLabel")
        self.body_label.pack(anchor="w", pady=(8, 8))
        self.note_label = ttk.Label(card, text="", wraplength=760, justify="left")
        self.note_label.pack(anchor="w")
        actions = ttk.Frame(self)
        actions.pack(anchor="w", pady=16)
        ttk.Button(actions, text="Refresh affirmation", command=self.refresh_affirmation).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Back to plan", command=lambda: app.show_screen("suggestions")).pack(side="left")

    def refresh_affirmation(self) -> None:
        if not self.app.current_snapshot or not self.app.current_result:
            return
        result = self.app.content_engine.generate(self.app.current_snapshot)
        self.app.current_result["affirmation"] = result["affirmation"]
        self.app.current_result["generation_source"] = result.get("generation_source", self.app.current_result.get("generation_source", "Rule-based"))
        self.on_show()

    def on_show(self) -> None:
        result = self.app.current_result
        if not result:
            self.tags_label.configure(text="No affirmation yet.")
            self.body_label.configure(text="")
            self.note_label.configure(text="")
            return
        affirmation = result["affirmation"]
        self.tags_label.configure(text=affirmation["tags"])
        self.body_label.configure(text=affirmation["body"])
        self.note_label.configure(text=f"✦ {affirmation['note']}")


class InsightsScreen(BaseScreen):
    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="Insights & Fun Facts", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Mood-related psychology and wellness facts.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        self.insight_text = ttk.Label(self, text="", wraplength=760, justify="left")
        self.insight_text.pack(anchor="w", pady=(0, 12))
        ttk.Button(self, text="Back to suggestions", command=lambda: app.show_screen("suggestions")).pack(anchor="w")

    def on_show(self) -> None:
        result = self.app.current_result
        if not result:
            self.insight_text.configure(text="No insight yet. Complete a mood check-in first.")
            return
        self.insight_text.configure(text=str(result["insight"]))


class HistoryScreen(BaseScreen):
    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="History & Trends", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Review your recent check-ins and simple trends.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        self.summary = ttk.Label(self, text="", justify="left", wraplength=760)
        self.summary.pack(anchor="w", pady=(0, 12))
        columns = ("date", "mood", "energy", "stress", "focus", "motivation", "mode", "source")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=110 if col not in {"date", "source"} else 150, anchor="center")
        self.tree.pack(fill="both", expand=True)

    def on_show(self) -> None:
        rows = self.app.db.get_recent_entries(limit=20)
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not rows:
            self.summary.configure(text="No mood history yet.")
            return
        energies = [r["energy"] for r in rows]
        stresses = [r["stress"] for r in rows]
        focuses = [r["focus"] for r in rows]
        motivations = [r["motivation"] for r in rows]
        mode_counts = {m: sum(1 for r in rows if r["suggestion_mode"] == m) for m in ["Restore", "Balanced", "Productive"]}
        top_mode = max(mode_counts, key=mode_counts.get)
        ai_count = sum(1 for r in rows if r["generation_source"] == "AI")
        self.summary.configure(
            text=(
                f"Entries: {len(rows)}\n"
                f"Average energy: {mean(energies):.1f}\n"
                f"Average stress: {mean(stresses):.1f}\n"
                f"Average focus: {mean(focuses):.1f}\n"
                f"Average motivation: {mean(motivations):.1f}\n"
                f"Most common mode: {top_mode}\n"
                f"AI-generated entries: {ai_count}"
            )
        )
        for r in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    r["created_at"].replace("T", " "),
                    r["mood"],
                    r["energy"],
                    r["stress"],
                    r["focus"],
                    r["motivation"],
                    r["suggestion_mode"],
                    r["generation_source"],
                ),
            )


class PreferencesScreen(BaseScreen):
    def __init__(self, parent: ttk.Frame, app: "MoodTrackerApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="Preferences", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Control tone, settings, and optional AI generation.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        form = ttk.Frame(self)
        form.pack(anchor="w", fill="x")

        ttk.Label(form, text="Name", width=20).grid(row=0, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky="w")

        ttk.Label(form, text="Affirmation tone", width=20).grid(row=1, column=0, sticky="w", pady=6)
        self.tone_var = tk.StringVar()
        ttk.Combobox(form, textvariable=self.tone_var, values=["Supportive", "Playful", "Direct"], state="readonly", width=27).grid(row=1, column=1, sticky="w")

        ttk.Label(form, text="Notifications", width=20).grid(row=2, column=0, sticky="w", pady=6)
        self.notifications_var = tk.StringVar()
        ttk.Combobox(form, textvariable=self.notifications_var, values=["Off", "Daily reminder", "Evening summary"], state="readonly", width=27).grid(row=2, column=1, sticky="w")

        self.types_vars = {"Productivity": tk.BooleanVar(), "Self-care": tk.BooleanVar(), "Social": tk.BooleanVar()}
        ttk.Label(form, text="Suggestion types", width=20).grid(row=3, column=0, sticky="nw", pady=6)
        type_box = ttk.Frame(form)
        type_box.grid(row=3, column=1, sticky="w")
        for i, (name, var) in enumerate(self.types_vars.items()):
            ttk.Checkbutton(type_box, text=name, variable=var).grid(row=i, column=0, sticky="w")

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=16)
        ttk.Label(self, text="AI Content Settings", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

        ai_form = ttk.Frame(self)
        ai_form.pack(anchor="w", fill="x")
        self.use_ai_var = tk.BooleanVar()
        ttk.Checkbutton(ai_form, text="Use AI for content", variable=self.use_ai_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=6)

        ttk.Label(ai_form, text="API URL", width=20).grid(row=1, column=0, sticky="w", pady=6)
        self.ai_url_var = tk.StringVar()
        ttk.Entry(ai_form, textvariable=self.ai_url_var, width=50).grid(row=1, column=1, sticky="w")

        ttk.Label(ai_form, text="API Key", width=20).grid(row=2, column=0, sticky="w", pady=6)
        self.ai_key_var = tk.StringVar()
        ttk.Entry(ai_form, textvariable=self.ai_key_var, width=50, show="*").grid(row=2, column=1, sticky="w")

        ttk.Label(ai_form, text="Model name", width=20).grid(row=3, column=0, sticky="w", pady=6)
        self.ai_model_var = tk.StringVar()
        ttk.Entry(ai_form, textvariable=self.ai_model_var, width=30).grid(row=3, column=1, sticky="w")

        ttk.Button(self, text="Save preferences", command=self.save_preferences).pack(anchor="w", pady=16)

    def on_show(self) -> None:
        self.name_var.set(self.app.db.get_pref("user_name", ""))
        self.tone_var.set(self.app.db.get_pref("tone", "Supportive"))
        self.notifications_var.set(self.app.db.get_pref("notifications", "Off"))
        selected = json.loads(self.app.db.get_pref("suggestion_types", '["Productivity", "Self-care", "Social"]'))
        for name, var in self.types_vars.items():
            var.set(name in selected)
        self.use_ai_var.set(self.app.db.get_pref("use_ai", "0") == "1")
        self.ai_url_var.set(self.app.db.get_pref("ai_api_url", ""))
        self.ai_key_var.set(self.app.db.get_pref("ai_api_key", ""))
        self.ai_model_var.set(self.app.db.get_pref("ai_model", "mood-support-v1"))

    def save_preferences(self) -> None:
        selected_types = [name for name, var in self.types_vars.items() if var.get()]
        if not selected_types:
            messagebox.showwarning("Preferences", "Please select at least one suggestion type.")
            return
        self.app.db.set_pref("user_name", self.name_var.get().strip())
        self.app.db.set_pref("tone", self.tone_var.get())
        self.app.db.set_pref("notifications", self.notifications_var.get())
        self.app.db.set_pref("suggestion_types", json.dumps(selected_types))
        self.app.db.set_pref("use_ai", "1" if self.use_ai_var.get() else "0")
        self.app.db.set_pref("ai_api_url", self.ai_url_var.get().strip())
        self.app.db.set_pref("ai_api_key", self.ai_key_var.get().strip())
        self.app.db.set_pref("ai_model", self.ai_model_var.get().strip() or "mood-support-v1")
        messagebox.showinfo("Preferences", "Preferences saved.")


class MoodTrackerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Mood → Wellness & Productivity")
        self.geometry("1200x780")
        self.minsize(1080, 700)

        self.db = Database(DB_PATH)
        self.rule_engine = RuleBasedEngine(self.db)
        self.content_engine = AIContentClient(self.db, self.rule_engine)
        self.current_snapshot: Snapshot | None = None
        self.current_result: dict[str, object] | None = None

        self._style_ui()
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        self.sidebar = ttk.Frame(container, padding=16, style="Sidebar.TFrame")
        self.sidebar.pack(side="left", fill="y")
        self.main = ttk.Frame(container, padding=0)
        self.main.pack(side="left", fill="both", expand=True)
        self._build_sidebar()
        self._build_header()
        self.screen_container = ttk.Frame(self.main, padding=0)
        self.screen_container.pack(fill="both", expand=True)
        self.screens: dict[str, BaseScreen] = {}
        self._create_screens()
        self.show_screen("home")

    def _style_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg = "#0b1020"
        card = "#1a2242"
        accent = "#405d9c"
        text = "#edf1ff"
        muted = "#b5bedc"
        self.configure(bg=bg)
        style.configure(".", background=bg, foreground=text, fieldbackground=card)
        style.configure("Sidebar.TFrame", background="#111a34")
        style.configure("Header.TFrame", background="#121a33")
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 12))
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 11))
        style.configure("Title.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 20))
        style.configure("Section.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 14))
        style.configure("BodyBold.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 14))
        style.configure("TButton", padding=10, font=("Segoe UI", 11))
        style.map("TButton", background=[("active", accent)])
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
        style.configure("TLabelframe", background=bg, foreground=text)
        style.configure("TLabelframe.Label", background=bg, foreground=text, font=("Segoe UI Semibold", 12))

    def _build_sidebar(self) -> None:
        ttk.Label(self.sidebar, text="Mood → Wellness &\nProductivity", font=("Segoe UI Semibold", 18), background="#111a34").pack(anchor="w", pady=(8, 6))
        ttk.Label(self.sidebar, text="Desktop prototype with optional AI", background="#111a34", foreground="#b5bedc", font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 18))
        nav_items = [
            ("Home", "home"),
            ("Mood Check-In", "checkin"),
            ("Today's Suggestions", "suggestions"),
            ("Affirmations", "affirmations"),
            ("Insights & Fun Facts", "insights"),
            ("History & Trends", "history"),
            ("Preferences", "preferences"),
        ]
        self.nav_buttons = {}
        for label, key in nav_items:
            btn = ttk.Button(self.sidebar, text=label, command=lambda k=key: self.show_screen(k))
            btn.pack(fill="x", pady=4)
            self.nav_buttons[key] = btn
        ttk.Label(
            self.sidebar,
            text=(
                "\nAI is optional. When enabled, the app tries the API first\n"
                "and falls back to rule-based content if needed."
            ),
            background="#111a34",
            foreground="#b5bedc",
            justify="left",
        ).pack(anchor="w", pady=(18, 0))

    def _build_header(self) -> None:
        header = ttk.Frame(self.main, padding=(18, 14), style="Header.TFrame")
        header.pack(fill="x")
        self.header_title = ttk.Label(header, text="Ready for today's check-in?", background="#121a33", font=("Segoe UI Semibold", 15))
        self.header_title.pack(side="left")
        self.header_metrics = ttk.Label(header, text="Mood: —   Energy: 50   Stress: 50", background="#121a33", foreground="#b5bedc")
        self.header_metrics.pack(side="right")

    def _create_screens(self) -> None:
        mapping = {
            "home": HomeScreen,
            "checkin": CheckInScreen,
            "suggestions": SuggestionsScreen,
            "affirmations": AffirmationsScreen,
            "insights": InsightsScreen,
            "history": HistoryScreen,
            "preferences": PreferencesScreen,
        }
        for key, cls in mapping.items():
            frame = cls(self.screen_container, self)
            self.screens[key] = frame
            frame.grid(row=0, column=0, sticky="nsew")
        self.screen_container.grid_rowconfigure(0, weight=1)
        self.screen_container.grid_columnconfigure(0, weight=1)

    def refresh_header(self, snapshot: Snapshot | None = None) -> None:
        snapshot = snapshot or self.current_snapshot
        if not snapshot:
            self.header_metrics.configure(text="Mood: —   Energy: 50   Stress: 50")
            return
        self.header_metrics.configure(text=f"Mood: {snapshot.mood}   Energy: {snapshot.energy}   Stress: {snapshot.stress}")

    def show_screen(self, key: str) -> None:
        screen = self.screens[key]
        screen.tkraise()
        screen.on_show()
        self.header_title.configure(text=screen.__class__.__name__.replace("Screen", "").replace("CheckIn", "Mood Check-In"))
        for name, btn in self.nav_buttons.items():
            btn.state(["!disabled"])
        self.nav_buttons[key].state(["disabled"])


def main() -> None:
    app = MoodTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

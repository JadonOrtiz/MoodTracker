from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict
import random
import json


# -----------------------------
# Data Models
# -----------------------------

@dataclass
class MoodEntry:
    mood: str
    energy: int        # 1 - 10
    stress: int        # 1 - 10
    focus: int         # 1 - 10
    motivation: int    # 1 - 10
    timestamp: str


# -----------------------------
# Main App Logic
# -----------------------------

class MoodTrackerApp:
    def __init__(self):
        self.history: List[MoodEntry] = []

        self.mood_labels = {
            "😊": "happy",
            "😌": "calm",
            "😴": "tired",
            "😟": "stressed",
            "😔": "sad",
            "😎": "confident",
            "🤩": "excited",
            "😤": "frustrated"
        }

        self.affirmations = {
            "happy": [
                "Keep riding this positive energy.",
                "Your good mood can fuel meaningful progress today.",
                "Celebrate the little wins."
            ],
            "calm": [
                "Peace is productive too.",
                "A steady mind creates steady progress.",
                "You are allowed to move at your own pace."
            ],
            "tired": [
                "Rest is not laziness; it is recovery.",
                "You do not have to do everything at once.",
                "Small progress still counts."
            ],
            "stressed": [
                "Take one thing at a time.",
                "You are doing better than you think.",
                "Pause. Breathe. Reset."
            ],
            "sad": [
                "Be gentle with yourself today.",
                "You are still worthy on hard days.",
                "Even small steps are enough."
            ],
            "confident": [
                "Trust yourself and take action.",
                "You are capable of great work.",
                "Use this momentum wisely."
            ],
            "excited": [
                "Channel your energy into something meaningful.",
                "This is a great moment to create.",
                "Your enthusiasm can take you far today."
            ],
            "frustrated": [
                "It is okay to pause before trying again.",
                "Progress is rarely a straight line.",
                "You can reset and restart."
            ]
        }

        self.fun_facts = [
            "Taking short breaks can improve focus and memory.",
            "Mood tracking can help people notice emotional patterns over time.",
            "A 10-minute walk can boost energy and reduce stress.",
            "Positive self-talk can improve motivation and resilience.",
            "Sleep quality strongly affects mood, focus, and productivity.",
            "Celebrating small wins helps reinforce healthy habits."
        ]

    # -----------------------------
    # Input Validation
    # -----------------------------
    def validate_slider(self, value: int, name: str) -> int:
        if not isinstance(value, int):
            raise TypeError(f"{name} must be an integer.")
        if value < 1 or value > 10:
            raise ValueError(f"{name} must be between 1 and 10.")
        return value

    def validate_mood(self, mood_input: str) -> str:
        mood_input = mood_input.strip().lower()

        # Case 1: user enters emoji
        if mood_input in self.mood_labels:
            return self.mood_labels[mood_input]

        # Case 2: user enters text (like "tired", "happy", etc.)
        if mood_input in self.mood_labels.values():
            return mood_input

        raise ValueError(
            "Invalid mood. Use emoji (😴) or mood name (tired)."
        )

    # -----------------------------
    # Core Function: Daily Check-In
    # -----------------------------
    def log_mood(self, mood_emoji: str, energy: int, stress: int, focus: int, motivation: int) -> MoodEntry:
        mood = self.validate_mood(mood_emoji)
        energy = self.validate_slider(energy, "energy")
        stress = self.validate_slider(stress, "stress")
        focus = self.validate_slider(focus, "focus")
        motivation = self.validate_slider(motivation, "motivation")

        entry = MoodEntry(
            mood=mood,
            energy=energy,
            stress=stress,
            focus=focus,
            motivation=motivation,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        self.history.append(entry)
        return entry

    # -----------------------------
    # Core Function: Personalized Suggestions
    # -----------------------------
    def generate_daily_suggestions(self, entry: MoodEntry) -> List[str]:
        suggestions = []

        if entry.energy <= 3:
            suggestions.append("Choose a light task like organizing notes or replying to one email.")
            suggestions.append("Take a short nap, stretch, or drink water before starting anything demanding.")
        elif entry.energy >= 8:
            suggestions.append("Use your energy for a meaningful task that needs momentum.")
            suggestions.append("This is a good time to start a creative or challenging activity.")

        if entry.stress >= 8:
            suggestions.append("Reduce pressure today: focus on one priority only.")
            suggestions.append("Try a 5-minute breathing break or a short walk.")
        elif entry.stress <= 3:
            suggestions.append("You may be in a good state for planning or focused work.")

        if entry.focus >= 7 and entry.motivation >= 7:
            suggestions.append("Set a 25- to 45-minute focus session and tackle your top goal.")
        elif entry.focus <= 4:
            suggestions.append("Break work into very small steps to make it easier to begin.")
            suggestions.append("Try working in a distraction-free space for 10 minutes.")

        if entry.motivation <= 4:
            suggestions.append("Pick one tiny win for today so progress feels manageable.")
            suggestions.append("Reward yourself after finishing a small task.")

        if entry.mood in ["sad", "stressed", "tired", "frustrated"]:
            suggestions.append("Give yourself permission to rest without guilt if needed.")
        elif entry.mood in ["happy", "confident", "excited", "calm"]:
            suggestions.append("Use this mood to build positive momentum for the day.")

        return suggestions

    # -----------------------------
    # Core Function: Self-Care / Reward Ideas
    # -----------------------------
    def generate_reward_ideas(self, entry: MoodEntry) -> List[str]:
        rewards = []

        if entry.stress >= 7 or entry.mood in ["stressed", "frustrated", "sad"]:
            rewards.extend([
                "Listen to a favorite song.",
                "Take a short walk outside.",
                "Watch one short relaxing video.",
                "Do a 5-minute breathing exercise."
            ])
        elif entry.energy <= 4 or entry.mood == "tired":
            rewards.extend([
                "Take a power break.",
                "Make tea or coffee mindfully.",
                "Stretch for 5 minutes.",
                "Step away from screens briefly."
            ])
        else:
            rewards.extend([
                "Celebrate with a snack or favorite drink.",
                "Journal one thing that went well.",
                "Spend 10 minutes on a hobby.",
                "Share your win with a friend."
            ])

        return rewards

    # -----------------------------
    # Core Function: Affirmations
    # -----------------------------
    def get_affirmation(self, entry: MoodEntry) -> str:
        return random.choice(self.affirmations.get(entry.mood, ["You are doing your best, and that matters."]))

    # -----------------------------
    # Core Function: Mood/Wellness Insight
    # -----------------------------
    def get_fun_fact(self) -> str:
        return random.choice(self.fun_facts)

    # -----------------------------
    # Future Feature: History & Trends
    # -----------------------------
    def get_history(self) -> List[Dict]:
        return [asdict(entry) for entry in self.history]

    def get_summary(self) -> Dict:
        if not self.history:
            return {"message": "No mood entries logged yet."}

        total_entries = len(self.history)
        avg_energy = sum(e.energy for e in self.history) / total_entries
        avg_stress = sum(e.stress for e in self.history) / total_entries
        avg_focus = sum(e.focus for e in self.history) / total_entries
        avg_motivation = sum(e.motivation for e in self.history) / total_entries

        mood_counts = {}
        for entry in self.history:
            mood_counts[entry.mood] = mood_counts.get(entry.mood, 0) + 1

        most_common_mood = max(mood_counts, key=mood_counts.get)

        return {
            "total_entries": total_entries,
            "average_energy": round(avg_energy, 2),
            "average_stress": round(avg_stress, 2),
            "average_focus": round(avg_focus, 2),
            "average_motivation": round(avg_motivation, 2),
            "most_common_mood": most_common_mood
        }

    # -----------------------------
    # Optional: Save / Load Data
    # -----------------------------
    def save_history_to_file(self, filename: str = "mood_history.json") -> None:
        with open(filename, "w") as f:
            json.dump(self.get_history(), f, indent=4)

    def load_history_from_file(self, filename: str = "mood_history.json") -> None:
        try:
            with open(filename, "r") as f:
                data = json.load(f)
                self.history = [MoodEntry(**entry) for entry in data]
        except FileNotFoundError:
            self.history = []


# -----------------------------
# Example Main Program
# -----------------------------
if __name__ == "__main__":
    app = MoodTrackerApp()

    mood_emoji = input("Enter your mood emoji: ")
    energy = int(input("Enter energy level (1-10): "))
    stress = int(input("Enter stress level (1-10): "))
    focus = int(input("Enter focus level (1-10): "))
    motivation = int(input("Enter motivation level (1-10): "))

    entry = app.log_mood(mood_emoji, energy, stress, focus, motivation)

    print("\nMood Entry Logged:")
    print(asdict(entry))

    print("\nDaily Suggestions:")
    for suggestion in app.generate_daily_suggestions(entry):
        print("-", suggestion)

    print("\nReward Ideas:")
    for reward in app.generate_reward_ideas(entry):
        print("-", reward)

    print("\nAffirmation:")
    print(app.get_affirmation(entry))

    print("\nFun Fact:")
    print(app.get_fun_fact())

    print("\nSummary:")
    print(app.get_summary())
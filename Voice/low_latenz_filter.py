import time
from collections import defaultdict


class LowLatencyCommandFilter:

    # Filter gegen Fehltrigger

    def __init__(
        self,
        thresholds=None,
        required_hits=3,
        cooldown_ms=300,
        debug=False
    ):

        self.thresholds = thresholds or {}

        self.required_hits = required_hits

        self.cooldown_ms = cooldown_ms

        self.debug = debug

        self.hit_counter = defaultdict(int)

        self.last_trigger_time = 0

    def reset_hits(self):

        self.hit_counter.clear()

    def process(self, predictions):

        if not predictions:
            return None

        best_command = max(
            predictions,
            key=predictions.get
        )

        best_score = predictions[best_command]

        threshold = self.thresholds.get(
            best_command,
            0.7
        )

        if self.debug:

            print(
                f"[DEBUG] "
                f"{best_command} "
                f"score={best_score}"
            )

        # Schwelle prüfen
        if best_score >= threshold:

            self.hit_counter[best_command] += 1

        else:

            self.hit_counter[best_command] = 0

            return None

        # Andere zurücksetzen
        for cmd in list(self.hit_counter.keys()):

            if cmd != best_command:
                self.hit_counter[cmd] = 0

        # Noch nicht genug Treffer
        if (
            self.hit_counter[best_command]
            < self.required_hits
        ):
            return None

        # Cooldown
        now_ms = int(time.time() * 1000)

        if (
            now_ms - self.last_trigger_time
            < self.cooldown_ms
        ):
            return None

        self.last_trigger_time = now_ms

        self.reset_hits()

        return best_command


class PartialCommandDetector:

    def __init__(
        self,
        command_keywords,
        confidence=0.8,
        required_hits=3,
        cooldown_ms=300,
        debug=False
    ):

        self.command_keywords = command_keywords

        self.filter = LowLatencyCommandFilter(

            thresholds={

                cmd: confidence

                for cmd in command_keywords.keys()
            },

            required_hits=required_hits,

            cooldown_ms=cooldown_ms,

            debug=debug
        )

    def text_to_predictions(self, text):

        text = text.lower().strip()

        predictions = {}

        for command, keywords in (
            self.command_keywords.items()
        ):

            score = 0.0

            for keyword in keywords:

                keyword = keyword.lower()

                if keyword in text:

                    score = 1.0

                    break

            predictions[command] = score

        return predictions

    def process_text(self, text):

        predictions = self.text_to_predictions(text)

        return self.filter.process(predictions)
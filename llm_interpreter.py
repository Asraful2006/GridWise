import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


ALLOWED_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def _no_op(note_index: int, explanation: str) -> dict:
    return {
        "note_index": note_index,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": explanation,
    }


def _validate_directives(data, notes: list[str]) -> list[dict]:
    """
    Validate and normalize the LLM output before sending it
    to the optimization layer.
    """

    if not isinstance(data, list):
        return [
            _no_op(i, "The LLM returned an invalid directive format.")
            for i in range(len(notes))
        ]

    result = []

    for i, note in enumerate(notes):
        # Find the directive corresponding to this note.
        item = None

        for candidate in data:
            if isinstance(candidate, dict):
                if candidate.get("note_index") == i:
                    item = candidate
                    break

        if item is None:
            result.append(
                _no_op(
                    i,
                    "No valid directive was extracted from this note."
                )
            )
            continue

        directive_type = item.get("directive_type")
        applies = bool(item.get("applies", False))
        adjustment = item.get("structured_adjustment")

        if directive_type not in ALLOWED_DIRECTIVE_TYPES:
            result.append(
                _no_op(
                    i,
                    "The extracted directive type was invalid."
                )
            )
            continue

        # Explicit no-op
        if directive_type == "no_op" or not applies:
            result.append(
                _no_op(
                    i,
                    item.get(
                        "explanation",
                        "This note does not affect energy scheduling."
                    ),
                )
            )
            continue

        if not isinstance(adjustment, dict):
            result.append(
                _no_op(
                    i,
                    "The directive did not contain a valid structured adjustment."
                )
            )
            continue

        hours = adjustment.get("hours")

        if not isinstance(hours, list):
            result.append(
                _no_op(
                    i,
                    "The directive did not contain a valid hour list."
                )
            )
            continue

        # Keep only valid integer hours from 0 through 23.
        clean_hours = []

        for h in hours:
            if isinstance(h, int) and 0 <= h <= 23:
                if h not in clean_hours:
                    clean_hours.append(h)

        clean_hours.sort()

        if not clean_hours:
            result.append(
                _no_op(
                    i,
                    "The directive did not contain valid operating hours."
                )
            )
            continue

        normalized = {
            "note_index": i,
            "applies": True,
            "directive_type": directive_type,
            "structured_adjustment": {},
            "explanation": str(
                item.get(
                    "explanation",
                    "Directive extracted from operator note."
                )
            ),
        }

        # -----------------------------
        # Solar reduction
        # -----------------------------
        if directive_type == "solar_reduction":
            factor = adjustment.get("factor")

            if not isinstance(factor, (int, float)):
                result.append(
                    _no_op(
                        i,
                        "Solar reduction factor was invalid."
                    )
                )
                continue

            factor = float(factor)

            if not 0.0 <= factor <= 1.0:
                result.append(
                    _no_op(
                        i,
                        "Solar reduction factor must be between 0 and 1."
                    )
                )
                continue

            normalized["structured_adjustment"] = {
                "hours": clean_hours,
                "factor": factor,
            }

        # -----------------------------
        # Minimum battery reserve
        # -----------------------------
        elif directive_type == "minimum_battery_reserve":
            minimum_energy = adjustment.get("minimum_energy_kwh")

            if not isinstance(minimum_energy, (int, float)):
                result.append(
                    _no_op(
                        i,
                        "Minimum battery reserve value was invalid."
                    )
                )
                continue

            minimum_energy = float(minimum_energy)

            if minimum_energy < 0:
                result.append(
                    _no_op(
                        i,
                        "Minimum battery reserve cannot be negative."
                    )
                )
                continue

            normalized["structured_adjustment"] = {
                "hours": clean_hours,
                "minimum_energy_kwh": minimum_energy,
            }

        # -----------------------------
        # No charge
        # -----------------------------
        elif directive_type == "no_charge_window":
            normalized["structured_adjustment"] = {
                "hours": clean_hours,
            }

        # -----------------------------
        # No discharge
        # -----------------------------
        elif directive_type == "no_discharge_window":
            normalized["structured_adjustment"] = {
                "hours": clean_hours,
            }

        # -----------------------------
        # Maximum grid
        # -----------------------------
        elif directive_type == "max_grid_window":
            max_grid = adjustment.get("max_grid_kwh")

            if not isinstance(max_grid, (int, float)):
                result.append(
                    _no_op(
                        i,
                        "Maximum grid limit was invalid."
                    )
                )
                continue

            max_grid = float(max_grid)

            if max_grid < 0:
                result.append(
                    _no_op(
                        i,
                        "Maximum grid limit cannot be negative."
                    )
                )
                continue

            normalized["structured_adjustment"] = {
                "hours": clean_hours,
                "max_grid_kwh": max_grid,
            }

        result.append(normalized)

    return result


def parse_operator_notes(notes: list[str]) -> list[dict]:
    """
    Convert natural-language operator notes into validated,
    machine-readable energy directives.
    """

    if not notes:
        return []

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return [
            _no_op(
                i,
                "GEMINI_API_KEY is not configured."
            )
            for i in range(len(notes))
        ]

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert Natural Language Understanding system
for a 24-hour campus energy optimization system.

You must interpret each operator note and convert it into
exactly ONE structured directive.

There are exactly six allowed directive types:

1. solar_reduction
   structured_adjustment:
   {{
       "hours": [int, ...],
       "factor": float
   }}

2. minimum_battery_reserve
   structured_adjustment:
   {{
       "hours": [int, ...],
       "minimum_energy_kwh": float
   }}

3. no_charge_window
   structured_adjustment:
   {{
       "hours": [int, ...]
   }}

4. no_discharge_window
   structured_adjustment:
   {{
       "hours": [int, ...]
   }}

5. max_grid_window
   structured_adjustment:
   {{
       "hours": [int, ...],
       "max_grid_kwh": float
   }}

6. no_op
   applies must be false and structured_adjustment must be null.

IMPORTANT TIME RULES:

- The system uses 0-indexed 24-hour time.
- 12 AM = 0
- 1 AM = 1
- ...
- 12 PM = 12
- 1 PM = 13
- ...
- 11 PM = 23

Time ranges are END-EXCLUSIVE.

Therefore:
- "1 PM to 3 PM" = [13, 14]
- "2 PM to 4 PM" = [14, 15]
- "6 PM to 9 PM" = [18, 19, 20]

IMPORTANT SOLAR RULES:

- "solar output will be 20%" means factor = 0.20
- "solar output drops to 20%" means factor = 0.20
- "one-fifth of normal solar output" means factor = 0.20
- "solar output is reduced by 20%" means factor = 0.80
- "solar output drops by 20%" means factor = 0.80
- The factor represents the remaining fraction of normal solar output.

OTHER RULES:

- If a note is unrelated to energy scheduling, classify it as no_op.
- Do not invent values that are not stated or clearly implied.
- Return one object for every input note.
- Preserve the original note order using note_index.
- hours must contain only integers from 0 through 23.
- Output ONLY valid JSON.
- Do not use Markdown.
- Do not add explanations outside the JSON array.

Required output format:

[
  {{
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {{
      "hours": [13, 14],
      "factor": 0.2
    }},
    "explanation": "Solar output is reduced to 20 percent during 1 PM to 3 PM."
  }}
]

Operator notes:

{json.dumps(notes, ensure_ascii=False)}
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )

        raw_text = response.text.strip()

        parsed = json.loads(raw_text)

        return _validate_directives(parsed, notes)

    except Exception as exc:
        print("\n========== GEMINI ERROR ==========")
        print(type(exc).__name__)
        print(str(exc))
        print("==================================\n")

        return [
            _no_op(
                i,
                f"Directive interpretation failed: {type(exc).__name__}: {str(exc)}"
            )
            for i in range(len(notes))
        ]
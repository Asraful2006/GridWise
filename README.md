# GridWise — Smart Energy Optimization

GridWise is an LLM-assisted energy optimization service that converts natural-language operator instructions into structured energy directives and applies them to a 24-hour energy schedule.

The system combines:
- Gemini LLM for interpreting `operator_notes`
- Deterministic validation and guardrails
- PuLP-based mathematical optimization
- FastAPI REST API

## Architecture

Operator Notes
       ↓
Gemini LLM
       ↓
Structured Directive Interpretation
       ↓
Deterministic Guardrails / Validation
       ↓
Directive Application
       ↓
PuLP Optimization
       ↓
24-Hour Energy Plan
       ↓
JSON API Response

## Features

- Natural-language interpretation of operator instructions
- Structured directive output for each operator note
- Deterministic validation before directives affect optimization
- 24-hour energy scheduling
- Grid, solar and battery optimization
- Battery constraints and operating limits
- Energy cost optimization
- REST API using FastAPI
- Health/readiness endpoint

## Technology Stack

- Python
- FastAPI
- Uvicorn
- Pydantic
- Google Gemini API (`google-genai`)
- PuLP
- python-dotenv

## LLM Provider

Provider: Google Gemini

The Gemini model is used specifically to interpret `operator_notes` into structured directive information that is consumed by the optimization pipeline.

The API credential is provided through an environment variable and is not included in the repository.

## Environment Variables

Create a `.env` file locally:

```env
GEMINI_API_KEY=your_gemini_api_key
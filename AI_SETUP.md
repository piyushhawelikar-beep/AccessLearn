# AccessLearn AI Setup

AccessLearn now uses AI-first logic:

1. OpenAI / ChatGPT first
2. Gemini backup
3. Local fallback only if both APIs fail

## Local setup

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
SECRET_KEY=accesslearn-secret-change-this
```

You can use only OpenAI if you want. Gemini is optional backup.

Install dependencies:

```powershell
pip install -r requirements.txt
python app.py
```

## Railway setup

Railway → Project → Variables → add:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
SECRET_KEY=accesslearn-secret-change-this
```

Start command:

```text
gunicorn app:app
```

## What AI is used for

- Chatbot answers general and educational questions.
- Chatbot can analyze selected teacher notes and answer using them as context.
- Summarizer understands notes and creates structured revision notes.
- Quiz generator creates topic-specific MCQs with answer explanations.

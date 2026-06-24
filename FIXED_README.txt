AccessLearn Readability + AI Debug Fix

What was fixed:
1. Chatbot AI prompt now forces structured headings, numbering, and bullet points.
2. CSS now preserves line breaks in chatbot and summarizer output.
3. Link reader now ignores example.com placeholder and uses a browser-like User-Agent.
4. Terminal now prints whether OpenAI, Gemini, or Local fallback is used.

Important:
- If terminal prints "AccessLearn AI: Local fallback used", API key is not working or missing.
- Add GEMINI_API_KEY or OPENAI_API_KEY in .env and restart app.
- Scanned/image PDFs cannot be read by PyPDF2. Use text-based PDFs or paste text.

"""
extractor.py — Structured data extraction via Google Gemini API (free tier).

Fields extracted match the CNICA-style card template:
  - headline       : Bold case headline (the main descriptive title)
  - case_name      : Petitioner vs Respondent
  - case_citation  : Case number / citation (e.g. O.P.(Com.Div.) No.603 of 2022)
  - case_date      : Date of judgment (DD.MM.YYYY format)
  - court          : Full court name (used internally, not on card)

Anti-hallucination: Temperature=0, strict grounding prompt, JSON-only output.
"""

import json
import re
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"
EXPECTED_FIELDS = ["headline", "case_name", "case_citation", "case_date", "court", "summary"]


def configure_gemini(api_key: str):
    genai.configure(api_key=api_key)


def build_extraction_prompt(article_text: str) -> str:
    truncated = article_text[:12000]

    return f"""You are a legal information extraction assistant. Extract ONLY what is explicitly stated in the article.

STRICT RULES:
1. Use ONLY information from the article text. Do NOT invent, infer, or add any details.
2. If a field is not clearly present, return exactly: "Not specified"
3. Return ONLY valid JSON. No markdown. No code blocks. No preamble.
4. For the headline: write a descriptive title summarizing the key legal ruling, as seen in legal publications.
   Example style: "One Biased Arbitrator Taints the Entire Tribunal: Madras High Court Sets Aside Award Applying the 'Poisoning the Well' Doctrine."
5. For case_date: format as DD.MM.YYYY. If only day and month are mentioned, infer the year from the article's publication context. If no date is mentioned at all, return "Not specified"
6. For case_citation: include the full case number / petition number (e.g. "Arbitration O.P.(Com.Div.) No.603 of 2022")
7. For summary: write a plain-English summary of the case and ruling in 5-6 sentences. Cover what the dispute was about, what the court held, and why it matters.

ARTICLE TEXT:
\"\"\"
{truncated}
\"\"\"

Return this exact JSON:
{{
  "headline": "Descriptive headline summarizing the legal ruling (can be 2 sentences, match legal publication style)",
  "case_name": "Petitioner Name Vs. Respondent Name",
  "case_citation": "Full case number / citation as in the article",
  "case_date": "DD.MM.YYYY",
  "court": "Full court name",
  "summary": "5-6 sentence plain-English summary covering the dispute, the court's holding, and its significance"
}}

Return ONLY the JSON. Nothing else."""


def extract_structured_data(article_text: str, api_key: str) -> dict:
    """
    Returns dict with keys: headline, case_name, case_citation, case_date, court,
                             error (None if success), raw_response (for debug)
    """
    result = {field: "Not specified" for field in EXPECTED_FIELDS}
    result["error"] = None
    result["raw_response"] = ""

    if not article_text or len(article_text) < 100:
        result["error"] = "Article text too short for extraction."
        return result

    try:
        configure_gemini(api_key)
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                max_output_tokens=4096,
            ),
        )
    except Exception as e:
        result["error"] = f"Gemini init failed: {str(e)}"
        return result

    try:
        response = model.generate_content(build_extraction_prompt(article_text))
        raw_text = response.text.strip()
        result["raw_response"] = raw_text
    except Exception as e:
        result["error"] = f"Gemini API call failed: {str(e)}"
        return result

    # Strip markdown fences if Gemini adds them
    raw_text = re.sub(r"```(?:json)?", "", raw_text).strip().strip("`")

    # Extract the first {...} block in case there's surrounding text
    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if json_match:
        raw_text = json_match.group(0)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        result["error"] = f"Malformed JSON from Gemini: {str(e)}"
        return result

    for field in EXPECTED_FIELDS:
        val = parsed.get(field, "Not specified")
        result[field] = str(val).strip() if val else "Not specified"

    logger.info("Extraction successful.")
    return result

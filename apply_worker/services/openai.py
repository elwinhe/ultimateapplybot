import logging
import json
from openai import OpenAI
import config

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be configured in .env")
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.prompt = """
        Analyze the following job description and extract these details:
        1. "job_title": The specific job title (e.g., "Software Engineer, Frontend").
        2. "seniority": The seniority level (e.g., "Intern", "Entry-Level", "Mid-Level", "Senior", "Staff").
        3. "technologies": A comma-separated string of key technologies mentioned (e.g., "Python, React, AWS, Docker").

        Return the output as a single, minified JSON object with no extra formatting.
        Example: {"job_title":"Senior Software Engineer","seniority":"Senior","technologies":"Go, Python, Kubernetes"}
        """
        self.answer_prompt = """
        You are a helpful AI assistant helping a candidate apply for a job.
        Given the context of a full job description, a specific question from the application form, and page detailing the applicant's achievements and experience,
        generate a concise and professional answer. The answer length should be based on the context of the job description. Be sure to follow the word limits if specified, if not keep it concise to 100 words or less.
        Directly answer the question. Do not add any conversational fluff or introductory phrases like "Certainly, here's an answer:".
        """

    def categorize_job_description(self, description: str) -> dict:
        logger.info("Sending job description to OpenAI for categorization...")
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.prompt},
                    {"role": "user", "content": description}
                ],
                temperature=0,
            )
            result_text = response.choices[0].message.content
            logger.info(f"Received categorization from OpenAI: {result_text}")
            return json.loads(result_text)
        except Exception as e:
            logger.error(f"Failed to categorize job description: {e}")
            return {}

    def generate_custom_answer(self, question: str, job_description: str, applicant_details: str) -> str:
        logger.info(f"Generating answer for custom question: '{question[:50]}...'")
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.answer_prompt},
                    {"role": "user", "content": f"THE JOB DESCRIPTION:\n{job_description}\n\nTHE QUESTION TO ANSWER:\n{question}\n\nTHE APPLICANT DETAILS:\n{applicant_details}"}
                ],
                temperature=0.5,
            )
            answer = response.choices[0].message.content
            logger.info(f"Generated answer: '{answer[:50]}...'")
            return answer
        except Exception as e:
            logger.error(f"Failed to generate custom answer: {e}")
            return ""
        
    """
    Todo: generate cover letter given job description and applicant details (resume, linkedin) and save it to pdf file locally
    
    def generate_cover_letter(self, job_description: str, applicant_details: dict) -> str:
        logger.info("Generating cover letter...")
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.cover_letter_prompt},
                    {"role": "user", "content": job_description}
                ],
                temperature=0.6,
            )
            result_text = response.choices[0].message.content
            logger.info(f"Received cover letter from OpenAI: {result_text}")
            return result_text
        except Exception as e:
            logger.error(f"Failed to generate cover letter: {e}")
            return ""
    """
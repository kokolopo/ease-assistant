from fastapi import FastAPI

from model import Question, Answer, QuestionAnswer

from assistant import MindsDBService

from dotenv import load_dotenv
import os

load_dotenv()

MINDSD_HOST = os.getenv("MINDS_HOST")
MINDSD_AGENT = os.getenv("MINDS_AGENT")
app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/conversation", response_model=QuestionAnswer)
async def conversation(question: Question):
    mindsdb_service = MindsDBService(host=MINDSD_HOST)

    pertanyaan = question.question
    nama_agent = MINDSD_AGENT

    jawaban = mindsdb_service.get_answer_from_agent(nama_agent, pertanyaan)

    return QuestionAnswer(question=pertanyaan, answer=jawaban)
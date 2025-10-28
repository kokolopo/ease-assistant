from pydantic import BaseModel, Field

class Question(BaseModel):
    question: str = Field(..., description="The question to be answered")

class Answer(BaseModel):
    answer: str = Field(..., description="The answer to the question")

class QuestionAnswer(BaseModel):
    question: str = Field(..., description="The question to be answered")
    answer: str = Field(..., description="The answer to the question")
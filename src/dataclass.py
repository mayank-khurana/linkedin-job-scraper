from pydantic import BaseModel

class HiringPost(BaseModel):
    classification: int
    
class NamesClassification(BaseModel):
    classification: int
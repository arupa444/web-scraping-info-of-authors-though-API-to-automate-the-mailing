from fastapi import FastAPI, Path, HTTPException, Query
from fastapi.responses import JSONResponse
import json
from pydantic import BaseModel, Field, field_validator, computed_field, AnyUrl, EmailStr
from typing import Annotated, Literal, Optional, List, Dict

from google import genai
from groq import Groq
import os
import httpx
import re
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()


class PulsusInputStr(BaseModel):



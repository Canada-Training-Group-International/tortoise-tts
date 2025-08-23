from dotenv import load_dotenv
import os

# Load variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))  # Explicit load

# Access them
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_REGION = os.getenv("S3_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
S3_ACL = os.getenv("S3_ACL")


"""
===============================================================================
 FastAPI Audio Generation API for Storybook
-------------------------------------------------------------------------------
 This API provides endpoints to generate speech audio files from text using
 the Tortoise TTS (Text-to-Speech) model. The generated audio is stored in an
 Lightsail Object Storage.

 Key Features:
 - Accepts text input along with metadata (chapter/page, number, and voice).
 - Uses Tortoise TTS to synthesize speech audio.
 - Uploads the generated audio directly to an S3 bucket.
 - Automatically creates the "audios" folder in S3 if it does not exist.
 - Returns the public S3 URL for the uploaded audio file.

 Dependencies:
 - FastAPI (API framework)
 - boto3 (AWS S3 interaction)
 - torchaudio (for saving audio tensors as .wav)
 - Tortoise TTS (text-to-speech model)
 - pydantic (request validation)
===============================================================================
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os
sys.path.append(os.path.dirname(__file__))
import boto3
import io
import uuid
import torchaudio
import logging
from tortoise.api import TextToSpeech
from tortoise.utils.audio import load_voice
from botocore.exceptions import BotoCoreError, ClientError
import s3Config  # your S3 config module
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# ------------------------------------------------------------------------------
# Request body model
# ------------------------------------------------------------------------------
class AudioRequest(BaseModel):
    s3_path: str  # Format: s3://bucket/folder
    text: str
    type: str  # "chapter" or "page"
    number: int
    voice: str = 'random'

# ------------------------------------------------------------------------------
# Function: Generate audio from text using Tortoise TTS
# ------------------------------------------------------------------------------
def generate_audio(text, voice='random'):
    try:
        tts = TextToSpeech()
        voice_samples, conditioning_latents = load_voice(voice)
        audio = tts.tts_with_preset(text, voice_samples=voice_samples, conditioning_latents=conditioning_latents, preset='fast')
        return audio
    except Exception as e:
        logging.error(f"Audio generation failed: {e}")
        raise

# ------------------------------------------------------------------------------
# Function: Upload audio file to S3
# Save audio tensor to WAV in memory and upload directly to S3 at the given path.
# Returns the public URL of the uploaded file.
# ------------------------------------------------------------------------------
def upload_audio_to_s3(audio, bucket_name, s3_key):
    
    # Setup S3 client with config values
    s3_params = {"region_name": s3Config.S3_REGION}
    if getattr(s3Config, "S3_ENDPOINT_URL", None):
        s3_params["endpoint_url"] = s3Config.S3_ENDPOINT_URL
    if getattr(s3Config, "AWS_ACCESS_KEY_ID", None) and getattr(s3Config, "AWS_SECRET_ACCESS_KEY", None):
        s3_params["aws_access_key_id"] = s3Config.AWS_ACCESS_KEY_ID
        s3_params["aws_secret_access_key"] = s3Config.AWS_SECRET_ACCESS_KEY

    s3 = boto3.client("s3", **s3_params)

    try:
        # Write audio to buffer as WAV
        buffer = io.BytesIO()
        torchaudio.save(
            buffer,
            audio.squeeze(0).cpu(),
            sample_rate=24000,
            format="wav"
        )
        buffer.seek(0)

        # Log buffer size before uploading
        size = buffer.getbuffer().nbytes
        logging.info(f"Prepared audio buffer size: {size} bytes")

        if size == 0:
            raise RuntimeError("Audio buffer is empty — audio generation or save failed.")

        # Upload buffer contents to S3
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=buffer,
            ACL="public-read",
            ContentType="audio/wav"
        )

        # Construct public URL based on config
        if getattr(s3Config, "S3_ENDPOINT_URL", None):
            base_url = s3Config.S3_ENDPOINT_URL.rstrip("/")
            url = f"{base_url}/{bucket_name}/{s3_key}"
        else:
            # fallback to standard AWS S3 URL
            url = f"https://{bucket_name}.s3.{s3Config.S3_REGION}.amazonaws.com/{s3_key}"

        return url

    except (BotoCoreError, ClientError) as e:
        logging.error(f"S3 upload failed: {e}")
        raise


# ------------------------------------------------------------------------------
# Helper Function: Parse S3 path into bucket and folder prefix
# ------------------------------------------------------------------------------
def parse_s3_path(s3_path):
    if not s3_path.startswith("s3://"):
        raise ValueError("Invalid S3 path format. Expected format: s3://bucket-name/path")
    parts = s3_path[5:].split('/', 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ''
    return bucket, prefix.rstrip('/')

# ------------------------------------------------------------------------------
# Helper Function: Ensure "audios" folder exists in S3
# ------------------------------------------------------------------------------
def ensure_audio_folder_exists(bucket, prefix):
    """
    Ensure that the given folder path exists in S3.
    If it doesn’t exist, create it by uploading a placeholder file (.keep).
    """
    s3 = boto3.client(
        "s3",
        region_name=s3Config.S3_REGION,
        aws_access_key_id=s3Config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=s3Config.AWS_SECRET_ACCESS_KEY
    )
    
     # Folder we want
    audios_prefix = f"{prefix.rstrip('/')}"
    
    try:
        # Check if the folder exists
        try:
            response = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=audios_prefix,
                MaxKeys=1
            )
            exists = 'Contents' in response
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                exists = False
                print(prefix, " Doesn't exist");
                response = {} # ensure response exists
            else:
                raise
        
        # Create folder if it does not exist
        if not exists:  
            # Folder doesn't exist — create it by putting an empty key
            dummy_key = audios_prefix + "/.keep"
            s3.put_object(Bucket=bucket, Key=dummy_key, Body=b'', ACL='public-read')
            print(f"Created folder: {audios_prefix}")
        else:
            print(f"Folder already exists: {audios_prefix}")

    except Exception:
        logging.error("Exception while checking/creating folder:")
        logging.error(traceback.format_exc())
        raise

# ------------------------------------------------------------------------------
# API Endpoint: Generate Audio
# ------------------------------------------------------------------------------
@app.post("/generate-audio")
def generate_audio_api(request: AudioRequest):
    """
    API endpoint to generate audio for a given text and upload it to S3.
    Request must include:
    - s3_path: Target S3 folder path (e.g., s3://bucket/folder)
    - text: Text to be converted into audio
    - type: "chapter" or "page"
    - number: Chapter/page number
    - voice: Voice name (optional, default = random)

    Returns:
    - status: "success"
    - s3_url: Public URL of uploaded audio file
    """
    
    try:
        # Parse bucket and folder path
        bucket, folder = parse_s3_path(request.s3_path)
        audio_dir = folder + "/audios"

        # Ensure the audios folder exists
        ensure_audio_folder_exists(bucket, audio_dir)
    
        # Determine filename based on type
        if request.type == "chapter":
            audio_filename = f"chapter_{request.number}.wav"
        elif request.type == "page":
            audio_filename = f"page_{request.number}.wav"
        else:
            raise ValueError("Invalid type. Must be 'chapter' or 'page'.")

        # Construct S3 key
        s3_key = f"{audio_dir}/{audio_filename}"

        logging.info(f"Generating audio for {request.type} {request.number} using voice: {request.voice}")
        audio = generate_audio(request.text, request.voice)

        logging.info(f"Uploading to S3: {s3_key}")
        s3_url = upload_audio_to_s3(audio, bucket, s3_key)

        return {"status": "success", "s3_url": s3_url}
        
    except Exception as e:
        logging.error(f"Process failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

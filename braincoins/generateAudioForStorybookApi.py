from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os
sys.path.append(os.path.dirname(__file__))
import boto3
import uuid
# import torchaudio
import logging
# from tortoise.api import TextToSpeech
# from tortoise.utils.audio import load_voice
from botocore.exceptions import BotoCoreError, ClientError
import s3Config  # your S3 config module
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)

app = FastAPI()


# Request body model
class AudioRequest(BaseModel):
    s3_path: str  # Format: s3://bucket/folder
    text: str
    type: str  # "chapter" or "page"
    number: int
    voice: str = 'random'


def generate_audio(text, voice='random'):
    try:
        tts = TextToSpeech()
        voice_samples, conditioning_latents = load_voice(voice)
        audio = tts.tts_with_preset(text, voice_samples=voice_samples, conditioning_latents=conditioning_latents, preset='fast')
        return audio
    except Exception as e:
        logging.error(f"Audio generation failed: {e}")
        raise


def save_audio_locally(audio, local_path):
    try:
        torchaudio.save(local_path, audio.squeeze(0).cpu(), 24000)
    except Exception as e:
        logging.error(f"Saving audio failed: {e}")
        raise


def upload_to_s3(local_path, bucket_name, s3_key):
    s3_params = {
        "region_name": s3Config.S3_REGION
    }

    if s3Config.S3_ENDPOINT_URL:
        s3_params["endpoint_url"] = s3Config.S3_ENDPOINT_URL
    if s3Config.AWS_ACCESS_KEY_ID and s3Config.AWS_SECRET_ACCESS_KEY:
        s3_params["aws_access_key_id"] = s3Config.AWS_ACCESS_KEY_ID
        s3_params["aws_secret_access_key"] = s3Config.AWS_SECRET_ACCESS_KEY

    s3 = boto3.client("s3", **s3_params)

    try:
        s3.upload_file(local_path, bucket_name, s3_key, ExtraArgs={"ACL": s3Config.S3_ACL})
        url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
        return url
    except (BotoCoreError, ClientError) as e:
        logging.error(f"S3 upload failed: {e}")
        raise


def parse_s3_path(s3_path):
    if not s3_path.startswith("s3://"):
        raise ValueError("Invalid S3 path format. Expected format: s3://bucket-name/path")
    parts = s3_path[5:].split('/', 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ''
    return bucket, prefix.rstrip('/')


def ensure_audio_folder_exists(bucket, prefix):
    """
    If folder 'prefix/' does not exist in Lightsail S3, create it by uploading an empty object with that prefix.
    """
    s3 = boto3.client(
        "s3",
        region_name=s3Config.S3_REGION,
        endpoint_url=s3Config.S3_ENDPOINT_URL,
        aws_access_key_id=s3Config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=s3Config.AWS_SECRET_ACCESS_KEY
    )
    
     # Folder we want
    audios_prefix = f"{prefix.rstrip('/')}"
    print("Prefix =================================>", audios_prefix);
    
    try:
        try:
            # response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix + "/")
            # key_count = response.get('KeyCount', 0)
            
            # Check if folder exists
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
                # key_count = 0
                response = {} # ensure response exists
            else:
                raise

        # if key_count == 0:
        #     dummy_key = prefix + "/.keep"
        #     s3.put_object(Bucket=bucket, Key=dummy_key, Body=b'', ACL=s3Config.S3_ACL)
        #     logging.info(f"Created dummy file to simulate folder at '{dummy_key}'")
        # else:
        #     logging.info(f"Folder '{prefix}/' already exists.")
        
        if not exists:  
            # Folder doesn't exist — create it by putting an empty key
            print("Create ---------------------------------------->",audios_prefix);
            s3.put_object(Bucket=bucket, Key=audios_prefix)
            print(f"Created folder: {audios_prefix}")
        else:
            print(f"Folder already exists: {audios_prefix}")

    except Exception:
        logging.error("Exception while checking/creating folder:")
        logging.error(traceback.format_exc())
        raise



@app.post("/generate-audio")
def generate_audio_api(request: AudioRequest):
    try:
        bucket, folder = parse_s3_path(request.s3_path)
        audio_dir = folder + "/audios"
        # print("S3Config =====> ", s3Config.S3_ENDPOINT_URL)
        
        # Build S3 client
        s3_params = {
            "region_name": s3Config.S3_REGION
        }
        if s3Config.S3_ENDPOINT_URL:
            s3_params["endpoint_url"] = s3Config.S3_ENDPOINT_URL
        if s3Config.AWS_ACCESS_KEY_ID and s3Config.AWS_SECRET_ACCESS_KEY:
            s3_params["aws_access_key_id"] = s3Config.AWS_ACCESS_KEY_ID
            s3_params["aws_secret_access_key"] = s3Config.AWS_SECRET_ACCESS_KEY
        s3_client = boto3.client("s3", **s3_params)

        # Ensure the audios folder exists
        ensure_audio_folder_exists(bucket, audio_dir)
        
        return {"audio_dir": audio_dir};
    
        if request.type == "chapter":
            audio_filename = f"chapter_{request.number}.wav"
        elif request.type == "page":
            audio_filename = f"page_{request.number}.wav"
        else:
            raise ValueError("Invalid type. Must be 'chapter' or 'page'.")

        s3_key = f"{audio_dir}/{audio_filename}"
        os.makedirs("/tmp", exist_ok=True)
        tmp_audio_path = os.path.join("/tmp", audio_filename)
        
        

        logging.info(f"Generating audio for {request.type} {request.number} using voice: {request.voice}")
        """audio = generate_audio(request.text, request.voice)

        logging.info("Saving audio locally...")
        save_audio_locally(audio, tmp_audio_path)

        logging.info(f"Uploading to S3: {s3_key}")
        s3_url = upload_to_s3(tmp_audio_path, bucket, s3_key)

        return {"status": "success", "s3_url": s3_url}
        """
    except Exception as e:
        logging.error(f"Process failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

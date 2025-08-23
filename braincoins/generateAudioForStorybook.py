import argparse
import os
import boto3
import uuid
import torchaudio
from botocore.exceptions import BotoCoreError, ClientError
from tortoise.api import TextToSpeech
from tortoise.utils.audio import load_voice
import logging

import s3Config  # Import s3 config module

# Configure logging
logging.basicConfig(level=logging.INFO)

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
    # Example: s3://my-bucket/folder/subfolder
    if not s3_path.startswith("s3://"):
        raise ValueError("Invalid S3 path format. Expected format: s3://bucket-name/path")
    parts = s3_path[5:].split('/', 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ''
    return bucket, prefix.rstrip('/')

def main():
    parser = argparse.ArgumentParser(description="Generate and upload audio from text using Tortoise TTS.")
    parser.add_argument('--s3_path', required=True, help="S3 folder path to upload audio. Format: s3://bucket/folder (e.g., s3://reading-library/dev/aura_story_5-6)")
    parser.add_argument('--text', required=True, help="Story page text or chapter title to convert into audio.")
    parser.add_argument('--type', required=True, choices=["chapter", "page"], help="Specify if it's a chapter or a page.")
    parser.add_argument('--number', required=True, help="Chapter number or Page number.")
    parser.add_argument('--voice', default='random', help="Voice to use (default: random)")
    args = parser.parse_args()

    try:
        bucket, folder = parse_s3_path(args.s3_path)
        audio_dir = folder + "/audios"

        # Generate audio filename based on type and number
        if args.type == "chapter":
            audio_filename = f"chapter_{args.number}.wav"
        elif args.type == "page":
            audio_filename = f"page_{args.number}.wav"
        else:
            raise ValueError("Invalid type provided. Must be 'chapter' or 'page'.")

        s3_key = f"{audio_dir}/{audio_filename}"
        os.makedirs("/tmp", exist_ok=True)
        tmp_audio_path = os.path.join("/tmp", audio_filename)

        logging.info(f"Generating audio for {args.type} {args.number} using voice: {args.voice}")
        audio = generate_audio(args.text, args.voice)

        logging.info("Saving audio locally...")
        save_audio_locally(audio, tmp_audio_path)

        logging.info(f"Uploading to S3: {s3_key}")
        s3_url = upload_to_s3(tmp_audio_path, bucket, s3_key)

        print(s3_url)
    except Exception as e:
        logging.error(f"Process failed: {e}")
        print("ERROR:" + str(e))
        exit(1)


if __name__ == '__main__':
    main()

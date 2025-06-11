import sys
import logging
import boto3
import json
import os
from app import background_video_generation, get_youtube_references, get_article_references  

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET", "compre-gen-vid")
if not S3_BUCKET:
    logger.error("S3_BUCKET environment variable not set")
    sys.exit(1)

if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            logger.error("No prompt key provided. Usage: worker.py <prompt_key>")
            sys.exit(1)
        prompt_key = sys.argv[1]
        logger.info(f"Received prompt key: {prompt_key}")
        
        # Retrieve prompt from S3
        s3_client = boto3.client("s3")
        logger.info(f"Fetching prompt from s3://{S3_BUCKET}/{prompt_key}")
        try:
            prompt_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=prompt_key)
            prompt = prompt_obj["Body"].read().decode("utf-8")
            logger.info(f"Prompt retrieved: {prompt[:100]}")
        except s3_client.exceptions.NoSuchKey:
            logger.error(f"S3 object not found: s3://{S3_BUCKET}/{prompt_key}")
            sys.exit(1)

        # Call background_video_generation
        logger.info("Running background video generation...")
        video_key, video_url = background_video_generation(prompt)
        logger.info("Background video generation completed: video_key=%s, video_url=%s", video_key, video_url)

        if video_key is None or video_url is None:
            logger.error("Video generation failed: video_key or video_url is None")
            sys.exit(1)

        # Fetch references
        logger.info("Fetching YouTube references...")
        youtube_refs = get_youtube_references(prompt)
        logger.info("YouTube references fetched: %s", youtube_refs)

        logger.info("Fetching article references...")
        article_refs = get_article_references(prompt)
        logger.info("Article references fetched: %s", article_refs)

        # Build JSON response
        logger.info("Building JSON response...")
        response = {
            "resources": {
                "video": {"title": f"Explanation: {prompt[:50]}", "url": video_url},
                "ref_videos": youtube_refs,
                "ref_articles": article_refs
            }
        }
        logger.info("JSON response built: %s", str(response)[:500])

        # Serialize JSON
        logger.info("Serializing JSON...")
        json_body = json.dumps(response, ensure_ascii=False)
        logger.info("JSON serialized: %s", json_body[:500])

        # Upload JSON to S3
        json_key = f"{video_key}.json"
        logger.info("Uploading JSON to s3://%s/%s", S3_BUCKET, json_key)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=json_key,
            Body=json_body.encode("utf-8"),
            ContentType="application/json"
        )
        logger.info("JSON uploaded to S3: %s", json_key)

        logger.info("Job completed successfully")
        sys.exit(0)
    except Exception as e:
        logger.error("Error in worker script: %s", str(e), exc_info=True)
        sys.exit(1)
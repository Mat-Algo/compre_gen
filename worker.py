import sys
import logging
import boto3
import json
import os
from app import background_video_generation, get_youtube_references, get_article_references  

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# S3 configuration
S3_BUCKET = os.getenv("S3_BUCKET", "compre-gen-vid")
if not S3_BUCKET:
    logger.error("S3_BUCKET environment variable not set")
    sys.exit(1)

if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            logger.error("No prompt provided. Usage: worker.py <prompt>")
            sys.exit(1)
        prompt = sys.argv[1]
        logger.info("Cloud Run job started with prompt: %s", prompt)

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
        s3 = boto3.client("s3")
        json_key = f"{video_key}.json"
        logger.info("Uploading JSON to s3://%s/%s", S3_BUCKET, json_key)
        s3.put_object(
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
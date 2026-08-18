#!/bin/sh
set -eu

RECORDINGS_DIR="/seed/listening-recordings"

# Audio is developer-provided and intentionally not baked into the image. A
# checkout without recordings should still start; Listening remains unavailable
# until the files are supplied. When they are present, every LocalStack restart
# reconstructs the 16 section objects instead of silently emptying the bucket.
if ! find "$RECORDINGS_DIR" -maxdepth 1 -type f -name 'Academic * Test *.mp3' -print -quit \
    | grep -q .; then
    echo "Listening audio seed skipped: no Academic <book> Test <n>.mp3 recordings"
    printf 'no-recordings' \
        | awslocal s3 cp - s3://goa-exam-audio/.listening-seed-ready >/dev/null
    exit 0
fi

AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}" \
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}" \
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
python /seed/upload_listening_audio.py \
    "$RECORDINGS_DIR" \
    --split-raw \
    --bucket goa-exam-audio \
    --endpoint-url http://localhost:4566 \
    --create-bucket

if [ -f "$RECORDINGS_DIR/test_2.png" ]; then
    awslocal s3 cp \
        "$RECORDINGS_DIR/test_2.png" \
        s3://goa-writing-files/listening/IELTS15/test2/minster-park.png \
        --content-type image/png >/dev/null
fi

if [ -f "$RECORDINGS_DIR/test_4.png" ]; then
    awslocal s3 cp \
        "$RECORDINGS_DIR/test_4.png" \
        s3://goa-writing-files/listening/IELTS15/test4/croft-valley-park.png \
        --content-type image/png >/dev/null
fi

printf 'ready' \
    | awslocal s3 cp - s3://goa-exam-audio/.listening-seed-ready >/dev/null

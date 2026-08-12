import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://goa:goa_pass@localhost:5432/exam_test"
)
os.environ["INTERNAL_API_KEY"] = "test-internal-key"
os.environ.setdefault("SPEAKING_SERVICE_URL", "http://test-speaking")
os.environ.setdefault("WRITING_SERVICE_URL", "http://test-writing")

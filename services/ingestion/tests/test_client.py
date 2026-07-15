import pytest
import requests

from client import upsert_visa_requirement, upsert_program_requirement, upsert_scholarship_program
from config import settings

SAMPLE_RECORD = {
    "country": "Germany",
    "visa_type": "Student Visa (National Visa - Type D)",
    "issuing_body": "German Embassy Cairo",
    "requirements": {"items": ["Valid passport", "APS certificate"]},
    "proof_of_funds": {"amount_eur": 11208.0},
    "source_url": "https://kairo.diplo.de",
    "processing_days_min": 15,
    "processing_days_max": 20,
    "notes": None,
    "content_hash": "abc123",
    "egyptian_specific": True,
}

SAMPLE_PROGRAM_REQUIREMENT_RECORD = {
    "university": "Technical University Munich",
    "country": "Germany",
    "degree_level": "Master",
    "min_ects": 120,
    "min_gpa": 3.0,
    "min_ielts": 6.5,
    "required_citizenship": None,
    "min_work_experience": 0,
    "source_url": "https://www.mastersportal.com/universities/123/technical-university-munich.html",
    "content_hash": "prog-hash-123",
}

SAMPLE_SCHOLARSHIP_PROGRAM_RECORD = {
    "name": "Chevening Scholarship",
    "provider": "Chevening",
    "source_url": "https://www.chevening.org/scholarships/who-can-apply/",
    "country": "UK",
    "degree_level": "Master",
    "award_amount": "Full tuition, monthly stipend, economy return airfare",
    "deadline": "2026-11-03",
    "eligibility": {"items": ["Egyptian citizenship"]},
    "citizenship_eligible": True,
    "min_gpa": 3.0,
    "min_ielts": 6.5,
    "content_hash": "scholarship-hash-456",
}


def test_upsert_visa_requirement_sends_correct_request(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_post = mocker.patch("client.requests.post", return_value=mock_response)

    result = upsert_visa_requirement(SAMPLE_RECORD)

    assert result is True
    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    assert call_args[0] == f"{settings.rag_service_url}/internal/visa-requirements"
    assert call_kwargs["json"] == SAMPLE_RECORD
    assert call_kwargs["headers"]["X-Internal-Api-Key"] == settings.internal_api_key
    assert call_kwargs["timeout"] == 15


def test_upsert_visa_requirement_returns_true_on_200(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mocker.patch("client.requests.post", return_value=mock_response)

    assert upsert_visa_requirement(SAMPLE_RECORD) is True


def test_upsert_visa_requirement_raises_on_401(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Invalid or missing X-Internal-Api-Key header"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Client Error")
    mocker.patch("client.requests.post", return_value=mock_response)

    with pytest.raises(requests.exceptions.HTTPError):
        upsert_visa_requirement(SAMPLE_RECORD)

    mock_response.raise_for_status.assert_called_once()


def test_upsert_visa_requirement_raises_on_500(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Database upsert failed"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    mocker.patch("client.requests.post", return_value=mock_response)

    with pytest.raises(requests.exceptions.HTTPError):
        upsert_visa_requirement(SAMPLE_RECORD)


def test_upsert_visa_requirement_reraises_connection_errors(mocker):
    mocker.patch("client.requests.post", side_effect=requests.exceptions.ConnectionError("refused"))

    with pytest.raises(requests.exceptions.ConnectionError):
        upsert_visa_requirement(SAMPLE_RECORD)


# ---------------------------------------------------------------------------
# upsert_program_requirement (GOA-088 Task 08)
# ---------------------------------------------------------------------------

def test_upsert_program_requirement_sends_correct_request(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_post = mocker.patch("client.requests.post", return_value=mock_response)

    result = upsert_program_requirement(SAMPLE_PROGRAM_REQUIREMENT_RECORD)

    assert result is True
    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    assert call_args[0] == f"{settings.rag_service_url}/internal/program-requirements"
    assert call_kwargs["json"] == SAMPLE_PROGRAM_REQUIREMENT_RECORD
    assert call_kwargs["headers"]["X-Internal-Api-Key"] == settings.internal_api_key
    assert call_kwargs["timeout"] == 15


def test_upsert_program_requirement_returns_true_on_200(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mocker.patch("client.requests.post", return_value=mock_response)

    assert upsert_program_requirement(SAMPLE_PROGRAM_REQUIREMENT_RECORD) is True


def test_upsert_program_requirement_raises_on_500(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Processing Error"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    mocker.patch("client.requests.post", return_value=mock_response)

    with pytest.raises(requests.exceptions.HTTPError):
        upsert_program_requirement(SAMPLE_PROGRAM_REQUIREMENT_RECORD)


def test_upsert_program_requirement_reraises_connection_errors(mocker):
    mocker.patch("client.requests.post", side_effect=requests.exceptions.ConnectionError("refused"))

    with pytest.raises(requests.exceptions.ConnectionError):
        upsert_program_requirement(SAMPLE_PROGRAM_REQUIREMENT_RECORD)


# ---------------------------------------------------------------------------
# upsert_scholarship_program (GOA-088 Task 08)
# ---------------------------------------------------------------------------

def test_upsert_scholarship_program_sends_correct_request(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_post = mocker.patch("client.requests.post", return_value=mock_response)

    result = upsert_scholarship_program(SAMPLE_SCHOLARSHIP_PROGRAM_RECORD)

    assert result is True
    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    assert call_args[0] == f"{settings.rag_service_url}/internal/scholarship-programs"
    assert call_kwargs["json"] == SAMPLE_SCHOLARSHIP_PROGRAM_RECORD
    assert call_kwargs["headers"]["X-Internal-Api-Key"] == settings.internal_api_key
    assert call_kwargs["timeout"] == 15


def test_upsert_scholarship_program_returns_true_on_200(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mocker.patch("client.requests.post", return_value=mock_response)

    assert upsert_scholarship_program(SAMPLE_SCHOLARSHIP_PROGRAM_RECORD) is True


def test_upsert_scholarship_program_raises_on_500(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Processing Error"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    mocker.patch("client.requests.post", return_value=mock_response)

    with pytest.raises(requests.exceptions.HTTPError):
        upsert_scholarship_program(SAMPLE_SCHOLARSHIP_PROGRAM_RECORD)


def test_upsert_scholarship_program_reraises_connection_errors(mocker):
    mocker.patch("client.requests.post", side_effect=requests.exceptions.ConnectionError("refused"))

    with pytest.raises(requests.exceptions.ConnectionError):
        upsert_scholarship_program(SAMPLE_SCHOLARSHIP_PROGRAM_RECORD)

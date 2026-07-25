import importlib.util
import os
import pydantic
import pytest
from app.schemas.visa_schema import ProofOfFunds, funding_schema_prompt_block, FundingPathway


def test_proof_of_funds_schema_parity():
    """Verify that ingestion's ProofOfFunds is an identical mirror of RAG's ProofOfFunds."""
    # Resolve the relative path to RAG's visa schema
    current_dir = os.path.dirname(__file__)
    rag_schema_path = os.path.join(current_dir, "..", "..", "rag", "app", "schemas", "visa.py")
    rag_schema_path = os.path.abspath(rag_schema_path)

    spec = importlib.util.spec_from_file_location("rag_visa_schema", rag_schema_path)
    rag_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rag_module)

    IngestionPOF = ProofOfFunds
    RagPOF = getattr(rag_module, "ProofOfFunds")

    assert IngestionPOF.model_json_schema() == RagPOF.model_json_schema()


def test_uk_amounts_representable():
    """Construct London/outside-London GBP monthly amounts and assert no EUR leakage."""
    payload = {
        "pathways": [
            {
                "pathway": "self_funded",
                "amounts": [
                    {"amount": 1334.0, "currency": "GBP", "period": "per_month", "qualifier": "London"},
                    {"amount": 1023.0, "currency": "GBP", "period": "per_month", "qualifier": "outside London"}
                ],
                "accepted_evidence": ["Bank statement", "Student loan letter"],
            }
        ]
    }
    obj = ProofOfFunds(**payload)
    dumped = obj.model_dump()
    assert len(dumped["pathways"]) == 1
    amounts = dumped["pathways"][0]["amounts"]
    assert amounts[0]["currency"] == "GBP"
    assert amounts[1]["currency"] == "GBP"
    assert "eur" not in str(dumped).lower()


def test_germany_blocked_account_representable():
    """Construct blocked_account pathway with EUR, per_month, and provider names."""
    payload = {
        "pathways": [
            {
                "pathway": "blocked_account",
                "amounts": [
                    {"amount": 934.0, "currency": "EUR", "period": "per_month", "qualifier": "first year"}
                ],
                "accepted_evidence": ["Fintiba confirmation", "Coracle confirmation"],
                "notes": "Blocked account must cover at least 11,208 EUR in total."
            }
        ]
    }
    obj = ProofOfFunds(**payload)
    assert obj.pathways[0].pathway == "blocked_account"
    assert obj.pathways[0].amounts[0].currency == "EUR"
    assert "Fintiba" in obj.pathways[0].accepted_evidence[0]


def test_unknown_pathway_rejected():
    """pathway='crypto' raises ValidationError."""
    payload = {
        "pathways": [
            {
                "pathway": "crypto",
                "amounts": [{"amount": 1.0, "currency": "BTC", "period": "total"}]
            }
        ]
    }
    with pytest.raises(pydantic.ValidationError):
        ProofOfFunds(**payload)


def test_prompt_block_matches_schema():
    """Verify that every field in the generated prompt block corresponds to the actual schema."""
    prompt_str = funding_schema_prompt_block()
    import json
    
    if prompt_str.startswith("```"):
        prompt_str = prompt_str.split("\n", 1)[-1]
        prompt_str = prompt_str.rsplit("```", 1)[0]
    
    prompt_json = json.loads(prompt_str)
    
    assert "pathways" in prompt_json
    if prompt_json["pathways"]:
        pathway_dict = prompt_json["pathways"][0]
        schema_fields = FundingPathway.model_fields.keys()
        for key in pathway_dict.keys():
            assert key in schema_fields, f"Field '{key}' in prompt block is not in FundingPathway schema"

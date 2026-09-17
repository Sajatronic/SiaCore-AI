import json
from unittest.mock import patch
import pytest
import httpx

from config.settings import settings
from models.schemas import EntityType, ExtractedEntity, LinkedEntity
from canonical.matchers import link_entities

def test_fallback_when_api_key_missing():
    old_key = settings.openrouter_api_key
    settings.openrouter_api_key = ""
    try:
        ext = [ExtractedEntity(text="Texas Instruments Inc.", entity_type=EntityType.MANUFACTURER, confidence=0.9)]
        res = link_entities(ext, "Texas Instruments Inc. announced a new fab.")

        mfrs = [r for r in res if r.entity_type == EntityType.MANUFACTURER]
        assert len(mfrs) == 1
        assert mfrs[0].canonical_name == "Texas Instruments"
    finally:
        settings.openrouter_api_key = old_key

def test_llm_linking_success():
    with patch("services.llm_client.chat_completion_json") as mock_json:
        mock_json.return_value = {
            "matches": [
                {
                    "extracted_text": "TI",
                    "canonical_id": "MFR:Texas Instruments",
                    "canonical_name": "Texas Instruments",
                    "entity_type": "MANUFACTURER",
                    "match_score": 0.95,
                    "requires_review": False,
                },
                {
                    "extracted_text": "Taiwan",
                    "canonical_id": "LOC:taiwan",
                    "canonical_name": "Taiwan",
                    "entity_type": "LOCATION",
                    "match_score": 0.90,
                    "requires_review": False,
                },
            ]
        }
        
        old_key = settings.openrouter_api_key
        old_mode = settings.llm_entity_linking_mode
        settings.openrouter_api_key = "dummy-key"
        settings.llm_entity_linking_mode = "always"
        try:
            ext = [
                ExtractedEntity(text="TI", entity_type=EntityType.MANUFACTURER, confidence=0.9),
                ExtractedEntity(text="Taiwan", entity_type=EntityType.LOCATION, confidence=0.9)
            ]
            res = link_entities(ext, "TI announced a fab in Taiwan.")
            
            mock_json.assert_called_once()
            # Verify manufacturers and locations from mock output
            mfrs = [r for r in res if r.canonical_id == "MFR:Texas Instruments"]
            assert len(mfrs) == 1
            assert mfrs[0].canonical_name == "Texas Instruments"
            
            locs = [r for r in res if r.canonical_id == "LOC:taiwan"]
            assert len(locs) == 1

        finally:
            settings.openrouter_api_key = old_key
            settings.llm_entity_linking_mode = old_mode

def test_llm_linking_exception_fallback():
    # If API call raises an exception, should fall back to legacy and succeed
    with patch("services.llm_client.chat_completion", side_effect=httpx.ConnectError("Connection failed")):
        old_key = settings.openrouter_api_key
        old_mode = settings.llm_entity_linking_mode
        settings.openrouter_api_key = "dummy-key"
        settings.llm_entity_linking_mode = "always"
        try:
            ext = [ExtractedEntity(text="Texas Instruments Inc.", entity_type=EntityType.MANUFACTURER, confidence=0.9)]
            res = link_entities(ext, "Texas Instruments Inc. announced a new fab.")
            
            # Legacy matching should succeed
            mfrs = [r for r in res if r.entity_type == EntityType.MANUFACTURER]
            assert len(mfrs) == 1
            assert mfrs[0].canonical_name == "Texas Instruments"
        finally:
            settings.openrouter_api_key = old_key
            settings.llm_entity_linking_mode = old_mode

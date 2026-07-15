import asyncio
import traceback
from app.adapters.ielts_org import IELTSOrgAdapter
from app.adapters.daad import DAADAdapter
from app.adapters.chevening import CheveningAdapter
from app.adapters.study_in_poland import StudyInPolandAdapter
from app.adapters.stipendium_hungaricum import StipendiumHungaricumAdapter
from app.adapters.masters_portal import MastersPortalAdapter
from app.adapters.german_embassy_cairo import GermanEmbassyCairoAdapter
from app.adapters.campus_france_egypt import CampusFranceEgyptAdapter
from app.adapters.uk_visa_egypt import UKVISAEgyptAdapter
from app.adapters.fintiba_sperrkonto import FintibaSperrkontoAdapter
from app.adapters.czech_embassy_cairo import CzechEmbassyCairoAdapter
from app.adapters.spain_visa_egypt import SpainVisaEgyptAdapter
from app.adapters.italy_embassy_cairo import ItalyEmbassyCairoAdapter

async def run_live_test():
    adapters = [
        ("IELTS", IELTSOrgAdapter()),
        ("DAAD", DAADAdapter()),
        ("Chevening", CheveningAdapter()),
        ("Poland (NAWA)", StudyInPolandAdapter()),
        ("Stipendium Hungaricum", StipendiumHungaricumAdapter()),
        ("MastersPortal (Playwright)", MastersPortalAdapter()),
        ("German Embassy Cairo", GermanEmbassyCairoAdapter()),
        ("Campus France Egypt", CampusFranceEgyptAdapter()),
        ("UK Visa Egypt", UKVISAEgyptAdapter()),
        ("Fintiba Sperrkonto", FintibaSperrkontoAdapter()),
        ("Czech Embassy Cairo", CzechEmbassyCairoAdapter()),
        ("Spain Visa Egypt", SpainVisaEgyptAdapter()),
        ("Italy Embassy Cairo", ItalyEmbassyCairoAdapter())
    ]
    
    for name, adapter in adapters:
        print(f"\n--- 🌍 Testing {name} Scraper LIVE ---")
        try:
            docs = await adapter.scrape()
            if docs:
                print(f"✅ SUCCESS! Extracted {len(docs)} document(s).")
                print("Preview (First 150 characters):")
                print(docs[0]["content"][:150].replace('\n', ' ') + "...\n")
            else:
                print("❌ FAILED: No documents returned. (HTML structure might have changed!)\n")
        except Exception as e:
            print(f"❌ FATAL ERROR: {str(e)}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_live_test())
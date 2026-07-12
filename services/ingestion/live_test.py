import asyncio
import traceback
from app.adapters.ielts_org import IELTSOrgAdapter
from app.adapters.daad import DAADAdapter
from app.adapters.chevening import CheveningAdapter
from app.adapters.study_in_poland import StudyInPolandAdapter
from app.adapters.stipendium_hungaricum import StipendiumHungaricumAdapter
from app.adapters.masters_portal import MastersPortalAdapter

async def run_live_test():
    adapters = [
        ("IELTS", IELTSOrgAdapter()),
        ("DAAD", DAADAdapter()),
        ("Chevening", CheveningAdapter()),
        ("Poland (NAWA)", StudyInPolandAdapter()),
        ("Stipendium Hungaricum", StipendiumHungaricumAdapter()),
        ("MastersPortal (Playwright)", MastersPortalAdapter())
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
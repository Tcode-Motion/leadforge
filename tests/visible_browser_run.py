import os
import sys
import time
from playwright.sync_api import sync_playwright

def run_visible_real_browser_test():
    print("=" * 70)
    print("LAUNCHING VISIBLE REAL CHROME BROWSER WINDOW ON YOUR SCREEN")
    print("=" * 70)

    # slow_mo adds realistic delay between actions so the user can watch the browser
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=600,  # 600ms pacing so user sees every action
            args=["--start-maximized"]
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        # -----------------------------------------------------------
        # 1. Open Leads Dashboard
        # -----------------------------------------------------------
        print("\n[Step 1] Opening Leads Dashboard: http://127.0.0.1:8790/leads")
        page.goto("http://127.0.0.1:8790/leads")
        time.sleep(1.5)

        # -----------------------------------------------------------
        # 2. Typing into Real-Time Search Bar
        # -----------------------------------------------------------
        print("[Step 2] Typing 'Dental' into the live search input...")
        search_input = page.locator("#leadFilter")
        search_input.click()
        search_input.press_sequentially("Dental", delay=120)
        time.sleep(1.5)

        print("[Step 2b] Clearing search...")
        search_input.fill("")
        time.sleep(1.0)

        # -----------------------------------------------------------
        # 3. Dynamic Category Dropdown Testing
        # -----------------------------------------------------------
        print("[Step 3] Selecting 'Dental Clinic' from category filter...")
        page.select_option("#categoryFilter", "Dental Clinic")
        time.sleep(1.5)

        print("[Step 3b] Selecting 'Gym & Fitness' from category filter...")
        page.select_option("#categoryFilter", "Gym & Fitness")
        time.sleep(1.5)

        print("[Step 3c] Resetting category filter to All...")
        page.select_option("#categoryFilter", "")
        time.sleep(1.0)

        # -----------------------------------------------------------
        # 4. Interactive Quick Filter Chips
        # -----------------------------------------------------------
        print("[Step 4] Clicking Quick Chip: '⭐ No Website (High Value)'...")
        no_web_chip = page.locator(".quick-chip:has-text('No Website')")
        if no_web_chip.count() > 0:
            no_web_chip.first.click()
            time.sleep(1.5)

        print("[Step 4b] Clicking Quick Chip: '💬 WhatsApp Ready'...")
        wa_chip = page.locator(".quick-chip:has-text('WhatsApp')")
        if wa_chip.count() > 0:
            wa_chip.first.click()
            time.sleep(1.5)

        print("[Step 4c] Clicking Quick Chip: 'All' to restore view...")
        all_chip = page.locator(".quick-chip:has-text('All')")
        if all_chip.count() > 0:
            all_chip.first.click()
            time.sleep(1.0)

        # -----------------------------------------------------------
        # 5. Smooth Scroll down to inspect table rows
        # -----------------------------------------------------------
        print("[Step 5] Scrolling table to inspect rows, exact maps, and verified channels...")
        page.evaluate("window.scrollBy({ top: 350, behavior: 'smooth' })")
        time.sleep(1.2)
        page.evaluate("window.scrollBy({ top: 400, behavior: 'smooth' })")
        time.sleep(1.2)
        page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
        time.sleep(1.0)

        # -----------------------------------------------------------
        # 6. Open Website Conversion Audit & Intelligence Modal
        # -----------------------------------------------------------
        print("[Step 6] Clicking Audit badge to open Conversion & Pitch Modal...")
        audit_pill = page.locator(".audit-card-pill").first
        if audit_pill.count() > 0:
            audit_pill.click()
            time.sleep(2.5)  # Pause so user can view modal content

            print("[Step 6b] Closing modal...")
            page.locator(".intel-modal-close").click()
            time.sleep(1.0)

        # -----------------------------------------------------------
        # 7. Changing Pipeline Outcome & Syncing
        # -----------------------------------------------------------
        print("[Step 7] Updating lead outcome to 'Call booked'...")
        first_outcome = page.locator("select.outcome-select").first
        if first_outcome.count() > 0:
            first_outcome.select_option("Call booked")
            time.sleep(1.0)

        print("[Step 7b] Clicking 'Sync to CRM & Apps'...")
        sync_btn = page.locator("#syncAppsBtn")
        if sync_btn.count() > 0:
            sync_btn.click()
            time.sleep(1.5)

        # -----------------------------------------------------------
        # 8. Visiting Standalone Apps Hub
        # -----------------------------------------------------------
        print("\n[Step 8] Navigating to Apps Hub: http://127.0.0.1:8790/apps")
        page.locator("a[href='/apps']").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2.0)

        # -----------------------------------------------------------
        # 9. Opening Standalone Microservices
        # -----------------------------------------------------------
        print("\n[Step 9] Opening Standalone Cal.diy Booking Calendar (:3002)...")
        cal_page = context.new_page()
        cal_page.goto("http://127.0.0.1:3002/book/discovery-call")
        time.sleep(2.0)
        cal_page.close()

        print("[Step 9b] Opening Standalone Chatwoot Omnichannel Inbox (:3001)...")
        cw_page = context.new_page()
        cw_page.goto("http://127.0.0.1:3001")
        time.sleep(2.0)
        cw_page.close()

        print("[Step 9c] Opening Standalone Listmonk Email Campaigns (:9000)...")
        lm_page = context.new_page()
        lm_page.goto("http://127.0.0.1:9000")
        time.sleep(2.0)
        lm_page.close()

        print("[Step 9d] Opening Standalone Twenty CRM Pipeline (:3003)...")
        tw_page = context.new_page()
        tw_page.goto("http://127.0.0.1:3003")
        time.sleep(2.0)
        tw_page.close()

        print("[Step 9e] Opening Standalone Documenso Proposals (:3004)...")
        dc_page = context.new_page()
        dc_page.goto("http://127.0.0.1:3004")
        time.sleep(2.0)
        dc_page.close()

        # -----------------------------------------------------------
        # 10. Visiting 1-Click Setup Page
        # -----------------------------------------------------------
        print("\n[Step 10] Navigating to 1-Click Setup: http://127.0.0.1:8790/setup")
        page.locator("a[href='/setup']").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2.0)

        # -----------------------------------------------------------
        # 11. Visiting AI Writer Page
        # -----------------------------------------------------------
        print("\n[Step 11] Navigating to AI Writer: http://127.0.0.1:8790/writer")
        page.locator("a[href='/writer']").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2.0)

        # -----------------------------------------------------------
        # 12. Visiting Health Page
        # -----------------------------------------------------------
        print("\n[Step 12] Navigating to System Health: http://127.0.0.1:8790/health")
        page.locator("a[href='/health']").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2.0)

        # -----------------------------------------------------------
        # 13. Return to Leads Dashboard
        # -----------------------------------------------------------
        print("\n[Step 13] Returning to Leads Dashboard: http://127.0.0.1:8790/leads")
        page.locator("a[href='/leads']").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2.0)

        print("\n" + "=" * 70)
        print("REAL VISIBLE BROWSER TESTING COMPLETED SUCCESSFULLY!")
        print("=" * 70)

        browser.close()

if __name__ == "__main__":
    run_visible_real_browser_test()


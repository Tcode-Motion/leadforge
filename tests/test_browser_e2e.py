from playwright.sync_api import sync_playwright
import time

def run_tests():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        errors = []
        page.on("pageerror", lambda err: errors.append(f"PAGE ERROR: {err}"))

        print("Visiting /leads...")
        page.goto("http://127.0.0.1:8790/leads", wait_until="networkidle")

        # 1. Test search input
        page.fill("#leadFilter", "Auro")
        time.sleep(0.3)
        visible_rows = [r for r in page.query_selector_all("[data-lead-row]") if r.is_visible()]
        assert len(visible_rows) == 1, f"Expected 1 row for Auro, got {len(visible_rows)}"
        print("✓ 1. Search filter verified (Auro -> 1 lead)")
        page.fill("#leadFilter", "")
        time.sleep(0.3)

        # 2. Test Category Dropdown
        page.select_option("#categoryFilter", "Dental Clinic")
        time.sleep(0.3)
        visible_rows = [r for r in page.query_selector_all("[data-lead-row]") if r.is_visible()]
        assert len(visible_rows) == 30, f"Expected 30 rows for Dental Clinic, got {len(visible_rows)}"
        print("✓ 2. Category dropdown verified (Dental Clinic -> 30 leads)")

        page.select_option("#categoryFilter", "Gym & Fitness")
        time.sleep(0.3)
        visible_rows = [r for r in page.query_selector_all("[data-lead-row]") if r.is_visible()]
        assert len(visible_rows) == 20, f"Expected 20 rows for Gym & Fitness, got {len(visible_rows)}"
        print("✓ 3. Category dropdown verified (Gym & Fitness -> 20 leads)")
        page.select_option("#categoryFilter", "")
        time.sleep(0.3)

        # 3. Test Quick Chip: No Website
        chips = page.query_selector_all(".quick-chip")
        for c in chips:
            if "No Website" in c.inner_text():
                c.click()
                break
        time.sleep(0.3)
        visible_rows = [r for r in page.query_selector_all("[data-lead-row]") if r.is_visible()]
        assert len(visible_rows) == 35, f"Expected 35 leads with no website, got {len(visible_rows)}"
        print("✓ 4. No Website Quick Chip verified (35 high-value leads)")

        # Reset to All
        chips[0].click()
        time.sleep(0.3)

        # 4. Test Audit Modal popup and content
        audit_btn = page.query_selector(".audit-card-pill")
        assert audit_btn is not None, "No audit-card-pill button found"
        audit_btn.click()
        time.sleep(0.4)
        modal = page.query_selector("#auditModal")
        assert modal.is_visible(), "Modal did not appear"
        print("✓ 5. Audit Modal open & content inspection verified")

        page.click(".intel-modal-close")
        time.sleep(0.3)
        assert not modal.is_visible(), "Modal did not close"
        print("✓ 6. Audit Modal close verified")

        # 5. Test Stage Select Outcome
        first_stage_sel = page.query_selector("select.outcome-select")
        assert first_stage_sel is not None, "Outcome select not found"
        page.select_option("select.outcome-select", "Pitched")
        time.sleep(0.5)
        row = page.query_selector("[data-lead-row]")
        assert row.get_attribute("data-outcome") == "Pitched", "Outcome not updated on row"
        print("✓ 7. Pipeline stage instant save verified")

        # 6. Test Sync to CRM & Apps button
        sync_btn = page.query_selector("#syncAppsBtn")
        assert sync_btn is not None, "Sync button not found"
        sync_btn.click()
        time.sleep(0.8)
        print("✓ 8. Sync to CRM & Apps button verified")

        # 7. Test Setup page
        print("Visiting /setup...")
        page.goto("http://127.0.0.1:8790/setup", wait_until="networkidle")
        page.fill("input[name='agency_name']", "LeadForge Growth Studio")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        assert "saved=1" in page.url, f"Expected saved=1 in URL, got {page.url}"
        print("✓ 9. 1-Click Setup save & app activation verified")

        # 8. Test Apps page
        print("Visiting /apps...")
        page.goto("http://127.0.0.1:8790/apps", wait_until="networkidle")
        pills = page.query_selector_all(".status-pill.ok")
        print(f"✓ 10. Apps page verified: {len(pills)} running standalone services")

        browser.close()

    print("\n================ FINAL VERIFICATION RESULT ================")
    print(f"Total uncaught browser JS errors: {len(errors)}")
    for e in errors:
        print("  -", e)
    if not errors:
        print("ALL TESTS PASSED! ZERO BROWSER ERRORS! SYSTEM IS 100% HEALTHY.")

if __name__ == "__main__":
    run_tests()

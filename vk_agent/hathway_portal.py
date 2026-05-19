"""
Hathway partners portal — login and Pack Management navigation.
Extends the same bot patterns as portal.py (Railtel). Subscriber search / status
automation can be added once Pack Management UI selectors are known.
"""
import os
import re
import time
import pytesseract
from PIL import Image, ImageEnhance
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from multi_credentials import get_hathway_credentials

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(ROOT_DIR, '.env'))
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def solve_captcha(element, length=6):
    try:
        img_path = 'hathway_temp_captcha.png'
        element.screenshot(path=img_path)
        img = Image.open(img_path).convert('L')
        img = ImageEnhance.Contrast(img).enhance(3.0)
        config = (
            r'--psm 6 -c tessedit_char_whitelist='
            r'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        )
        text = pytesseract.image_to_string(img, config=config).strip()
        return ''.join(filter(str.isalnum, text))[:length]
    except Exception:
        return ''


def navigate_to_pack_management(page):
    """Clicks the Pack Management cell on the Dashboard table."""
    print('🖱️ Navigating to Pack Management...')
    try:
        selector = '#td1 > div > center > table > tbody > tr:nth-child(1) > td:nth-child(2)'
        page.wait_for_selector(selector, timeout=20000)
        page.locator(selector).click()
        page.wait_for_timeout(2000)
        print('✅ Arrived at Pack Management.')
        return True
    except Exception as e:
        print(f'⚠️ Navigation Error: {e}')
        return False


def navigate_to_dashboard_tile(page):
    """Clicks the **Dashboard** tile on Home.aspx (first cell, top-left; Pack Management is column 2)."""
    print('🖱️ Navigating to Dashboard tile…')
    try:
        selector = '#td1 > div > center > table > tbody > tr:nth-child(1) > td:nth-child(1)'
        page.wait_for_selector(selector, timeout=20000)
        page.locator(selector).click()
        page.wait_for_timeout(2500)
        try:
            page.wait_for_load_state('domcontentloaded', timeout=20000)
        except Exception:
            pass
        print('✅ Dashboard tile clicked.')
        return True
    except Exception as e:
        print(f'⚠️ Dashboard navigation error: {e}')
        return False


def _hathway_click_dashboard_summary_tab(page):
    """Ensures inner **Dashboard** tab is selected (alongside Base / Financial Summary) if present."""
    cleanup_hathway_ui(page)
    clicked = False
    try:
        tab = page.get_by_role('tab', name=re.compile(r'^\s*Dashboard\s*$', re.I)).first
        if tab.count() > 0:
            tab.scroll_into_view_if_needed(timeout=5000)
            tab.click(timeout=8000, force=True)
            clicked = True
    except Exception:
        pass
    if not clicked:
        for filt in (
            page.locator('a').filter(has_text=re.compile(r'^\s*Dashboard\s*$', re.I)),
            page.locator('li').filter(has_text=re.compile(r'^\s*Dashboard\s*$', re.I)),
            page.locator('span').filter(has_text=re.compile(r'^\s*Dashboard\s*$', re.I)),
        ):
            try:
                if filt.count() == 0:
                    continue
                loc = filt.first
                loc.scroll_into_view_if_needed(timeout=4000)
                loc.click(timeout=6000, force=True)
                clicked = True
                break
            except Exception:
                continue
    page.wait_for_timeout(1200 if clicked else 400)


def hathway_parse_dashboard_stats_text(blob):
    """
    Regex-parse visible Hathway Dashboard summary body text.
    Returns dict keys: active_stb, inactive_stb, total_stb, actual_balance (str or None).
    """
    out = {
        'active_stb': None,
        'inactive_stb': None,
        'total_stb': None,
        'actual_balance': None,
    }
    if not blob:
        return out
    m = re.search(r'Active\s*:\s*(\d+)', blob, re.I)
    if m:
        out['active_stb'] = int(m.group(1))
    m_in = (
        re.search(r'InActive\s*:\s*(\d+)', blob, re.I)
        or re.search(r'Inactive\s*:\s*(\d+)', blob, re.I)
        or re.search(r'In\s*Active\s*:\s*(\d+)', blob, re.I)
    )
    if m_in:
        out['inactive_stb'] = int(m_in.group(1))
    mt = re.search(r'Total\s*:\s*(\d+)', blob, re.I)
    if mt:
        out['total_stb'] = int(mt.group(1))
    mb = re.search(r'Actual\s+Balance\s*:\s*([\d,]+(?:\.\d+)?)', blob, re.I)
    if mb:
        out['actual_balance'] = mb.group(1).strip().replace(',', '')
    return out


def hathway_scrape_dashboard_stats(page):
    """
    On Dashboard page: ensure **Dashboard** tab content, scrape body text for STB counts + Actual Balance.
    """
    cleanup_hathway_ui(page)
    try:
        _hathway_click_dashboard_summary_tab(page)
        cleanup_hathway_ui(page)
        blob = page.locator('body').inner_text(timeout=15000) or ''
    except Exception:
        blob = ''
    merged = hathway_parse_dashboard_stats_text(blob)
    return merged


def _hathway_login_url():
    return (os.getenv('HATHWAY_LOGIN_URL') or 'https://partners.hathway-connect.com/Login.aspx').strip()


def _still_on_hathway_login_page(url):
    """Portal may use Login.aspx or login.aspx — treat case-insensitively."""
    return 'login.aspx' in (url or '').lower()


def _hathway_resolve_login_target(page, timeout_ms):
    """
    Wait until Hathway login form (captcha + user field) is visible and interactable.
    If the landing page is not ready within timeout_ms, returns None so the caller can retry.
    """
    deadline = time.monotonic() + max(1.0, timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        target = page
        for f in page.frames:
            try:
                if f.locator('#imgCaptcha').count() > 0:
                    target = f
                    break
            except Exception:
                continue
        try:
            cap = target.locator('#imgCaptcha').first
            usr = target.locator("input[id*='txtUser']").first
            if cap.count() == 0 or usr.count() == 0:
                page.wait_for_timeout(250)
                continue
            cap.wait_for(state='visible', timeout=2500)
            usr.wait_for(state='visible', timeout=2500)
            return target
        except Exception:
            page.wait_for_timeout(300)
    return None


def _hathway_transaction_base(current_url):
    """
    Build transaction app base URL from post-login location.

    Legacy portals used a virtual directory named hathway + digits, e.g. /hathway3/...
    Current flows often land on /hathway/Transaction/... (no digits).
    """
    u = (current_url or '').strip()
    # Legacy: https://host/hathwayN (N = digits)
    for pat in (
        r'(https?://[^/\s?#]+/hathway\d+)',
        r'(https?://[^/\s?#]+/Hathway\d+)',
    ):
        m = re.search(pat, u, re.I)
        if m:
            return m.group(1).rstrip('/')
    # Modern: .../hathway/Transaction/frmSliderShowPage.aspx etc.
    m = re.search(r'(https?://[^/\s?#]+)/hathway/Transaction', u, re.I)
    if m:
        return f'{m.group(1)}/hathway'
    # Any .../hathway/... under host (single path segment "hathway", not hathway+digits)
    m = re.search(r'(https?://[^/\s?#]+)/hathway(?:/|$|\?)', u, re.I)
    if m:
        return f'{m.group(1)}/hathway'
    return None


def login_hathway(page, account_id=None, user=None, password=None, *, goto_pack_management=True):
    """
    Hathway partners login with CAPTCHA; on success jumps to Home.aspx.
    By default continues into Pack Management; set goto_pack_management=False to stay on Home grid
    (e.g. Dashboard tile flow).
    Credentials: HATHWAY_USER/PASS, or HATHWAY_ACCOUNTS_FILE (see multi_credentials).
    Optional: HATHWAY_LOGIN_URL (default partners login page).
    """
    if user is not None and password is not None:
        u, p = user, password
    else:
        try:
            u, p, _acc = get_hathway_credentials(account_id)
        except ValueError as exc:
            print(f'⚠️ Hathway credentials: {exc}')
            return False

    user = (u or '').strip()
    pwd = (p or '').strip()
    if not user or not pwd:
        print('⚠️ HATHWAY_USER or HATHWAY_PASS missing in .env')
        return False

    login_url = _hathway_login_url()
    form_ready_ms = int(os.getenv('HATHWAY_LOGIN_FORM_READY_MS', '10000'))
    goto_timeout_ms = int(os.getenv('HATHWAY_LOGIN_GOTO_TIMEOUT_MS', '45000'))
    leave_login_ms = int(os.getenv('HATHWAY_LEAVE_LOGIN_URL_WAIT_MS', '12000'))
    post_login_polls = int(os.getenv('HATHWAY_POST_LOGIN_POLL_MAX', '12'))
    post_login_poll_ms = int(os.getenv('HATHWAY_POST_LOGIN_POLL_MS', '1000'))
    retry_wait_ms = int(os.getenv('HATHWAY_LOGIN_RETRY_WAIT_MS', '10000'))

    for attempt in range(1, 4):
        print(f'\n[Hathway] Attempt {attempt} of 3...')
        try:
            # networkidle often never fires on Login.aspx (analytics / long-polling).
            page.goto(login_url, wait_until='domcontentloaded', timeout=goto_timeout_ms)
            page.wait_for_timeout(800)

            target = _hathway_resolve_login_target(page, form_ready_ms)
            if target is None:
                print(
                    f'⚠️ Login page not ready within {form_ready_ms} ms — waiting {retry_wait_ms // 1000}s '
                    f'then retry (attempt {attempt}).'
                )
                page.wait_for_timeout(retry_wait_ms)
                continue

            target.locator("input[id*='txtUser']").first.fill(user)
            target.locator("input[id*='txtPass']").first.fill(pwd)

            for f in page.frames:
                try:
                    if f.locator('#chkTerms').count() > 0:
                        f.locator('#chkTerms').click(force=True)
                        break
                except Exception:
                    continue

            captcha_text = solve_captcha(target.locator('#imgCaptcha').first, 6)
            print(f'🤖 OCR Detected: {captcha_text!r} (len={len(captcha_text)})')
            if len(captcha_text) < 4:
                print('⚠️ CAPTCHA looks too short — will retry with fresh page.')
                try:
                    page.screenshot(path=f'hathway_login_captcha_attempt_{attempt}.png')
                except Exception:
                    pass
                page.wait_for_timeout(800)
                continue

            target.locator('#txtcaptcha').fill(captcha_text)
            target.locator('#ibtLogIn').click()

            print('⏳ Waiting to leave login page (URL must not contain login.aspx)…')
            try:
                page.wait_for_url(
                    lambda u: not _still_on_hathway_login_page(u),
                    timeout=leave_login_ms,
                )
            except Exception:
                pass

            for poll in range(post_login_polls):
                current_url = page.url
                body_snip = ''
                try:
                    body_snip = (page.locator('body').inner_text(timeout=3000) or '')[:400]
                except Exception:
                    pass

                if _still_on_hathway_login_page(current_url):
                    if re.search(r'invalid|incorrect|wrong|fail|captcha', body_snip, re.I):
                        print(f'⚠️ Still on login; page says: {body_snip[:200]!r}…')
                    page.wait_for_timeout(post_login_poll_ms)
                    continue

                if 'hathway' not in current_url.lower():
                    page.wait_for_timeout(post_login_poll_ms)
                    continue

                print('🎉 Left login page. Resolving dashboard host…')
                base_url = _hathway_transaction_base(current_url)
                if not base_url:
                    print(f'⚠️ Could not parse /hathwayN from URL: {current_url!r}')
                    try:
                        page.screenshot(path=f'hathway_login_bad_url_{attempt}.png')
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)
                    continue

                home_url = f'{base_url}/Transaction/Home.aspx'
                print(f'🚀 Opening dashboard: {home_url}')
                try:
                    page.goto(home_url, wait_until='domcontentloaded', timeout=60000)
                except Exception as nav_e:
                    print(f'⚠️ Home.aspx goto: {nav_e}')
                page.wait_for_timeout(2500)
                cleanup_hathway_ui(page)
                if not goto_pack_management:
                    print('✅ Hathway logged in — Home.aspx (skipped Pack Management).')
                    return True
                if navigate_to_pack_management(page):
                    cleanup_hathway_ui(page)
                    return True
                print('⚠️ Pack Management click failed after Home.aspx — see hathway_login_pack_nav.png')
                try:
                    page.screenshot(path='hathway_login_pack_nav.png')
                except Exception:
                    pass
                return False

            print('⚠️ Timed out waiting to leave login page (CAPTCHA wrong or portal slow).')
            try:
                page.screenshot(path=f'hathway_login_timeout_{attempt}.png')
            except Exception:
                pass
            page.wait_for_timeout(800)
        except Exception as e:
            print(f'⚠️ Attempt Error: {e}')
            try:
                page.screenshot(path=f'hathway_login_exception_{attempt}.png')
            except Exception:
                pass
            page.wait_for_timeout(1000)
            continue
    return False


def launch_hathway_browser(headless=False, slow_mo=None):
    if slow_mo is None:
        slow_mo = int(os.getenv('HATHWAY_SLOW_MO', '500'))
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
    page = browser.new_page()
    page.set_default_timeout(int(os.getenv('PLAYWRIGHT_DEFAULT_TIMEOUT_MS', '300000')))
    return playwright, browser, page


def close_hathway_browser(playwright, browser):
    try:
        try:
            browser.close()
        except Exception as exc:
            print(f'close_hathway_browser: {exc}')
    finally:
        try:
            playwright.stop()
        except Exception:
            pass


def hathway_login_once(page, account_id=None):
    return login_hathway(page, account_id=account_id)


def cleanup_hathway_ui(page):
    """
    Close marketing / notice layers that block clicks on Pack Management.
    Reused browser (multi STB) often keeps these open; single runs hit them less often.
    """
    selectors = [
        '#closeBtn',
        "#modal-anp button.close",
        "#modal-anp button[aria-label='Close']",
        "button.close[data-dismiss='modal']",
        'button[aria-label="Close"]',
        '.modal.in .close',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            if not loc.is_visible(timeout=400):
                continue
            loc.click(timeout=2500)
            page.wait_for_timeout(350)
        except Exception:
            continue


def _hathway_ensure_main_tv_tab(page):
    """
    Activate Main TV tab and wait until bouquet / plan grid is visible (not hidden tab DOM).
    """
    cleanup_hathway_ui(page)
    for attempt in range(1, 4):
        try:
            tab = page.get_by_role('tab', name=re.compile(r'^Main\s*TV$', re.I)).first
            if tab.count() > 0:
                tab.scroll_into_view_if_needed(timeout=5000)
                tab.click(timeout=8000, force=True)
            else:
                page.locator('a, span, td, li').filter(
                    has_text=re.compile(r'^Main\s*TV$', re.I)
                ).first.click(timeout=8000, force=True)
        except Exception:
            try:
                page.locator('a, span, td, li').filter(
                    has_text=re.compile(r'Main\s*TV', re.I)
                ).first.click(timeout=6000, force=True)
            except Exception:
                pass
        page.wait_for_timeout(700)
        cleanup_hathway_ui(page)
        visible_ok = False
        for loc in (
            page.get_by_text(re.compile(r'Hathway\s*Bouquet', re.I)).first,
            page.get_by_text(re.compile(r'Plan\s*Details', re.I)).first,
            page.locator('table').filter(has_text=re.compile(r'LCO\s*Price', re.I)).first,
        ):
            try:
                if loc.count() == 0:
                    continue
                loc.wait_for(state='visible', timeout=10000)
                visible_ok = True
                break
            except Exception:
                continue
        if visible_ok:
            return True
        page.wait_for_timeout(500 * attempt)
    return False


def _hathway_ensure_customer_details_tab(page):
    """
    Activate **Customer Details** tab and wait until Action Required / Plan Details region is usable.
    """
    cleanup_hathway_ui(page)
    for attempt in range(1, 4):
        try:
            tab = page.get_by_role('tab', name=re.compile(r'^Customer\s+Details$', re.I)).first
            if tab.count() > 0:
                tab.scroll_into_view_if_needed(timeout=5000)
                tab.click(timeout=8000, force=True)
            else:
                page.locator('a, span, td, li').filter(
                    has_text=re.compile(r'^Customer\s+Details$', re.I)
                ).first.click(timeout=8000, force=True)
        except Exception:
            try:
                page.locator('a, span, td, li').filter(
                    has_text=re.compile(r'Customer\s+Details', re.I)
                ).first.click(timeout=6000, force=True)
            except Exception:
                pass
        page.wait_for_timeout(700)
        cleanup_hathway_ui(page)
        visible_ok = False
        for loc in (
            page.get_by_text(re.compile(r'Action\s+Required', re.I)).first,
            page.get_by_text(re.compile(r'Quick\s+Recharge', re.I)).first,
            page.get_by_text(re.compile(r'Plan\s*Details', re.I)).first,
            page.get_by_text(re.compile(r'VC/Mac\s*ID', re.I)).first,
        ):
            try:
                if loc.count() == 0:
                    continue
                loc.wait_for(state='visible', timeout=10000)
                visible_ok = True
                break
            except Exception:
                continue
        if visible_ok:
            return True
        page.wait_for_timeout(500 * attempt)
    return False


def looks_like_hathway_stb_id(text):
    """VC / STB: N + 11 digits or T + 12 digits (e.g. N70130838231, T403030313577).

    Phone numbers and Railtel CIDs (ka.user) must not match — those are strict elsewhere.
    """
    t = (text or '').strip().upper()
    if re.fullmatch(r'N\d{11}', t):
        return True
    if re.fullmatch(r'T\d{12}', t):
        return True
    return False


def _hathway_click_vc_mac_search_mode(page):
    """Select Search By: VC/Mac ID/VM/JVM (default in screenshots)."""
    for loc in (
        page.get_by_role('radio', name=re.compile(r'VC/Mac|VM/JVM', re.I)).first,
        page.locator('label').filter(has_text=re.compile(r'VC/Mac', re.I)).first,
        page.get_by_text(re.compile(r'VC/Mac\s*ID', re.I)).first,
    ):
        try:
            if loc.count() == 0:
                continue
            loc.click(timeout=5000, force=True)
            return True
        except Exception:
            continue
    return False


def _hathway_fill_pack_search(page, stb_id):
    """Fill Pack Management search box (left of Search button)."""
    filled = page.evaluate(
        """(id) => {
            const nodes = [...document.querySelectorAll('input[type="submit"], input[type="button"], button')];
            const searchBtn = nodes.find(el => /^\\s*search\\s*$/i.test((el.value || el.textContent || '').trim()));
            const root = searchBtn
                ? (searchBtn.closest('table') || searchBtn.closest('form') || searchBtn.parentElement)
                : document.body;
            const inputs = [...root.querySelectorAll('input[type="text"], input:not([type])')];
            let best = inputs[0] || null;
            if (searchBtn && inputs.length) {
                const br = searchBtn.getBoundingClientRect();
                let dmin = 1e9;
                for (const inp of inputs) {
                    if (!inp.offsetParent) continue;
                    const r = inp.getBoundingClientRect();
                    const d = Math.abs(r.right - br.left) + Math.abs(r.top - br.top);
                    if (d < dmin && r.width > 40) { dmin = d; best = inp; }
                }
            }
            if (!best) return false;
            best.focus();
            best.value = id;
            best.dispatchEvent(new Event('input', { bubbles: true }));
            best.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }""",
        stb_id,
    )
    if filled:
        return
    try:
        page.locator('table').filter(has_text=re.compile(r'Search By', re.I)).locator(
            'input[type="text"]'
        ).first.fill(stb_id, timeout=8000)
    except Exception:
        page.locator('input[type="text"]').first.fill(stb_id, timeout=8000)


def _hathway_click_search(page):
    for loc in (
        page.get_by_role('button', name=re.compile(r'^\s*Search\s*$', re.I)).first,
        page.locator('input[type="submit"][value*="Search" i]').first,
        page.locator('input[type="button"][value*="Search" i]').first,
    ):
        try:
            if loc.count() == 0:
                continue
            loc.click(timeout=8000, force=True)
            return True
        except Exception:
            continue
    page.get_by_text(re.compile(r'^Search$', re.I)).first.click(timeout=8000, force=True)
    return True


def _hathway_scrape_pack_management_dom(page):
    """Pack Management DOM: optional TV Details table; Main TV tab — bouquet row, header prices, scheme."""
    return page.evaluate("""() => {
        const body = document.body.innerText || '';
        const out = {
            tv_table_status: '',
            main_tv_row_status: '',
            vc_id: '',
            stb_no: '',
            customer_ac: '',
            customer_name: '',
            customer_mobile: '',
            total_lco_price: '',
            total_customer_price: '',
            scheme_name: '',
            plan_name: '',
            plan_lco_price: '',
            plan_status: '',
            plan_valid_upto: '',
            action_buttons: [],
        };

        const visible = (el) => {
            if (!el || !el.getBoundingClientRect) return false;
            let e = el;
            for (let d = 0; d < 14 && e; d++) {
                const st = window.getComputedStyle(e);
                if (st.display === 'none' || st.visibility === 'hidden' || Number.parseFloat(st.opacity || '1') === 0) {
                    return false;
                }
                e = e.parentElement;
            }
            const r = el.getBoundingClientRect();
            return r.width > 20 && r.height > 6;
        };

        const tables = [...document.querySelectorAll('table')].filter(visible);

        const statusColumnIndex = (headers) => {
            for (let i = 0; i < headers.length; i++) {
                const h = (headers[i] || '').trim().toLowerCase();
                if (!h || h.includes('suspension')) continue;
                if (h === 'status' || /^stb\\s*status$/i.test(h)) return i;
            }
            return -1;
        };

        const kv = (label) => {
            const m = body.match(new RegExp(label + '\\s*[:.]\\s*([^\\n]+)', 'i'));
            return m ? m[1].trim() : '';
        };
        out.customer_ac = kv('Customer A/C No') || kv('Customer A/C No.') || out.customer_ac;
        out.customer_name = kv('Customer Name') || out.customer_name;
        out.customer_mobile = kv('Customer Mobile') || out.customer_mobile;

        let m = body.match(/Total\\s+LCO\\s+Price\\s*[:.]?\\s*Rs\\.?\\s*([\\d,.]+)/i);
        if (m) out.total_lco_price = m[1].replace(/,/g, '');
        m = body.match(/Total\\s+Customer\\s+Price\\s*[:.]?\\s*Rs\\.?\\s*([\\d,.]+)/i);
        if (m) out.total_customer_price = m[1].replace(/,/g, '');
        m = body.match(/Scheme\\s+Name\\s*[:.]?\\s*([^\\n]+)/i);
        if (m) out.scheme_name = m[1].trim().slice(0, 120);
        m = body.match(/VC\\/Mac\\s*ID\\s*[:.]?\\s*([^\\s\\n]+)/i);
        if (m) out.vc_id = m[1].trim().slice(0, 40);
        m = body.match(/STB\\/Mac\\s*ID\\s*[:.]?\\s*([^\\s\\n]+)/i);
        if (m) out.stb_no = m[1].trim().slice(0, 40);

        const norm = (s) =>
            (s || '')
                .replace(/\u00a0/g, ' ')
                .replace(/\\s+/g, ' ')
                .trim();
        const junkPlanCell = (t) => {
            if (!t || t.length > 140) return true;
            if ((t.match(/\\|/g) || []).length > 5) return true;
            return /Pack Management|Customer Details|Search By|Distributor Name|Enter VCID|VC\\/Mac|GridView|Page\\$/i.test(t);
        };

        const isAlacartePlanName = (pname) => {
            const t = norm(pname);
            const tl = t.toLowerCase();
            if (!t || t.length < 3) return false;
            if (/^(a-la-carte|alacarte|à-la-carte)$/i.test(tl.replace(/\\s+/g, ' ').trim())) return true;
            if (/^a[-\\s]?la[-\\s]?carte$/i.test(tl.replace(/[\\u25ba\\u25b6\\u25bc\\u25bd\\s]+/g, ' ').trim())) return true;
            const noAccent = tl.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
            if (/^a[-\\s]?la[-\\s]?carte$/i.test(noAccent.trim())) return true;
            if (
                tl.length < 28 &&
                /a[-\\s]?la[-\\s]?carte/i.test(tl) &&
                !/hw\\s|hathway|budget|plus|pack|\\d{3,}/i.test(tl)
            )
                return true;
            return false;
        };

        const looksLikeDate = (t) => {
            const s = norm(t);
            if (s.length < 6 || s.length > 28) return false;
            if (/\\b\\d{1,2}-[A-Za-z]{3}-\\d{2,4}\\b/.test(s)) return true;
            if (/\\d{1,2}[-./]\\d{1,2}[-./]\\d{2,4}|\\d{4}[-./]\\d{1,2}[-./]\\d{1,2}/.test(s)) return true;
            return /\\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\s+\\d{1,2},?\\s*\\d{2,4}\\b/i.test(s);
        };

        const junkValidUpto = (t) => {
            const s = norm(t);
            const c = s.toLowerCase().replace(/\\s+/g, '');
            if (!s) return false;
            if (s.length > 36) return true;
            if (/plan\\s*name|sd\\s*hd|sdhd|total\\s*mrp|package\\s*name|hathway\\s*bouquet|gridview|valid\\s*upto$/i.test(s))
                return true;
            if (/planname|sdhd|totalmrp|package|^validupto$/i.test(c)) return true;
            const hdrHints = [/plan\\s*name/i, /lco\\s*price/i, /valid\\s*upto/i, /\\bstatus\\b/i, /total\\s*mrp/i];
            if (hdrHints.filter((rx) => rx.test(s)).length >= 3) return true;
            return false;
        };

        const junkStatusCell = (t) => {
            const s = norm(t).toLowerCase();
            if (!s || s.length > 36) return true;
            if (s === 'status' || s === 'stb status' || s === 'stbstatus') return true;
            if (/^view$/i.test(s)) return true;
            return /^plan\\s*name|valid\\s*upto|^sd$|^hd$|^mrp$/i.test(norm(t));
        };

        const inferValidUptoFromCells = (cells) => {
            for (const c of cells) {
                const t = norm(c.textContent || '');
                if (looksLikeDate(t) && !junkValidUpto(t)) return t;
            }
            return '';
        };

        const normKey = (s) => norm(s).toLowerCase().replace(/\\s+/g, ' ').trim();
        const sameAsPlanName = (vu, pname) => normKey(vu) === normKey(pname) && normKey(pname).length >= 2;
        const bouquetDateRe = /\\b\\d{1,2}-[A-Za-z]{3}-\\d{2,4}\\b/;
        const scanRowForBouquetDate = (cells) => {
            for (const c of cells) {
                const t = norm(c.textContent || '');
                const m = t.match(bouquetDateRe);
                if (m && looksLikeDate(m[0]) && !junkValidUpto(m[0])) return m[0];
            }
            return '';
        };
        const refineValidUpto = (vu, pname, cells) => {
            if (junkValidUpto(vu)) vu = inferValidUptoFromCells(cells);
            if (junkValidUpto(vu)) vu = '';
            if (sameAsPlanName(vu, pname)) vu = '';
            else if (vu && !looksLikeDate(vu)) vu = '';
            if (!vu) vu = inferValidUptoFromCells(cells);
            if (!vu) vu = scanRowForBouquetDate(cells);
            if (sameAsPlanName(vu, pname)) vu = '';
            return vu;
        };

        const inferStatusFromCells = (cells) => {
            for (const c of cells) {
                const t = norm(c.textContent || '');
                const tl = t.toLowerCase();
                if (!t || t.length > 24) continue;
                if (/^active$/i.test(t) || /^inactive$/i.test(t)) return t;
                if (/suspend|termination|disconnect/i.test(tl) && !/mrp|price/i.test(tl)) return t.slice(0, 24);
            }
            return '';
        };

        const dayFromBouquetValidUpto = (vu) => {
            const m = norm(vu).match(/\\b(\\d{1,2})-[A-Za-z]{3}-\\d{2,4}\\b/i);
            if (!m) return NaN;
            const d = parseInt(m[1], 10);
            return d >= 1 && d <= 31 ? d : NaN;
        };

        const extractLcoDigitsFromCell = (raw) => {
            const t = norm(raw);
            if (!t) return '';
            if (looksLikeDate(t) || bouquetDateRe.test(t)) return '';
            if (/\\d{1,2}[-./]\\d{1,2}[-./]\\d{2,4}|\\d{4}[-./]\\d{1,2}[-./]\\d{1,2}/.test(t)) return '';
            let rawDigits = '';
            const rsLead = t.match(/rs\\.?\\s*([\\d,.]+)/i);
            const rsTrail = t.match(/\\b([\\d]{1,7}(?:\\.[\\d]{1,2})?)\\s*rs\\.?/i);
            if (rsLead) rawDigits = (rsLead[1] || '').replace(/,/g, '');
            else if (rsTrail) rawDigits = (rsTrail[1] || '').replace(/,/g, '');
            else {
                const stripped = t.replace(/^rs\\.?\\s*/i, '').replace(/,/g, '').trim();
                if (/^[\\d]+(?:\\.[\\d]+)?$/.test(stripped)) rawDigits = stripped;
            }
            if (!rawDigits) return '';
            const n = parseFloat(rawDigits);
            if (!isFinite(n) || n < 1) return '';
            return rawDigits;
        };

        const inferBestPriceDigits = (cells, preferIdx = -1, skipIdx = -1) => {
            const tryText = (t) => {
                if (looksLikeDate(t) || bouquetDateRe.test(t) || junkStatusCell(t) || junkValidUpto(t))
                    return '';
                if (/\\d{1,2}[-./]\\d{1,2}[-./]\\d{2,4}|\\d{4}[-./]\\d{1,2}[-./]\\d{1,2}/.test(t))
                    return '';
                let raw = '';
                const rsLead = t.match(/rs\\.?\\s*([\\d,.]+)/i);
                const rsTrail = t.match(/\\b([\\d]{1,7}(?:\\.[\\d]{1,2})?)\\s*rs\\.?/i);
                if (rsLead) raw = (rsLead[1] || '').replace(/,/g, '');
                else if (rsTrail) raw = (rsTrail[1] || '').replace(/,/g, '');
                else {
                    const stripped = t.replace(/^rs\\.?\\s*/i, '').replace(/,/g, '').trim();
                    if (/^[\\d]+(?:\\.[\\d]+)?$/.test(stripped)) raw = stripped;
                }
                if (!raw) return '';
                const n = parseFloat(raw);
                if (!isFinite(n) || n < 1) return '';
                if (n < 50 && cells.length >= 8) return '';
                return raw;
            };
            if (preferIdx >= 0 && preferIdx < cells.length && preferIdx !== skipIdx) {
                const one = tryText(norm(cells[preferIdx].textContent || ''));
                if (one) return one;
            }
            let best = '';
            let bestN = -1;
            const order = [];
            for (let i = 0; i < cells.length; i++) order.push(i);
            if (preferIdx >= 0 && preferIdx < cells.length) {
                order.sort((a, b) => (a === preferIdx ? -1 : b === preferIdx ? 1 : a - b));
            }
            for (const i of order) {
                if (skipIdx >= 0 && i === skipIdx) continue;
                const raw = tryText(norm(cells[i].textContent || ''));
                if (!raw) continue;
                const n = parseFloat(raw);
                if (n > bestN) {
                    bestN = n;
                    best = raw;
                }
            }
            return best;
        };

        const resolveRowLco = (cells, lcoIdx, vuIdx, vu, outObj) => {
            const skipVu = vuIdx >= 0 ? vuIdx : -1;

            let lcoDigits = extractLcoDigitsFromCell(
                cells[lcoIdx] ? cells[lcoIdx].textContent || '' : ''
            );
            let lcoNum = lcoDigits ? parseFloat(lcoDigits) : NaN;
            let vuDay = dayFromBouquetValidUpto(vu);

            const suspiciousDay =
                isFinite(vuDay) && isFinite(lcoNum) && lcoNum === vuDay && vuDay >= 1 && vuDay <= 31;

            let needsFallback =
                !lcoDigits ||
                !/[0-9]/.test(lcoDigits) ||
                !isFinite(lcoNum) ||
                lcoNum < 10 ||
                suspiciousDay;

            if (needsFallback) {
                const preferIdx = suspiciousDay ? -1 : lcoIdx;
                const alt = inferBestPriceDigits(cells, preferIdx, skipVu);
                if (alt) {
                    lcoDigits = alt;
                    lcoNum = parseFloat(lcoDigits);
                }
            }

            vuDay = dayFromBouquetValidUpto(vu);
            const stillSuspicious =
                isFinite(vuDay) &&
                vuDay >= 1 &&
                vuDay <= 31 &&
                isFinite(lcoNum) &&
                lcoNum === vuDay;
            if (stillSuspicious) {
                const alt2 = inferBestPriceDigits(cells, -1, skipVu);
                if (alt2) {
                    const n2 = parseFloat(alt2);
                    if (isFinite(n2) && n2 !== lcoNum) {
                        lcoDigits = alt2;
                        lcoNum = n2;
                    }
                }
            }

            let lco = lcoDigits;
            vuDay = dayFromBouquetValidUpto(vu);
            const stillMatchesDay =
                isFinite(vuDay) &&
                vuDay >= 1 &&
                vuDay <= 31 &&
                isFinite(lcoNum) &&
                lcoNum === vuDay;

            if (
                (!isFinite(lcoNum) || lcoNum < 10 || lcoNum === 1 || stillMatchesDay) &&
                outObj.total_lco_price
            ) {
                const tot = parseFloat(String(outObj.total_lco_price).replace(/,/g, ''));
                if (isFinite(tot) && tot >= 10) {
                    lcoDigits = String(outObj.total_lco_price).replace(/,/g, '');
                    lco = lcoDigits;
                    lcoNum = tot;
                }
            }

            return { lco, lcoDigits, lcoNum };
        };

        const priceColumnIndex = (headers) => {
            const badNonLcoHeader = (h) =>
                /^\\s*sd\\s*$/i.test(h) ||
                (/\\bsd\\b/i.test(h) && !/\\blco\\b/i.test(h) && /total|mrp|price/i.test(h));
            let i = headers.findIndex(
                (h) =>
                    /^\\s*lco\\s*price\\s*(?:\\(?rs\\.?\\)?)?\\s*$/i.test(h) ||
                    /^\\s*lco\\s*(?:price|rate)\\s*$/i.test(h)
            );
            if (i >= 0) return i;
            i = headers.findIndex(
                (h) =>
                    /\\blco\\b/i.test(h) &&
                    (h.includes('price') || /\\brs\\.?\\b/i.test(h) || /^lco\\s*$/i.test(h)) &&
                    !/\\btotal\\b/i.test(h) &&
                    !/\\blco\\s*(id|no\\.?|number|code)\\b/i.test(h) &&
                    !badNonLcoHeader(h)
            );
            if (i >= 0) return i;
            i = headers.findIndex(
                (h) =>
                    !badNonLcoHeader(h) &&
                    (/total\\s*mrp|mrp\\s*\\(rs/.test(h) || (h.includes('total') && h.includes('mrp')))
            );
            if (i >= 0) return i;
            i = headers.findIndex(
                (h) =>
                    !badNonLcoHeader(h) &&
                    (h === 'mrp' || h === 'total') &&
                    h.length < 16 &&
                    !/^\\s*(sd|hd)\\s*$/i.test(h)
            );
            return i;
        };

        const validUpToColumnIndex = (headers) => {
            let i = headers.findIndex((h) => h.includes('valid') && (h.includes('upto') || h.includes('up to')));
            if (i >= 0) return i;
            i = headers.findIndex((h) => h.replace(/\\s/g, '') === 'validupto');
            if (i >= 0) return i;
            i = headers.findIndex((h) => h.includes('expiry') || h.includes('validity'));
            return i;
        };

        const statusColFromHeaders = (headers) => {
            for (let i = headers.length - 1; i >= 0; i--) {
                const h = (headers[i] || '').trim().toLowerCase();
                if (!h || h.includes('suspension')) continue;
                if (h === 'status' || h === 'stb status') return i;
            }
            return -1;
        };

        const parseHathwayBouquetGrid = (tbl) => {
            const rows = [...tbl.querySelectorAll('tr')];
            for (let ri = 0; ri < Math.min(rows.length, 40); ri++) {
                const hdrCells = [...rows[ri].querySelectorAll('th, td')];
                if (hdrCells.length < 5) continue;
                const thn = hdrCells.filter((c) => c.tagName === 'TH').length;
                const headers = hdrCells.map((c) => norm(c.textContent).toLowerCase());
                if (thn < 1 && !headers.some((h) => h === 'plan name' || h.includes('plan name'))) continue;
                const planIdx = headers.findIndex(
                    (h) => h === 'plan name' || (h.includes('plan') && h.includes('name'))
                );
                const lcoIdx = priceColumnIndex(headers);
                const vuIdx = validUpToColumnIndex(headers);
                const stCol = statusColFromHeaders(headers);
                if (planIdx < 0 || lcoIdx < 0 || stCol < 0) continue;

                const candidates = [];
                for (let j = ri + 1; j < rows.length; j++) {
                    const cells = [...rows[j].querySelectorAll('td, th')];
                    const need = Math.max(planIdx, lcoIdx, stCol);
                    const needVu = vuIdx >= 0 ? Math.max(need, vuIdx) : need;
                    if (cells.length <= needVu || cells.length <= need) continue;
                    const rowTxt = norm(rows[j].innerText || '');
                    if (/^\\s*total/i.test(rowTxt)) continue;
                    if (
                        /^(plan\\s*name|hathway\\s*bouquet)/i.test(rowTxt.slice(0, 40)) &&
                        rowTxt.length < 140
                    )
                        continue;
                    let pname = norm(cells[planIdx].innerText || cells[planIdx].textContent || '');
                    if (isAlacartePlanName(pname)) continue;
                    let vu =
                        vuIdx >= 0 && cells.length > vuIdx ? norm(cells[vuIdx].textContent || '') : '';
                    let rst = cells.length > stCol ? norm(cells[stCol].textContent || '') : '';
                    if (junkPlanCell(pname)) continue;
                    if (pname.length < 2) continue;
                    if (/^(plan name|sd|hd|total|mrp)$/i.test(pname)) continue;

                    vu = refineValidUpto(vu, pname, cells);

                    if (junkStatusCell(rst)) rst = inferStatusFromCells(cells);

                    const rl = resolveRowLco(cells, lcoIdx, vuIdx, vu, out);
                    let { lco, lcoDigits, lcoNum } = rl;
                    if (!/[0-9]/.test(String(lcoDigits || lco || ''))) continue;
                    if (!rst || /^view$/i.test(rst) || junkStatusCell(rst)) continue;

                    const vuN = norm(vu);
                    const bouquetDatePat = /\\b\\d{1,2}-[A-Za-z]{3}-\\d{2,4}\\b/i;
                    const goodBouquetDate = bouquetDatePat.test(vuN) && !junkValidUpto(vu);
                    const goodStatus = /^active$/i.test(rst) || /^inactive$/i.test(rst);
                    let score = 0;
                    if (goodStatus) score += 120;
                    if (goodBouquetDate) score += 80;
                    else if (looksLikeDate(vu) && !junkValidUpto(vu)) score += 40;
                    if (lcoNum >= 50) score += 30;
                    else if (lcoNum >= 10) score += 15;
                    if (pname.length >= 8) score += 5;
                    candidates.push({ pname, lco, lcoDigits, vu, rst, score });
                }
                if (!candidates.length) continue;
                candidates.sort((a, b) => b.score - a.score);
                const pick = candidates[0];
                out.plan_name = pick.pname;
                out.plan_lco_price = pick.lco.replace(/^rs\\.?\\s*/i, '').trim();
                out.plan_valid_upto = pick.vu;
                out.plan_status = pick.rst;
                out.main_tv_row_status = pick.rst;
                if (/^inactive$/i.test(pick.rst)) out.tv_table_status = 'INACTIVE';
                else if (/^active$/i.test(pick.rst)) out.tv_table_status = 'ACTIVE';
                return true;
            }
            return false;
        };

        const tryBouquetTables = (list) => {
            const low = (el) => norm(el.innerText || '').toLowerCase();
            const sorted = [...list].sort((a, b) => {
                const ha = low(a).includes('hathway bouquet');
                const hb = low(b).includes('hathway bouquet');
                if (ha && !hb) return -1;
                if (!ha && hb) return 1;
                return 0;
            });
            const labeled = sorted.filter((t) => low(t).includes('hathway bouquet'));
            const ordered = labeled.length
                ? [...labeled, ...sorted.filter((t) => !low(t).includes('hathway bouquet'))]
                : sorted;
            for (const tbl of ordered) {
                if (parseHathwayBouquetGrid(tbl)) return true;
            }
            return false;
        };

        let bouquetDone = tryBouquetTables(tables);
        if (!bouquetDone) {
            bouquetDone = tryBouquetTables([...document.querySelectorAll('table')]);
        }

        // Fallback: older grids — same column detection + junk filtering as main parser
        if (!out.plan_name) {
            for (const tbl of tables) {
                const tblBlob = norm(tbl.innerText || '');
                const tblLo = tblBlob.toLowerCase();
                if (
                    /a[-\\s]?la[-\\s]?carte/i.test(tblLo) &&
                    !tblLo.includes('hathway bouquet') &&
                    !/plan\\s*name/i.test(tblBlob.slice(0, 6000))
                )
                    continue;

                const rows = [...tbl.querySelectorAll('tr')];
                for (let ri = 0; ri < Math.min(rows.length, 24); ri++) {
                    const hdrCells = [...rows[ri].querySelectorAll('th, td')];
                    if (hdrCells.length < 3) continue;
                    const headers = hdrCells.map((c) => norm(c.textContent).toLowerCase());
                    const planIdx = headers.findIndex((h) =>
                        (h.includes('plan') && h.includes('name')) ||
                        h === 'package name' ||
                        h === 'bouquet name' ||
                        (h.includes('plan') && !h.includes('status') && !h.includes('valid'))
                    );
                    const lcoIdx = priceColumnIndex(headers);
                    if (planIdx < 0 || lcoIdx < 0) continue;
                    let vuIdx = validUpToColumnIndex(headers);
                    let stIdx = statusColFromHeaders(headers);
                    if (stIdx < 0) stIdx = statusColumnIndex(headers);

                    for (let j = ri + 1; j < rows.length; j++) {
                        const cells = [...rows[j].querySelectorAll('td, th')];
                        const idxNeed = [planIdx, lcoIdx];
                        if (vuIdx >= 0) idxNeed.push(vuIdx);
                        if (stIdx >= 0) idxNeed.push(stIdx);
                        const need = Math.max(...idxNeed);
                        if (cells.length <= need) continue;

                        let pname = norm(cells[planIdx].textContent || '');
                        if (isAlacartePlanName(pname)) continue;

                        let vu =
                            vuIdx >= 0 && cells.length > vuIdx ? norm(cells[vuIdx].textContent || '') : '';
                        let rst =
                            stIdx >= 0 && cells.length > stIdx ? norm(cells[stIdx].textContent || '') : '';

                        if (junkPlanCell(pname)) continue;
                        if (pname.length < 2) continue;
                        if (/^(plan name|sd|hd|total|mrp)$/i.test(pname)) continue;

                        vu = refineValidUpto(vu, pname, cells);

                        if (junkStatusCell(rst)) rst = inferStatusFromCells(cells);

                        const rl = resolveRowLco(cells, lcoIdx, vuIdx, vu, out);
                        let lco = rl.lco;
                        let lcoDigits = rl.lcoDigits;
                        let lcoNum = rl.lcoNum;
                        if (!/[0-9]/.test(String(lcoDigits || lco || ''))) continue;
                        if (!rst || /^view$/i.test(rst) || junkStatusCell(rst)) continue;

                        out.plan_name = pname;
                        out.plan_lco_price = lco.replace(/^rs\\.?\\s*/i, '').trim();
                        out.plan_valid_upto = vu;
                        out.plan_status = rst;
                        out.main_tv_row_status = rst;
                        if (/^inactive$/i.test(rst)) out.tv_table_status = 'INACTIVE';
                        else if (/^active$/i.test(rst)) out.tv_table_status = 'ACTIVE';
                        ri = rows.length;
                        break;
                    }
                    if (out.plan_name) break;
                }
                if (out.plan_name) break;
            }
        }

        return out;
    }""")


_JUNK_HATHWAY_TEXT = re.compile(
    r'Pack\s+Management|Customer\s+Details|Search\s+By|Distributor\s+Name|Enter\s+VCID|VC/Mac',
    re.I,
)

_HATHWAY_SCRAPE_HEADER_JUNK = re.compile(
    r'plan\s*name|sd\s*hd|sdhd|total\s*mrp|package\s*name|hathway\s*bouquet|a[-\s]?la[-\s]?carte',
    re.I,
)


def _hathway_sanitize_scraped_valid_upto(val):
    if val is None:
        return ''
    s = ' '.join(str(val).split()).strip()
    if not s:
        return ''
    compact = re.sub(r'[\s\-]+', '', s.lower())
    if _HATHWAY_SCRAPE_HEADER_JUNK.search(compact):
        return ''
    return s


def _hathway_sanitize_scraped_status(val):
    if val is None:
        return ''
    s = ' '.join(str(val).split()).strip()
    if not s:
        return ''
    if re.fullmatch(r'status|stb\s*status', s, re.I):
        return ''
    return s


def _hathway_clean_display_field(val, max_len=100):
    if val is None:
        return ''
    t = ' '.join(str(val).split()).strip()
    if len(t) > max_len or t.count('|') > 5:
        return ''
    if _JUNK_HATHWAY_TEXT.search(t):
        return ''
    return t


def _hathway_format_rs(val):
    """Digits from scraped price cell or total line → 'Rs. 135.00'."""
    if val is None or val == '':
        return ''
    s = str(val).strip().replace(',', '')
    m = re.search(r'(\d+\.?\d*)', s)
    if not m:
        return ''
    num = m.group(1)
    if '.' in num:
        return f'Rs. {num}'
    return f'Rs. {num}'


def _hathway_audit_norm_cmp_key(s):
    if s is None:
        return ''
    return ' '.join(str(s).split()).lower().strip()


def _hathway_extract_date_from_data_dict(data):
    """If valid_upto was wrongly copied (e.g. plan name), try DD-MON-YY date elsewhere in scrape."""
    if not isinstance(data, dict):
        return ''
    skip = {'plan_name', 'plan_valid_upto'}
    pat = re.compile(r'\b\d{1,2}-[A-Za-z]{3}-\d{2,4}\b', re.I)
    for k, v in data.items():
        if k in skip or not isinstance(v, str) or not v.strip():
            continue
        m = pat.search(v)
        if m:
            return m.group(0)
    return ''


def hathway_audit_to_dict(data, search_value, success=True, error=None):
    """Normalize Hathway scrape for Telegram (aligns loosely with Railtel audit keys)."""
    if not success:
        return {'success': False, 'error': error or 'Unknown', 'search_value': search_value, 'provider': 'hathway'}

    def _online_from_status_blob(blob):
        t = (blob or '').strip().lower()
        if t == 'active':
            return True
        if t == 'inactive':
            return False
        return (data.get('tv_table_status') or '').strip().upper() == 'ACTIVE'

    status_blob = (
        data.get('main_tv_row_status') or data.get('plan_status') or data.get('tv_table_status') or ''
    ).strip()
    status_blob = _hathway_sanitize_scraped_status(status_blob)

    is_active = _online_from_status_blob(status_blob)

    plan_raw = (data.get('plan_name') or '').strip()
    scheme_raw = (data.get('scheme_name') or '').strip()
    plan_clean = _hathway_clean_display_field(plan_raw, max_len=100)
    scheme_clean = _hathway_clean_display_field(scheme_raw, max_len=90)
    pack_for_bot = plan_clean or scheme_clean

    # Prefer the header-level Total LCO Price shown above the bouquet grid when present.
    lco_raw = (data.get('total_lco_price') or data.get('plan_lco_price') or '').strip()
    lco_display = _hathway_format_rs(lco_raw) or _hathway_format_rs(data.get('plan_lco_price'))

    status_display = _hathway_clean_display_field(status_blob, 40)
    vu_raw = _hathway_sanitize_scraped_valid_upto(data.get('plan_valid_upto'))
    if vu_raw and plan_clean and _hathway_audit_norm_cmp_key(vu_raw) == _hathway_audit_norm_cmp_key(plan_clean):
        vu_raw = _hathway_sanitize_scraped_valid_upto(_hathway_extract_date_from_data_dict(data)) or ''
    valid_upto_display = _hathway_clean_display_field(vu_raw, 32)

    fallback_expiry_raw = (data.get('plan_valid_upto') or '')[:32]
    if (
        plan_clean
        and fallback_expiry_raw.strip()
        and _hathway_audit_norm_cmp_key(fallback_expiry_raw) == _hathway_audit_norm_cmp_key(plan_clean)
    ):
        fallback_expiry_raw = ''

    lines = []
    if data.get('customer_name'):
        lines.append(f"Customer: {data['customer_name']}")
    if data.get('customer_ac'):
        lines.append(f"A/C: {data['customer_ac']}")
    if data.get('customer_mobile'):
        lines.append(f"Mobile: {data['customer_mobile']}")
    if data.get('vc_id'):
        lines.append(f"VC ID: {data['vc_id']}")
    if data.get('stb_no'):
        lines.append(f"STB NO: {data['stb_no']}")

    summary = ' | '.join(lines) if lines else 'Pack Management details'

    return {
        'success': True,
        'provider': 'hathway',
        'search_value': search_value,
        'matched_cid': data.get('vc_id') or search_value,
        'is_online': is_active,
        'session_days': 0,
        'downtime': summary,
        'mac': data.get('stb_no') or '',
        'expiry': valid_upto_display or fallback_expiry_raw,
        'hathway_tv_status': status_display or (data.get('tv_table_status') or ''),
        'hathway_total_lco_price': (data.get('total_lco_price') or '').replace(',', '') if data.get('total_lco_price') else '',
        'hathway_total_customer_price': (data.get('total_customer_price') or '').replace(',', '') if data.get('total_customer_price') else '',
        'hathway_scheme_name': scheme_clean or scheme_raw[:90] if scheme_raw else '',
        'hathway_plan_name': pack_for_bot,
        'hathway_plan_lco_price': _hathway_clean_display_field(data.get('plan_lco_price'), 24),
        'hathway_plan_status': _hathway_clean_display_field(
            _hathway_sanitize_scraped_status(data.get('plan_status')), 40
        ),
        'hathway_action_buttons': [],
        'hathway_bot_lco_display': lco_display,
        'hathway_valid_upto': valid_upto_display,
    }


def _hathway_click_named_tab(page, label_re):
    """Tabs may be role=tab or links/spans (ASP.NET)."""
    try:
        page.get_by_role('tab', name=label_re).first.click(timeout=4000, force=True)
        return True
    except Exception:
        pass
    try:
        page.locator('a, span, li, td').filter(has_text=label_re).first.click(timeout=5000, force=True)
        return True
    except Exception:
        return False


def _hathway_clear_modal_markers(page):
    """Remove temporary markers used to anchor Playwright to the Change Service Status box."""
    for fr in page.frames:
        try:
            fr.evaluate(
                """() => {
                    document.querySelectorAll('[data-hathway-bot-modal]').forEach((e) => {
                        e.removeAttribute('data-hathway-bot-modal');
                    });
                }"""
            )
        except Exception:
            pass


def _hathway_change_service_modal_locator(page, miss_screenshot='hathway_deactivate_modal_miss.png'):
    """
    Hathway 'Change Service Status' is often not in role=dialog / .modal.show. We anchor from the
    Playwright-resolved title node (handles split text across children), walk up the DOM for a
    container that still shows the title plus Confirm (and usually Reason / STB / select), and tag
    it for a stable locator. Polls while the popup finishes rendering.
    """
    deadline = time.monotonic() + 35.0
    last_err = None
    while time.monotonic() < deadline:
        try:
            titles = page.get_by_text(re.compile(r'Change\s+Service\s+Status', re.I))
            n = titles.count()
            if n == 0:
                page.wait_for_timeout(450)
                continue
        except Exception as e:
            last_err = e
            page.wait_for_timeout(450)
            continue

        _hathway_clear_modal_markers(page)
        anchored = False
        for ti in range(min(n, 12)):
            tloc = titles.nth(ti)
            try:
                tloc.wait_for(state='visible', timeout=4000)
            except Exception as e:
                last_err = e
                continue
            try:
                ok = tloc.evaluate(
                    """(start) => {
                        const norm = (s) => (s || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ');
                        const hasTitle = (root) =>
                            /change\\s+service\\s+status/i.test(norm(root.innerText || '').slice(0, 12000));
                        const hasConfirm = (root) =>
                            [...root.querySelectorAll(
                                'input[type="submit"], input[type="button"], button, a'
                            )].some((e) => {
                                if (!e || !e.offsetParent) return false;
                                const v = ((e.value || '') + (e.textContent || ''))
                                    .replace(/\\u00a0/g, ' ')
                                    .trim();
                                if (/^cancel$/i.test(v) || /^close$/i.test(v)) return false;
                                return /^confirm$/i.test(v) || /^\\s*confirm\\s*$/i.test(v)
                                    || /confirm/i.test(v);
                            });
                        const hasReasonish = (root) => {
                            if (root.querySelector('select')) return true;
                            const t = norm(root.innerText || '').slice(0, 12000).toLowerCase();
                            return /\\breason\\b/.test(t) || /stb\\s*number/.test(t) || /select\\s*reason/i.test(t);
                        };
                        let n = start;
                        for (let depth = 0; depth < 32 && n; depth++) {
                            if (hasTitle(n) && hasConfirm(n) && hasReasonish(n)) {
                                n.setAttribute('data-hathway-bot-modal', '1');
                                return true;
                            }
                            n = n.parentElement;
                        }
                        n = start;
                        for (let depth = 0; depth < 32 && n; depth++) {
                            if (hasTitle(n) && hasConfirm(n)) {
                                n.setAttribute('data-hathway-bot-modal', '1');
                                return true;
                            }
                            n = n.parentElement;
                        }
                        return false;
                    }"""
                )
                if ok:
                    anchored = True
                    break
            except Exception as e:
                last_err = e

        if not anchored:
            for fr in page.frames:
                try:
                    found = fr.evaluate(
                        """() => {
                            document.querySelectorAll('[data-hathway-bot-modal]').forEach((e) => {
                                e.removeAttribute('data-hathway-bot-modal');
                            });
                            const titleRe = /change\\s+service\\s+status/i;
                            const sels = [
                                '[id*="Modal" i]',
                                '[id*="modal" i]',
                                '[id*="Popup" i]',
                                '[class*="modal" i]',
                                '[class*="Modal" i]',
                                '[class*="popup" i]',
                                '.ajax__modal_popup',
                                'table[role="presentation"]',
                            ];
                            for (const sel of sels) {
                                let nodes = [];
                                try {
                                    nodes = [...document.querySelectorAll(sel)];
                                } catch (e) {
                                    continue;
                                }
                                for (const el of nodes) {
                                    if (!el || !el.offsetParent) continue;
                                    const txt = (el.innerText || '').replace(/\\u00a0/g, ' ').slice(0, 14000);
                                    if (!titleRe.test(txt)) continue;
                                    const hasCtl = el.querySelector(
                                        'select, input[type="submit"], input[type="button"], button'
                                    );
                                    if (!hasCtl) continue;
                                    el.setAttribute('data-hathway-bot-modal', '1');
                                    return true;
                                }
                            }
                            const divs = [...document.querySelectorAll('div')];
                            const scored = [];
                            for (const d of divs) {
                                if (!d.offsetParent) continue;
                                const txt = (d.innerText || '').replace(/\\u00a0/g, ' ').slice(0, 14000);
                                if (!titleRe.test(txt)) continue;
                                const r = d.getBoundingClientRect();
                                const area = r.width * r.height;
                                if (r.width < 100 || r.height < 60 || area > 3e6) continue;
                                if (!d.querySelector('select, input, button')) continue;
                                scored.push({ d, len: txt.length, area });
                            }
                            scored.sort((a, b) => a.len - b.len || a.area - b.area);
                            if (scored.length) {
                                scored[0].d.setAttribute('data-hathway-bot-modal', '1');
                                return true;
                            }
                            return false;
                        }"""
                    )
                    if found:
                        anchored = True
                        break
                except Exception as e:
                    last_err = e

        if anchored:
            for fr in page.frames:
                try:
                    loc = fr.locator('[data-hathway-bot-modal="1"]').first
                    if loc.count() == 0:
                        continue
                    loc.wait_for(state='visible', timeout=10000)
                    return loc
                except Exception as e:
                    last_err = e
            _hathway_clear_modal_markers(page)

        page.wait_for_timeout(450)

    try:
        page.screenshot(path=miss_screenshot, full_page=True)
    except Exception:
        pass
    raise RuntimeError(
        'Could not anchor Change Service Status dialog (portal markup may differ). '
        f'Screenshot: {miss_screenshot}. Last error: {last_err!r}'
    )


def _hathway_click_deactivate_main_tv(page):
    cleanup_hathway_ui(page)
    candidates = [
        page.locator('input[type="button"][value="Deactivate"]'),
        page.locator('input[type="submit"][value="Deactivate"]'),
        page.locator('input[type="button"][value="Deactivate" i]'),
        page.locator('input[type="submit"][value="Deactivate" i]'),
        page.get_by_role('button', name=re.compile(r'^\s*Deactivate\s*$', re.I)),
    ]
    for loc in candidates:
        try:
            if loc.count() == 0:
                continue
            btn = loc.first
            if not btn.is_visible(timeout=2500):
                continue
            btn.scroll_into_view_if_needed(timeout=5000)
            btn.click(timeout=10000, force=True)
            return True
        except Exception:
            continue
    try:
        clicked = page.evaluate(
            """() => {
                const nodes = [...document.querySelectorAll('input[type="button"], input[type="submit"], button')];
                for (const el of nodes) {
                    const v = ((el.value || el.textContent || '') + '').trim();
                    if (!/^deactivate$/i.test(v) || !el.offsetParent) continue;
                    el.click();
                    return true;
                }
                return false;
            }"""
        )
        if clicked:
            return True
    except Exception:
        pass
    return False


def _hathway_select_reason_change_service_modal(page, modal, reason_label, flow='deactivate'):
    """
    Modal 'Change Service Status': pick reason (native select, hidden select, or Select2), wait 2s
    after opening where applicable, then Confirm.

    flow: 'deactivate' (payment not received…) or 'activate' (payment received / promise to pay…).
    """
    reason_label = (reason_label or '').strip()
    flow = (flow or 'deactivate').strip().lower()
    if flow not in ('deactivate', 'activate'):
        flow = 'deactivate'
    page.wait_for_timeout(400)
    open_ms = int(os.getenv('HATHWAY_DEACTIVATE_REASON_OPEN_MS', '2000'))

    opt_re = (
        re.compile(r'Payment\s+not\s+received', re.I)
        if flow == 'deactivate'
        else re.compile(
            r'Payment\s+received\s+from\s+customer\s*/\s*Promise\s+to\s+pay|'
            r'Payment\s+received\s+from\s+customer|Promise\s+to\s+pay|'
            r'Customer\s+agreed\s+to\s+make\s+payment|agreed\s+to\s+make\s+payment|customer.*agreed.*payment',
            re.I,
        )
    )
    fallback_labels = (
        (reason_label, 'Payment not received by customer', 'Payment not received')
        if flow == 'deactivate'
        else (
            reason_label,
            'Payment received from customer/Promise to pay',
            'Payment received from customer / Promise to pay',
            'payment received from customer/promise to pay',
            'Customer agreed to make payment',
            'customer agreed to make payment',
            'Customer agreed to make Payment',
        )
    )

    sel = modal.locator('select').first
    if sel.count() > 0:
        try:
            sel.wait_for(state='attached', timeout=5000)
        except Exception:
            pass
        visible = False
        try:
            visible = sel.is_visible(timeout=800)
        except Exception:
            visible = False

        if visible:
            sel.click(timeout=5000, force=True)
            page.wait_for_timeout(open_ms)
        else:
            sel.click(timeout=5000, force=True)
            page.wait_for_timeout(open_ms)

        picked_text = sel.evaluate(
            """(el, args) => {
                const [preferred, flow] = args;
                const pref = (preferred || '').toLowerCase().trim();
                const score = (t) => {
                    const x = (t || '').toLowerCase();
                    if (pref && x.includes(pref)) return 4;
                    if (flow === 'activate') {
                        if (x.includes('payment received') && x.includes('customer') && x.includes('promise')) return 4;
                        if (x.includes('payment received') && x.includes('customer')) return 3;
                        if (x.includes('promise to pay')) return 3;
                        if (x.includes('promise') && x.includes('pay')) return 2;
                        if (x.includes('payment') && x.includes('received')) return 2;
                        if (x.includes('agreed') && x.includes('payment') && x.includes('customer')) return 2;
                        if (x.includes('agreed') && x.includes('payment')) return 1;
                        if (x.includes('agreed') && x.includes('customer')) return 1;
                        return 0;
                    }
                    if (x.includes('payment') && x.includes('received') && x.includes('customer')) return 3;
                    if (x.includes('payment') && x.includes('received')) return 2;
                    return 0;
                };
                let bestI = -1;
                let bestS = -1;
                for (let i = 0; i < el.options.length; i++) {
                    const t = (el.options[i].text || '').trim();
                    const s = score(t);
                    if (s > bestS) { bestS = s; bestI = i; }
                }
                if (bestI < 0 || bestS <= 0) return '';
                el.selectedIndex = bestI;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return (el.options[bestI].text || '').trim();
            }""",
            [reason_label, flow],
        )
        if not picked_text:
            for opt in fallback_labels:
                if not opt:
                    continue
                try:
                    sel.select_option(label=opt, timeout=4000)
                    picked_text = opt
                    break
                except Exception:
                    continue
        if not picked_text:
            raise RuntimeError(f'Could not select {flow} reason (native <select> options mismatch).')
    else:
        sel2 = modal.locator(
            '.select2-selection, span.select2-selection__rendered, .select2-container a'
        ).first
        if sel2.count() > 0:
            try:
                sel2.click(timeout=8000, force=True)
            except Exception:
                modal.locator('.select2-container').first.click(timeout=8000, force=True)
            page.wait_for_timeout(open_ms)
            opt = page.locator('.select2-results__option, li.select2-results__option').filter(
                has_text=opt_re
            ).first
            opt.wait_for(state='visible', timeout=12000)
            opt.click(timeout=8000, force=True)
        else:
            try:
                modal.get_by_text(re.compile(r'Select\s+Reason', re.I)).first.click(
                    timeout=8000, force=True
                )
            except Exception:
                modal.locator('td, label, div').filter(has_text=re.compile(r'Reason', re.I)).first.click(
                    timeout=5000, force=True
                )
            page.wait_for_timeout(open_ms)
            opt = page.get_by_role('option', name=opt_re).first
            if opt.count() == 0:
                opt = page.locator('option, li, a, div, span').filter(has_text=opt_re).first
            opt.wait_for(state='visible', timeout=12000)
            opt.click(timeout=8000, force=True)

    page.wait_for_timeout(350)
    for conf in (
        modal.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
        modal.locator('input[type="submit"][value*="Confirm" i]').first,
        modal.locator('input[type="button"][value*="Confirm" i]').first,
    ):
        try:
            if conf.count() == 0:
                continue
            conf.click(timeout=10000, force=True)
            break
        except Exception:
            continue
    else:
        raise RuntimeError('Confirm button not found on Change Service Status dialog.')


def _hathway_click_confirm_service_change_are_you_sure(page, flow='deactivate'):
    """Second dialog after first Confirm — 'Are you sure…' for activate or deactivate."""
    flow = (flow or 'deactivate').lower()
    if flow == 'activate':
        patterns = [
            re.compile(r'This will activate the service', re.I),
            re.compile(r'activate the service', re.I),
            re.compile(r'Are you sure.*activat', re.I),
        ]
        box_kw = re.compile(r'activat|reactivat|resume', re.I)
    else:
        patterns = [
            re.compile(r'This will deactivate the service', re.I),
            re.compile(r'Are you sure.*deactivat', re.I),
        ]
        box_kw = re.compile(r'deactivat', re.I)

    found = False
    last_err = None
    for pat in patterns:
        try:
            page.get_by_text(pat).first.wait_for(state='visible', timeout=12000)
            found = True
            break
        except Exception as e:
            last_err = e
    if not found:
        raise RuntimeError(f'Confirmation popup not found ({flow}): {last_err!r}')

    page.wait_for_timeout(400)
    box = page.locator(
        '[role="dialog"], .modal.in, .modal.show, .modal, .ui-dialog, [data-hathway-bot-modal="1"]'
    ).filter(has_text=box_kw).filter(has_text=re.compile(r'sure', re.I)).first
    if box.count() == 0:
        for conf in (
            page.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
            page.locator('input[type="submit"][value*="Confirm" i]').first,
            page.locator('input[type="button"][value*="Confirm" i]').first,
        ):
            try:
                if conf.count() and conf.is_visible(timeout=1500):
                    conf.click(timeout=10000, force=True)
                    return
            except Exception:
                continue
        return
    for conf in (
        box.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
        box.locator('input[type="submit"][value*="Confirm" i]').first,
        box.locator('input[type="button"][value*="Confirm" i]').first,
    ):
        try:
            if conf.count() == 0:
                continue
            conf.click(timeout=10000, force=True)
            return
        except Exception:
            continue


def _hathway_click_ok_service_change_complete_message(page, flow='deactivate'):
    """Final 'Message' dialog — OK after success line.

    Avoids broad regexes on full page text (e.g. ``activation`` matches inside ``Subscription``).
    Prefer Hathway popup label ``#MasterBody_lblPopupResponse`` when present.
    """
    flow = (flow or 'deactivate').lower()
    if flow == 'activate':
        text_check = re.compile(
            r'Service activated successfully|Service\s+activated\s+successfully|'
            r'resumed successfully|reactivated successfully',
            re.I,
        )
        fallback_text = re.compile(r'Service activated successfully', re.I)
    else:
        text_check = re.compile(
            r'Service deactivated successfully|Service suspend status completed|deactivated successfully',
            re.I,
        )
        fallback_text = re.compile(
            r'Service deactivated successfully|Service suspend status completed',
            re.I,
        )

    popup = page.locator('#MasterBody_lblPopupResponse')
    try:
        if popup.count() > 0:
            popup.first.wait_for(state='visible', timeout=90000)
        else:
            page.get_by_text(fallback_text).first.wait_for(state='visible', timeout=90000)
    except Exception:
        page.get_by_text(fallback_text).first.wait_for(state='visible', timeout=90000)

    def _ok_candidates():
        dlg = page.get_by_role('dialog').filter(has_text=text_check).last
        if dlg.count() > 0:
            yield dlg.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).first
            yield dlg.locator('input[type="button"][value="OK"]').first
            yield dlg.locator('input[type="submit"][value="OK"]').first
        for sel in (
            page.locator('.ui-dialog:visible').last.locator(
                'button, input[type="button"], input[type="submit"]'
            ).filter(has_text=re.compile(r'^\s*OK\s*$', re.I)).first,
            page.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).last,
            page.locator('input[type="button"][value="OK"]').last,
            page.locator('input[type="submit"][value="OK"]').last,
            page.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).first,
            page.locator('input[type="button"][value="OK"]').first,
            page.locator('input[type="submit"][value="OK"]').first,
        ):
            yield sel

    for loc in _ok_candidates():
        try:
            if loc.count() == 0:
                continue
            if loc.is_visible(timeout=2000):
                loc.click(timeout=8000, force=True)
                return True
        except Exception:
            continue
    page.evaluate("""() => {
        const lbl = document.querySelector('#MasterBody_lblPopupResponse');
        const clickOkIn = (root) => {
            if (!root) return false;
            const nodes = root.querySelectorAll('button, input[type="button"], input[type="submit"]');
            for (const b of nodes) {
                const t = (b.value || b.textContent || '').trim();
                if (!/^ok$/i.test(t) || !b.offsetParent) continue;
                b.click();
                return true;
            }
            return false;
        };
        if (lbl && lbl.offsetParent) {
            let n = lbl;
            for (let i = 0; i < 12 && n; i++, n = n.parentElement) {
                if (clickOkIn(n)) return true;
                if (n.classList && n.classList.contains('ui-dialog')) break;
                if (n.getAttribute && n.getAttribute('role') === 'dialog') break;
            }
        }
        const btns = [...document.querySelectorAll('button, input[type="button"], input[type="submit"]')];
        const vis = btns.filter(b => b.offsetParent);
        const ok = vis.slice().reverse().find(b => /^\\s*ok\\s*$/i.test((b.value || b.textContent || '').trim()));
        if (ok) { ok.click(); return true; }
        return false;
    }""")
    return True


def _hathway_click_activate_main_tv(page):
    cleanup_hathway_ui(page)
    candidates = [
        page.locator('input[type="button"][value="Activate"]'),
        page.locator('input[type="submit"][value="Activate"]'),
        page.locator('input[type="button"][value="Activate" i]'),
        page.locator('input[type="submit"][value="Activate" i]'),
        page.get_by_role('button', name=re.compile(r'^\s*Activate\s*$', re.I)),
    ]
    for loc in candidates:
        try:
            if loc.count() == 0:
                continue
            btn = loc.first
            if not btn.is_visible(timeout=2500):
                continue
            btn.scroll_into_view_if_needed(timeout=5000)
            btn.click(timeout=10000, force=True)
            return True
        except Exception:
            continue
    try:
        clicked = page.evaluate(
            """() => {
                const nodes = [...document.querySelectorAll('input[type="button"], input[type="submit"], button')];
                for (const el of nodes) {
                    const v = ((el.value || el.textContent || '') + '').trim();
                    if (!/^activate$/i.test(v) || !el.offsetParent) continue;
                    el.click();
                    return true;
                }
                return false;
            }"""
        )
        if clicked:
            return True
    except Exception:
        pass
    return False


def hathway_temp_deactivate_stb(page, stb_id, reason_label=None):
    """
    Pack Management → search STB → Main TV → Deactivate → reason → confirms → OK.

    reason_label defaults from env HATHWAY_DEACTIVATE_REASON
    (default: Payment not received by customer).
    """
    stb_id = (stb_id or '').strip()
    if not stb_id:
        return {'success': False, 'error': 'Empty STB / VC id', 'provider': 'hathway', 'search_value': ''}

    reason_label = (
        (reason_label or os.getenv('HATHWAY_DEACTIVATE_REASON') or 'Payment not received by customer').strip()
    )
    post_confirm_ms = int(os.getenv('HATHWAY_DEACTIVATE_POST_CONFIRM_MS', '10000'))

    try:
        cleanup_hathway_ui(page)
        _hathway_click_vc_mac_search_mode(page)
        page.wait_for_timeout(300)

        _hathway_fill_pack_search(page, stb_id)
        _hathway_click_search(page)
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            page.wait_for_load_state('domcontentloaded', timeout=15000)
        page.wait_for_timeout(1200)
        cleanup_hathway_ui(page)

        body = page.locator('body').inner_text(timeout=15000)
        portal_msg = _hathway_search_portal_user_message(body)
        if portal_msg:
            return {'success': False, 'error': portal_msg, 'provider': 'hathway', 'search_value': stb_id}

        if re.search(r'no\s+record|not\s+found|invalid|no\s+match', body, re.I):
            return {
                'success': False,
                'error': 'No matching subscriber for this STB / VC id.',
                'provider': 'hathway',
                'search_value': stb_id,
            }

        if not _hathway_ensure_main_tv_tab(page):
            return {
                'success': False,
                'error': 'Could not open Main TV tab.',
                'provider': 'hathway',
                'search_value': stb_id,
            }
        page.wait_for_timeout(600)
        cleanup_hathway_ui(page)

        if not _hathway_click_deactivate_main_tv(page):
            try:
                page.screenshot(path='hathway_deactivate_no_button.png')
            except Exception:
                pass
            return {
                'success': False,
                'error': 'Deactivate control not found (STB may already be inactive, or UI changed).',
                'provider': 'hathway',
                'search_value': stb_id,
            }

        page.wait_for_timeout(int(os.getenv('HATHWAY_DEACTIVATE_MODAL_WAIT_MS', '2800')))
        try:
            modal = _hathway_change_service_modal_locator(page)
            _hathway_select_reason_change_service_modal(page, modal, reason_label, flow='deactivate')

            page.wait_for_timeout(800)
            _hathway_click_confirm_service_change_are_you_sure(page, 'deactivate')

            page.wait_for_timeout(max(0, post_confirm_ms))

            _hathway_click_ok_service_change_complete_message(page, 'deactivate')
            page.wait_for_timeout(600)
            cleanup_hathway_ui(page)

            return {
                'success': True,
                'provider': 'hathway',
                'search_value': stb_id,
                'matched_cid': stb_id,
                'message': 'Hathway reported service deactivated (temp).',
            }
        finally:
            _hathway_clear_modal_markers(page)
    except Exception as e:
        try:
            page.screenshot(path='hathway_deactivate_error.png')
        except Exception:
            pass
        print(f'⚠️ Hathway temp deactivate error: {e}')
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}


def check_hathway_temp_deactivate(stb_id, account_id=None):
    """Login, Pack Management, temp deactivate STB, close browser."""
    playwright, browser, page = launch_hathway_browser()
    try:
        if not login_hathway(page, account_id=account_id):
            return {
                'success': False,
                'error': 'Hathway login failed — check credentials and CAPTCHA.',
                'provider': 'hathway',
                'search_value': stb_id,
            }
        return hathway_temp_deactivate_stb(page, stb_id)
    except Exception as e:
        try:
            page.screenshot(path='hathway_deactivate_fatal.png')
        except Exception:
            pass
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}
    finally:
        close_hathway_browser(playwright, browser)


def hathway_temp_activate_stb(page, stb_id, reason_label=None):
    """
    Pack Management → search STB → Main TV → Activate → reason → confirms → OK.

    reason_label defaults from env HATHWAY_ACTIVATE_REASON
    (default: Payment received from customer/Promise to pay).
    """
    stb_id = (stb_id or '').strip()
    if not stb_id:
        return {'success': False, 'error': 'Empty STB / VC id', 'provider': 'hathway', 'search_value': ''}

    reason_label = (
        (reason_label or os.getenv('HATHWAY_ACTIVATE_REASON') or 'Payment received from customer/Promise to pay').strip()
    )
    post_confirm_ms = int(
        os.getenv('HATHWAY_ACTIVATE_POST_CONFIRM_MS', os.getenv('HATHWAY_DEACTIVATE_POST_CONFIRM_MS', '10000'))
    )

    try:
        cleanup_hathway_ui(page)
        _hathway_click_vc_mac_search_mode(page)
        page.wait_for_timeout(300)

        _hathway_fill_pack_search(page, stb_id)
        _hathway_click_search(page)
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            page.wait_for_load_state('domcontentloaded', timeout=15000)
        page.wait_for_timeout(1200)
        cleanup_hathway_ui(page)

        body = page.locator('body').inner_text(timeout=15000)
        portal_msg = _hathway_search_portal_user_message(body)
        if portal_msg:
            return {'success': False, 'error': portal_msg, 'provider': 'hathway', 'search_value': stb_id}

        if re.search(r'no\s+record|not\s+found|invalid|no\s+match', body, re.I):
            return {
                'success': False,
                'error': 'No matching subscriber for this STB / VC id.',
                'provider': 'hathway',
                'search_value': stb_id,
            }

        if not _hathway_ensure_main_tv_tab(page):
            return {
                'success': False,
                'error': 'Could not open Main TV tab.',
                'provider': 'hathway',
                'search_value': stb_id,
            }
        page.wait_for_timeout(600)
        cleanup_hathway_ui(page)

        if not _hathway_click_activate_main_tv(page):
            try:
                page.screenshot(path='hathway_activate_no_button.png')
            except Exception:
                pass
            return {
                'success': False,
                'error': 'Activate control not found (STB may already be active, or UI changed).',
                'provider': 'hathway',
                'search_value': stb_id,
            }

        page.wait_for_timeout(
            int(os.getenv('HATHWAY_ACTIVATE_MODAL_WAIT_MS', os.getenv('HATHWAY_DEACTIVATE_MODAL_WAIT_MS', '2800')))
        )
        try:
            modal = _hathway_change_service_modal_locator(page, miss_screenshot='hathway_activate_modal_miss.png')
            _hathway_select_reason_change_service_modal(page, modal, reason_label, flow='activate')

            page.wait_for_timeout(800)
            _hathway_click_confirm_service_change_are_you_sure(page, 'activate')

            page.wait_for_timeout(max(0, post_confirm_ms))

            _hathway_click_ok_service_change_complete_message(page, 'activate')
            page.wait_for_timeout(600)
            cleanup_hathway_ui(page)

            return {
                'success': True,
                'provider': 'hathway',
                'search_value': stb_id,
                'matched_cid': stb_id,
                'message': 'STB Activated Successfully.',
            }
        finally:
            _hathway_clear_modal_markers(page)
    except Exception as e:
        try:
            page.screenshot(path='hathway_activate_error.png')
        except Exception:
            pass
        print(f'⚠️ Hathway temp activate error: {e}')
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}


def check_hathway_temp_activate(stb_id, account_id=None):
    """Login, Pack Management, temp activate STB, close browser."""
    playwright, browser, page = launch_hathway_browser()
    try:
        if not login_hathway(page, account_id=account_id):
            return {
                'success': False,
                'error': 'Hathway login failed — check credentials and CAPTCHA.',
                'provider': 'hathway',
                'search_value': stb_id,
            }
        return hathway_temp_activate_stb(page, stb_id)
    except Exception as e:
        try:
            page.screenshot(path='hathway_activate_fatal.png')
        except Exception:
            pass
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}
    finally:
        close_hathway_browser(playwright, browser)


def _hathway_remove_pack_step_ms():
    """Pause between major UI steps (default slow for debugging; set 0 or 300 when stable)."""
    return max(0, int(os.getenv('HATHWAY_REMOVE_PACK_STEP_MS', '2500')))


def _hathway_bouquet_menu_wait_ms():
    """Wait after clicking bouquet ▼ before looking for CANCEL (default slow)."""
    return max(0, int(os.getenv('HATHWAY_BOUQUET_MENU_WAIT_MS', '4500')))


def _hathway_cancel_menu_poll_ms():
    """How long to keep polling for the CANCEL menu item after opening the row menu."""
    return max(1500, int(os.getenv('HATHWAY_CANCEL_MENU_POLL_MS', '20000')))


def _hathway_terminate_after_pack_settle_ms():
    """After pack removal, wait for Main TV grid / Terminate to refresh (AJAX)."""
    return max(0, int(os.getenv('HATHWAY_TERMINATE_AFTER_PACK_MS', '2800')))


def _hathway_terminate_click_contexts(page):
    """Documents that may host the Terminate control (same iframe as bouquet, or other frames)."""
    out = []
    seen = set()
    for ctx in _hathway_pack_dom_roots(page):
        if id(ctx) in seen:
            continue
        seen.add(id(ctx))
        out.append(ctx)
    try:
        for fr in list(page.frames):
            try:
                if fr.is_detached():
                    continue
            except Exception:
                continue
            if id(fr) in seen:
                continue
            seen.add(id(fr))
            out.append(fr)
    except Exception:
        pass
    return out if out else [page]


def _hathway_bouquet_menu_post_open_scroll_px():
    """After ▼ opens, scroll document down slightly so R/C/C is not clipped at viewport bottom (0 disables)."""
    return max(0, int(os.getenv('HATHWAY_BOUQUET_MENU_POST_OPEN_SCROLL_PX', '140')))


def _hathway_nudge_viewport_after_bouquet_menu_open(page):
    """Move viewport down a bit so the downward menu has room; clamped to scroll range."""
    dy = _hathway_bouquet_menu_post_open_scroll_px()
    if not dy:
        return
    try:
        page.evaluate(
            """(px) => {
                const y = window.scrollY || document.documentElement.scrollTop || 0;
                const h = document.documentElement.scrollHeight || document.body.scrollHeight || 0;
                const vh = window.innerHeight || 0;
                const maxBy = Math.max(0, h - vh - y - 2);
                window.scrollBy(0, Math.min(px, maxBy));
            }""",
            dy,
        )
    except Exception:
        try:
            page.evaluate(f"() => window.scrollBy(0, {dy})")
        except Exception:
            pass
    settle = max(120, int(os.getenv('HATHWAY_BOUQUET_MENU_POST_OPEN_SCROLL_WAIT_MS', '400')))
    page.wait_for_timeout(settle)


def _hathway_remove_pack_step_pause(page):
    ms = _hathway_remove_pack_step_ms()
    if ms:
        page.wait_for_timeout(ms)


def _hathway_pack_dom_roots(page):
    """Pack grid may live in an iframe — return every document (page + frames) that contains the bouquet table."""
    tbl_re = re.compile(r'Hathway\s*Bouquet|Plan\s*Name', re.I)
    roots = []
    seen = set()

    def _add(ctx):
        if ctx is None or id(ctx) in seen:
            return
        try:
            if ctx.locator('table').filter(has_text=tbl_re).count() > 0:
                roots.append(ctx)
                seen.add(id(ctx))
        except Exception:
            pass

    _add(page)
    try:
        for fr in list(page.frames):
            try:
                if fr.is_detached():
                    continue
            except Exception:
                continue
            _add(fr)
    except Exception:
        pass
    if not roots:
        roots = [page]
    else:
        try:
            if page not in roots:
                roots.insert(0, page)
        except TypeError:
            pass
    return roots


def _hathway_viewport_click_at(ctx, pos):
    """Click in *ctx*'s document at viewport (client) coordinates — correct for iframes; do not use page.mouse."""
    if not isinstance(pos, dict):
        return False
    x, y = pos.get('x'), pos.get('y')
    if x is None or y is None:
        return False
    try:
        return bool(
            ctx.evaluate(
                """([xv, yv]) => {
                    const el = document.elementFromPoint(xv, yv);
                    if (!el) return false;
                    const chain = [];
                    for (let z = el; z; z = z.parentElement) {
                        chain.push(z);
                        if (chain.length > 28) break;
                    }
                    for (const z of chain) {
                        if (typeof z.click === 'function') {
                            try {
                                z.click();
                                return true;
                            } catch (e) {}
                        }
                    }
                    return false;
                }""",
                [float(x), float(y)],
            )
        )
    except Exception:
        return False


def _hathway_pw_click_bouquet_cancel(ctx):
    """Pick the CANCEL control nearest the Active row action column (Playwright; iframe-safe)."""
    try:
        tbl = ctx.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet|Plan\s*Name', re.I)).first
        if tbl.count() == 0:
            return False
        row = tbl.locator('tr').filter(has_text=re.compile(r'\bActive\b', re.I)).first
        if row.count() == 0:
            return False
        acell = row.locator('td').last
        if acell.count() == 0:
            return False
        ab = acell.bounding_box()
        if not ab:
            return False
        ax = ab['x'] + ab['width'] / 2
        ay = ab['y'] + ab['height'] / 2
        factories = (
            lambda c: c.get_by_text(re.compile(r'^\s*CANCEL\s*$', re.I)),
            lambda c: c.get_by_role('link', name=re.compile(r'^\s*CANCEL\s*$', re.I)),
            lambda c: c.get_by_role('button', name=re.compile(r'^\s*CANCEL\s*$', re.I)),
            lambda c: c.locator('a, button, span, div, input').filter(has_text=re.compile(r'^\s*CANCEL\s*$', re.I)),
        )
        for factory in factories:
            loc = factory(ctx)
            try:
                n = loc.count()
            except Exception:
                continue
            if n == 0:
                continue
            best_i = -1
            best_s = 1e9
            for i in range(min(n, 50)):
                el = loc.nth(i)
                try:
                    b = el.bounding_box()
                    if not b:
                        continue
                    if b['width'] > 520 or b['height'] > 110:
                        continue
                    mx = b['x'] + b['width'] / 2
                    my = b['y'] + b['height'] / 2
                    if abs(mx - ax) > 320:
                        continue
                    score = abs(mx - ax)
                    if b['y'] > ab['y'] - 2:
                        score += 75
                    if b['y'] + b['height'] <= ab['y'] + 12:
                        score -= 35
                    if score < best_s:
                        best_s = score
                        best_i = i
                except Exception:
                    continue
            if best_i < 0:
                continue
            try:
                tgt = loc.nth(best_i)
                tgt.scroll_into_view_if_needed(timeout=5000)
                tgt.click(timeout=10000, force=True)
                return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _hathway_try_cancel_playwright_on_roots(roots, page):
    """Returns True on success, 'retry' if Renew mis-click, False if nothing clicked."""
    for ctx in roots:
        if not _hathway_pw_click_bouquet_cancel(ctx):
            continue
        page.wait_for_timeout(450)
        if _hathway_bouquet_renew_misclick_visible(page):
            _hathway_dismiss_renew_misclick(page)
            if not _hathway_bouquet_row_menu_visible(page):
                _hathway_click_bouquet_action_dropdown(page)
            return 'retry'
        return True
    return False

def _hathway_pw_click_bouquet_renew(ctx):
    """Pick the RENEW control nearest the Active row action column (Playwright; iframe-safe)."""
    try:
        tbl = ctx.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet|Plan\s*Name', re.I)).first
        if tbl.count() == 0:
            return False
        row = tbl.locator('tr').filter(has_text=re.compile(r'\bActive\b', re.I)).first
        if row.count() == 0:
            return False
        acell = row.locator('td').last
        if acell.count() == 0:
            return False
        ab = acell.bounding_box()
        if not ab:
            return False
        ax = ab['x'] + ab['width'] / 2
        renew_re = re.compile(r'^\s*RENEW\s*$', re.I)
        factories = (
            lambda c: c.get_by_text(renew_re),
            lambda c: c.get_by_role('link', name=renew_re),
            lambda c: c.get_by_role('button', name=renew_re),
            lambda c: c.locator('a, button, span, div, input').filter(has_text=renew_re),
        )
        for factory in factories:
            loc = factory(ctx)
            try:
                n = loc.count()
            except Exception:
                continue
            if n == 0:
                continue
            best_i = -1
            best_s = 1e9
            for i in range(min(n, 50)):
                el = loc.nth(i)
                try:
                    b = el.bounding_box()
                    if not b:
                        continue
                    if b['width'] > 520 or b['height'] > 110:
                        continue
                    mx = b['x'] + b['width'] / 2
                    if abs(mx - ax) > 320:
                        continue
                    score = abs(mx - ax)
                    if b['y'] > ab['y'] - 2:
                        score += 75
                    if b['y'] + b['height'] <= ab['y'] + 12:
                        score -= 35
                    if score < best_s:
                        best_s = score
                        best_i = i
                except Exception:
                    continue
            if best_i < 0:
                continue
            try:
                tgt = loc.nth(best_i)
                tgt.scroll_into_view_if_needed(timeout=5000)
                tgt.click(timeout=10000, force=True)
                return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _hathway_cancel_pack_prompt_visible(page):
    """True if cancel-pack confirmation sheet opened (mis-click when aiming for RENEW)."""
    try:
        body = page.locator('body').inner_text(timeout=3000)[:12000]
    except Exception:
        return False
    return bool(
        re.search(r'this\s+will\s+cancel\s+the\s+plan|cancel\s+the\s+plan\s+with\s+following', body, re.I)
    )


def _hathway_try_renew_playwright_on_roots(roots, page):
    """Return True when renew dialog visible; retry reopen menu after cancel-pack mis-click."""
    for ctx in roots:
        if not _hathway_pw_click_bouquet_renew(ctx):
            continue
        page.wait_for_timeout(450)
        if _hathway_bouquet_renew_misclick_visible(page):
            return True
        if _hathway_cancel_pack_prompt_visible(page):
            _hathway_dismiss_renew_misclick(page)
            if not _hathway_bouquet_row_menu_visible(page):
                _hathway_click_bouquet_action_dropdown(page)
            return 'retry'
        return True
    return False




def _hathway_bouquet_row_menu_visible(page):
    js = """() => {
                    const t = (document.body.innerText || '').replace(/\\s+/g, ' ');
                    return /\\bRENEW\\b/i.test(t) && /\\bCANCEL\\b/i.test(t) && /\\bCHANGE\\b/i.test(t);
                }"""
    for ctx in _hathway_pack_dom_roots(page):
        try:
            if bool(ctx.evaluate(js)):
                return True
        except Exception:
            continue
    return False


def _hathway_bouquet_renew_misclick_visible(page):
    """True if a Renew pack / subscription dialog likely opened instead of Cancel pack."""
    try:
        body = page.locator('body').inner_text(timeout=3000)[:14000]
    except Exception:
        return False
    if re.search(r'cancel\s*pack|remove\s*pack|sure\s*you\s*want\s*to\s*cancel', body, re.I):
        return False
    return bool(
        re.search(
            r'renew\s*my\s*pack|renew\s*subscription|pack\s*renewal|renew\s*plan\b|'
            r'would\s*you\s*like\s*to\s*renew|select\s*renew|subscribe\s*to\s*renew|'
            r'enable\s*(?:auto\s*)?renew|renewal\s*request',
            body,
            re.I,
        )
    )


def _hathway_dismiss_renew_misclick(page):
    try:
        page.keyboard.press('Escape')
    except Exception:
        pass
    page.wait_for_timeout(250)
    cleanup_hathway_ui(page)


def _hathway_click_bouquet_action_dropdown(page):
    """Main TV → Hathway Bouquet first Active row → action cell (▼) to open RENEW/CANCEL/CHANGE menu."""
    menu_wait = _hathway_bouquet_menu_wait_ms()
    _hathway_remove_pack_step_pause(page)

    def _js_click_main(ctx_p):
        return ctx_p.evaluate(
            """() => {
            const norm = (s) =>
                (s || '')
                    .replace(/\\u00a0/g, ' ')
                    .replace(/\\s+/g, ' ')
                    .trim()
                    .toLowerCase();
            const visible = (el) => {
                if (!el || !el.getBoundingClientRect) return false;
                let e = el;
                for (let d = 0; d < 16 && e; d++) {
                    const st = window.getComputedStyle(e);
                    if (st.display === 'none' || st.visibility === 'hidden' || Number.parseFloat(st.opacity || '1') === 0) {
                        return false;
                    }
                    e = e.parentElement;
                }
                const r = el.getBoundingClientRect();
                return r.width > 1 && r.height > 1;
            };
            const fireClick = (el) => {
                if (!el || !visible(el)) return false;
                try {
                    el.dispatchEvent(
                        new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window })
                    );
                    el.dispatchEvent(
                        new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window })
                    );
                    el.dispatchEvent(
                        new MouseEvent('click', { bubbles: true, cancelable: true, view: window })
                    );
                } catch (e) {}
                if (typeof el.click === 'function') el.click();
                return true;
            };
            const clickCellControl = (cell) => {
                if (!cell || !visible(cell)) return false;
                const order = [
                    'input[type="image"]',
                    'input[type="button"]',
                    'input[type="submit"]',
                    'a[href*="__doPostBack" i]',
                    'a[href^="javascript:"]',
                    'a[href]',
                    'button',
                    'img',
                    '[onclick]',
                    'span',
                    'div',
                ];
                for (const sel of order) {
                    for (const n of cell.querySelectorAll(sel)) {
                        if (!visible(n)) continue;
                        const tag = (n.tagName || '').toLowerCase();
                        const r = n.getBoundingClientRect();
                        if ((tag === 'span' || tag === 'div') && r.width * r.height > 12000) continue;
                        if (fireClick(n)) return true;
                    }
                }
                return fireClick(cell);
            };

            const tables = [...document.querySelectorAll('table')].filter(visible);
            const scored = tables
                .map((tbl) => {
                    const tx = norm(tbl.innerText);
                    let sc = 0;
                    if (tx.includes('hathway bouquet')) sc = 3;
                    else if (tx.includes('plan name') && tx.includes('lco')) sc = 2;
                    else if (tx.includes('plan name')) sc = 1;
                    return { tbl, sc };
                })
                .filter((x) => x.sc > 0)
                .sort((a, b) => b.sc - a.sc);

            for (const { tbl } of scored) {
                const rows = [...tbl.querySelectorAll('tr')];
                let planIdx = -1;
                let statusIdx = -1;
                let actionIdx = -1;
                let headerRow = -1;
                for (let ri = 0; ri < Math.min(rows.length, 40); ri++) {
                    const cells = [...rows[ri].querySelectorAll('th, td')];
                    if (cells.length < 4) continue;
                    const headers = cells.map((c) => norm(c.textContent));
                    const hasPlan = headers.some(
                        (h) => h === 'plan name' || (h.includes('plan') && h.includes('name'))
                    );
                    if (!hasPlan) continue;
                    planIdx = headers.findIndex((h) => h === 'plan name' || (h.includes('plan') && h.includes('name')));
                    if (planIdx < 0) planIdx = 0;
                    statusIdx = headers.findIndex((h) => h === 'status' || /^stb\\s*status$/.test(h));
                    if (statusIdx < 0) {
                        statusIdx = headers.findIndex((h) => h.includes('status') && !h.includes('suspension'));
                    }
                    if (statusIdx < 0) statusIdx = headers.length - 2;
                    actionIdx = headers.findIndex((h) => h === 'action' || h === 'actions');
                    if (actionIdx < 0) actionIdx = cells.length - 1;
                    headerRow = ri;
                    for (let j = headerRow + 1; j < rows.length; j++) {
                        const cs = [...rows[j].querySelectorAll('td')];
                        if (cs.length <= Math.max(planIdx, statusIdx, actionIdx)) continue;
                        const rowT = norm(rows[j].innerText || '');
                        if (/^\\s*total/i.test(rowT)) continue;
                        if (rowT.length < 25 && /plan name|lco price|valid upto|hathway bouquet/i.test(rowT)) continue;
                        const st = norm(cs[statusIdx]?.textContent || '');
                        if (!/\\bactive\\b/i.test(st)) continue;
                        const pn = norm(cs[planIdx]?.textContent || '');
                        if (!pn || pn.length < 2 || /^(plan name|total|mrp)$/i.test(pn)) continue;
                        if (clickCellControl(cs[actionIdx])) return true;
                    }
                    break;
                }
            }
            return false;
        }"""
        )

    def _js_click_last_cell(ctx_p):
        return ctx_p.evaluate(
            """() => {
                const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const visible = (el) => {
                    if (!el || !el.getBoundingClientRect) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width < 2 || r.height < 2) return false;
                    const st = window.getComputedStyle(el);
                    return st.display !== 'none' && st.visibility !== 'hidden';
                };
                const tables = [...document.querySelectorAll('table')].filter((t) => t.offsetParent);
                for (const tbl of tables) {
                    if (!norm(tbl.innerText).includes('hathway bouquet') && !norm(tbl.innerText).includes('plan name')) continue;
                    const rows = [...tbl.querySelectorAll('tr')];
                    for (const r of rows) {
                        if (!/active/i.test(r.innerText || '')) continue;
                        const tds = [...r.querySelectorAll('td')];
                        if (tds.length < 3) continue;
                        const last = tds[tds.length - 1];
                        const el =
                            last.querySelector('input, a, button, img, [onclick]') || last;
                        if (visible(el)) {
                            el.click();
                            return true;
                        }
                    }
                }
                return false;
            }"""
        )

    def _pw_click_action_cell(ctx_p):
        try:
            tbl = ctx_p.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet', re.I)).first
            if tbl.count() == 0:
                tbl = (
                    ctx_p.locator('table')
                    .filter(has_text=re.compile(r'Plan\s*Name', re.I))
                    .filter(has_text=re.compile(r'LCO', re.I))
                    .first
                )
            if tbl.count() == 0:
                return False
            tbl.scroll_into_view_if_needed(timeout=10000)
            row = tbl.locator('tr').filter(has_text=re.compile(r'\bActive\b', re.I)).first
            if row.count() == 0:
                return False
            row.scroll_into_view_if_needed(timeout=8000)
            for inner in (
                row.locator('td').last.locator(
                    'input[type="image"], input[type="button"], input[type="submit"], a, button, img'
                ),
                row.locator('td').last,
            ):
                try:
                    if inner.count() == 0:
                        continue
                    el = inner.first
                    if el.is_visible(timeout=2000):
                        el.click(timeout=10000, force=True)
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    for attempt in range(1, 4):
        cleanup_hathway_ui(page)
        roots = _hathway_pack_dom_roots(page)
        for ctx in roots:
            try:
                tbl = ctx.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet|Plan\s*Name', re.I)).first
                if tbl.count():
                    tbl.scroll_into_view_if_needed(timeout=10000)
            except Exception:
                pass
        _hathway_remove_pack_step_pause(page)

        clicked = False
        for ctx in roots:
            if _js_click_main(ctx):
                clicked = True
                break
        if not clicked:
            for ctx in roots:
                if _js_click_last_cell(ctx):
                    clicked = True
                    break
        if not clicked:
            for ctx in roots:
                if _pw_click_action_cell(ctx):
                    clicked = True
                    break
        if not clicked:
            _hathway_remove_pack_step_pause(page)
            continue

        page.wait_for_timeout(menu_wait)
        if _hathway_bouquet_row_menu_visible(page):
            return True

        for ctx in roots:
            if _pw_click_action_cell(ctx):
                page.wait_for_timeout(menu_wait)
                if _hathway_bouquet_row_menu_visible(page):
                    return True
                break

        _hathway_remove_pack_step_pause(page)

    return False


def _hathway_expired_plan_add_popup_visible(page):
    """After ▼ on an Expired bouquet row: portal shows a prominent **ADD** control."""
    add_lab = re.compile(r'^\s*ADD\s*$', re.I)
    for ctx in _hathway_modal_search_roots(page):
        try:
            for loc in (
                ctx.get_by_role('button', name=add_lab),
                ctx.get_by_role('link', name=add_lab),
                ctx.locator('input[type="button"], input[type="submit"]').filter(has_text=add_lab),
            ):
                if loc.count() > 0:
                    try:
                        if loc.first.is_visible(timeout=600):
                            return True
                    except Exception:
                        continue
        except Exception:
            continue
    try:
        return bool(
            page.evaluate(
                """() => {
                    const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                    const nodes = [...document.querySelectorAll(
                        'button, a, input[type="button"], input[type="submit"], span'
                    )];
                    for (const el of nodes) {
                        if (!el.offsetParent) continue;
                        const t = norm(el.value || el.innerText || el.textContent || '');
                        if (!/^ADD$/i.test(t)) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width < 14 || r.height < 8) continue;
                        return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


def _hathway_click_manage_expired_plans_main_tv(page):
    """Main TV → **Manage Expired Plans** (toolbar under Action Required)."""
    cleanup_hathway_ui(page)
    label = re.compile(r'Manage\s+Expired\s+Plans', re.I)
    for ctx in _hathway_modal_search_roots(page):
        try:
            for loc in (
                ctx.get_by_role('button', name=label),
                ctx.get_by_role('link', name=label),
                ctx.locator('input[type="button"], input[type="submit"]').filter(has_text=label),
            ):
                if loc.count() == 0:
                    continue
                el = loc.first
                if el.is_visible(timeout=2800):
                    el.scroll_into_view_if_needed(timeout=6000)
                    el.click(timeout=12000, force=True)
                    return True
        except Exception:
            continue
    try:
        return bool(
            page.evaluate(
                """() => {
                    const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const want = /manage\\s+expired\\s+plans/;
                    for (const el of document.querySelectorAll(
                        'input[type="button"], input[type="submit"], button, a, span[onclick], td[onclick]'
                    )) {
                        if (!el.offsetParent) continue;
                        const t = norm(el.value || el.innerText || el.textContent || '');
                        if (!want.test(t)) continue;
                        try {
                            el.scrollIntoView({ block: 'center', inline: 'nearest' });
                        } catch (e) {}
                        el.click();
                        return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


def _hathway_click_quick_recharge(page):
    """Click **Quick Recharge** under Action Required.

    Portal renders this as a styled tile (often ``div`` / ``span`` / ``td``, not ``<button>``).
    When two tiles exist (toolbar wraps), prefer the **lower / second-row** hit (largest viewport ``top``).
    """
    cleanup_hathway_ui(page)
    loose = re.compile(r'Quick\s+Recharge', re.I)
    exactish = re.compile(r'^\s*Quick\s+Recharge\s*$', re.I)

    def _pw_collect_click(ctx):
        ranked = []
        groups = (
            ctx.get_by_role('button', name=loose),
            ctx.get_by_role('link', name=loose),
            ctx.locator('input[type="button"], input[type="submit"]').filter(has_text=loose),
            ctx.locator('[role="button"]').filter(has_text=loose),
            ctx.locator('div, span, td, li, a').filter(has_text=exactish),
        )
        for grp in groups:
            try:
                n = grp.count()
                for i in range(min(n, 18)):
                    el = grp.nth(i)
                    try:
                        if not el.is_visible(timeout=950):
                            continue
                        box = el.bounding_box()
                        if not box or box['width'] < 4 or box['height'] < 4:
                            continue
                        ranked.append((box['y'], box['x'], el))
                    except Exception:
                        continue
            except Exception:
                continue
        ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
        for _, __, el in ranked:
            try:
                el.scroll_into_view_if_needed(timeout=6000)
                el.click(timeout=12000, force=True)
                return True
            except Exception:
                continue
        return False

    for ctx in _hathway_modal_search_roots(page):
        if _pw_collect_click(ctx):
            return True

    try:
        return bool(
            page.evaluate(
                """() => {
                    const norm = (s) =>
                        (s || '')
                            .replace(/\\u00a0/g, ' ')
                            .replace(/\\s+/g, ' ')
                            .trim()
                            .toLowerCase();
                    const visible = (el) => {
                        if (!el || !el.getBoundingClientRect) return false;
                        let e = el;
                        for (let d = 0; d < 14 && e; d++) {
                            const st = window.getComputedStyle(e);
                            if (
                                st.display === 'none' ||
                                st.visibility === 'hidden' ||
                                Number.parseFloat(st.opacity || '1') === 0
                            ) {
                                return false;
                            }
                            e = e.parentElement;
                        }
                        const r = el.getBoundingClientRect();
                        return r.width > 3 && r.height > 3;
                    };
                    const labelOk = (el) => {
                        const raw = norm(el.innerText || el.textContent || el.value || '');
                        if (raw.length > 48) return false;
                        return /^quick\\s+recharge$/.test(raw);
                    };
                    const hits = [];
                    for (const el of document.querySelectorAll(
                        'button, a, input[type="button"], input[type="submit"], span, div, td, li, [role="button"], label'
                    )) {
                        if (!visible(el)) continue;
                        if (!labelOk(el)) continue;
                        const r = el.getBoundingClientRect();
                        hits.push({ el, top: r.top, left: r.left });
                    }
                    hits.sort((a, b) => b.top - a.top || b.left - a.left);
                    for (const { el } of hits) {
                        try {
                            el.scrollIntoView({ block: 'center', inline: 'nearest' });
                        } catch (e) {}
                        try {
                            el.dispatchEvent(
                                new MouseEvent('click', { bubbles: true, cancelable: true, view: window })
                            );
                        } catch (e) {}
                        if (typeof el.click === 'function') el.click();
                        return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


def _hathway_quick_recharge_click_plan_details_submit(page):
    """Plan Details area → primary **submit** (paired with Reset); avoids unrelated submits."""
    cleanup_hathway_ui(page)
    page.wait_for_timeout(450)
    submit_lab = re.compile(r'^\s*submit\s*$', re.I)
    for ctx in _hathway_modal_search_roots(page):
        try:
            for loc in (
                ctx.get_by_role('button', name=submit_lab),
                ctx.locator('input[type="submit"], input[type="button"]').filter(has_text=submit_lab),
            ):
                if loc.count() == 0:
                    continue
                for i in range(min(loc.count(), 14)):
                    el = loc.nth(i)
                    try:
                        if el.is_visible(timeout=1400):
                            el.scroll_into_view_if_needed(timeout=6000)
                            el.click(timeout=12000, force=True)
                            return True
                    except Exception:
                        continue
        except Exception:
            continue
    try:
        return bool(
            page.evaluate(
                """() => {
                    const norm = (s) =>
                        (s || '')
                            .replace(/\\u00a0/g, ' ')
                            .replace(/\\s+/g, ' ')
                            .trim()
                            .toLowerCase();
                    const visible = (el) => {
                        if (!el || !el.offsetParent) return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 2 && r.height > 2;
                    };
                    const inPlanRegion = (el) => {
                        let n = el;
                        for (let i = 0; i < 18 && n; i++, n = n.parentElement) {
                            const t = norm(n.innerText || '').slice(0, 1400);
                            if (/plan\\s*details/.test(t) || /hathway\\s*bouquet/.test(t)) return true;
                        }
                        return false;
                    };
                    const hits = [];
                    for (const el of document.querySelectorAll(
                        'button, input[type="submit"], input[type="button"], a'
                    )) {
                        if (!visible(el)) continue;
                        const t = norm(el.value || el.innerText || el.textContent || '');
                        if (t !== 'submit') continue;
                        const r = el.getBoundingClientRect();
                        hits.push({ el, r, ok: inPlanRegion(el) });
                    }
                    hits.sort((a, b) => {
                        if (a.ok !== b.ok) return a.ok ? -1 : 1;
                        return b.r.bottom - a.r.bottom;
                    });
                    const pick = hits[0];
                    if (!pick) return false;
                    try {
                        pick.el.scrollIntoView({ block: 'center', inline: 'nearest' });
                    } catch (e) {}
                    pick.el.click();
                    return true;
                }"""
            )
        )
    except Exception:
        return False


def _hathway_manage_expired_click_tab(page, pattern):
    """Click a Pack Management tab by regex name (Customer Details / Main TV); best-effort."""
    try:
        tab = page.get_by_role('tab', name=pattern).first
        if tab.count() > 0 and tab.is_visible(timeout=2400):
            tab.click(timeout=9000, force=True)
            page.wait_for_timeout(500)
            cleanup_hathway_ui(page)
            return True
    except Exception:
        pass
    return False


def _hathway_scroll_hathway_bouquet_heading_into_view(page):
    """Ensure the Hathway Bouquet section is scrolled into view on *page*."""
    try:
        loc = page.get_by_text(re.compile(r'Hathway\s*Bouquet', re.I)).first
        if loc.count() > 0:
            loc.scroll_into_view_if_needed(timeout=12000)
            return True
    except Exception:
        pass
    return False


def _hathway_focus_manage_expired_plans_page(page):
    """Use newly opened tab/window if the portal opens Manage Expired Plans separately."""
    try:
        ctx = page.context
    except Exception:
        return page
    page.wait_for_timeout(600)
    try:
        ordered = list(ctx.pages)
    except Exception:
        return page
    for p in reversed(ordered):
        try:
            if p.is_closed():
                continue
            u = (p.url or '').lower()
            if 'expired' in u or 'manageexpired' in u.replace('_', '').replace('-', ''):
                p.bring_to_front()
                return p
        except Exception:
            continue
    page.wait_for_timeout(1400)
    try:
        ordered = list(ctx.pages)
    except Exception:
        return page
    for p in reversed(ordered):
        try:
            if p.is_closed():
                continue
            loc = p.get_by_text(re.compile(r'Manage\s+Expired\s+Plans', re.I))
            if loc.count() > 0:
                try:
                    loc.first.wait_for(state='visible', timeout=4000)
                    p.bring_to_front()
                    return p
                except Exception:
                    continue
        except Exception:
            continue
    return page


def _hathway_click_expired_bouquet_action_dropdown(page):
    """Manage Expired Plans → Hathway Bouquet **Expired** row → Action ▼ (opens ADD tooltip)."""
    menu_wait = _hathway_bouquet_menu_wait_ms()
    _hathway_remove_pack_step_pause(page)

    def _js_click_main(ctx_p):
        return ctx_p.evaluate(
            """() => {
            const norm = (s) =>
                (s || '')
                    .replace(/\\u00a0/g, ' ')
                    .replace(/\\s+/g, ' ')
                    .trim()
                    .toLowerCase();
            const visible = (el) => {
                if (!el || !el.getBoundingClientRect) return false;
                let e = el;
                for (let d = 0; d < 16 && e; d++) {
                    const st = window.getComputedStyle(e);
                    if (st.display === 'none' || st.visibility === 'hidden' || Number.parseFloat(st.opacity || '1') === 0) {
                        return false;
                    }
                    e = e.parentElement;
                }
                const r = el.getBoundingClientRect();
                return r.width > 1 && r.height > 1;
            };
            const fireClick = (el) => {
                if (!el || !visible(el)) return false;
                try {
                    el.dispatchEvent(
                        new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window })
                    );
                    el.dispatchEvent(
                        new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window })
                    );
                    el.dispatchEvent(
                        new MouseEvent('click', { bubbles: true, cancelable: true, view: window })
                    );
                } catch (e) {}
                if (typeof el.click === 'function') el.click();
                return true;
            };
            const rectArea = (el) => {
                const r = el.getBoundingClientRect();
                return Math.max(1, r.width) * Math.max(1, r.height);
            };
            /** Expired-row ▼ is usually a tiny ASP.NET image hyperlink (<a><img>), not a native button. */
            const clickExpiredRowDropdownCell = (cell) => {
                if (!cell || !visible(cell)) return false;
                const tryEl = (el) => !!(el && visible(el) && fireClick(el));

                const anchors = [...cell.querySelectorAll('a[href]')].filter(visible);
                anchors.sort((a, b) => rectArea(a) - rectArea(b));
                for (const a of anchors) {
                    const href = ((a.getAttribute('href') || '') + '').toLowerCase();
                    const hasImg = !!a.querySelector('img');
                    if (
                        hasImg ||
                        href.includes('__dopostback') ||
                        href.startsWith('javascript:')
                    ) {
                        if (tryEl(a)) return true;
                    }
                }

                const imgsInAnchors = new Set();
                for (const a of anchors) {
                    for (const im of a.querySelectorAll('img')) imgsInAnchors.add(im);
                }
                const loneImgs = [...cell.querySelectorAll('img')].filter(
                    (im) => visible(im) && !imgsInAnchors.has(im) && rectArea(im) <= 14000
                );
                loneImgs.sort((a, b) => rectArea(a) - rectArea(b));
                for (const im of loneImgs) {
                    if (tryEl(im)) return true;
                }

                for (const inp of cell.querySelectorAll('input[type="image"]')) {
                    if (tryEl(inp)) return true;
                }

                const order = [
                    'input[type="button"]',
                    'input[type="submit"]',
                    'button',
                    'img',
                    '[onclick]',
                    'span',
                    'div',
                ];
                for (const sel of order) {
                    for (const n of cell.querySelectorAll(sel)) {
                        if (!visible(n)) continue;
                        const tag = (n.tagName || '').toLowerCase();
                        const r = n.getBoundingClientRect();
                        if ((tag === 'span' || tag === 'div') && r.width * r.height > 12000) continue;
                        if (fireClick(n)) return true;
                    }
                }
                return fireClick(cell);
            };

            const tables = [...document.querySelectorAll('table')].filter(visible);
            const scored = tables
                .map((tbl) => {
                    const tx = norm(tbl.innerText);
                    let sc = 0;
                    if (tx.includes('hathway bouquet')) sc = 3;
                    else if (tx.includes('plan name') && tx.includes('lco')) sc = 2;
                    else if (tx.includes('plan name')) sc = 1;
                    return { tbl, sc };
                })
                .filter((x) => x.sc > 0)
                .sort((a, b) => b.sc - a.sc);

            for (const { tbl } of scored) {
                const rows = [...tbl.querySelectorAll('tr')];
                let planIdx = -1;
                let statusIdx = -1;
                let actionIdx = -1;
                let headerRow = -1;
                for (let ri = 0; ri < Math.min(rows.length, 40); ri++) {
                    const cells = [...rows[ri].querySelectorAll('th, td')];
                    if (cells.length < 4) continue;
                    const headers = cells.map((c) => norm(c.textContent));
                    const hasPlan = headers.some(
                        (h) => h === 'plan name' || (h.includes('plan') && h.includes('name'))
                    );
                    if (!hasPlan) continue;
                    planIdx = headers.findIndex((h) => h === 'plan name' || (h.includes('plan') && h.includes('name')));
                    if (planIdx < 0) planIdx = 0;
                    statusIdx = headers.findIndex((h) => h === 'status' || /^stb\\s*status$/.test(h));
                    if (statusIdx < 0) {
                        statusIdx = headers.findIndex((h) => h.includes('status') && !h.includes('suspension'));
                    }
                    if (statusIdx < 0) statusIdx = headers.length - 2;
                    actionIdx = headers.findIndex((h) => h === 'action' || h === 'actions');
                    if (actionIdx < 0) actionIdx = cells.length - 1;
                    headerRow = ri;
                    for (let j = headerRow + 1; j < rows.length; j++) {
                        const cs = [...rows[j].querySelectorAll('td')];
                        if (cs.length < 2) continue;
                        const rowT = norm(rows[j].innerText || '');
                        if (!/\\bexpired\\b/i.test(rowT)) continue;
                        if (/^\\s*total/i.test(rowT)) continue;
                        if (rowT.length < 20 && /plan name|lco price|valid upto|hathway bouquet/i.test(rowT)) continue;
                        const n = cs.length;
                        const planI = Math.min(Math.max(planIdx, 0), n - 1);
                        let actionI = actionIdx >= 0 && actionIdx < n ? actionIdx : n - 1;
                        const pn = norm(cs[planI]?.textContent || '');
                        const pnBad = !pn || pn.length < 2 || /^(plan name|total|mrp)$/i.test(pn);
                        if (pnBad && rowT.length < 40) continue;
                        const tryIdx = [];
                        const push = (x) => {
                            if (x >= 0 && x < n && !tryIdx.includes(x)) tryIdx.push(x);
                        };
                        push(actionI);
                        push(n - 1);
                        push(n - 2);
                        push(n - 3);
                        for (const ci of tryIdx) {
                            if (clickExpiredRowDropdownCell(cs[ci])) return true;
                        }
                    }
                    break;
                }
            }
            return false;
        }"""
        )

    def _js_click_last_cell(ctx_p):
        return ctx_p.evaluate(
            """() => {
                const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const visible = (el) => {
                    if (!el || !el.getBoundingClientRect) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width < 2 || r.height < 2) return false;
                    const st = window.getComputedStyle(el);
                    return st.display !== 'none' && st.visibility !== 'hidden';
                };
                const rectArea = (el) => {
                    const r = el.getBoundingClientRect();
                    return Math.max(1, r.width) * Math.max(1, r.height);
                };
                const tables = [...document.querySelectorAll('table')].filter((t) => t.offsetParent);
                for (const tbl of tables) {
                    if (!norm(tbl.innerText).includes('hathway bouquet') && !norm(tbl.innerText).includes('plan name')) continue;
                    const rows = [...tbl.querySelectorAll('tr')];
                    for (const r of rows) {
                        if (!/expired/i.test(r.innerText || '')) continue;
                        const tds = [...r.querySelectorAll('td')];
                        if (tds.length < 3) continue;
                        for (let ti = tds.length - 1; ti >= Math.max(0, tds.length - 5); ti--) {
                            const cell = tds[ti];
                            const anchors = [...cell.querySelectorAll('a[href]')].filter(visible);
                            anchors.sort((a, b) => rectArea(a) - rectArea(b));
                            for (const a of anchors) {
                                const href = ((a.getAttribute('href') || '') + '').toLowerCase();
                                if (
                                    a.querySelector('img') ||
                                    href.includes('__dopostback') ||
                                    href.startsWith('javascript:')
                                ) {
                                    a.click();
                                    return true;
                                }
                            }
                            for (const inp of cell.querySelectorAll('input[type="image"]')) {
                                if (visible(inp)) {
                                    inp.click();
                                    return true;
                                }
                            }
                            const el =
                                cell.querySelector('input, a, button, img, [onclick]') || cell;
                            if (visible(el)) {
                                el.click();
                                return true;
                            }
                        }
                    }
                }
                return false;
            }"""
        )

    def _pw_click_action_cell(ctx_p):
        try:
            tbl = ctx_p.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet', re.I)).first
            if tbl.count() == 0:
                tbl = (
                    ctx_p.locator('table')
                    .filter(has_text=re.compile(r'Plan\s*Name', re.I))
                    .filter(has_text=re.compile(r'LCO', re.I))
                    .first
                )
            if tbl.count() == 0:
                return False
            tbl.scroll_into_view_if_needed(timeout=10000)
            row = tbl.locator('tr').filter(has_text=re.compile(r'\bExpired\b', re.I)).first
            if row.count() == 0:
                return False
            row.scroll_into_view_if_needed(timeout=8000)
            try:
                ntd = row.locator('td').count()
            except Exception:
                ntd = 0
            td_indices = []
            if ntd > 0:
                for off in range(0, min(6, ntd)):
                    td_indices.append(ntd - 1 - off)
            for ti in td_indices:
                cell = row.locator('td').nth(ti)
                img_links = cell.locator('a:has(img)')
                try:
                    ni = img_links.count()
                    for ii in range(min(ni, 8)):
                        el = img_links.nth(ii)
                        try:
                            if el.is_visible(timeout=1400):
                                el.click(timeout=10000, force=True)
                                return True
                        except Exception:
                            continue
                except Exception:
                    pass
                for inner in (
                    cell.locator('input[type="image"]'),
                    cell.locator('a[href*="__doPostBack"]'),
                    cell.locator('a[href*="doPostBack"]'),
                    cell.locator('a[href^="javascript:"]'),
                    cell.locator(
                        'input[type="button"], input[type="submit"], a, button, img, [onclick]'
                    ),
                    cell,
                ):
                    try:
                        if inner.count() == 0:
                            continue
                        el = inner.first
                        if el.is_visible(timeout=1800):
                            el.click(timeout=10000, force=True)
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            return False

    for attempt in range(1, 4):
        cleanup_hathway_ui(page)
        roots = _hathway_pack_dom_roots(page)
        for ctx in roots:
            try:
                tbl = ctx.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet|Plan\s*Name', re.I)).first
                if tbl.count():
                    tbl.scroll_into_view_if_needed(timeout=10000)
            except Exception:
                pass
        _hathway_remove_pack_step_pause(page)

        clicked = False
        for ctx in roots:
            if _js_click_main(ctx):
                clicked = True
                break
        if not clicked:
            for ctx in roots:
                if _js_click_last_cell(ctx):
                    clicked = True
                    break
        if not clicked:
            for ctx in roots:
                if _pw_click_action_cell(ctx):
                    clicked = True
                    break
        if not clicked:
            _hathway_remove_pack_step_pause(page)
            continue

        page.wait_for_timeout(menu_wait)
        if _hathway_expired_plan_add_popup_visible(page):
            return True

        for ctx in roots:
            if _pw_click_action_cell(ctx):
                page.wait_for_timeout(menu_wait)
                if _hathway_expired_plan_add_popup_visible(page):
                    return True
                break

        _hathway_remove_pack_step_pause(page)

    return False


def _hathway_click_expired_plan_popup_add(page):
    """Click **ADD** on the tooltip/popover after Expired-row ▼."""
    cleanup_hathway_ui(page)
    page.wait_for_timeout(350)
    add_lab = re.compile(r'^\s*ADD\s*$', re.I)
    for ctx in _hathway_modal_search_roots(page):
        for loc in (
            ctx.get_by_role('button', name=add_lab).first,
            ctx.get_by_role('link', name=add_lab).first,
            ctx.locator('input[type="button"], input[type="submit"]').filter(has_text=add_lab).first,
        ):
            try:
                if loc.count() > 0 and loc.is_visible(timeout=2500):
                    loc.scroll_into_view_if_needed(timeout=5000)
                    loc.click(timeout=10000, force=True)
                    return True
            except Exception:
                continue
    try:
        return bool(
            page.evaluate(
                """() => {
                    const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                    const hits = [...document.querySelectorAll(
                        'button, a, input[type="button"], input[type="submit"], span'
                    )].filter((el) => {
                        if (!el.offsetParent) return false;
                        const t = norm(el.value || el.innerText || el.textContent || '');
                        return /^ADD$/i.test(t);
                    });
                    hits.sort((a, b) => {
                        const ra = a.getBoundingClientRect();
                        const rb = b.getBoundingClientRect();
                        return ra.top + ra.left - (rb.top + rb.left);
                    });
                    const pick = hits[hits.length - 1] || hits[0];
                    if (!pick) return false;
                    pick.click();
                    return true;
                }"""
            )
        )
    except Exception:
        return False


def _hathway_add_new_plan_modal_click_add(page):
    """Modal **Add New Plan** → primary **Add** (not Cancel)."""
    _hathway_remove_pack_step_pause(page)
    page.get_by_text(re.compile(r'Add\s+New\s+Plan', re.I)).first.wait_for(state='visible', timeout=90000)
    page.wait_for_timeout(450)
    modal = (
        page.locator('[role="dialog"], .modal.in, .modal.show, .modal, .ui-dialog')
        .filter(has_text=re.compile(r'Add\s+New\s+Plan', re.I))
        .last
    )
    if modal.count() == 0:
        modal = page.locator('body')
    add_btn = re.compile(r'^\s*Add\s*$', re.I)
    for btn in (
        modal.get_by_role('button', name=add_btn).first,
        modal.locator('input[type="submit"][value="Add" i]').first,
        modal.locator('input[type="button"][value="Add" i]').first,
    ):
        try:
            if btn.count() > 0 and btn.is_visible(timeout=4000):
                btn.click(timeout=12000, force=True)
                return
        except Exception:
            continue
    raise RuntimeError('Add New Plan modal: Add button not found.')


def _hathway_confirm_add_plan_modal_click_confirm(page):
    """Confirmation — “This will add the plan…” → **Confirm**."""
    _hathway_remove_pack_step_pause(page)
    hint = re.compile(r'This\s+will\s+add\s+the\s+plan|add\s+the\s+plan\s+with\s+following', re.I)
    if not _hathway_wait_visible_text_match(page, hint, timeout_ms=90000):
        raise RuntimeError('Add-plan confirmation dialog did not appear.')
    page.wait_for_timeout(450)
    box = page.locator('[role="dialog"], .modal.in, .modal.show, .modal, .ui-dialog').filter(has_text=hint).last
    if box.count() == 0:
        box = page.locator('body')
    for btn in (
        box.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
        box.locator('input[type="submit"][value*="Confirm" i]').first,
        box.locator('input[type="button"][value*="Confirm" i]').first,
    ):
        try:
            if btn.count() > 0 and btn.is_visible(timeout=4000):
                btn.click(timeout=12000, force=True)
                return
        except Exception:
            continue
    raise RuntimeError('Add-plan confirmation: Confirm not found.')


def _hathway_acknowledge_plan_add_success_popup(page):
    """Dismiss final Message / OK if the portal shows one after Confirm."""
    page.wait_for_timeout(700)
    deadline = time.monotonic() + 38.0
    while time.monotonic() < deadline:
        clicked = False
        for ctx in _hathway_modal_search_roots(page):
            try:
                lbl = ctx.locator('#MasterBody_lblPopupResponse')
                if lbl.count() > 0 and lbl.first.is_visible(timeout=500):
                    dlg = ctx.locator('[role="dialog"], .ui-dialog, .modal').filter(has_text=re.compile(r'Message', re.I)).last
                    box = dlg if dlg.count() > 0 else ctx.locator('body')
                    if _hathway_click_label_in_modal_container(box, 'OK'):
                        clicked = True
                        break
            except Exception:
                pass
            try:
                okc = ctx.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I))
                for i in range(min(okc.count(), 14) - 1, -1, -1):
                    b = okc.nth(i)
                    if b.is_visible(timeout=400):
                        b.click(timeout=8000, force=True)
                        clicked = True
                        break
            except Exception:
                pass
            if clicked:
                break
        if clicked:
            page.wait_for_timeout(400)
            cleanup_hathway_ui(page)
            return
        page.wait_for_timeout(280)
    cleanup_hathway_ui(page)


def _hathway_renew_via_quick_recharge(page):
    """
    **Main TV** or **Customer Details** → **Quick Recharge** → Plan Details **submit**
    → Confirmation **Confirm** → **OK**.

    Quick Recharge appears under Action Required on either tab depending on portal layout.

    Returns (True, None) or (False, err_key).
    """
    try:
        tab_attempts = (_hathway_ensure_main_tv_tab, _hathway_ensure_customer_details_tab)
        qr_clicked = False
        cleanup_hathway_ui(page)
        if _hathway_click_quick_recharge(page):
            qr_clicked = True
        else:
            for prepare_tab in tab_attempts:
                prepare_tab(page)
                page.wait_for_timeout(450)
                cleanup_hathway_ui(page)
                if _hathway_click_quick_recharge(page):
                    qr_clicked = True
                    break
        if not qr_clicked:
            return False, 'quick_recharge'
        page.wait_for_timeout(int(os.getenv('HATHWAY_QUICK_RECHARGE_NAV_WAIT_MS', '2200')))
        try:
            page.wait_for_load_state('domcontentloaded', timeout=25000)
        except Exception:
            pass
        cleanup_hathway_ui(page)
        _hathway_scroll_hathway_bouquet_heading_into_view(page)
        page.wait_for_timeout(400)
        if not _hathway_quick_recharge_click_plan_details_submit(page):
            return False, 'plan_submit'
        page.wait_for_timeout(450)
        _hathway_confirm_add_plan_modal_click_confirm(page)
        _hathway_acknowledge_plan_add_success_popup(page)
        return True, None
    except Exception as e:
        return False, f'modal:{e}'


def _hathway_click_bouquet_menu_cancel(page):
    """Click CANCEL in the bouquet RENEW/CANCEL/CHANGE strip — uses viewport coordinates to avoid wrong .click() target."""
    poll_ms = _hathway_cancel_menu_poll_ms()
    deadline = time.monotonic() + poll_ms / 1000.0
    first_pass = True

    while time.monotonic() < deadline:
        roots = _hathway_pack_dom_roots(page)
        for ctx in roots:
            try:
                ctx.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet|Plan\s*Name', re.I)).first.scroll_into_view_if_needed(
                    timeout=10000
                )
            except Exception:
                pass
            try:
                ctx.locator('tr').filter(has_text=re.compile(r'\bActive\b', re.I)).first.scroll_into_view_if_needed(timeout=8000)
            except Exception:
                pass
        if first_pass:
            _hathway_nudge_viewport_after_bouquet_menu_open(page)
            first_pass = False
        page.wait_for_timeout(250)

        pw = _hathway_try_cancel_playwright_on_roots(roots, page)
        if pw is True:
            return True
        if pw == 'retry':
            continue

        pos = None
        pos_ctx = None
        for ctx in roots:
            try:
                p = ctx.evaluate(
            """() => {
                const norm = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/[\\u200B-\\u200D\\uFEFF]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toUpperCase();
                const lab = (n) => {
                    const t = (n.tagName || '').toUpperCase();
                    let s = '';
                    if (t === 'INPUT') s = n.value || n.alt || (n.getAttribute && n.getAttribute('value')) || '';
                    else s = (n.innerText || n.textContent || '').trim();
                    let out = norm(s);
                    if (out !== 'RENEW' && out !== 'CANCEL' && out !== 'CHANGE') {
                        const a = n.getAttribute && (n.getAttribute('aria-label') || n.getAttribute('title'));
                        const alt = norm((a || '').trim());
                        if (alt === 'RENEW' || alt === 'CANCEL' || alt === 'CHANGE') out = alt;
                    }
                    return out;
                };

                const findTable = () =>
                    [...document.querySelectorAll('table')].find(
                        (t) => t.offsetParent && /hathway\\s*bouquet/i.test((t.innerText || '').replace(/\\s+/g, ' '))
                    ) ||
                    [...document.querySelectorAll('table')].find(
                        (t) =>
                            t.offsetParent &&
                            /plan\\s*name/i.test((t.innerText || '').toLowerCase()) &&
                            /lco/i.test((t.innerText || '').toLowerCase())
                    ) ||
                    null;

                const tbl = findTable();
                if (!tbl) return null;
                const activeTr = [...tbl.querySelectorAll('tr')].find((tr) => {
                    if (!tr.offsetParent) return false;
                    const x = (tr.innerText || '').replace(/\\s+/g, ' ');
                    return /\\bActive\\b/i.test(x) && x.length < 1400;
                });
                if (!activeTr) return null;

                const normH = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toLowerCase();

                const resolveActionTd = (tbl0, atr) => {
                    const rows = [...tbl0.querySelectorAll('tr')];
                    let actionIdx = -1;
                    for (let ri = 0; ri < Math.min(rows.length, 40); ri++) {
                        const cells = [...rows[ri].querySelectorAll('th, td')];
                        if (cells.length < 4) continue;
                        const headers = cells.map((c) => normH(c.textContent));
                        const hasPlan = headers.some(
                            (h) => h === 'plan name' || (h.includes('plan') && h.includes('name'))
                        );
                        if (!hasPlan) continue;
                        actionIdx = headers.findIndex((h) => h === 'action' || h === 'actions');
                        if (actionIdx < 0) actionIdx = cells.length - 1;
                        break;
                    }
                    const rowTds = [...atr.querySelectorAll('td')];
                    if (!rowTds.length) return null;
                    if (actionIdx >= 0 && actionIdx < rowTds.length) return rowTds[actionIdx];
                    return rowTds[rowTds.length - 1];
                };

                let actionTd = resolveActionTd(tbl, activeTr);
                if (!actionTd || !actionTd.offsetParent) return null;
                const rowTds2 = [...activeTr.querySelectorAll('td')];
                const hasChevronCell = (td) => {
                    if (!td || !td.offsetParent) return false;
                    const im = td.querySelector('input[type="image"], img');
                    if (!im || !im.offsetParent) return false;
                    const r = im.getBoundingClientRect();
                    return r.width > 4 && r.width < 72 && r.height > 4 && r.height < 72;
                };
                if (!hasChevronCell(actionTd)) {
                    for (let i = rowTds2.length - 1; i >= 0; i--) {
                        if (hasChevronCell(rowTds2[i])) {
                            actionTd = rowTds2[i];
                            break;
                        }
                    }
                }

                const pickNear = (cx, arTop, arBot, activeTr0, actionTd0) => {
                    const excludeTableRenewInRow = (n) =>
                        activeTr0.contains(n) && !actionTd0.contains(n) && lab(n) === 'RENEW';
                    const sel =
                        'a, button, input[type="button"], input[type="submit"], [role="button"], [role="menuitem"], td[onclick], span[onclick], span, div, label, li';
                    const raw = [...document.querySelectorAll(sel)].filter((n) => {
                        if (!n.offsetParent) return false;
                        if (excludeTableRenewInRow(n)) return false;
                        const r = n.getBoundingClientRect();
                        if (r.width < 8 || r.height < 8 || r.width > 520) return false;
                        const mx = r.left + r.width / 2;
                        if (Math.abs(mx - cx) > 168) return false;
                        const L = lab(n);
                        if (L !== 'RENEW' && L !== 'CANCEL' && L !== 'CHANGE') return false;
                        const above = r.bottom <= arTop + 48 && r.top >= arTop - 520;
                        const overlapCol = r.top < arBot + 95 && r.bottom > arTop - 110 && Math.abs(mx - cx) < 168;
                        return above || overlapCol;
                    });
                    raw.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
                    const centerOf = (el) => {
                        const rr = el.getBoundingClientRect();
                        return { x: rr.left + rr.width / 2, y: rr.top + rr.height / 2 };
                    };
                    const cancelUnderPoint = (xx, yy) => {
                        const hit = document.elementFromPoint(xx, yy);
                        let z = hit;
                        while (z) {
                            if (lab(z) === 'CANCEL') return { x: xx, y: yy };
                            z = z.parentElement;
                        }
                        return null;
                    };
                    const nudgedPoint = (el) => {
                        const c = centerOf(el);
                        for (const dy of [0, -4, 4, -8, 8, -12, 12, -16, 16, -20, 20]) {
                            for (const dx of [0, -4, 4, -8, 8]) {
                                const ok = cancelUnderPoint(c.x + dx, c.y + dy);
                                if (ok) return ok;
                            }
                        }
                        return { x: c.x, y: c.y };
                    };
                    for (let i = 0; i <= raw.length - 3; i++) {
                        const st = raw.slice(i, i + 3);
                        const ra = st[0].getBoundingClientRect();
                        const rb = st[1].getBoundingClientRect();
                        const rc = st[2].getBoundingClientRect();
                        if (rb.top - ra.bottom > 40 || rc.top - rb.bottom > 40) continue;
                        const la = lab(st[0]);
                        const lb = lab(st[1]);
                        const lc = lab(st[2]);
                        let target = null;
                        if (la === 'RENEW' && lb === 'CANCEL' && lc === 'CHANGE') target = st[1];
                        else {
                            const j = [la, lb, lc].indexOf('CANCEL');
                            if (j >= 0) target = st[j];
                        }
                        if (target) {
                            return nudgedPoint(target);
                        }
                    }
                    if (raw.length === 3) {
                        const ra = raw[0].getBoundingClientRect();
                        const rb = raw[1].getBoundingClientRect();
                        const rc = raw[2].getBoundingClientRect();
                        if (rb.top - ra.bottom < 40 && rc.top - rb.bottom < 40) {
                            return nudgedPoint(raw[1]);
                        }
                    }
                    return null;
                };

                const soloCancelNearAction = (cx, arTop, arBot, activeTr0, actionTd0) => {
                    const excludeTableRenewInRow = (n) =>
                        activeTr0.contains(n) && !actionTd0.contains(n) && lab(n) === 'RENEW';
                    let best = null;
                    let bestScore = 1e9;
                    const nodes = document.querySelectorAll(
                        'a, button, input[type="button"], input[type="submit"], span, div, label, li, [role="button"], [role="menuitem"], td'
                    );
                    for (const n of nodes) {
                        if (!n.offsetParent) continue;
                        if (excludeTableRenewInRow(n)) continue;
                        if (lab(n) !== 'CANCEL') continue;
                        const r = n.getBoundingClientRect();
                        if (r.width < 8 || r.height < 8 || r.width > 440 || r.height > 88) continue;
                        const mx = r.left + r.width / 2;
                        if (Math.abs(mx - cx) > 175) continue;
                        const above = r.bottom <= arTop + 48 && r.top >= arTop - 520;
                        const overlapCol = r.top < arBot + 95 && r.bottom > arTop - 110 && Math.abs(mx - cx) < 175;
                        if (!above && !overlapCol) continue;
                        const score = Math.abs(mx - cx) + (above ? 0 : 40);
                        if (score < bestScore) {
                            bestScore = score;
                            best = n;
                        }
                    }
                    if (!best) return null;
                    const centerOf = (el) => {
                        const rr = el.getBoundingClientRect();
                        return { x: rr.left + rr.width / 2, y: rr.top + rr.height / 2 };
                    };
                    const cancelUnderPoint = (xx, yy) => {
                        const hit = document.elementFromPoint(xx, yy);
                        let z = hit;
                        while (z) {
                            if (lab(z) === 'CANCEL') return { x: xx, y: yy };
                            z = z.parentElement;
                        }
                        return null;
                    };
                    const c = centerOf(best);
                    for (const dy of [0, -4, 4, -8, 8, -12, 12, -16, 16]) {
                        for (const dx of [0, -4, 4, -8, 8]) {
                            const ok = cancelUnderPoint(c.x + dx, c.y + dy);
                            if (ok) return ok;
                        }
                    }
                    return { x: c.x, y: c.y };
                };

                const ar = actionTd.getBoundingClientRect();
                if (ar.width < 6) return null;
                const cx = ar.left + ar.width / 2;
                const stacked = pickNear(cx, ar.top, ar.bottom, activeTr, actionTd);
                if (stacked) return stacked;
                return soloCancelNearAction(cx, ar.top, ar.bottom, activeTr, actionTd);
            }"""
                )
            except Exception:
                p = None
            if isinstance(p, dict) and p.get('x') is not None and p.get('y') is not None:
                pos, pos_ctx = p, ctx
                break

        if (
            pos_ctx is not None
            and isinstance(pos, dict)
            and pos.get('x') is not None
            and pos.get('y') is not None
        ):
            try:
                if _hathway_viewport_click_at(pos_ctx, pos):
                    page.wait_for_timeout(450)
                    if _hathway_bouquet_renew_misclick_visible(page):
                        _hathway_dismiss_renew_misclick(page)
                        if not _hathway_bouquet_row_menu_visible(page):
                            _hathway_click_bouquet_action_dropdown(page)
                        continue
                    return True
            except Exception:
                pass

        clicked = False
        for ctx in roots:
            try:
                c = ctx.evaluate(
            """() => {
                const vis = (el) => el && el.offsetParent;
                const norm = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/[\\u200B-\\u200D\\uFEFF]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toUpperCase();
                const normH = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toLowerCase();
                const labelOf = (n) => {
                    const tag = (n.tagName || '').toUpperCase();
                    let s = '';
                    if (tag === 'INPUT') s = n.value || n.alt || (n.getAttribute && n.getAttribute('value')) || '';
                    else s = (n.innerText || n.textContent || '').trim();
                    let out = norm(s);
                    if (out !== 'RENEW' && out !== 'CANCEL' && out !== 'CHANGE') {
                        const a = n.getAttribute && (n.getAttribute('aria-label') || n.getAttribute('title'));
                        const alt = norm((a || '').trim());
                        if (alt === 'RENEW' || alt === 'CANCEL' || alt === 'CHANGE') out = alt;
                    }
                    return out;
                };
                const rowLabel = (el) => {
                    const tag = (el.tagName || '').toUpperCase();
                    if (tag === 'INPUT') return norm(el.value || '');
                    if (tag === 'A' || tag === 'BUTTON') return labelOf(el);
                    const inner = el.querySelector('a,button,input');
                    if (inner) return labelOf(inner);
                    return norm((el.textContent || '').trim());
                };
                const findTable = () =>
                    [...document.querySelectorAll('table')].find(
                        (t) => t.offsetParent && /hathway\\s*bouquet/i.test((t.innerText || '').replace(/\\s+/g, ' '))
                    ) ||
                    [...document.querySelectorAll('table')].find(
                        (t) =>
                            t.offsetParent &&
                            /plan\\s*name/i.test((t.innerText || '').toLowerCase()) &&
                            /lco/i.test((t.innerText || '').toLowerCase())
                    ) ||
                    null;
                const resolveActionTd = (tbl0, atr) => {
                    const rows = [...tbl0.querySelectorAll('tr')];
                    let actionIdx = -1;
                    for (let ri = 0; ri < Math.min(rows.length, 40); ri++) {
                        const cells = [...rows[ri].querySelectorAll('th, td')];
                        if (cells.length < 4) continue;
                        const headers = cells.map((c) => normH(c.textContent));
                        const hasPlan = headers.some(
                            (h) => h === 'plan name' || (h.includes('plan') && h.includes('name'))
                        );
                        if (!hasPlan) continue;
                        actionIdx = headers.findIndex((h) => h === 'action' || h === 'actions');
                        if (actionIdx < 0) actionIdx = cells.length - 1;
                        break;
                    }
                    const rowTds = [...atr.querySelectorAll('td')];
                    if (!rowTds.length) return null;
                    if (actionIdx >= 0 && actionIdx < rowTds.length) return rowTds[actionIdx];
                    return rowTds[rowTds.length - 1];
                };
                const clickLeaf = (el) => {
                    const t = el.querySelector('a,button,input') || el;
                    if (t && vis(t)) {
                        t.click();
                        return true;
                    }
                    return false;
                };

                const tbl = findTable();
                if (!tbl) return false;
                const activeTr = [...tbl.querySelectorAll('tr')].find((tr) => {
                    if (!tr.offsetParent) return false;
                    const x = (tr.innerText || '').replace(/\\s+/g, ' ');
                    return /\\bActive\\b/i.test(x) && x.length < 1400;
                });
                if (!activeTr) return false;
                let actionTd = resolveActionTd(tbl, activeTr);
                if (!actionTd || !actionTd.offsetParent) return false;
                const rowTds2 = [...activeTr.querySelectorAll('td')];
                const hasChevronCell = (td) => {
                    if (!td || !td.offsetParent) return false;
                    const im = td.querySelector('input[type="image"], img');
                    if (!im || !im.offsetParent) return false;
                    const r = im.getBoundingClientRect();
                    return r.width > 4 && r.width < 72 && r.height > 4 && r.height < 72;
                };
                if (!hasChevronCell(actionTd)) {
                    for (let i = rowTds2.length - 1; i >= 0; i--) {
                        if (hasChevronCell(rowTds2[i])) {
                            actionTd = rowTds2[i];
                            break;
                        }
                    }
                }
                const arAct = actionTd.getBoundingClientRect();
                const ax = arAct.left + arAct.width / 2;
                const rowTop = arAct.top;
                const rowBot = arAct.bottom;
                const nearMenuToAction = (r) => {
                    const mx = r.left + r.width / 2;
                    if (Math.abs(mx - ax) > 175) return false;
                    if (r.bottom < rowTop - 520 || r.top > rowBot + 100) return false;
                    return true;
                };
                const excludeTableRenewInRow = (n) => activeTr.contains(n) && !actionTd.contains(n) && labelOf(n) === 'RENEW';

                const clickCancelAnchoredToBouquetAction = () => {
                    const ar = arAct;
                    const cx = ax;
                    const cand = [...document.querySelectorAll(
                        'a, button, input[type="button"], input[type="submit"], span, div, label, li, [role="button"], [role="menuitem"], td'
                    )].filter((n) => {
                            if (!n.offsetParent) return false;
                            if (excludeTableRenewInRow(n)) return false;
                            const labv = labelOf(n);
                            if (labv !== 'RENEW' && labv !== 'CANCEL' && labv !== 'CHANGE') return false;
                            const r = n.getBoundingClientRect();
                            if (r.width < 8 || r.height < 8 || r.width > 520 || r.height > 90) return false;
                            const mx = r.left + r.width / 2;
                            if (Math.abs(mx - cx) > 168) return false;
                            const above = r.bottom <= ar.top + 48 && r.top >= ar.top - 520;
                            const besideRow =
                                r.top < ar.bottom + 95 &&
                                r.bottom > ar.top - 110 &&
                                Math.abs(mx - cx) < 168;
                            return above || besideRow;
                        });
                    const cancel = cand.find((n) => labelOf(n) === 'CANCEL');
                    if (cancel) {
                        const leaf = cancel.querySelector('a,button,input') || cancel;
                        if (leaf && vis(leaf)) leaf.click();
                        else cancel.click();
                        return true;
                    }
                    return false;
                };
                if (clickCancelAnchoredToBouquetAction()) return true;

                const clickTripleMenu = () => {
                    for (const list of document.querySelectorAll('ul')) {
                        if (!vis(list)) continue;
                        if (!nearMenuToAction(list.getBoundingClientRect())) continue;
                        const items = [...list.querySelectorAll(':scope > li')].filter(vis);
                        if (items.length !== 3) continue;
                        const labs = items.map(rowLabel);
                        if (!labs.includes('RENEW') || !labs.includes('CANCEL') || !labs.includes('CHANGE')) continue;
                        const mid = items.find((it) => rowLabel(it) === 'CANCEL');
                        if (mid && clickLeaf(mid)) return true;
                    }
                    for (const p of document.querySelectorAll('div')) {
                        if (!vis(p)) continue;
                        const ttxt = (p.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (ttxt.length > 80) continue;
                        const kids = [...p.children].filter(vis);
                        if (kids.length !== 3) continue;
                        if (!nearMenuToAction(p.getBoundingClientRect())) continue;
                        const labs = kids.map(rowLabel);
                        if (!labs.includes('RENEW') || !labs.includes('CANCEL') || !labs.includes('CHANGE')) continue;
                        const mid = kids.find((k) => rowLabel(k) === 'CANCEL');
                        if (mid && clickLeaf(mid)) return true;
                    }
                    for (const p of document.querySelectorAll('div, td, span')) {
                        if (!vis(p)) continue;
                        const kids = [...p.querySelectorAll(':scope > a, :scope > button, :scope > input')].filter(vis);
                        if (kids.length !== 3) continue;
                        if (!nearMenuToAction(p.getBoundingClientRect())) continue;
                        const labs = kids.map(rowLabel);
                        if (!labs.includes('RENEW') || !labs.includes('CANCEL') || !labs.includes('CHANGE')) continue;
                        const mid = kids.find((k) => rowLabel(k) === 'CANCEL');
                        if (mid) {
                            mid.click();
                            return true;
                        }
                    }
                    return false;
                };
                if (clickTripleMenu()) return true;

                const clickCancelDirectNearAction = () => {
                    const ar = arAct;
                    const cx = ax;
                    const excludeTableRenewInRow = (n) =>
                        activeTr.contains(n) && !actionTd.contains(n) && labelOf(n) === 'RENEW';
                    let best = null;
                    let bestScore = 1e9;
                    const nodes = document.querySelectorAll(
                        'a, button, input[type="button"], input[type="submit"], span, div, label, li, [role="button"], [role="menuitem"], td'
                    );
                    for (const n of nodes) {
                        if (!vis(n)) continue;
                        if (excludeTableRenewInRow(n)) continue;
                        if (labelOf(n) !== 'CANCEL') continue;
                        const r = n.getBoundingClientRect();
                        if (r.width < 8 || r.height < 8 || r.width > 440 || r.height > 88) continue;
                        const mx = r.left + r.width / 2;
                        if (Math.abs(mx - cx) > 175) continue;
                        const above = r.bottom <= ar.top + 48 && r.top >= ar.top - 520;
                        const overlapCol = r.top < ar.bottom + 95 && r.bottom > ar.top - 110 && Math.abs(mx - cx) < 175;
                        if (!above && !overlapCol) continue;
                        const score = Math.abs(mx - cx) + (above ? 0 : 35);
                        if (score < bestScore) {
                            bestScore = score;
                            best = n;
                        }
                    }
                    if (!best) return false;
                    const leaf = best.querySelector('a,button,input') || best;
                    if (leaf && vis(leaf)) {
                        leaf.click();
                        return true;
                    }
                    best.click();
                    return true;
                };
                if (clickCancelDirectNearAction()) return true;

                return false;
            }"""
                )
            except Exception:
                c = False
            if c:
                clicked = True
                break

        if clicked:
            page.wait_for_timeout(450)
            if _hathway_bouquet_renew_misclick_visible(page):
                _hathway_dismiss_renew_misclick(page)
                if not _hathway_bouquet_row_menu_visible(page):
                    _hathway_click_bouquet_action_dropdown(page)
                continue
            return True

        page.wait_for_timeout(700)

    return False


def _hathway_click_bouquet_menu_renew(page):
    """Click RENEW in the bouquet RENEW/CANCEL/CHANGE strip — uses viewport coordinates to avoid wrong .click() target."""
    poll_ms = _hathway_cancel_menu_poll_ms()
    deadline = time.monotonic() + poll_ms / 1000.0
    first_pass = True

    while time.monotonic() < deadline:
        roots = _hathway_pack_dom_roots(page)
        for ctx in roots:
            try:
                ctx.locator('table').filter(has_text=re.compile(r'Hathway\s*Bouquet|Plan\s*Name', re.I)).first.scroll_into_view_if_needed(
                    timeout=10000
                )
            except Exception:
                pass
            try:
                ctx.locator('tr').filter(has_text=re.compile(r'\bActive\b', re.I)).first.scroll_into_view_if_needed(timeout=8000)
            except Exception:
                pass
        if first_pass:
            _hathway_nudge_viewport_after_bouquet_menu_open(page)
            first_pass = False
        page.wait_for_timeout(250)

        pw = _hathway_try_renew_playwright_on_roots(roots, page)
        if pw is True:
            return True
        if pw == 'retry':
            continue

        pos = None
        pos_ctx = None
        for ctx in roots:
            try:
                p = ctx.evaluate(
            """() => {
                const norm = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/[\\u200B-\\u200D\\uFEFF]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toUpperCase();
                const lab = (n) => {
                    const t = (n.tagName || '').toUpperCase();
                    let s = '';
                    if (t === 'INPUT') s = n.value || n.alt || (n.getAttribute && n.getAttribute('value')) || '';
                    else s = (n.innerText || n.textContent || '').trim();
                    let out = norm(s);
                    if (out !== 'RENEW' && out !== 'CANCEL' && out !== 'CHANGE') {
                        const a = n.getAttribute && (n.getAttribute('aria-label') || n.getAttribute('title'));
                        const alt = norm((a || '').trim());
                        if (alt === 'RENEW' || alt === 'CANCEL' || alt === 'CHANGE') out = alt;
                    }
                    return out;
                };

                const findTable = () =>
                    [...document.querySelectorAll('table')].find(
                        (t) => t.offsetParent && /hathway\\s*bouquet/i.test((t.innerText || '').replace(/\\s+/g, ' '))
                    ) ||
                    [...document.querySelectorAll('table')].find(
                        (t) =>
                            t.offsetParent &&
                            /plan\\s*name/i.test((t.innerText || '').toLowerCase()) &&
                            /lco/i.test((t.innerText || '').toLowerCase())
                    ) ||
                    null;

                const tbl = findTable();
                if (!tbl) return null;
                const activeTr = [...tbl.querySelectorAll('tr')].find((tr) => {
                    if (!tr.offsetParent) return false;
                    const x = (tr.innerText || '').replace(/\\s+/g, ' ');
                    return /\\bActive\\b/i.test(x) && x.length < 1400;
                });
                if (!activeTr) return null;

                const normH = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toLowerCase();

                const resolveActionTd = (tbl0, atr) => {
                    const rows = [...tbl0.querySelectorAll('tr')];
                    let actionIdx = -1;
                    for (let ri = 0; ri < Math.min(rows.length, 40); ri++) {
                        const cells = [...rows[ri].querySelectorAll('th, td')];
                        if (cells.length < 4) continue;
                        const headers = cells.map((c) => normH(c.textContent));
                        const hasPlan = headers.some(
                            (h) => h === 'plan name' || (h.includes('plan') && h.includes('name'))
                        );
                        if (!hasPlan) continue;
                        actionIdx = headers.findIndex((h) => h === 'action' || h === 'actions');
                        if (actionIdx < 0) actionIdx = cells.length - 1;
                        break;
                    }
                    const rowTds = [...atr.querySelectorAll('td')];
                    if (!rowTds.length) return null;
                    if (actionIdx >= 0 && actionIdx < rowTds.length) return rowTds[actionIdx];
                    return rowTds[rowTds.length - 1];
                };

                let actionTd = resolveActionTd(tbl, activeTr);
                if (!actionTd || !actionTd.offsetParent) return null;
                const rowTds2 = [...activeTr.querySelectorAll('td')];
                const hasChevronCell = (td) => {
                    if (!td || !td.offsetParent) return false;
                    const im = td.querySelector('input[type="image"], img');
                    if (!im || !im.offsetParent) return false;
                    const r = im.getBoundingClientRect();
                    return r.width > 4 && r.width < 72 && r.height > 4 && r.height < 72;
                };
                if (!hasChevronCell(actionTd)) {
                    for (let i = rowTds2.length - 1; i >= 0; i--) {
                        if (hasChevronCell(rowTds2[i])) {
                            actionTd = rowTds2[i];
                            break;
                        }
                    }
                }

                const pickNear = (cx, arTop, arBot, activeTr0, actionTd0) => {
                    const excludeTableCancelInRowPick = (n) =>
                        activeTr0.contains(n) && !actionTd0.contains(n) && lab(n) === 'CANCEL';
                    const sel =
                        'a, button, input[type="button"], input[type="submit"], [role="button"], [role="menuitem"], td[onclick], span[onclick], span, div, label, li';
                    const raw = [...document.querySelectorAll(sel)].filter((n) => {
                        if (!n.offsetParent) return false;
                        if (excludeTableCancelInRowPick(n)) return false;
                        const r = n.getBoundingClientRect();
                        if (r.width < 8 || r.height < 8 || r.width > 520) return false;
                        const mx = r.left + r.width / 2;
                        if (Math.abs(mx - cx) > 168) return false;
                        const L = lab(n);
                        if (L !== 'RENEW' && L !== 'CANCEL' && L !== 'CHANGE') return false;
                        const above = r.bottom <= arTop + 48 && r.top >= arTop - 520;
                        const overlapCol = r.top < arBot + 95 && r.bottom > arTop - 110 && Math.abs(mx - cx) < 168;
                        return above || overlapCol;
                    });
                    raw.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
                    const centerOf = (el) => {
                        const rr = el.getBoundingClientRect();
                        return { x: rr.left + rr.width / 2, y: rr.top + rr.height / 2 };
                    };
                    const renewUnderPoint = (xx, yy) => {
                        const hit = document.elementFromPoint(xx, yy);
                        let z = hit;
                        while (z) {
                            if (lab(z) === 'RENEW') return { x: xx, y: yy };
                            z = z.parentElement;
                        }
                        return null;
                    };
                    const nudgedPoint = (el) => {
                        const c = centerOf(el);
                        for (const dy of [0, -4, 4, -8, 8, -12, 12, -16, 16, -20, 20]) {
                            for (const dx of [0, -4, 4, -8, 8]) {
                                const ok = renewUnderPoint(c.x + dx, c.y + dy);
                                if (ok) return ok;
                            }
                        }
                        return { x: c.x, y: c.y };
                    };
                    for (let i = 0; i <= raw.length - 3; i++) {
                        const st = raw.slice(i, i + 3);
                        const ra = st[0].getBoundingClientRect();
                        const rb = st[1].getBoundingClientRect();
                        const rc = st[2].getBoundingClientRect();
                        if (rb.top - ra.bottom > 40 || rc.top - rb.bottom > 40) continue;
                        const la = lab(st[0]);
                        const lb = lab(st[1]);
                        const lc = lab(st[2]);
                        let target = null;
                        if (la === 'RENEW' && lb === 'CANCEL' && lc === 'CHANGE') target = st[0];
                        else {
                            const j = [la, lb, lc].indexOf('RENEW');
                            if (j >= 0) target = st[j];
                        }
                        if (target) {
                            return nudgedPoint(target);
                        }
                    }
                    if (raw.length === 3) {
                        const ra = raw[0].getBoundingClientRect();
                        const rb = raw[1].getBoundingClientRect();
                        const rc = raw[2].getBoundingClientRect();
                        if (rb.top - ra.bottom < 40 && rc.top - rb.bottom < 40) {
                            return nudgedPoint(raw[0]);
                        }
                    }
                    return null;
                };

                const soloRenewNearAction = (cx, arTop, arBot, activeTr0, actionTd0) => {
                    const excludeTableCancelInRowSolo = (n) =>
                        activeTr0.contains(n) && !actionTd0.contains(n) && lab(n) === 'CANCEL';
                    let best = null;
                    let bestScore = 1e9;
                    const nodes = document.querySelectorAll(
                        'a, button, input[type="button"], input[type="submit"], span, div, label, li, [role="button"], [role="menuitem"], td'
                    );
                    for (const n of nodes) {
                        if (!n.offsetParent) continue;
                        if (excludeTableCancelInRowSolo(n)) continue;
                        if (lab(n) !== 'RENEW') continue;
                        const r = n.getBoundingClientRect();
                        if (r.width < 8 || r.height < 8 || r.width > 440 || r.height > 88) continue;
                        const mx = r.left + r.width / 2;
                        if (Math.abs(mx - cx) > 175) continue;
                        const above = r.bottom <= arTop + 48 && r.top >= arTop - 520;
                        const overlapCol = r.top < arBot + 95 && r.bottom > arTop - 110 && Math.abs(mx - cx) < 175;
                        if (!above && !overlapCol) continue;
                        const score = Math.abs(mx - cx) + (above ? 0 : 40);
                        if (score < bestScore) {
                            bestScore = score;
                            best = n;
                        }
                    }
                    if (!best) return null;
                    const centerOf = (el) => {
                        const rr = el.getBoundingClientRect();
                        return { x: rr.left + rr.width / 2, y: rr.top + rr.height / 2 };
                    };
                    const renewUnderPointSolo = (xx, yy) => {
                        const hit = document.elementFromPoint(xx, yy);
                        let z = hit;
                        while (z) {
                            if (lab(z) === 'RENEW') return { x: xx, y: yy };
                            z = z.parentElement;
                        }
                        return null;
                    };
                    const c = centerOf(best);
                    for (const dy of [0, -4, 4, -8, 8, -12, 12, -16, 16]) {
                        for (const dx of [0, -4, 4, -8, 8]) {
                            const ok = renewUnderPointSolo(c.x + dx, c.y + dy);
                            if (ok) return ok;
                        }
                    }
                    return { x: c.x, y: c.y };
                };

                const ar = actionTd.getBoundingClientRect();
                if (ar.width < 6) return null;
                const cx = ar.left + ar.width / 2;
                const stacked = pickNear(cx, ar.top, ar.bottom, activeTr, actionTd);
                if (stacked) return stacked;
                return soloRenewNearAction(cx, ar.top, ar.bottom, activeTr, actionTd);
            }"""
                )
            except Exception:
                p = None
            if isinstance(p, dict) and p.get('x') is not None and p.get('y') is not None:
                pos, pos_ctx = p, ctx
                break

        if (
            pos_ctx is not None
            and isinstance(pos, dict)
            and pos.get('x') is not None
            and pos.get('y') is not None
        ):
            try:
                if _hathway_viewport_click_at(pos_ctx, pos):
                    page.wait_for_timeout(450)
                    if _hathway_bouquet_renew_misclick_visible(page):
                        return True
                    if _hathway_cancel_pack_prompt_visible(page):
                        _hathway_dismiss_renew_misclick(page)
                        if not _hathway_bouquet_row_menu_visible(page):
                            _hathway_click_bouquet_action_dropdown(page)
                        continue
                    return True
            except Exception:
                pass

        clicked = False
        for ctx in roots:
            try:
                c = ctx.evaluate(
            """() => {
                const vis = (el) => el && el.offsetParent;
                const norm = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/[\\u200B-\\u200D\\uFEFF]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toUpperCase();
                const normH = (s) =>
                    (s || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toLowerCase();
                const labelOf = (n) => {
                    const tag = (n.tagName || '').toUpperCase();
                    let s = '';
                    if (tag === 'INPUT') s = n.value || n.alt || (n.getAttribute && n.getAttribute('value')) || '';
                    else s = (n.innerText || n.textContent || '').trim();
                    let out = norm(s);
                    if (out !== 'RENEW' && out !== 'CANCEL' && out !== 'CHANGE') {
                        const a = n.getAttribute && (n.getAttribute('aria-label') || n.getAttribute('title'));
                        const alt = norm((a || '').trim());
                        if (alt === 'RENEW' || alt === 'CANCEL' || alt === 'CHANGE') out = alt;
                    }
                    return out;
                };
                const rowLabel = (el) => {
                    const tag = (el.tagName || '').toUpperCase();
                    if (tag === 'INPUT') return norm(el.value || '');
                    if (tag === 'A' || tag === 'BUTTON') return labelOf(el);
                    const inner = el.querySelector('a,button,input');
                    if (inner) return labelOf(inner);
                    return norm((el.textContent || '').trim());
                };
                const findTable = () =>
                    [...document.querySelectorAll('table')].find(
                        (t) => t.offsetParent && /hathway\\s*bouquet/i.test((t.innerText || '').replace(/\\s+/g, ' '))
                    ) ||
                    [...document.querySelectorAll('table')].find(
                        (t) =>
                            t.offsetParent &&
                            /plan\\s*name/i.test((t.innerText || '').toLowerCase()) &&
                            /lco/i.test((t.innerText || '').toLowerCase())
                    ) ||
                    null;
                const resolveActionTd = (tbl0, atr) => {
                    const rows = [...tbl0.querySelectorAll('tr')];
                    let actionIdx = -1;
                    for (let ri = 0; ri < Math.min(rows.length, 40); ri++) {
                        const cells = [...rows[ri].querySelectorAll('th, td')];
                        if (cells.length < 4) continue;
                        const headers = cells.map((c) => normH(c.textContent));
                        const hasPlan = headers.some(
                            (h) => h === 'plan name' || (h.includes('plan') && h.includes('name'))
                        );
                        if (!hasPlan) continue;
                        actionIdx = headers.findIndex((h) => h === 'action' || h === 'actions');
                        if (actionIdx < 0) actionIdx = cells.length - 1;
                        break;
                    }
                    const rowTds = [...atr.querySelectorAll('td')];
                    if (!rowTds.length) return null;
                    if (actionIdx >= 0 && actionIdx < rowTds.length) return rowTds[actionIdx];
                    return rowTds[rowTds.length - 1];
                };
                const clickLeaf = (el) => {
                    const t = el.querySelector('a,button,input') || el;
                    if (t && vis(t)) {
                        t.click();
                        return true;
                    }
                    return false;
                };

                const tbl = findTable();
                if (!tbl) return false;
                const activeTr = [...tbl.querySelectorAll('tr')].find((tr) => {
                    if (!tr.offsetParent) return false;
                    const x = (tr.innerText || '').replace(/\\s+/g, ' ');
                    return /\\bActive\\b/i.test(x) && x.length < 1400;
                });
                if (!activeTr) return false;
                let actionTd = resolveActionTd(tbl, activeTr);
                if (!actionTd || !actionTd.offsetParent) return false;
                const rowTds2 = [...activeTr.querySelectorAll('td')];
                const hasChevronCell = (td) => {
                    if (!td || !td.offsetParent) return false;
                    const im = td.querySelector('input[type="image"], img');
                    if (!im || !im.offsetParent) return false;
                    const r = im.getBoundingClientRect();
                    return r.width > 4 && r.width < 72 && r.height > 4 && r.height < 72;
                };
                if (!hasChevronCell(actionTd)) {
                    for (let i = rowTds2.length - 1; i >= 0; i--) {
                        if (hasChevronCell(rowTds2[i])) {
                            actionTd = rowTds2[i];
                            break;
                        }
                    }
                }
                const arAct = actionTd.getBoundingClientRect();
                const ax = arAct.left + arAct.width / 2;
                const rowTop = arAct.top;
                const rowBot = arAct.bottom;
                const nearMenuToAction = (r) => {
                    const mx = r.left + r.width / 2;
                    if (Math.abs(mx - ax) > 175) return false;
                    if (r.bottom < rowTop - 520 || r.top > rowBot + 100) return false;
                    return true;
                };
                const excludeTableCancelInRowMenu = (n) => activeTr.contains(n) && !actionTd.contains(n) && labelOf(n) === 'CANCEL';

                const clickRenewAnchoredToBouquetAction = () => {
                    const ar = arAct;
                    const cx = ax;
                    const cand = [...document.querySelectorAll(
                        'a, button, input[type="button"], input[type="submit"], span, div, label, li, [role="button"], [role="menuitem"], td'
                    )].filter((n) => {
                            if (!n.offsetParent) return false;
                            if (excludeTableCancelInRowPick(n)) return false;
                            const labv = labelOf(n);
                            if (labv !== 'RENEW' && labv !== 'CANCEL' && labv !== 'CHANGE') return false;
                            const r = n.getBoundingClientRect();
                            if (r.width < 8 || r.height < 8 || r.width > 520 || r.height > 90) return false;
                            const mx = r.left + r.width / 2;
                            if (Math.abs(mx - cx) > 168) return false;
                            const above = r.bottom <= ar.top + 48 && r.top >= ar.top - 520;
                            const besideRow =
                                r.top < ar.bottom + 95 &&
                                r.bottom > ar.top - 110 &&
                                Math.abs(mx - cx) < 168;
                            return above || besideRow;
                        });
                    const renewPick = cand.find((n) => labelOf(n) === 'RENEW');
                    if (renewPick) {
                        const leaf = renewPick.querySelector('a,button,input') || renewPick;
                        if (leaf && vis(leaf)) leaf.click();
                        else renewPick.click();
                        return true;
                    }
                    return false;
                };
                if (clickRenewAnchoredToBouquetAction()) return true;

                const clickTripleMenu = () => {
                    for (const list of document.querySelectorAll('ul')) {
                        if (!vis(list)) continue;
                        if (!nearMenuToAction(list.getBoundingClientRect())) continue;
                        const items = [...list.querySelectorAll(':scope > li')].filter(vis);
                        if (items.length !== 3) continue;
                        const labs = items.map(rowLabel);
                        if (!labs.includes('RENEW') || !labs.includes('CANCEL') || !labs.includes('CHANGE')) continue;
                        const mid = items.find((it) => rowLabel(it) === 'RENEW');
                        if (mid && clickLeaf(mid)) return true;
                    }
                    for (const p of document.querySelectorAll('div')) {
                        if (!vis(p)) continue;
                        const ttxt = (p.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (ttxt.length > 80) continue;
                        const kids = [...p.children].filter(vis);
                        if (kids.length !== 3) continue;
                        if (!nearMenuToAction(p.getBoundingClientRect())) continue;
                        const labs = kids.map(rowLabel);
                        if (!labs.includes('RENEW') || !labs.includes('CANCEL') || !labs.includes('CHANGE')) continue;
                        const mid = kids.find((k) => rowLabel(k) === 'RENEW');
                        if (mid && clickLeaf(mid)) return true;
                    }
                    for (const p of document.querySelectorAll('div, td, span')) {
                        if (!vis(p)) continue;
                        const kids = [...p.querySelectorAll(':scope > a, :scope > button, :scope > input')].filter(vis);
                        if (kids.length !== 3) continue;
                        if (!nearMenuToAction(p.getBoundingClientRect())) continue;
                        const labs = kids.map(rowLabel);
                        if (!labs.includes('RENEW') || !labs.includes('CANCEL') || !labs.includes('CHANGE')) continue;
                        const mid = kids.find((k) => rowLabel(k) === 'RENEW');
                        if (mid) {
                            mid.click();
                            return true;
                        }
                    }
                    return false;
                };
                if (clickTripleMenu()) return true;

                const clickRenewDirectNearAction = () => {
                    const ar = arAct;
                    const cx = ax;
                    const excludeTableCancelInRowDirect = (n) =>
                        activeTr.contains(n) && !actionTd.contains(n) && labelOf(n) === 'CANCEL';
                    let best = null;
                    let bestScore = 1e9;
                    const nodes = document.querySelectorAll(
                        'a, button, input[type="button"], input[type="submit"], span, div, label, li, [role="button"], [role="menuitem"], td'
                    );
                    for (const n of nodes) {
                        if (!vis(n)) continue;
                        if (excludeTableCancelInRowDirect(n)) continue;
                        if (labelOf(n) !== 'RENEW') continue;
                        const r = n.getBoundingClientRect();
                        if (r.width < 8 || r.height < 8 || r.width > 440 || r.height > 88) continue;
                        const mx = r.left + r.width / 2;
                        if (Math.abs(mx - cx) > 175) continue;
                        const above = r.bottom <= ar.top + 48 && r.top >= ar.top - 520;
                        const overlapCol = r.top < ar.bottom + 95 && r.bottom > ar.top - 110 && Math.abs(mx - cx) < 175;
                        if (!above && !overlapCol) continue;
                        const score = Math.abs(mx - cx) + (above ? 0 : 35);
                        if (score < bestScore) {
                            bestScore = score;
                            best = n;
                        }
                    }
                    if (!best) return false;
                    const leaf = best.querySelector('a,button,input') || best;
                    if (leaf && vis(leaf)) {
                        leaf.click();
                        return true;
                    }
                    best.click();
                    return true;
                };
                if (clickRenewDirectNearAction()) return true;

                return false;
            }"""
                )
            except Exception:
                c = False
            if c:
                clicked = True
                break

        if clicked:
            page.wait_for_timeout(450)
            if _hathway_bouquet_renew_misclick_visible(page):
                return True
            if _hathway_cancel_pack_prompt_visible(page):
                _hathway_dismiss_renew_misclick(page)
                if not _hathway_bouquet_row_menu_visible(page):
                    _hathway_click_bouquet_action_dropdown(page)
                continue
            return True

        page.wait_for_timeout(700)

    return False


def _hathway_normalize_reason_compare(text):
    """Lowercase, unify dashes and spaces for option vs env reason matching."""
    if not text:
        return ''
    t = str(text).lower().strip()
    for ch in ('\u2013', '\u2014', '\u2212'):
        t = t.replace(ch, '-')
    return ' '.join(t.split())


def _hathway_reason_label_variants(reason_label):
    """Env / portal wording variants (Customer vs Customers, dash spacing)."""
    base = (reason_label or '').strip()
    if not base:
        return []
    out = []
    seen = set()

    def add(s):
        s = (s or '').strip()
        if not s:
            return
        k = _hathway_normalize_reason_compare(s)
        if k in seen:
            return
        seen.add(k)
        out.append(s)

    add(base)
    add(base.lower())
    add(base.title())
    n = _hathway_normalize_reason_compare(base)
    add(n)
    if 'customers' in n:
        add(re.sub(r'customers', 'customer', base, count=1, flags=re.I))
    if 'customer' in n and 'customers' not in n:
        add(re.sub(r'\bcustomer\b', 'Customers', base, count=1, flags=re.I))
    if '-' in base:
        add(base.replace('-', '\u2013'))
        add(base.replace('-', '\u2014'))
    return out


def _hathway_reason_select_locator(page, modal):
    """
    Hathway TERMINATE / cancel modals sometimes use a plain div shell without .modal / role=dialog
    wrapping the <select>. Prefer select inside *modal*; then any visible select under TERMINATE + IDs.
    """
    try:
        s = modal.locator('select')
        if s.count() > 0:
            return s.first
    except Exception:
        pass
    shell = page.locator('div, form, table').filter(
        has_text=re.compile(r'\bTERMINATE\b', re.I)
    ).filter(has_text=re.compile(r'VC/MAC ID|STB/MAC ID', re.I)).last
    try:
        s2 = shell.locator('select')
        if s2.count() > 0:
            return s2.first
    except Exception:
        pass
    return None


def _hathway_modal_select_reason_only(page, modal, reason_label):
    """
    Inside a modal: open reason control and pick option matching reason_label (native <select> or Select2).
    Does not click Confirm / Submit.
    """
    reason_label = (reason_label or '').strip()
    if not reason_label:
        raise RuntimeError('Empty reason label.')
    open_ms = int(os.getenv('HATHWAY_DEACTIVATE_REASON_OPEN_MS', '2000'))
    page.wait_for_timeout(300)
    prefs = _hathway_reason_label_variants(reason_label)
    opt_re = re.compile(re.escape(reason_label), re.I)
    fallbacks = prefs[:]

    sel = _hathway_reason_select_locator(page, modal)
    if sel is not None and sel.count() > 0:
        try:
            sel.wait_for(state='attached', timeout=8000)
        except Exception:
            pass
        try:
            sel.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        for fb in fallbacks:
            if not fb:
                continue
            try:
                sel.select_option(label=re.compile(r'^\s*' + re.escape(fb) + r'\s*$', re.I), timeout=3500)
                return
            except Exception:
                pass
            try:
                sel.select_option(label=fb, timeout=3500)
                return
            except Exception:
                pass
            try:
                sel.select_option(label=re.compile(re.escape(fb), re.I), timeout=3500)
                return
            except Exception:
                pass
        try:
            sel.click(timeout=5000, force=True)
        except Exception:
            pass
        page.wait_for_timeout(open_ms)
        picked = sel.evaluate(
            """(el, prefs) => {
                const norm = (s) =>
                    (s || '')
                        .toLowerCase()
                        .replace(/[\u2013\u2014\u2212]/g, '-')
                        .replace(/\\s+/g, ' ')
                        .trim();
                const prefsN = (prefs || []).map(norm).filter(Boolean);
                const scoreOpt = (t) => {
                    const x = norm(t);
                    if (!x || /^select\\s+reason/i.test(x)) return -1;
                    let best = 0;
                    for (const p of prefsN) {
                        if (!p) continue;
                        if (x === p) return 100;
                        if (x.includes(p) || p.includes(x)) best = Math.max(best, 85);
                        const ptoks = p.split(/[\\s\\-,.]+/).filter((w) => w.length > 2);
                        let hit = 0;
                        for (const w of ptoks) if (x.includes(w)) hit++;
                        if (ptoks.length) best = Math.max(best, (hit / ptoks.length) * 55);
                    }
                    return best;
                };
                let bestI = -1;
                let bestS = -1;
                for (let i = 0; i < el.options.length; i++) {
                    const t = (el.options[i].text || '').trim();
                    const s = scoreOpt(t);
                    if (s > bestS) {
                        bestS = s;
                        bestI = i;
                    }
                }
                if (bestI < 0 || bestS < 18) return '';
                el.selectedIndex = bestI;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return (el.options[bestI].text || '').trim();
            }""",
            prefs,
        )
        if picked:
            return
        for fb in fallbacks:
            if not fb:
                continue
            try:
                sel.select_option(label=fb, timeout=4000)
                return
            except Exception:
                continue
        try:
            nopt = min(sel.evaluate('el => el.options.length') or 0, 40)
            for i in range(1, nopt):
                try:
                    lab = (sel.evaluate('(el, i) => (el.options[i] && el.options[i].text) || ""', i) or '').strip()
                    if not lab or re.match(r'^\s*select\s+reason', lab, re.I):
                        continue
                    for fb in fallbacks:
                        if _hathway_normalize_reason_compare(fb) in _hathway_normalize_reason_compare(lab) or (
                            _hathway_normalize_reason_compare(lab) in _hathway_normalize_reason_compare(fb)
                        ):
                            sel.select_option(index=i, timeout=3000)
                            return
                except Exception:
                    continue
        except Exception:
            pass
        raise RuntimeError(f'Could not select reason "{reason_label}" in modal (native <select>).')

    sel2 = modal.locator(
        '.select2-selection, span.select2-selection__rendered, .select2-container a'
    ).first
    if sel2.count() > 0:
        try:
            sel2.click(timeout=8000, force=True)
        except Exception:
            modal.locator('.select2-container').first.click(timeout=8000, force=True)
        page.wait_for_timeout(open_ms)
        for fb in fallbacks:
            if not fb:
                continue
            opt_r = re.compile(re.escape(fb), re.I)
            opt = page.locator('.select2-results__option, li.select2-results__option').filter(has_text=opt_r).first
            try:
                if opt.count() > 0:
                    opt.wait_for(state='visible', timeout=8000)
                    opt.click(timeout=8000, force=True)
                    return
            except Exception:
                continue
        opt = page.locator('.select2-results__option, li.select2-results__option').filter(has_text=opt_re).first
        try:
            if opt.count() > 0:
                opt.wait_for(state='visible', timeout=12000)
                opt.click(timeout=8000, force=True)
                return
        except Exception:
            pass
        raise RuntimeError(f'Could not pick reason "{reason_label}" in Select2 dropdown.')

    try:
        modal.get_by_text(re.compile(r'Select\s+Reason', re.I)).first.click(timeout=6000, force=True)
    except Exception:
        modal.locator('td, label, div').filter(has_text=re.compile(r'Reason', re.I)).first.click(timeout=5000, force=True)
    page.wait_for_timeout(open_ms)
    for fb in fallbacks:
        if not fb:
            continue
        opt_r = re.compile(re.escape(fb), re.I)
        opt = page.get_by_role('option', name=opt_r).first
        if opt.count() == 0:
            opt = page.locator('option, li, a, div, span').filter(has_text=opt_r).first
        try:
            if opt.count() > 0:
                opt.wait_for(state='visible', timeout=8000)
                opt.click(timeout=8000, force=True)
                return
        except Exception:
            continue
    opt = page.get_by_role('option', name=opt_re).first
    if opt.count() > 0:
        opt.wait_for(state='visible', timeout=12000)
        opt.click(timeout=8000, force=True)
        return
    opt2 = page.locator('option, li, a, div, span').filter(has_text=opt_re).first
    if opt2.count() > 0:
        opt2.wait_for(state='visible', timeout=12000)
        opt2.click(timeout=8000, force=True)
        return
    raise RuntimeError(f'Could not pick reason "{reason_label}" from listbox / Select2.')


def _hathway_cancel_pack_modal_chain(page, cancel_reason):
    """Confirmation → reason Customer request → wait 1s → Confirm → Yes/Confirm → Cancel Pack Status OK."""
    _hathway_remove_pack_step_pause(page)
    page.get_by_text(
        re.compile(r'This will cancel the plan|cancel the plan with following', re.I)
    ).first.wait_for(state='visible', timeout=90000)
    page.wait_for_timeout(400)
    modal = page.locator('[role="dialog"], .modal.in, .modal.show, .modal, .ui-dialog').filter(
        has_text=re.compile(r'cancel the plan', re.I)
    ).last
    if modal.count() == 0:
        modal = page.locator('div').filter(has_text=re.compile(r'This will cancel the plan', re.I)).last
    _hathway_modal_select_reason_only(page, modal, cancel_reason)
    wait_after = int(os.getenv('HATHWAY_CANCEL_PACK_REASON_WAIT_MS', '1000'))
    page.wait_for_timeout(max(0, wait_after))
    for conf in (
        modal.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
        modal.locator('input[type="submit"][value*="Confirm" i]').first,
        modal.locator('input[type="button"][value*="Confirm" i]').first,
    ):
        try:
            if conf.count() == 0:
                continue
            conf.click(timeout=10000, force=True)
            break
        except Exception:
            continue
    else:
        raise RuntimeError('Confirm not found on cancel-pack dialog.')

    page.wait_for_timeout(600)
    box2 = page.locator('[role="dialog"], .ui-dialog, .modal').filter(
        has_text=re.compile(r'sure you want to cancel|not autorenew', re.I)
    ).last
    if box2.count() == 0:
        box2 = page.locator('body')
    clicked = False
    for btn in (
        box2.get_by_role('button', name=re.compile(r'^\s*Yes\s*$', re.I)).first,
        box2.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
        box2.locator('input[type="submit"][value*="Yes" i]').first,
        box2.locator('input[type="button"][value*="Yes" i]').first,
    ):
        try:
            if btn.count() == 0:
                continue
            if btn.is_visible(timeout=3000):
                btn.click(timeout=10000, force=True)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        page.get_by_role('button', name=re.compile(r'^\s*Yes\s*$', re.I)).first.click(timeout=10000, force=True)

    page.get_by_text(re.compile(r'Cancel Pack Status|cancel plan completed successfully', re.I)).first.wait_for(
        state='visible', timeout=90000
    )
    page.wait_for_timeout(400)
    dlg3 = page.locator('[role="dialog"], .ui-dialog, .modal').filter(
        has_text=re.compile(r'Cancel Pack Status|cancel plan completed', re.I)
    ).last
    for okb in (
        dlg3.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).first,
        page.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).last,
    ):
        try:
            if okb.count() == 0:
                continue
            if okb.is_visible(timeout=3000):
                okb.click(timeout=10000, force=True)
                break
        except Exception:
            continue
    page.wait_for_timeout(800)
    cleanup_hathway_ui(page)


_HATHWAY_RENEW_DIALOG_HINT_RE = re.compile(
    r'renew\s*my\s*pack|renew\s*subscription|pack\s*renewal|renew\s*plan\b|'
    r'would\s*you\s*like\s*to\s*renew|renewal\s*request|renew\s*your\s*pack|subscribe\s*to\s*renew',
    re.I,
)


def _hathway_renew_pack_modal_chain(page, renew_reason=None):
    """Bouquet **RENEW** → optional reason → Confirm → optional Yes → success OK."""
    _hathway_remove_pack_step_pause(page)
    renew_reason = (renew_reason or os.getenv('HATHWAY_RENEW_REASON') or '').strip()

    if not _hathway_wait_visible_text_match(page, _HATHWAY_RENEW_DIALOG_HINT_RE, timeout_ms=90000):
        raise RuntimeError('Renew pack dialog did not appear (portal wording may differ).')

    page.wait_for_timeout(450)
    modal = (
        page.locator('[role="dialog"], .modal.in, .modal.show, .modal, .ui-dialog')
        .filter(has_text=_HATHWAY_RENEW_DIALOG_HINT_RE)
        .last
    )
    if modal.count() == 0:
        modal = page.locator('div').filter(has_text=_HATHWAY_RENEW_DIALOG_HINT_RE).last

    if renew_reason:
        try:
            if modal.locator('select').count() > 0:
                _hathway_modal_select_reason_only(page, modal, renew_reason)
                wait_after = int(
                    os.getenv(
                        'HATHWAY_RENEW_REASON_WAIT_MS',
                        os.getenv('HATHWAY_CANCEL_PACK_REASON_WAIT_MS', '1000'),
                    )
                )
                page.wait_for_timeout(max(0, wait_after))
        except Exception:
            pass

    clicked = False
    for conf in (
        modal.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
        modal.locator('input[type="submit"][value*="Confirm" i]').first,
        modal.locator('input[type="button"][value*="Confirm" i]').first,
        modal.get_by_role('button', name=re.compile(r'^\s*Proceed\s*$', re.I)).first,
    ):
        try:
            if conf.count() == 0:
                continue
            if conf.is_visible(timeout=3000):
                conf.click(timeout=10000, force=True)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        if not _hathway_modal_click_named(
            page, _HATHWAY_RENEW_DIALOG_HINT_RE, re.compile(r'^\s*Confirm\s*$', re.I), timeout_ms=12000
        ):
            raise RuntimeError('Confirm not found on renew-pack dialog.')

    page.wait_for_timeout(650)
    box2 = page.locator('[role="dialog"], .ui-dialog, .modal').filter(
        has_text=re.compile(r'sure.*renew|renew.*sure|confirm.*renew', re.I)
    ).last
    if box2.count() > 0:
        for btn in (
            box2.get_by_role('button', name=re.compile(r'^\s*Yes\s*$', re.I)).first,
            box2.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
            box2.locator('input[type="submit"][value*="Yes" i]').first,
            box2.locator('input[type="button"][value*="Yes" i]').first,
        ):
            try:
                if btn.count() == 0:
                    continue
                if btn.is_visible(timeout=2500):
                    btn.click(timeout=10000, force=True)
                    break
            except Exception:
                continue

    success_re = re.compile(
        r'renew.*success|renewal.*success|renew\s*pack|pack\s*renew|subscription\s*renew|'
        r'renewal\s*completed|completed\s+successfully|request\s*submitted',
        re.I,
    )
    if not _hathway_wait_visible_text_match(page, success_re, timeout_ms=90000):
        raise RuntimeError('Renew completion message not detected (portal wording may differ).')

    page.wait_for_timeout(400)
    dlg3 = page.locator('[role="dialog"], .ui-dialog, .modal').filter(has_text=success_re).last
    for okb in (
        dlg3.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).first,
        page.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).last,
        page.locator('input[type="button"][value="OK" i]').last,
        page.locator('input[type="submit"][value="OK" i]').last,
    ):
        try:
            if okb.count() == 0:
                continue
            if okb.is_visible(timeout=3000):
                okb.click(timeout=10000, force=True)
                break
        except Exception:
            continue
    page.wait_for_timeout(800)
    cleanup_hathway_ui(page)


def _hathway_all_cancel_modal_wait_ms():
    return max(0, int(os.getenv('HATHWAY_ALL_CANCEL_MODAL_WAIT_MS', '3000')))


def _hathway_all_cancel_post_toolbar_ms():
    """Extra wait after clicking toolbar ALL Cancel before expecting the sheet (UpdatePanel delay)."""
    return max(0, int(os.getenv('HATHWAY_ALL_CANCEL_POST_TOOLBAR_MS', '2200')))


def _hathway_all_cancel_ok_preclick_ms():
    """After the ALL Cancel plan sheet is detected, wait this long before clicking OK (default 3s)."""
    return max(0, int(os.getenv('HATHWAY_ALL_CANCEL_OK_WAIT_MS', '3000')))


def _hathway_modal_search_roots(page):
    roots = [page]
    try:
        for fr in list(page.frames):
            try:
                if fr.is_detached():
                    continue
            except Exception:
                continue
            if fr is getattr(page, 'main_frame', None):
                continue
            roots.append(fr)
    except Exception:
        pass
    return roots


def _hathway_all_cancel_action_visible(page):
    """True if Main TV shows an ALL Cancel control (toolbar or equivalent)."""
    re_ac = re.compile(r'ALL\s*Cancel', re.I)
    for ctx in _hathway_pack_dom_roots(page):
        try:
            if ctx.get_by_role('button', name=re_ac).count() > 0:
                return True
            if ctx.get_by_role('link', name=re_ac).count() > 0:
                return True
            if ctx.locator('input[type="button"], input[type="submit"]').filter(has_text=re_ac).count() > 0:
                return True
            if bool(
                ctx.evaluate(
                    """() => {
                        const norm = (s) =>
                            (s || '')
                                .replace(/\\u00a0/g, ' ')
                                .replace(/\\s+/g, ' ')
                                .trim();
                        const want = /all\\s*cancel/i;
                        for (const el of document.querySelectorAll(
                            'input[type="button"], input[type="submit"], button, a, span[onclick], td[onclick]'
                        )) {
                            if (!el.offsetParent) continue;
                            const t = norm(el.value || el.innerText || el.textContent || '');
                            if (want.test(t)) return true;
                        }
                        return false;
                    }"""
                )
            ):
                return True
        except Exception:
            continue
    return False


def _hathway_click_all_cancel_toolbar_js(ctx):
    try:
        return bool(
            ctx.evaluate(
                """() => {
                    const norm = (s) =>
                        (s || '')
                            .replace(/\\u00a0/g, ' ')
                            .replace(/\\s+/g, ' ')
                            .trim();
                    const want = /all\\s*cancel/i;
                    const txt = (el) => norm(el.value || el.innerText || el.textContent || el.getAttribute('aria-label') || '');
                    const nodes = [...document.querySelectorAll(
                        'input[type="button"], input[type="submit"], button, a, span[onclick], td[onclick], div[onclick]'
                    )];
                    const hits = [];
                    for (const el of nodes) {
                        if (!el.offsetParent) continue;
                        if (!want.test(txt(el))) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width < 20 || r.height < 6 || r.width > 640) continue;
                        hits.push({ el, a: r.width * r.height });
                    }
                    hits.sort((x, y) => x.a - y.a);
                    for (const { el } of hits.slice(0, 10)) {
                        try {
                            el.scrollIntoView({ block: 'center', inline: 'nearest' });
                            el.click();
                            return true;
                        } catch (e) {}
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


def _hathway_click_all_cancel_toolbar(page):
    re_ac = re.compile(r'ALL\s*Cancel', re.I)
    for ctx in _hathway_pack_dom_roots(page):
        try:
            for loc in (
                ctx.get_by_role('button', name=re_ac),
                ctx.get_by_role('link', name=re_ac),
                ctx.locator('input[type="button"], input[type="submit"]').filter(has_text=re_ac),
            ):
                if loc.count() == 0:
                    continue
                for i in range(min(loc.count(), 15)):
                    el = loc.nth(i)
                    try:
                        if el.is_visible(timeout=2000):
                            el.scroll_into_view_if_needed(timeout=6000)
                            el.click(timeout=12000, force=True)
                            return True
                    except Exception:
                        continue
            if _hathway_click_all_cancel_toolbar_js(ctx):
                return True
        except Exception:
            continue
    return False


def _hathway_wait_visible_text_match(page, text_re, timeout_ms=90000):
    """
    Wait until *some* element matching ``text_re`` is actually visible (not a hidden template span).
    Scans main page and iframes — avoids ``get_by_text().first`` resolving to ``display:none`` nodes.
    """
    deadline = time.monotonic() + max(2.0, timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        for ctx in _hathway_modal_search_roots(page):
            try:
                loc = ctx.get_by_text(text_re)
                n = min(loc.count(), 30)
                for i in range(n):
                    try:
                        if loc.nth(i).is_visible(timeout=200):
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        page.wait_for_timeout(280)
    return False


def _hathway_click_all_cancel_plan_sheet_ok(page, timeout_ms=12000):
    """
    Click OK on the ALL Cancel plan sheet (Plan Name table). Sheet is often a plain div; Playwright
    ``.last`` modal can miss OK — alternate ``_hathway_modal_click_named`` with a targeted JS click.
    Caller should wait ``_hathway_all_cancel_ok_preclick_ms()`` after the sheet appears; ``timeout_ms``
    is only for brief retries if the first OK click misses (default 12s, not a long poll).
    """
    deadline = time.monotonic() + max(1.0, timeout_ms / 1000.0)
    modal_f = re.compile(r'ALL\s*Cancel', re.I)
    ok_re = re.compile(r'^\s*OK\s*$', re.I)
    while time.monotonic() < deadline:
        if _hathway_modal_click_named(page, modal_f, ok_re, timeout_ms=900):
            return True
        for ctx in _hathway_modal_search_roots(page):
            try:
                if bool(
                    ctx.evaluate(
                        """() => {
                            const roots = [...document.querySelectorAll(
                                'div, [role="dialog"], .modal, .ui-dialog, .popupwindow, [class*="modal" i]'
                            )];
                            const candidates = [];
                            for (const root of roots) {
                                if (!root || !root.offsetParent) continue;
                                const t = (root.innerText || '').replace(/\\s+/g, ' ');
                                if (t.length > 11000) continue;
                                if (!/all\\s*cancel/i.test(t)) continue;
                                if (!/plan\\s*name/i.test(t)) continue;
                                candidates.push(root);
                            }
                            for (let i = candidates.length - 1; i >= 0; i--) {
                                const root = candidates[i];
                                for (const el of root.querySelectorAll(
                                    'input[type="submit"], input[type="button"], button, a'
                                )) {
                                    if (!el.offsetParent) continue;
                                    const v = ((el.value || el.textContent || '') + '')
                                        .replace(/\\s+/g, ' ')
                                        .trim();
                                    if (!/^ok\\.?$/i.test(v)) continue;
                                    try {
                                        el.scrollIntoView({ block: 'center', inline: 'nearest' });
                                    } catch (e) {}
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }"""
                    )
                ):
                    return True
            except Exception:
                pass
        page.wait_for_timeout(180)
    return False


def _hathway_click_label_in_modal_container(modal_box, label: str) -> bool:
    """
    Click button-like control whose visible label / value matches `label` (e.g. OK, Yes).
    ASP.NET often uses <input type="submit" value="OK"> — no role=button, empty textContent.
    """
    want = (label or '').strip().upper()
    if not want:
        return False
    try:
        return bool(
            modal_box.first.evaluate(
                """(root, w) => {
                    const want = String(w || '').toUpperCase();
                    const norm = (s) =>
                        (s || '')
                            .replace(/\\u00a0/g, ' ')
                            .replace(/\\s+/g, ' ')
                            .trim()
                            .toUpperCase();
                    const rootEl = !root || root.nodeType === 9 ? document.body : root;
                    const nodes = [...rootEl.querySelectorAll(
                        'button, a, input[type="submit"], input[type="button"], input[type="image"], [role="button"], span[onclick]'
                    )];
                    const visible = (el) => {
                        if (!el || !el.offsetParent) return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 4 && r.height > 3;
                    };
                    const matches = (el) => {
                        const v = norm(el.value || el.innerText || el.textContent || '');
                        const a = norm((el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('title'))) || '');
                        if (v === want || a === want) return true;
                        if (want === 'OK' && /^OK\\.?$/i.test(v)) return true;
                        if (want === 'YES' && /^YES\\.?$/i.test(v)) return true;
                        return false;
                    };
                    for (const el of nodes) {
                        if (!visible(el) || !matches(el)) continue;
                        try {
                            el.scrollIntoView({ block: 'center', inline: 'nearest' });
                            if (typeof el.focus === 'function') el.focus();
                            el.click();
                            return true;
                        } catch (e) {}
                    }
                    return false;
                }""",
                want,
            )
        )
    except Exception:
        return False


def _hathway_modal_click_named(page, modal_filter, name_re, timeout_ms=70000):
    """Click a button (or submit) named name_re inside the last modal matching modal_filter."""
    sec = timeout_ms / 1000.0
    if sec >= 3.0:
        budget = max(3.0, sec)
    else:
        budget = max(0.25, sec)
    deadline = time.monotonic() + budget
    pat = getattr(name_re, 'pattern', str(name_re))
    want_plain = None
    m = re.search(r'\b(OK|YES)\b', pat, re.I)
    if m:
        want_plain = m.group(1).upper()
    while time.monotonic() < deadline:
        for ctx in _hathway_modal_search_roots(page):
            try:
                modal = (
                    ctx.locator(
                        '[role="dialog"], .modal.in, .modal.show, .modal, .ui-dialog, '
                        '.popupwindow, .fancybox-wrap, [class*="Modal"], [class*="modal"], [id*="Modal" i]'
                    ).filter(modal_filter)
                )
                if modal.count() == 0:
                    modal = ctx.locator('div').filter(modal_filter)
                if modal.count() == 0:
                    continue
                box = modal.last
                if want_plain and _hathway_click_label_in_modal_container(box, want_plain):
                    return True
                extra_first = []
                if want_plain == 'OK':
                    extra_first.extend(
                        [
                            box.locator('input[type="submit"][value="OK" i]').first,
                            box.locator('input[type="button"][value="OK" i]').first,
                            box.locator('input[type="submit"][value="Ok"]').first,
                        ]
                    )
                elif want_plain == 'YES':
                    extra_first.extend(
                        [
                            box.locator('input[type="submit"][value="Yes" i]').first,
                            box.locator('input[type="button"][value="Yes" i]').first,
                        ]
                    )
                for cand in (
                    *extra_first,
                    box.get_by_role('button', name=name_re).first,
                    box.get_by_role('link', name=name_re).first,
                    box.locator('input[type="submit"], input[type="button"]').filter(has_text=name_re).first,
                    box.get_by_text(name_re).first,
                ):
                    try:
                        if cand.count() == 0:
                            continue
                        if cand.is_visible(timeout=2500):
                            cand.scroll_into_view_if_needed(timeout=5000)
                            cand.click(timeout=12000, force=True)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        page.wait_for_timeout(280)
    return False


def _hathway_wait_modal_text(page, text_re, timeout_ms=70000):
    deadline = time.monotonic() + max(2.0, timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        for ctx in _hathway_modal_search_roots(page):
            try:
                t = ctx.get_by_text(text_re).first
                if t.count() > 0 and t.is_visible(timeout=1200):
                    return True
            except Exception:
                continue
        page.wait_for_timeout(280)
    return False


def _hathway_wait_all_cancel_plan_sheet(page, timeout_ms=90000):
    """Wait for the ALL Cancel plan sheet (table / Plan Name or plan rows inside a popup)."""
    deadline = time.monotonic() + max(2.0, timeout_ms / 1000.0)
    t1 = re.compile(r'ALL\s*Cancel', re.I)
    t2 = re.compile(r'Plan\s*Name', re.I)
    while time.monotonic() < deadline:
        for ctx in _hathway_modal_search_roots(page):
            try:
                if bool(
                    ctx.evaluate(
                        """() => {
                            const roots = [...document.querySelectorAll(
                                '[role="dialog"], .modal, .ui-dialog, .popupwindow, [class*="modal" i], [id*="modal" i]'
                            )];
                            for (const d of roots) {
                                if (!d || !d.offsetParent) continue;
                                const t = (d.innerText || '').replace(/\\s+/g, ' ');
                                if (t.length > 14000) continue;
                                if (!/all\\s*cancel/i.test(t)) continue;
                                if (/plan\\s*name/i.test(t)) return true;
                                if (d.querySelector('table') && /cancel/i.test(t)) return true;
                            }
                            return false;
                        }"""
                    )
                ):
                    return True
            except Exception:
                pass
            try:
                m = (
                    ctx.locator(
                        '[role="dialog"], .modal.in, .modal.show, .modal, .ui-dialog, '
                        '.popupwindow, .fancybox-wrap, [class*="Modal"], [class*="modal"], [id*="Modal" i]'
                    )
                    .filter(has_text=t1)
                    .filter(has_text=t2)
                )
                if m.count() > 0 and m.first.is_visible(timeout=1500):
                    return True
                m3 = ctx.locator(
                    '[role="dialog"], .modal, .ui-dialog, .popupwindow, [class*="modal" i]'
                ).filter(has_text=t1)
                if m3.count() > 0:
                    try:
                        if m3.first.locator('table').count() > 0 and m3.first.is_visible(timeout=1500):
                            return True
                    except Exception:
                        pass
            except Exception:
                continue
        page.wait_for_timeout(300)
    return False


def _hathway_remove_pack_via_all_cancel(page):
    """
    Main TV → ALL Cancel → (wait) ALL Cancel sheet OK → (wait) Confirmation Yes →
    (wait) Cancel Pack Status OK. Does not use bouquet ▼ or cancel-reason chain from bouquet.
    """
    pause = _hathway_all_cancel_modal_wait_ms()
    if not _hathway_click_all_cancel_toolbar(page):
        return False
    page.wait_for_timeout(_hathway_all_cancel_post_toolbar_ms())
    if not _hathway_wait_all_cancel_plan_sheet(page, 90000):
        return False
    page.wait_for_timeout(_hathway_all_cancel_ok_preclick_ms())
    if not _hathway_click_all_cancel_plan_sheet_ok(page, timeout_ms=12000):
        return False
    page.wait_for_timeout(pause)
    if not _hathway_wait_modal_text(page, re.compile(r'Confirmation|Are you sure you want to cancel', re.I), 70000):
        return False
    if not _hathway_modal_click_named(
        page,
        re.compile(r'Confirmation', re.I),
        re.compile(r'^\s*Yes\s*$', re.I),
    ):
        return False
    page.wait_for_timeout(pause)
    if not _hathway_wait_modal_text(
        page, re.compile(r'Cancel\s*Pack\s*Status|cancel plan completed successfully', re.I), 70000
    ):
        return False
    if not _hathway_modal_click_named(
        page,
        re.compile(r'Cancel\s*Pack\s*Status', re.I),
        re.compile(r'^\s*OK\s*$', re.I),
    ):
        return False
    page.wait_for_timeout(500)
    cleanup_hathway_ui(page)
    return True


def _hathway_remove_pack_via_bouquet_menu(page, cancel_reason):
    """
    Bouquet row ▼ → CANCEL → cancel-reason modal chain.

    Returns (True, None) on success, or (False, err_key) where err_key is one of:
    ``no_dropdown``, ``menu_missing``, ``cancel_missing``, ``modal``.
    """
    if not _hathway_click_bouquet_action_dropdown(page):
        return False, 'no_dropdown'
    if not _hathway_click_bouquet_menu_cancel(page):
        if not _hathway_bouquet_row_menu_visible(page):
            return False, 'menu_missing'
        return False, 'cancel_missing'
    try:
        _hathway_cancel_pack_modal_chain(page, cancel_reason)
    except Exception:
        return False, 'modal'
    return True, None


def _hathway_renew_pack_via_bouquet_menu(page, renew_reason=None):
    """
    Bouquet row ▼ → RENEW → renew modal chain.

    Returns (True, None) on success, or (False, err_key) where err_key is one of:
    ``no_dropdown``, ``menu_missing``, ``renew_missing``, ``modal``.
    """
    if not _hathway_click_bouquet_action_dropdown(page):
        return False, 'no_dropdown'
    if not _hathway_click_bouquet_menu_renew(page):
        if not _hathway_bouquet_row_menu_visible(page):
            return False, 'menu_missing'
        return False, 'renew_missing'
    try:
        _hathway_renew_pack_modal_chain(page, renew_reason=renew_reason)
    except Exception:
        return False, 'modal'
    return True, None


def _hathway_click_terminate_main_tv(page, wait_visible_ms=42000):
    """
    Terminate on Main TV after pack removal. Waits for grid refresh, then clicks in page or iframes
    (Terminate often lives in the same frame as the bouquet table; page.evaluate alone misses it).
    """
    cleanup_hathway_ui(page)
    page.wait_for_timeout(_hathway_terminate_after_pack_settle_ms())
    deadline = time.monotonic() + max(1.5, wait_visible_ms / 1000.0)
    term_btn_name = re.compile(r'^\s*Terminate\s*$', re.I)

    def _try_click_on(ctx):
        candidates = [
            ctx.locator('input[type="button"][value="Terminate"]'),
            ctx.locator('input[type="submit"][value="Terminate"]'),
            ctx.locator('input[type="button"][value="Terminate" i]'),
            ctx.locator('input[type="submit"][value="Terminate" i]'),
            ctx.locator('input[type="button"][value*="Terminate" i]'),
            ctx.locator('input[type="submit"][value*="Terminate" i]'),
            ctx.get_by_role('button', name=term_btn_name),
            ctx.get_by_role('link', name=term_btn_name),
        ]
        for loc in candidates:
            try:
                if loc.count() == 0:
                    continue
                btn = loc.first
                if not btn.is_visible(timeout=1400):
                    continue
                btn.scroll_into_view_if_needed(timeout=5000)
                btn.click(timeout=10000, force=True)
                return True
            except Exception:
                continue
        try:
            return bool(
                ctx.evaluate(
                    """() => {
                        const nodes = [...document.querySelectorAll(
                            'input[type="button"], input[type="submit"], button, a, [role="button"]'
                        )];
                        for (const el of nodes) {
                            if (!el.offsetParent) continue;
                            const raw = (
                                (el.value || el.textContent || el.getAttribute('aria-label') || '') + ''
                            )
                                .replace(/\\s+/g, ' ')
                                .trim();
                            if (!/^terminate$/i.test(raw)) continue;
                            el.click();
                            return true;
                        }
                        return false;
                    }"""
                )
            )
        except Exception:
            return False

    while time.monotonic() < deadline:
        cleanup_hathway_ui(page)
        for ctx in _hathway_terminate_click_contexts(page):
            if _try_click_on(ctx):
                return True
        page.wait_for_timeout(420)
    return False


def _hathway_click_terminate_confirmation_submit(page):
    """
    Hathway second confirmation: title often 'Confirmation', text 'Are You Sure? You Want To Terminate',
    buttons Submit + Cancel. Shell is frequently a plain div (not .modal / role=dialog), so role-based
    modal filters miss it. Search page + iframes; Playwright first, then JS.
    """
    submit_name = re.compile(r'^\s*Submit\s*$', re.I)
    for ctx in _hathway_modal_search_roots(page):
        shells = [
            ctx.locator('div, [role="dialog"], .ui-dialog, .modal').filter(
                has_text=re.compile(r'Want\s+To\s+Terminate|You\s+Want\s+To\s+Terminate', re.I)
            ).filter(has_text=re.compile(r'Submit', re.I)),
            ctx.locator('div, [role="dialog"], .ui-dialog, .modal').filter(
                has_text=re.compile(r'Confirmation', re.I)
            ).filter(has_text=re.compile(r'Want\s+To\s+Terminate|You\s+Want\s+To\s+Terminate', re.I)),
        ]
        for shell in shells:
            try:
                box = shell.last
                if box.count() == 0:
                    continue
            except Exception:
                continue
            for loc in (
                box.locator('input[type="submit"][value="Submit" i]'),
                box.locator('input[type="button"][value="Submit" i]'),
                box.locator('input[type="submit"][value*="Submit" i]'),
                box.locator('input[type="button"][value*="Submit" i]'),
                box.get_by_role('button', name=submit_name),
                box.locator('button, a').filter(has_text=submit_name),
            ):
                try:
                    if loc.count() == 0:
                        continue
                    el = loc.first
                    if not el.is_visible(timeout=2200):
                        continue
                    el.scroll_into_view_if_needed(timeout=4000)
                    el.click(timeout=10000, force=True)
                    return True
                except Exception:
                    continue
        try:
            if bool(
                ctx.evaluate(
                    """() => {
                        const blocks = [...document.querySelectorAll(
                            'div, [role="dialog"], .modal, .ui-dialog, .popupwindow'
                        )];
                        for (const root of blocks) {
                            if (!root.offsetParent) continue;
                            const t = (root.innerText || '').replace(/\\s+/g, ' ');
                            if (t.length > 6000) continue;
                            if (!/want\\s+to\\s+terminate|you\\s+want\\s+to\\s+terminate/i.test(t)) continue;
                            const inputs = [
                                ...root.querySelectorAll('input[type="submit"], input[type="button"], button'),
                            ];
                            for (const el of inputs) {
                                const v = ((el.value || el.textContent || '') + '')
                                    .replace(/\\s+/g, ' ')
                                    .trim();
                                if (!/^submit$/i.test(v) || !el.offsetParent) continue;
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }"""
                )
            ):
                return True
        except Exception:
            pass
    return False


def _hathway_terminate_stb_modal_chain(page, terminate_reason):
    """TERMINATE modal → reason → Submit → Confirm → Submit (sure) → Message OK."""
    _hathway_remove_pack_step_pause(page)
    for hint in (
        re.compile(r'\bTERMINATE\b', re.I),
        re.compile(r'Terminate\s*STB', re.I),
    ):
        try:
            page.get_by_text(hint).first.wait_for(state='visible', timeout=20000)
            break
        except Exception:
            continue
    else:
        page.get_by_text(re.compile(r'\bTERMINATE\b', re.I)).first.wait_for(state='visible', timeout=90000)
    page.wait_for_timeout(400)
    modal = page.locator('div, [role="dialog"], .ui-dialog, .modal').filter(
        has_text=re.compile(r'\bTERMINATE\b', re.I)
    ).filter(has_text=re.compile(r'VC/MAC ID|STB/MAC ID', re.I)).last
    if modal.count() == 0:
        modal = page.locator('[role="dialog"], .ui-dialog, .modal').filter(
            has_text=re.compile(r'TERMINATE|Terminate', re.I)
        ).filter(has_text=re.compile(r'Reason', re.I)).last
    if modal.count() == 0:
        modal = page.locator('div').filter(has_text=re.compile(r'STB/MAC ID', re.I)).filter(
            has_text=re.compile(r'VC/MAC ID', re.I)
        ).last
    _hathway_modal_select_reason_only(page, modal, terminate_reason)
    page.wait_for_timeout(500)
    for sub in (
        modal.get_by_role('button', name=re.compile(r'^\s*Submit\s*$', re.I)).first,
        modal.locator('input[type="submit"][value*="Submit" i]').first,
        modal.locator('input[type="button"][value*="Submit" i]').first,
    ):
        try:
            if sub.count() == 0:
                continue
            if sub.is_visible(timeout=2500):
                sub.click(timeout=10000, force=True)
                break
        except Exception:
            continue
    else:
        for sub2 in (
            page.get_by_role('button', name=re.compile(r'^\s*Submit\s*$', re.I)).first,
            page.locator('input[type="submit"][value*="Submit" i]').first,
            page.locator('input[type="button"][value*="Submit" i]').first,
        ):
            try:
                if sub2.count() > 0 and sub2.is_visible(timeout=2000):
                    sub2.click(timeout=10000, force=True)
                    break
            except Exception:
                continue

    page.wait_for_timeout(600)
    conf_box = page.locator('[role="dialog"], .ui-dialog, .modal').filter(
        has_text=re.compile(r'VC/MAC ID|STB/MAC ID', re.I)
    ).filter(has_text=re.compile(r'Reason\s*:', re.I)).last
    clicked_conf = False
    for cbtn in (
        conf_box.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).first,
        page.get_by_role('button', name=re.compile(r'^\s*Confirm\s*$', re.I)).last,
        conf_box.locator('input[type="submit"][value*="Confirm" i]').first,
        conf_box.locator('input[type="button"][value*="Confirm" i]').first,
    ):
        try:
            if cbtn.count() == 0:
                continue
            if cbtn.is_visible(timeout=4000):
                cbtn.click(timeout=10000, force=True)
                clicked_conf = True
                break
        except Exception:
            continue
    if not clicked_conf:
        try:
            page.locator('input[type="submit"][value*="Confirm" i]').first.click(timeout=10000, force=True)
        except Exception:
            pass

    page.wait_for_timeout(600)
    # Do not match hidden pack-cancel copy (e.g. MasterBody_lblPopupText2 "Are you sure you want to cancel?")
    # which satisfies a naive "Are You Sure" regex but is not the terminate dialog.
    _terminate_sure_visible = re.compile(
        r'Want\s+To\s+Terminate|You\s+Want\s+To\s+Terminate', re.I
    )
    if not _hathway_wait_visible_text_match(page, _terminate_sure_visible, 95000):
        raise RuntimeError(
            'Terminate confirmation (visible "Want To Terminate") did not appear after Confirm — '
            'wrong dialog, hidden template text only, or flow still on pack cancel.'
        )
    clicked_sure = False
    sure_boxes = [
        page.locator('div, [role="dialog"], .ui-dialog, .modal').filter(
            has_text=re.compile(r'Want\s+To\s+Terminate|You\s+Want\s+To\s+Terminate', re.I)
        ),
        page.locator('div, [role="dialog"], .ui-dialog, .modal').filter(
            has_text=re.compile(r'Confirmation', re.I)
        ).filter(has_text=re.compile(r'Want\s+To\s+Terminate|You\s+Want\s+To\s+Terminate', re.I)),
    ]
    for sure in sure_boxes:
        try:
            if sure.count() == 0:
                continue
        except Exception:
            continue
        box = sure.last
        for sbtn in (
            box.locator('input[type="submit"][value="Submit" i]').first,
            box.locator('input[type="button"][value="Submit" i]').first,
            box.locator('input[type="submit"][value*="Submit" i]').first,
            box.locator('input[type="button"][value*="Submit" i]').first,
            box.get_by_role('button', name=re.compile(r'^\s*Submit\s*$', re.I)).first,
            box.get_by_role('button', name=re.compile(r'^\s*Yes\s*$', re.I)).first,
            page.get_by_role('button', name=re.compile(r'^\s*Submit\s*$', re.I)).last,
        ):
            try:
                if sbtn.count() == 0:
                    continue
                if sbtn.is_visible(timeout=4000):
                    sbtn.scroll_into_view_if_needed(timeout=4000)
                    sbtn.click(timeout=10000, force=True)
                    clicked_sure = True
                    break
            except Exception:
                continue
        if clicked_sure:
            break
    if not clicked_sure:
        clicked_sure = _hathway_click_terminate_confirmation_submit(page)
    if not clicked_sure:
        page.wait_for_timeout(550)
        cleanup_hathway_ui(page)
        clicked_sure = _hathway_click_terminate_confirmation_submit(page)

    page.wait_for_timeout(500)
    for done_hint in (
        re.compile(
            r'Depairing is Successful|Depairing|Pairing is Successful|STB and VC|'
            r'Termination.*[Ss]uccess|terminated successfully|STB.*terminated|'
            r'depairing.*success',
            re.I,
        ),
    ):
        try:
            page.get_by_text(done_hint).first.wait_for(state='visible', timeout=25000)
            break
        except Exception:
            continue
    else:
        page.get_by_text(
            re.compile(r'Depairing is Successful|Depairing|Pairing is Successful|STB and VC', re.I)
        ).first.wait_for(state='visible', timeout=90000)
    msg_modal = page.locator('[role="dialog"], .ui-dialog, .modal').filter(
        has_text=re.compile(r'Depairing|Pairing|STB and VC|terminated|Termination', re.I)
    ).last
    for okb in (
        msg_modal.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).first,
        msg_modal.locator('input[type="button"][value="OK" i]').first,
        msg_modal.locator('input[type="submit"][value="OK" i]').first,
        page.get_by_role('button', name=re.compile(r'^\s*OK\s*$', re.I)).last,
    ):
        try:
            if okb.count() == 0:
                continue
            if okb.is_visible(timeout=4000):
                okb.click(timeout=10000, force=True)
                break
        except Exception:
            continue
    page.wait_for_timeout(600)
    cleanup_hathway_ui(page)


def hathway_remove_pack_and_terminate_stb(page, stb_id, cancel_reason=None, terminate_reason=None):
    """
    Pack Management → Main TV → remove active pack, then Terminate STB.

    Pack removal uses **ALL Cancel** (toolbar) when ``HATHWAY_REMOVE_PACK_METHOD=all_cancel`` or when
    ``auto`` and the action is visible; if ``auto`` and ALL Cancel fails, it falls back to the **bouquet
    row ▼ → CANCEL** path. With ``HATHWAY_REMOVE_PACK_METHOD=bouquet`` only the bouquet path runs.
    Then Terminate (reason) → …
    """
    stb_id = (stb_id or '').strip()
    if not stb_id:
        return {'success': False, 'error': 'Empty STB / VC id', 'provider': 'hathway', 'search_value': ''}

    cancel_reason = (
        cancel_reason or os.getenv('HATHWAY_CANCEL_PACK_REASON') or 'Customer request'
    ).strip()
    terminate_reason = (
        terminate_reason
        or os.getenv('HATHWAY_TERMINATE_REASON')
        or 'Customers Request - Price Issue'
    ).strip()

    try:
        cleanup_hathway_ui(page)
        _hathway_click_vc_mac_search_mode(page)
        page.wait_for_timeout(300)

        _hathway_fill_pack_search(page, stb_id)
        _hathway_click_search(page)
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            page.wait_for_load_state('domcontentloaded', timeout=15000)
        page.wait_for_timeout(1200)
        cleanup_hathway_ui(page)

        body = page.locator('body').inner_text(timeout=15000)
        portal_msg = _hathway_search_portal_user_message(body)
        if portal_msg:
            return {'success': False, 'error': portal_msg, 'provider': 'hathway', 'search_value': stb_id}

        if re.search(r'no\s+record|not\s+found|invalid|no\s+match', body, re.I):
            return {
                'success': False,
                'error': 'No matching subscriber for this STB / VC id.',
                'provider': 'hathway',
                'search_value': stb_id,
            }

        if not _hathway_ensure_main_tv_tab(page):
            return {
                'success': False,
                'error': 'Could not open Main TV tab.',
                'provider': 'hathway',
                'search_value': stb_id,
            }
        page.wait_for_timeout(600)
        _hathway_remove_pack_step_pause(page)
        cleanup_hathway_ui(page)

        method = (os.getenv('HATHWAY_REMOVE_PACK_METHOD') or 'auto').strip().lower()
        forced_all_cancel = method in ('all_cancel', 'allcancel', 'bulk')
        forced_bouquet = method in ('bouquet', 'row', 'menu')
        if forced_all_cancel:
            use_all_cancel = True
        elif forced_bouquet:
            use_all_cancel = False
        else:
            use_all_cancel = _hathway_all_cancel_action_visible(page)

        pack_removed = False
        tried_all_cancel = False
        if use_all_cancel:
            tried_all_cancel = True
            pack_removed = _hathway_remove_pack_via_all_cancel(page)
            if not pack_removed and forced_all_cancel:
                try:
                    page.screenshot(path='hathway_remove_pack_all_cancel_failed.png')
                except Exception:
                    pass
                return {
                    'success': False,
                    'error': (
                        'ALL Cancel flow failed (toolbar, or ALL Cancel / Confirmation / Cancel Pack Status modals). '
                        'Set HATHWAY_REMOVE_PACK_METHOD=bouquet for the bouquet-row menu, or increase '
                        'HATHWAY_ALL_CANCEL_MODAL_WAIT_MS or HATHWAY_ALL_CANCEL_POST_TOOLBAR_MS if pages are slow.'
                    ),
                    'provider': 'hathway',
                    'search_value': stb_id,
                }

        bouquet_prefix = 'ALL Cancel failed; ' if tried_all_cancel and not pack_removed else ''
        if not pack_removed:
            bouquet_ok, bouquet_err = _hathway_remove_pack_via_bouquet_menu(page, cancel_reason)
            if not bouquet_ok:
                if bouquet_err == 'no_dropdown':
                    try:
                        page.screenshot(path='hathway_remove_pack_no_bouquet_action.png')
                    except Exception:
                        pass
                    return {
                        'success': False,
                        'error': bouquet_prefix
                        + 'Could not open bouquet row action menu (no Active row or UI changed).',
                        'provider': 'hathway',
                        'search_value': stb_id,
                    }
                if bouquet_err in ('menu_missing', 'cancel_missing'):
                    try:
                        page.screenshot(path='hathway_remove_pack_no_cancel_menu.png')
                    except Exception:
                        pass
                    if bouquet_err == 'menu_missing':
                        err = (
                            bouquet_prefix
                            + 'Bouquet row menu did not appear after clicking Action (▼). '
                            'Try increasing HATHWAY_BOUQUET_MENU_WAIT_MS or HATHWAY_REMOVE_PACK_STEP_MS in .env.'
                        )
                    else:
                        err = (
                            bouquet_prefix
                            + 'CANCEL was not found in the bouquet menu (RENEW/CANCEL/CHANGE visible). '
                            'Portal UI may have changed. Try HATHWAY_REMOVE_PACK_METHOD=all_cancel if ALL Cancel is available.'
                        )
                    return {
                        'success': False,
                        'error': err,
                        'provider': 'hathway',
                        'search_value': stb_id,
                    }
                try:
                    page.screenshot(path='hathway_remove_pack_bouquet_modal_failed.png')
                except Exception:
                    pass
                return {
                    'success': False,
                    'error': bouquet_prefix
                    + 'Cancel pack modal sequence failed after bouquet CANCEL (Confirm / Yes / status).',
                    'provider': 'hathway',
                    'search_value': stb_id,
                }

        page.wait_for_timeout(800)
        cleanup_hathway_ui(page)

        if not _hathway_click_terminate_main_tv(page):
            try:
                page.screenshot(path='hathway_remove_pack_no_terminate_btn.png')
            except Exception:
                pass
            return {
                'success': False,
                'error': (
                    'Terminate control not found after pack removal (grid still loading, in an iframe, or UI changed). '
                    'Try increasing HATHWAY_TERMINATE_AFTER_PACK_MS (default 2800) or HATHWAY_REMOVE_PACK_STEP_MS.'
                ),
                'provider': 'hathway',
                'search_value': stb_id,
            }

        _hathway_terminate_stb_modal_chain(page, terminate_reason)

        return {
            'success': True,
            'provider': 'hathway',
            'search_value': stb_id,
            'matched_cid': stb_id,
            'message': 'Package removed and STB Terminated',
        }
    except Exception as e:
        try:
            page.screenshot(path='hathway_remove_pack_terminate_error.png')
        except Exception:
            pass
        print(f'⚠️ Hathway remove pack + terminate error: {e}')
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}


def hathway_renew_stb_pack(page, stb_id, renew_reason=None):
    """
    Pack Management → **Main TV** or **Customer Details** → **Quick Recharge** → Plan Details **submit**
    → **Confirmation** → **Confirm** → **OK**.

    Alternative to the Manage Expired Plans / bouquet ▼ flow when operators use Quick Recharge.

    ``renew_reason`` is unused here (kept for API compatibility).
    """
    stb_id = (stb_id or '').strip()
    if not stb_id:
        return {'success': False, 'error': 'Empty STB / VC id', 'provider': 'hathway', 'search_value': ''}

    try:
        cleanup_hathway_ui(page)
        _hathway_click_vc_mac_search_mode(page)
        page.wait_for_timeout(300)

        _hathway_fill_pack_search(page, stb_id)
        _hathway_click_search(page)
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            page.wait_for_load_state('domcontentloaded', timeout=15000)
        page.wait_for_timeout(1200)
        cleanup_hathway_ui(page)

        body = page.locator('body').inner_text(timeout=15000)
        portal_msg = _hathway_search_portal_user_message(body)
        if portal_msg:
            return {'success': False, 'error': portal_msg, 'provider': 'hathway', 'search_value': stb_id}

        if re.search(r'no\s+record|not\s+found|invalid|no\s+match', body, re.I):
            return {
                'success': False,
                'error': 'No matching subscriber for this STB / VC id.',
                'provider': 'hathway',
                'search_value': stb_id,
            }

        renew_ok, renew_err = _hathway_renew_via_quick_recharge(page)
        if not renew_ok:
            key = renew_err or 'unknown'
            if key == 'quick_recharge':
                try:
                    page.screenshot(path='hathway_renew_no_quick_recharge_btn.png')
                except Exception:
                    pass
                err = (
                    'Could not find or click Quick Recharge (try Main TV / Customer Details; tile may be div/span).'
                )
            elif key == 'plan_submit':
                try:
                    page.screenshot(path='hathway_renew_plan_submit_failed.png')
                except Exception:
                    pass
                err = (
                    'Quick Recharge opened but Plan Details submit was not found or not clickable.'
                )
            elif isinstance(key, str) and key.startswith('modal:'):
                try:
                    page.screenshot(path='hathway_renew_quick_recharge_modal_failed.png')
                except Exception:
                    pass
                err = f'Confirm / OK modal sequence failed: {key[6:]}'
            else:
                try:
                    page.screenshot(path='hathway_renew_quick_recharge_unknown_failed.png')
                except Exception:
                    pass
                err = f'Renew via Quick Recharge failed ({key}).'
            return {'success': False, 'error': err, 'provider': 'hathway', 'search_value': stb_id}

        page.wait_for_timeout(800)
        cleanup_hathway_ui(page)
        return {
            'success': True,
            'provider': 'hathway',
            'search_value': stb_id,
            'matched_cid': stb_id,
            'message': 'Expired plan renew submitted in portal (Quick Recharge flow).',
        }
    except Exception as e:
        try:
            page.screenshot(path='hathway_renew_error.png')
        except Exception:
            pass
        print(f'⚠️ Hathway renew STB error: {e}')
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}


def check_hathway_renew_stb(stb_id, account_id=None):
    """Login, Pack Management → Quick Recharge renew flow for STB, close browser."""
    playwright, browser, page = launch_hathway_browser()
    try:
        if not login_hathway(page, account_id=account_id):
            return {
                'success': False,
                'error': 'Hathway login failed — check credentials and CAPTCHA.',
                'provider': 'hathway',
                'search_value': stb_id,
            }
        return hathway_renew_stb_pack(page, stb_id)
    except Exception as e:
        try:
            page.screenshot(path='hathway_renew_fatal.png')
        except Exception:
            pass
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}
    finally:
        close_hathway_browser(playwright, browser)


def check_hathway_remove_pack_and_terminate(stb_id, account_id=None):
    """Login, Pack Management, remove active pack (ALL Cancel or bouquet menu) + terminate STB, close browser."""
    playwright, browser, page = launch_hathway_browser()
    try:
        if not login_hathway(page, account_id=account_id):
            return {
                'success': False,
                'error': 'Hathway login failed — check credentials and CAPTCHA.',
                'provider': 'hathway',
                'search_value': stb_id,
            }
        return hathway_remove_pack_and_terminate_stb(page, stb_id)
    except Exception as e:
        try:
            page.screenshot(path='hathway_remove_pack_terminate_fatal.png')
        except Exception:
            pass
        return {'success': False, 'error': str(e), 'provider': 'hathway', 'search_value': stb_id}
    finally:
        close_hathway_browser(playwright, browser)


def _hathway_search_portal_user_message(body):
    """
    Map known Pack Management search responses to short bot messages.
    Returns None if no known phrase matched.
    Portal wording varies; body may include popups after search.
    """
    if not body:
        return None
    low = ' '.join(body.split()).lower()
    low = low.replace('’', "'").replace('`', "'")

    # Terminated / does not exist (English phrasing variants)
    if 'vc which you are searching is either terminated or does not exist' in low:
        return 'STB is terminated.'
    if 'terminated or does not exist' in low and ('vc' in low or 'searching' in low):
        return 'STB is terminated.'

    # Other LCO / no privileges (wording and line breaks vary)
    if 'not with your lco' in low:
        return 'STB is not with your LCO ID.'
    if 'belongs to other' in low and 'lco' in low:
        return 'STB is not with your LCO ID.'
    if 'no privileges' in low and 'other lco' in low:
        return 'STB is not with your LCO ID.'
    if 'no privileges' in low and 'lco' in low and 'other' in low:
        return 'STB is not with your LCO ID.'
    if 'privileges' in low and 'access' in low and 'customer' in low and 'other' in low and 'lco' in low:
        return 'STB is not with your LCO ID.'
    return None


def audit_hathway_subscriber(page, stb_id):
    """
    Pack Management: search by VC/Mac (STB id), open Main TV tab, read Hathway Bouquet row
    (Pack name, Valid upto, STB/Status, LCO) plus header scheme and totals.
    """
    stb_id = (stb_id or '').strip()
    if not stb_id:
        return hathway_audit_to_dict({}, '', success=False, error='Empty STB / VC id')

    try:
        cleanup_hathway_ui(page)
        _hathway_click_vc_mac_search_mode(page)
        page.wait_for_timeout(300)

        _hathway_fill_pack_search(page, stb_id)
        _hathway_click_search(page)
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            page.wait_for_load_state('domcontentloaded', timeout=15000)
        page.wait_for_timeout(1200)
        cleanup_hathway_ui(page)

        body = page.locator('body').inner_text(timeout=15000)
        portal_msg = _hathway_search_portal_user_message(body)
        if portal_msg:
            return hathway_audit_to_dict({}, stb_id, success=False, error=portal_msg)

        if re.search(r'no\s+record|not\s+found|invalid|no\s+match', body, re.I):
            return hathway_audit_to_dict({}, stb_id, success=False, error='No matching subscriber for this STB / VC id.')

        if not _hathway_ensure_main_tv_tab(page):
            return hathway_audit_to_dict(
                {},
                stb_id,
                success=False,
                error='Could not open Main TV or bouquet panel (blocked by a popup, or UI changed).',
            )
        try:
            page.wait_for_load_state('domcontentloaded', timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(600)

        data = _hathway_scrape_pack_management_dom(page)

        row_status = (data.get('main_tv_row_status') or data.get('plan_status') or '').strip()
        if not data.get('plan_name') or not row_status:
            try:
                body_retry = page.locator('body').inner_text(timeout=8000)
            except Exception:
                body_retry = ''
            portal_retry = _hathway_search_portal_user_message(body_retry)
            if portal_retry:
                return hathway_audit_to_dict(data, stb_id, success=False, error=portal_retry)
            try:
                page.screenshot(path='hathway_main_tv_no_bouquet.png')
            except Exception:
                pass
            return hathway_audit_to_dict(
                data,
                stb_id,
                success=False,
                error='Could not read Main TV bouquet row (package name + status from grid).',
            )

        return hathway_audit_to_dict(data, stb_id)
    except Exception as e:
        try:
            page.screenshot(path='hathway_audit_error.png')
        except Exception:
            pass
        print(f'⚠️ Hathway audit error: {e}')
        return hathway_audit_to_dict({}, stb_id, success=False, error=str(e))


def check_hathway_dashboard_stats(account_id=None):
    """
    Login → Home.aspx → Dashboard tile → inner **Dashboard** tab → scrape STB counts + Actual Balance.
    Uses a standalone browser session (closes after); does not use Pack Management.
    """
    playwright, browser, page = launch_hathway_browser()
    try:
        if not login_hathway(page, account_id=account_id, goto_pack_management=False):
            return {
                'success': False,
                'error': 'Hathway login failed — check credentials and CAPTCHA.',
                'provider': 'hathway',
            }
        if not navigate_to_dashboard_tile(page):
            try:
                page.screenshot(path='hathway_dashboard_nav_failed.png')
            except Exception:
                pass
            return {
                'success': False,
                'error': 'Could not open Dashboard from Home.aspx.',
                'provider': 'hathway',
            }
        scraped = hathway_scrape_dashboard_stats(page)
        if (
            scraped.get('active_stb') is None
            and scraped.get('inactive_stb') is None
            and scraped.get('total_stb') is None
            and scraped.get('actual_balance') is None
        ):
            try:
                page.screenshot(path='hathway_dashboard_scrape_empty.png')
            except Exception:
                pass
            return {
                'success': False,
                'error': 'Dashboard page loaded but expected summary text was not found.',
                'provider': 'hathway',
                **scraped,
            }
        return {'success': True, 'provider': 'hathway', **scraped}
    except Exception as e:
        try:
            page.screenshot(path='hathway_dashboard_error.png')
        except Exception:
            pass
        return {'success': False, 'error': str(e), 'provider': 'hathway'}
    finally:
        close_hathway_browser(playwright, browser)


def check_hathway_portal(subscriber_id, account_id=None):
    """Login, Pack Management, full STB audit, close browser."""
    playwright, browser, page = launch_hathway_browser()
    try:
        if not login_hathway(page, account_id=account_id):
            return {'success': False, 'error': 'Hathway login failed — check credentials and CAPTCHA.', 'provider': 'hathway'}
        return audit_hathway_subscriber(page, subscriber_id)
    except Exception as e:
        try:
            page.screenshot(path='hathway_portal_error.png')
        except Exception:
            pass
        return {'success': False, 'error': str(e), 'provider': 'hathway'}
    finally:
        close_hathway_browser(playwright, browser)


def check_hathway_clear_session(subscriber_id):
    _ = subscriber_id
    return {
        'success': False,
        'error': 'Hathway session clear is not implemented yet.',
    }


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        h_page = context.new_page()
        if login_hathway(h_page):
            print('\n✅ Hathway: Pack Management ready.')
            h_page.wait_for_timeout(10000)
        else:
            print('\n❌ Hathway login failed.')
        browser.close()

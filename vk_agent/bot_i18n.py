"""
Per-chat UI language (English / ಕನ್ನಡ). Reply keyboard labels and bot text use get_lang(chat_id).
Language pick: buttons "English" and "ಕನ್ನಡ" (same in both locales); optional /lang en | kn.
"""
import html
import json

# Fixed labels for the first step — must match before get_lang is set.
LBL_PICK_ENGLISH = 'English'
LBL_PICK_KANNADA = 'ಕನ್ನಡ'


# chat_id -> 'en' | 'kn' | None (None = must choose language)
_chat_lang = {}


def get_lang(chat_id):
    return _chat_lang.get(chat_id)


def set_lang(chat_id, code):
    c = (code or '').strip().lower()
    if c in ('en', 'english'):
        _chat_lang[chat_id] = 'en'
    elif c in ('kn', 'kannada', 'ಕನ್ನಡ'):
        _chat_lang[chat_id] = 'kn'
    else:
        return False
    return True


def clear_lang(chat_id):
    _chat_lang.pop(chat_id, None)


def _t(lang, key, **kw):
    if lang not in ('en', 'kn'):
        lang = 'en'
    s = STRINGS[lang][key]
    return s.format(**kw) if kw else s


def T(chat_id, key, **kw):
    lang = get_lang(chat_id) or 'en'
    return _t(lang, key, **kw)


def lbl(chat_id, key):
    lang = get_lang(chat_id) or 'en'
    return LABELS[lang][key]


def reply_markup_language_select(chat_id=None):
    """Language pick; optional ``chat_id`` adds **Menu** + **Change language** on the bottom row."""
    rows = [[{'text': LBL_PICK_ENGLISH}, {'text': LBL_PICK_KANNADA}]]
    if chat_id is not None:
        L = lambda k: lbl(chat_id, k)
    else:
        L = lambda k: LABELS['en'][k]
    rows.append([{'text': L('menu')}, {'text': L('change_language')}])
    return json.dumps({'keyboard': rows, 'resize_keyboard': True})


def reply_markup_portal_keyboard(chat_id):
    """Hathway Pack Management actions; **Menu** and **Change language** on the bottom row."""
    L = lambda k: lbl(chat_id, k)
    rows = [
        [{'text': L('hathway_multi')}],
        [{'text': L('hathway_single')}],
        [{'text': L('hathway_deactivate')}],
        [{'text': L('hathway_activate')}],
        [{'text': L('hathway_remove_terminate')}],
        [{'text': L('done')}],
        [{'text': L('menu')}, {'text': L('change_language')}],
    ]
    return json.dumps({'keyboard': rows, 'resize_keyboard': True})


def reply_markup_menu_minimal(chat_id):
    """Same keyboard as the main screen (Menu repeats this help)."""
    return reply_markup_portal_keyboard(chat_id)


def is_pick_english(t):
    s = (t or '').strip()
    return s == LBL_PICK_ENGLISH or s.lower() in ('/lang en', '/english')


def is_pick_kannada(t):
    s = (t or '').strip()
    return s == LBL_PICK_KANNADA or s.lower() in ('/lang kn', '/kannada')


STRINGS = {
    'en': {
        'welcome_choose': (
            '<b>Welcome — Hathway Agent</b>\n\n'
            '<b>Choose your language</b> (you can change it later from the menu).\n\n'
            'Tap <b>English</b> or <b>ಕನ್ನಡ</b> below.'
        ),
        'language_set_en': '<b>Language: English</b>',
        'language_set_kn': '<b>Language: ಕನ್ನಡ</b>',
        'please_choose_lang': (
            '<b>ಭಾಷೆ ಆಯ್ಕೆಮಾಡಿ / Choose language</b>\n'
            'Tap <b>English</b> or <b>ಕನ್ನಡ</b> below.'
        ),
        'help_intro': (
            '<b>Hathway Agent</b> (partners portal — Pack Management)\n\n'
            'Use <b>{hathway_multi}</b> for a persistent login, then send <b>STB / VC ids</b> one per message '
            '(e.g. <code>N70130838231</code> or <code>T403030313577</code>). '
            '<b>{hathway_single}</b> runs one audit in a fresh browser. '
            '<b>{hathway_deactivate}</b>, <b>{hathway_activate}</b>, and <b>{hathway_remove_terminate}</b> '
            'open a browser for those flows. Tap <b>{menu}</b> for this help and <b>{change_language}</b> '
            'for English / ಕನ್ನಡ.\n\n'
            'Credentials in <code>.env</code>: <code>HATHWAY_USER</code>, <code>HATHWAY_PASS</code>, '
            'optional <code>HATHWAY_LOGIN_URL</code>. Multiple operators: <code>HATHWAY_ACCOUNTS_FILE</code> (JSON) '
            'and <code>/hath_accounts</code>, <code>/hath_account ID</code>.'
        ),
        'help_active_railtel': 'Active portal: <b>Railtel (Railwire)</b>\n\n',
        'help_active_hathway': 'Active portal: <b>Hathway (Pack Management)</b>\n\n',
        'menu_main': (
            '<b>Menu</b> — Hathway\n\n'
            '<b>{hathway_multi}</b> · <b>{hathway_single}</b> · <b>{hathway_deactivate}</b> · '
            '<b>{hathway_activate}</b> · <b>{hathway_remove_terminate}</b> · <b>{done}</b>\n\n'
            'Bottom row: <b>{menu}</b> and <b>{change_language}</b>.'
        ),
        'session_closed': 'Portal session closed. Choose an option from the menu when needed.',
        'session_idle_timeout': (
            '<b>Session closed (idle).</b> There was no activity for several minutes, so the portal '
            'browser was closed. Use <b>Multi</b> or <b>Single</b> from the menu when you need it again. '
            'If you just sent a command, send it again after starting a new session.'
        ),
        'multi_wrong_railtel_row': (
            'That is the <b>Railtel</b> login row. Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, '
            'then use <b>{hathway_multi}</b> so Hathway does not use Railtel login.'
        ),
        'multi_wrong_hathway_row': (
            'That is the <b>Hathway</b> login row. Tap <b>{menu}</b>, then <b>{portal_railtel}</b>, '
            'then use <b>{railtel_multi}</b> so Railtel does not use Hathway login.'
        ),
        'logging_in_railtel': 'Logging in (Railtel)… A Chromium window will open. This may take a minute.',
        'logging_in_hathway': 'Logging in (Hathway)… A Chromium window will open. This may take a minute.',
        'logged_in_hathway': (
            '<b>Logged in (Hathway).</b> Send one <b>STB / VC id</b> per message for '
            '<b>STB status</b> and pack details from Main TV. Tap <b>{done}</b> when finished.'
        ),
        'logged_in_railtel': (
            '<b>Logged in (Railtel).</b> Send subscriber ID or phone (one per message). '
            'Tap <b>{done}</b> when finished.'
        ),
        'multi_start_fail': '<b>Could not start multi session.</b>\n{err}',
        'multi_login_not_ready': (
            '<b>Login is still in progress.</b> Please wait — you can send subscriber ID, phone, '
            'or STB / VC id only after the bot shows the logged-in message.'
        ),
        'single_wrong_railtel': (
            'That is the <b>Railtel</b> single-audit button. Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, '
            'then use <b>{hathway_single}</b>.'
        ),
        'single_wrong_hathway': (
            'That is the <b>Hathway</b> single-audit button. Tap <b>{menu}</b>, then <b>{portal_railtel}</b>, '
            'then use <b>{railtel_single}</b>.'
        ),
        'single_prompt_hathway': (
            '<b>Single STB status.</b> Send one <b>STB / VC id</b> (e.g. <code>N70130838231</code>).'
        ),
        'single_prompt_railtel': '<b>Single audit.</b> Send one subscriber ID or phone number.',
        'clear_railtel_only': (
            '<b>Clear session</b> is only on <b>Railtel</b>. Tap <b>{menu}</b>, then <b>{portal_railtel}</b>, '
            'then <b>{railtel_clear}</b> and send the subscriber ID.'
        ),
        'clear_wait_prompt': (
            '<b>Clear session.</b> Send subscriber ID or phone. '
            'A browser window will open for login and disconnect.'
        ),
        'browser_portal_mismatch': (
            'The open browser did not match the selected portal — choose <b>multi login</b> again '
            'for the portal you want (Railtel vs Hathway are separate logins).'
        ),
        'stb_on_railtel_multi': (
            'That looks like a <b>Hathway</b> STB / VC id (N + 11 digits or T + 12 digits). '
            'Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, then send it again (Railtel uses '
            '<code>ka.user</code> or a 10-digit / <code>+91</code> phone).'
        ),
        'stb_on_railtel_single': (
            'That looks like a <b>Hathway</b> STB / VC id (N + 11 digits or T + 12 digits). '
            'Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, then tap <b>{hathway_single}</b> and send it again.'
        ),
        'stb_on_railtel_idle': (
            'That looks like a <b>Hathway</b> STB / VC id (N + 11 digits or T + 12 digits). '
            'Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, then send it.'
        ),
        'wait_hathway_multi': 'Send an <b>STB / VC id</b> (one per message), or tap <b>{done}</b>.',
        'wait_railtel_multi': 'Send a subscriber ID or phone, or tap <b>{done}</b>.',
        'running_audit': 'Running audit for <code>{cid}</code>…',
        'audit_error': '<b>Audit error</b>\n<code>{exc}</code>',
        'single_wait_hathway': 'Send a valid <b>STB / VC id</b> (e.g. <code>N70130838231</code>).',
        'single_wait_railtel': (
            'Send a valid subscriber ID or phone '
            '(e.g. <code>ka.user</code>, 10 digits, or <code>+91</code>…).'
        ),
        'running_single_audit': 'Running single audit for <code>{cid}</code>…',
        'clear_send_id': 'Send subscriber ID or phone to clear session.',
        'clearing': 'Clearing session for <code>{cid}</code>… browser will open.',
        'clear_error': '<b>Clear session error</b>\n<code>{exc}</code>',
        'hathway_deactivate_wait_prompt': (
            '<b>Hathway — temp STB deactivate.</b> Send one <b>STB / VC id</b> (e.g. <code>N70152403369</code>). '
            'A browser will open, log in, and run <b>Deactivate</b> on Main TV with reason '
            '<i>Payment not received by customer</i> (override via <code>HATHWAY_DEACTIVATE_REASON</code> in .env). '
            'Or use <code>/hath_deactivate YOUR_STB</code> in one message.'
        ),
        'hathway_deactivate_running': 'Running Hathway temp deactivate for <code>{stb}</code>… browser will open.',
        'hathway_deactivate_wrong_portal': (
            '<b>Temp STB deactivate</b> is only on <b>Hathway</b>. Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, '
            'then <b>{hathway_deactivate}</b> or <code>/hath_deactivate</code>.'
        ),
        'hathway_deactivate_need_stb': 'Send a valid <b>STB / VC id</b> (N + 11 digits or T + 12 digits), or tap Menu.',
        'hathway_activate_wait_prompt': (
            '<b>Hathway — Activate Back.</b> Send one <b>STB / VC id</b>. A browser will open, then '
            '<b>Activate</b> on Main TV with reason <i>Payment received from customer/Promise to pay</i> '
            '(override via <code>HATHWAY_ACTIVATE_REASON</code> in .env). '
            'Or <code>/hath_activate YOUR_STB</code> in one message.'
        ),
        'hathway_activate_running': 'Running Activate Back for <code>{stb}</code>… browser will open.',
        'hathway_activate_wrong_portal': (
            '<b>Activate Back</b> is only on <b>Hathway</b>. Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, '
            'then <b>{hathway_activate}</b> or <code>/hath_activate</code>.'
        ),
        'hathway_activate_need_stb': 'Send a valid <b>STB / VC id</b> (N + 11 digits or T + 12 digits), or tap Menu.',
        'hathway_remove_terminate_wait_prompt': (
            '<b>Hathway — remove pack &amp; terminate STB.</b> Send one <b>STB / VC id</b>. '
            'Pack removal tries <b>ALL Cancel</b> on Main TV when that control is visible (and when '
            '<code>HATHWAY_REMOVE_PACK_METHOD</code> is not forced to bouquet). In <code>auto</code>, if ALL Cancel '
            'does not complete, it falls back to the bouquet row <b>▼ → CANCEL</b>. If ALL Cancel is not shown, '
            'only the bouquet path is used. Then <b>Terminate</b> with reason '
            '<i>Customers Request - Price Issue</i> (<code>HATHWAY_TERMINATE_REASON</code>). '
            'Bouquet path reason: <code>HATHWAY_CANCEL_PACK_REASON</code> (default <i>Customer request</i>). '
            'Or <code>/hath_remove_terminate YOUR_STB</code> in one message.\n\n'
            '<i>Env:</i> <code>HATHWAY_REMOVE_PACK_METHOD</code> = <code>auto</code> (default), '
            '<code>all_cancel</code>, or <code>bouquet</code>. '
            '<code>HATHWAY_ALL_CANCEL_MODAL_WAIT_MS</code> (default 3000) between ALL Cancel popups; '
            '<code>HATHWAY_ALL_CANCEL_POST_TOOLBAR_MS</code> (default 2200) after clicking ALL Cancel before the sheet. '
            '<code>HATHWAY_ALL_CANCEL_OK_WAIT_MS</code> (default 3000) after the sheet appears, before clicking OK. '
            '<i>After pack removal (Terminate):</i> <code>HATHWAY_TERMINATE_AFTER_PACK_MS</code> (default 2800). '
            '<code>HATHWAY_BOUQUET_MENU_WAIT_MS</code> (4500), <code>HATHWAY_CANCEL_MENU_POLL_MS</code> (20000).'
        ),
        'hathway_remove_terminate_running': (
            'Removing pack and terminating STB for <code>{stb}</code>… browser will open.'
        ),
        'hathway_remove_terminate_wrong_portal': (
            '<b>Remove pack &amp; terminate</b> is only on <b>Hathway</b>. Tap <b>{menu}</b>, then <b>{portal_hathway}</b>, '
            'then <b>{hathway_remove_terminate}</b> or <code>/hath_remove_terminate</code>.'
        ),
        'hathway_remove_terminate_need_stb': 'Send a valid <b>STB / VC id</b> (N + 11 digits or T + 12 digits), or tap Menu.',
        'idle_prompt_hathway': 'Choose an option below, or send an <b>STB / VC id</b> for a quick Hathway audit.',
        'idle_prompt_railtel': (
            'Choose an option below or send a subscriber ID / phone for a quick single audit.'
        ),
        'railtel_input_on_hathway': (
            'That looks like a <b>Railtel</b> subscriber id or phone. This bot is <b>Hathway only</b> — send '
            'an <b>STB / VC id</b> (N + 11 digits or T + 12 digits). Use the <b>Railtel Agent</b> bot for subscriber audits.'
        ),
        'login_fail_hathway': 'Hathway login failed — check HATHWAY_USER, HATHWAY_PASS, and CAPTCHA.',
        'login_fail_railtel': 'Login failed — check credentials and CAPTCHA.',
        'audit_fail_hathway': 'Hathway audit failed for {search}\nReason: {reason}.',
        'audit_fail_railtel_head': '<b>Audit failed for {search}</b>',
        'audit_fail_railtel_reason': 'Reason: {reason}.',
        'hathway_pack_lines': 'Pack Name: {pack}\nValid upto: {valid}\nSTB Status: {stb}\nLCO Price: {lco}',
        'hathway_pack_mgmt': (
            'Hathway — Pack Management\n'
            'Reference: {ref}\n\n'
            'Browser is on Pack Management after login. Subscriber status in this bot is not '
            'automated yet — search in the portal window, or share Pack Management selectors '
            'to add the same kind of audit as Railtel.'
        ),
        'audit_result_head': '<b>Audit result for {matched}</b>',
        'audit_search_input': 'Search input: {search}',
        'audit_status': 'Status: {status}',
        'audit_session_days': 'Session Days: {days}',
        'audit_time_info': 'Time Info: {downtime}',
        'audit_mac': 'MAC: {mac}',
        'audit_expiry': 'Expiry: {expiry}',
        'status_active': '🟢 ACTIVE',
        'status_inactive': '🔴 INACTIVE',
        'clear_ok_head': '<b>Clear session OK</b>',
        'clear_ok_matched': 'Matched: <code>{mc}</code>',
        'clear_fail_head': '<b>Clear session failed</b>',
        'clear_fail_input': 'Input: <code>{search}</code>',
        'clear_fail_reason': 'Reason: {err}',
        'clear_fail_matched_line': 'Matched: <code>{mc}</code>',
        'na': 'N/A',
        'session_cleared_msg': 'Session cleared.',
    },
    'kn': {
        'welcome_choose': (
            '<b>ಸ್ವಾಗತ — ಹ್ಯಾಥ್‌ವೇ ಏಜೆಂಟ್</b>\n\n'
            '<b>ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ</b> (ಮೆನುವಿನಿಂದ ನಂತರ ಬದಲಾಯಿಸಬಹುದು).\n\n'
            'ಕೆಳಗೆ <b>English</b> ಅಥವಾ <b>ಕನ್ನಡ</b> ಒತ್ತಿ.'
        ),
        'language_set_en': '<b>ಭಾಷೆ: English</b>',
        'language_set_kn': '<b>ಭಾಷೆ: ಕನ್ನಡ</b>',
        'please_choose_lang': (
            '<b>ಭಾಷೆ ಆಯ್ಕೆಮಾಡಿ / Choose language</b>\n'
            'ಕೆಳಗೆ <b>English</b> ಅಥವಾ <b>ಕನ್ನಡ</b> ಒತ್ತಿ.'
        ),
        'help_intro': (
            '<b>ಹ್ಯಾಥ್‌ವೇ ಏಜೆಂಟ್</b> (ಪಾರ್ಟ್ನರ್ ಪೋರ್ಟಲ್ — ಪ್ಯಾಕ್ ಮ್ಯಾನೇಜ್‌ಮೆಂಟ್)\n\n'
            '<b>{hathway_multi}</b> — ಬಹು ಲಾಗಿನ್, ನಂತರ ಪ್ರತಿ ಸಂದೇಶಕ್ಕೆ <b>STB / VC id</b> '
            '(ಉದಾ. <code>N70130838231</code>). <b>{hathway_single}</b> — ಒಂದೇ ಪರಿಶೀಲನೆ. '
            '<b>{hathway_deactivate}</b>, <b>{hathway_activate}</b>, <b>{hathway_remove_terminate}</b> — '
            'ಆ ಕ್ರಿಯೆಗಳಿಗೆ ಬ್ರೌಸರ್. <b>{menu}</b> ಈ ಸಹಾಯ, <b>{change_language}</b>.\n\n'
            '<code>.env</code>: <code>HATHWAY_USER</code>, <code>HATHWAY_PASS</code>, ಐಚ್ಛಿಕ <code>HATHWAY_LOGIN_URL</code>. '
            'ಅನೇಕ ಖಾತೆಗಳು: <code>HATHWAY_ACCOUNTS_FILE</code>, <code>/hath_accounts</code>, <code>/hath_account ID</code>.'
        ),
        'help_active_railtel': 'ಸಕ್ರಿಯ ಪೋರ್ಟಲ್: <b>ರೈಲ್‌ಟೆಲ್ (ರೈಲ್‌ವೈರ್)</b>\n\n',
        'help_active_hathway': 'ಸಕ್ರಿಯ ಪೋರ್ಟಲ್: <b>ಹ್ಯಾಥ್‌ವೇ (ಪ್ಯಾಕ್ ಮ್ಯಾನೇಜ್‌ಮೆಂಟ್)</b>\n\n',
        'menu_main': (
            '<b>ಮೆನು</b> — ಹ್ಯಾಥ್‌ವೇ\n\n'
            '<b>{hathway_multi}</b> · <b>{hathway_single}</b> · <b>{hathway_deactivate}</b> · '
            '<b>{hathway_activate}</b> · <b>{hathway_remove_terminate}</b> · <b>{done}</b>\n\n'
            'ಕೆಳಗಿನ ಸಾಲು: <b>{menu}</b> ಮತ್ತು <b>{change_language}</b>.'
        ),
        'session_closed': 'ಪೋರ್ಟಲ್ ಸೆಷನ್ ಮುಚ್ಚಲಾಗಿದೆ. ಅಗತ್ಯವಿದ್ದಾಗ ಮೆನುವಿನಿಂದ ಆಯ್ಕೆಮಾಡಿ.',
        'session_idle_timeout': (
            '<b>ಸೆಷನ್ ಮುಚ್ಚಲಾಗಿದೆ (ನಿಶ್ಚಲ).</b> ಸಾಕಷ್ಟು ನಿಮಿಷಗಳ ಕಾಲ ಚಟುವಟಿಕೆ ಇರಲಿಲ್ಲ — ಪೋರ್ಟಲ್ ಬ್ರೌಸರ್ '
            'ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಮುಚ್ಚಲಾಗಿದೆ. ಪುನಃ ಬೇಕಾದಾಗ ಮೆನುವಿನಿಂದ <b>ಬಹು ಲಾಗಿನ್</b> ಅಥವಾ '
            '<b>1 STB ಚೆಕ್ / ಒಂದು ಪರಿಶೀಲನೆ</b> ಆರಂಭಿಸಿ. ಈಗಲೇ ಆಜ್ಞೆ ಕಳುಹಿಸಿದ್ದರೆ, ಹೊಸ ಸೆಷನ್ ನಂತರ ಮತ್ತೆ ಕಳುಹಿಸಿ.'
        ),
        'multi_wrong_railtel_row': (
            'ಇದು <b>ರೈಲ್‌ಟೆಲ್</b> ಲಾಗಿನ್ ಸಾಲು. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, '
            'ನಂತರ <b>{hathway_multi}</b> — ಹ್ಯಾಥ್‌ವೇಗೆ ರೈಲ್‌ಟೆಲ್ ಲಾಗಿನ್ ಬೇಡ.'
        ),
        'multi_wrong_hathway_row': (
            'ಇದು <b>ಹ್ಯಾಥ್‌ವೇ</b> ಲಾಗಿನ್ ಸಾಲು. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_railtel}</b>, '
            'ನಂತರ <b>{railtel_multi}</b> — ರೈಲ್‌ಟೆಲ್‌ಗೆ ಹ್ಯಾಥ್‌ವೇ ಲಾಗಿನ್ ಬೇಡ.'
        ),
        'logging_in_railtel': 'ರೈಲ್‌ಟೆಲ್ ಪೋರ್ಟಲ್‌ಗೆ ಲಾಗಿನ್ ಆಗುತ್ತಿದೆ, ಕಾಯಿರಿ',
        'logging_in_hathway': 'Hathway ಪೋರ್ಟಲ್‌ಗೆ ಲಾಗಿನ್ ಆಗುತ್ತಿದೆ, ಕಾಯಿರಿ',
        'logged_in_hathway': (
            '<b>ಲಾಗಿನ್ (ಹ್ಯಾಥ್‌ವೇ).</b> ಪ್ರತಿ ಸಂದೇಶಕ್ಕೆ ಒಂದು <b>STB / VC id</b> ಕಳುಹಿಸಿ — '
            '<b>STB Status</b> ಮತ್ತು ಮುಖ್ಯ TV ಪ್ಯಾಕ್ ವಿವರ. ಮುಗಿದಾಗ <b>{done}</b> ಒತ್ತಿ.'
        ),
        'logged_in_railtel': (
            '<b>ಲಾಗಿನ್ (ರೈಲ್‌ಟೆಲ್).</b> ಪ್ರತಿ ಸಂದೇಶಕ್ಕೆ ಗ್ರಾಹಕ ID ಅಥವಾ ಫೋನ್ ಸಂಖ್ಯೆ ಕಳುಹಿಸಿ. '
            'ಮುಗಿದಾಗ <b>{done}</b> ಒತ್ತಿ.'
        ),
        'multi_start_fail': '<b>ಬಹು ಸೆಷನ್ ಪ್ರಾರಂಭಿಸಲಾಗಲಿಲ್ಲ.</b>\n{err}',
        'multi_login_not_ready': (
            '<b>ಲಾಗಿನ್ ಇನ್ನೂ ನಡೆಯುತ್ತಿದೆ.</b> ದಯವಿಟ್ಟು ಕಾಯಿರಿ — ಬಾಟ್ “ಲಾಗಿನ್” ಸಂದೇಶ ತೋರಿಸಿದ ನಂತರವೇ '
            'ಗ್ರಾಹಕ ID, ಫೋನ್, ಅಥವಾ STB / VC id ಕಳುಹಿಸಿ.'
        ),
        'single_wrong_railtel': (
            'ಇದು <b>ರೈಲ್‌ಟೆಲ್</b> ಒಂದು-ಗ್ರಾಹಕ ಬಟನ್. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, '
            'ನಂತರ <b>{hathway_single}</b> ಬಳಸಿ.'
        ),
        'single_wrong_hathway': (
            'ಇದು <b>ಹ್ಯಾಥ್‌ವೇ</b> ಒಂದು-STB ಬಟನ್. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_railtel}</b>, '
            'ನಂತರ <b>{railtel_single}</b> ಬಳಸಿ.'
        ),
        'single_prompt_hathway': (
            '<b>1 STB ಚೆಕ್.</b> ಒಂದು <b>STB / VC id</b> ಕಳುಹಿಸಿ (ಉದಾ. <code>N70130838231</code>).'
        ),
        'single_prompt_railtel': '<b>ಒಂದು ಪರಿಶೀಲನೆ.</b> ಒಂದು ಗ್ರಾಹಕ ID ಅಥವಾ ಫೋನ್ ಸಂಖ್ಯೆ ಕಳುಹಿಸಿ.',
        'clear_railtel_only': (
            '<b>ಸೆಷನ್ ತೆರವು</b> ಕೇವಲ <b>ರೈಲ್‌ಟೆಲ್</b>ನಲ್ಲಿ. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_railtel}</b>, '
            'ನಂತರ <b>{railtel_clear}</b> ಮತ್ತು ಗ್ರಾಹಕ ID ಕಳುಹಿಸಿ.'
        ),
        'clear_wait_prompt': (
            '<b>ಸೆಷನ್ ತೆರವು.</b> ಗ್ರಾಹಕ ID ಅಥವಾ ಫೋನ್ ಕಳುಹಿಸಿ. '
            'ಲಾಗಿನ್ ಮತ್ತು ಸಂಪರ್ಕ ಕಡಿತಕ್ಕೆ ಬ್ರೌಸರ್ ಕಿಟಕಿ ತೆರೆಯುತ್ತದೆ.'
        ),
        'browser_portal_mismatch': (
            'ತೆರೆದ ಬ್ರೌಸರ್ ಆಯ್ಕೆಮಾಡಿದ ಪೋರ್ಟಲ್‌ಗೆ ಹೊಂದಿಕೆಯಾಗಿಲ್ಲ — ಬೇಕಾದ ಪೋರ್ಟಲ್‌ಗೆ '
            '<b>ಬಹು ಲಾಗಿನ್</b> ಮತ್ತೆ ಆರಂಭಿಸಿ (ರೈಲ್‌ಟೆಲ್ ಮತ್ತು ಹ್ಯಾಥ್‌ವೇ ಪ್ರತ್ಯೇಕ ಲಾಗಿನ್).'
        ),
        'stb_on_railtel_multi': (
            'ಇದು <b>ಹ್ಯಾಥ್‌ವೇ</b> STB / VC id ಎಂದು ಕಾಣುತ್ತದೆ (N + 11 ಅಂಕೆ ಅಥವಾ T + 12 ಅಂಕೆ). '
            'ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, ನಂತರ ಮತ್ತೆ ಕಳುಹಿಸಿ (ರೈಲ್‌ಟೆಲ್‌ಗೆ '
            '<code>ka.user</code> ಅಥವಾ 10 ಅಂಕಿಯ ಫೋನ್ / <code>+91</code>).'
        ),
        'stb_on_railtel_single': (
            'ಇದು <b>ಹ್ಯಾಥ್‌ವೇ</b> STB / VC id ಎಂದು ಕಾಣುತ್ತದೆ (N + 11 ಅಂಕೆ ಅಥವಾ T + 12 ಅಂಕೆ). '
            'ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, ನಂತರ <b>{hathway_single}</b> ಮತ್ತು ಮತ್ತೆ ಕಳುಹಿಸಿ.'
        ),
        'stb_on_railtel_idle': (
            'ಇದು <b>ಹ್ಯಾಥ್‌ವೇ</b> STB / VC id ಎಂದು ಕಾಣುತ್ತದೆ (N + 11 ಅಂಕೆ ಅಥವಾ T + 12 ಅಂಕೆ). '
            'ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, ನಂತರ ಕಳುಹಿಸಿ.'
        ),
        'wait_hathway_multi': 'ಒಂದು <b>STB / VC id</b> ಕಳುಹಿಸಿ, ಅಥವಾ <b>{done}</b> ಒತ್ತಿ.',
        'wait_railtel_multi': 'ಗ್ರಾಹಕ ID ಅಥವಾ ಫೋನ್ ಕಳುಹಿಸಿ, ಅಥವಾ <b>{done}</b> ಒತ್ತಿ.',
        'running_audit': 'ಪರಿಶೀಲನೆ ನಡೆಯುತ್ತಿದೆ: <code>{cid}</code>…',
        'audit_error': '<b>ಪರಿಶೀಲನೆ ದೋಷ</b>\n<code>{exc}</code>',
        'single_wait_hathway': 'ಸರಿಯಾದ <b>STB / VC id</b> ಕಳುಹಿಸಿ (ಉದಾ. <code>N70130838231</code>).',
        'single_wait_railtel': (
            'ಸರಿಯಾದ ಗ್ರಾಹಕ ID ಅಥವಾ ಫೋನ್ ಕಳುಹಿಸಿ '
            '(ಉದಾ. <code>ka.user</code>, 10 ಅಂಕೆ, ಅಥವಾ <code>+91</code>…).'
        ),
        'running_single_audit': 'ಒಂದು ಪರಿಶೀಲನೆ ನಡೆಯುತ್ತಿದೆ: <code>{cid}</code>…',
        'clear_send_id': 'ಸೆಷನ್ ತೆರವಿಗೆ ಗ್ರಾಹಕ ID ಅಥವಾ ಫೋನ್ ಕಳುಹಿಸಿ.',
        'clearing': 'ಸೆಷನ್ ತೆರವು: <code>{cid}</code>… ಬ್ರೌಸರ್ ತೆರೆಯುತ್ತದೆ.',
        'clear_error': '<b>ಸೆಷನ್ ತೆರವು ದೋಷ</b>\n<code>{exc}</code>',
        'hathway_deactivate_wait_prompt': (
            '<b>ಹ್ಯಾಥ್‌ವೇ — ತಾತ್ಕಾಲಿಕ STB ನಿಷ್ಕ್ರಿಯ.</b> ಒಂದು <b>STB / VC id</b> ಕಳುಹಿಸಿ (ಉದಾ. <code>N70152403369</code>). '
            'ಬ್ರೌಸರ್ ತೆರೆದು ಲಾಗಿನ್ ಮಾಡಿ Main TV ನಲ್ಲಿ <b>Deactivate</b> — ಕಾರಣ '
            '<i>Payment not received by customer</i> (ಬದಲಾಯಿಸಲು .env ನಲ್ಲಿ <code>HATHWAY_DEACTIVATE_REASON</code>). '
            'ಒಂದೇ ಸಂದೇಶದಲ್ಲಿ: <code>/hath_deactivate YOUR_STB</code>.'
        ),
        'hathway_deactivate_running': 'ಹ್ಯಾಥ್‌ವೇ ತಾತ್ಕಾಲಿಕ ನಿಷ್ಕ್ರಿಯ: <code>{stb}</code> … ಬ್ರೌಸರ್ ತೆರುತ್ತದೆ.',
        'hathway_deactivate_wrong_portal': (
            '<b>ತಾತ್ಕಾಲಿಕ STB ನಿಷ್ಕ್ರಿಯ</b> ಕೇವಲ <b>ಹ್ಯಾಥ್‌ವೇ</b>ಯಲ್ಲಿ. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, '
            'ನಂತರ <b>{hathway_deactivate}</b> ಅಥವಾ <code>/hath_deactivate</code>.'
        ),
        'hathway_deactivate_need_stb': 'ಮಾನ್ಯ <b>STB / VC id</b> ಕಳುಹಿಸಿ, ಅಥವಾ ಮೆನು.',
        'hathway_activate_wait_prompt': (
            '<b>ಹ್ಯಾಥ್‌ವೇ — Activate Back.</b> ಒಂದು <b>STB / VC id</b> ಕಳುಹಿಸಿ. ಬ್ರೌಸರ್ ತೆರೆದು Main TV ನಲ್ಲಿ '
            '<b>Activate</b> — ಕಾರಣ <i>Payment received from customer/Promise to pay</i> '
            '(ಬದಲಾಯಿಸಲು .env ನಲ್ಲಿ <code>HATHWAY_ACTIVATE_REASON</code>). '
            'ಒಂದೇ ಸಂದೇಶ: <code>/hath_activate YOUR_STB</code>.'
        ),
        'hathway_activate_running': 'Activate Back: <code>{stb}</code> … ಬ್ರೌಸರ್ ತೆರುತ್ತದೆ.',
        'hathway_activate_wrong_portal': (
            '<b>Activate Back</b> ಕೇವಲ <b>ಹ್ಯಾಥ್‌ವೇ</b>ಯಲ್ಲಿ. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, '
            'ನಂತರ <b>{hathway_activate}</b> ಅಥವಾ <code>/hath_activate</code>.'
        ),
        'hathway_activate_need_stb': 'ಮಾನ್ಯ <b>STB / VC id</b> ಕಳುಹಿಸಿ, ಅಥವಾ ಮೆನು.',
        'hathway_remove_terminate_wait_prompt': (
            '<b>ಹ್ಯಾಥ್‌ವೇ — ಪ್ಯಾಕ್ ತೆಗೆದು STB Terminate.</b> ಒಂದು <b>STB / VC id</b> ಕಳುಹಿಸಿ. '
            'Main TV ನಲ್ಲಿ <b>ALL Cancel</b> ಕಾಣಿಸಿದರೆ ಮೊದಲು ಅದನ್ನು ಪ್ರಯತ್ನಿಸುತ್ತದೆ; <code>auto</code>ದಲ್ಲಿ ಅದು ಪೂರ್ಣಗೊಳ್ಳದಿದ್ದರೆ ▼ → CANCEL ಗೆ ಹೋಗುತ್ತದೆ. '
            'ಬ್ರೌಸರ್ ನಂತರ <b>Terminate</b> — <code>HATHWAY_TERMINATE_REASON</code>. '
            '<code>HATHWAY_REMOVE_PACK_METHOD</code> = auto / all_cancel / bouquet. '
            'ಒಂದೇ ಸಂದೇಶ: <code>/hath_remove_terminate YOUR_STB</code>.'
        ),
        'hathway_remove_terminate_running': (
            'ಪ್ಯಾಕ್ ತೆಗೆದು STB terminate: <code>{stb}</code> … ಬ್ರೌಸರ್ ತೆರುತ್ತದೆ.'
        ),
        'hathway_remove_terminate_wrong_portal': (
            '<b>ಪ್ಯಾಕ್ ತೆಗೆ + Terminate</b> ಕೇವಲ <b>ಹ್ಯಾಥ್‌ವೇ</b>ಯಲ್ಲಿ. ಮೊದಲು <b>{menu}</b> ಒತ್ತಿ, ನಂತರ <b>{portal_hathway}</b>, '
            'ನಂತರ <b>{hathway_remove_terminate}</b> ಅಥವಾ <code>/hath_remove_terminate</code>.'
        ),
        'hathway_remove_terminate_need_stb': 'ಮಾನ್ಯ <b>STB / VC id</b> ಕಳುಹಿಸಿ, ಅಥವಾ ಮೆನು.',
        'idle_prompt_hathway': 'ಕೆಳಗೆ ಆಯ್ಕೆಮಾಡಿ, ಅಥವಾ ತ್ವರಿತ ಹ್ಯಾಥ್‌ವೇ ಪರಿಶೀಲನೆಗೆ <b>STB / VC id</b> ಕಳುಹಿಸಿ.',
        'idle_prompt_railtel': (
            'ಕೆಳಗೆ ಆಯ್ಕೆಮಾಡಿ, ಅಥವಾ ತ್ವರಿತ ಒಂದು ಪರಿಶೀಲನೆಗೆ ಗ್ರಾಹಕ ID / ಫೋನ್ ಕಳುಹಿಸಿ.'
        ),
        'railtel_input_on_hathway': (
            'ಇದು <b>ರೈಲ್‌ಟೆಲ್</b> ಗ್ರಾಹಕ ID ಅಥವಾ ಫೋನ್ ಎಂದು ಕಾಣುತ್ತದೆ. ಈ ಬಾಟ್ <b>ಕೇವಲ ಹ್ಯಾಥ್‌ವೇ</b> — '
            '<b>STB / VC id</b> (N + 11 ಅಥವಾ T + 12 ಅಂಕೆ) ಕಳುಹಿಸಿ. ಗ್ರಾಹಕ ಪರಿಶೀಲನೆಗೆ <b>ರೈಲ್‌ಟೆಲ್ ಏಜೆಂಟ್</b> ಬಳಸಿ.'
        ),
        'login_fail_railtel': 'ಲಾಗಿನ್ ವಿಫಲ — ರುಜುವಾತುಗಳು ಮತ್ತು CAPTCHA ಪರಿಶೀಲಿಸಿ.',
        'audit_fail_hathway': 'ಹ್ಯಾಥ್‌ವೇ ಪರಿಶೀಲನೆ ವಿಫಲ ({search})\nಕಾರಣ: {reason}.',
        'audit_fail_railtel_head': '<b>ಪರಿಶೀಲನೆ ವಿಫಲ: {search}</b>',
        'audit_fail_railtel_reason': 'ಕಾರಣ: {reason}.',
        'hathway_pack_lines': (
            'ಪ್ಯಾಕ್ ಹೆಸರು: {pack}\nಮಾನ್ಯತೆ ವರೆಗೆ: {valid}\nSTB Status: {stb}\nLCO ಬೆಲೆ: {lco}'
        ),
        'hathway_pack_mgmt': (
            'ಹ್ಯಾಥ್‌ವೇ — ಪ್ಯಾಕ್ ಮ್ಯಾನೇಜ್‌ಮೆಂಟ್\n'
            'ಉಲ್ಲೇಖ: {ref}\n\n'
            'ಲಾಗಿನ್ ನಂತರ ಬ್ರೌಸರ್ ಪ್ಯಾಕ್ ಮ್ಯಾನೇಜ್‌ಮೆಂಟ್‌ನಲ್ಲಿದೆ. ಈ ಬಾಟ್‌ನಲ್ಲಿ ಗ್ರಾಹಕ Status ಮಾಹಿತಿ ಸ್ವಯಂಚಾಲಿತವಲ್ಲ — '
            'ಪೋರ್ಟಲ್ ಕಿಟಕಿಯಲ್ಲಿ ಹುಡುಕಿ, ಅಥವಾ ರೈಲ್‌ಟೆಲ್‌ನಂತಹ ಪರಿಶೀಲನೆಗೆ ಸೆಲೆಕ್ಟರ್ ಹಂಚಿಕೊಳ್ಳಿ.'
        ),
        'audit_result_head': '<b>ಪರಿಶೀಲನೆ ಫಲಿತಾಂಶ: {matched}</b>',
        'audit_search_input': 'ಹುಡುಕಾಟ ಒಳಬರಹ: {search}',
        'audit_status': 'Status: {status}',
        'audit_session_days': 'ಸೆಷನ್ ದಿನಗಳು: {days}',
        'audit_time_info': 'ಸಮಯ ಮಾಹಿತಿ: {downtime}',
        'audit_mac': 'MAC: {mac}',
        'audit_expiry': 'ಮುಕ್ತಾಯ: {expiry}',
        'status_active': '🟢 ಸಕ್ರಿಯ',
        'status_inactive': '🔴 ನಿಷ್ಕ್ರಿಯ',
        'clear_ok_head': '<b>ಸೆಷನ್ ತೆರವು ಯಶಸ್ವಿ</b>',
        'clear_ok_matched': 'ಹೊಂದಿದೆ: <code>{mc}</code>',
        'clear_fail_head': '<b>ಸೆಷನ್ ತೆರವು ವಿಫಲ</b>',
        'clear_fail_input': 'ಒಳಬರಹ: <code>{search}</code>',
        'clear_fail_reason': 'ಕಾರಣ: {err}',
        'clear_fail_matched_line': 'ಹೊಂದಿದೆ: <code>{mc}</code>',
        'na': 'ಲಭ್ಯವಿಲ್ಲ',
        'session_cleared_msg': 'ಸೆಷನ್ ತೆರವಾಗಿದೆ.',
    },
}

LABELS = {
    'en': {
        'hathway_multi': 'Login — multi STB status',
        'hathway_single': 'Single STB status',
        'hathway_deactivate': 'Temp STB deactivate',
        'hathway_activate': 'Activate Back',
        'hathway_remove_terminate': 'Remove pack & terminate',
        'menu': 'Menu',
        'done': 'Done / Logout',
        'change_language': 'Change language',
    },
    'kn': {
        'hathway_multi': 'ಅನೇಕ STB ಚೆಕ್',
        'hathway_single': 'ಒಂದು STB ಚೆಕ್',
        'hathway_deactivate': 'ತಾತ್ಕಾಲಿಕ STB ನಿಷ್ಕ್ರಿಯ',
        'hathway_activate': 'Activate Back',
        'hathway_remove_terminate': 'Remove pack & terminate',
        'menu': 'ಮೆನು',
        'done': 'Logout/ಪೋರ್ಟಲ್ ಮುಚ್ಚುವಿಕೆ',
        'change_language': 'ಭಾಷೆ ಬದಲಾಯಿಸಿ',
    },
}


def _label_ctx(chat_id):
    """Substitute other localized button texts into messages."""
    return {k: lbl(chat_id, k) for k in LABELS['en']}


def welcome_language_prompt():
    """Shown before language is chosen (bilingual intro)."""
    return STRINGS['en']['welcome_choose']


def remind_choose_language():
    """When user sent something else before picking a language."""
    return STRINGS['en']['please_choose_lang']


def format_help_body(chat_id):
    lang = get_lang(chat_id) or 'en'
    ctx = _label_ctx(chat_id)
    intro = _t(lang, 'help_intro', **ctx)
    active = _t(lang, 'help_active_hathway')
    return active + intro


def msg_with_labels(chat_id, key, **kw):
    ctx = {**_label_ctx(chat_id), **kw}
    return T(chat_id, key, **ctx)


_KN_HATHWAY_ERROR_KN = {
    'STB is not with your LCO ID.': 'ಈ STB ನಿಮ್ಮ LCO ಅಕೌಂಟ್ ನಲ್ಲಿ ಇಲ್ಲ',
    'STB is terminated.': 'ಈ STB ನಿಷ್ಕ್ರಿಯಗೊಳಿಸಲಾಗಿದೆ/Terminated',
}


def translate_hathway_bot_error(lang, message):
    """Map known English Hathway errors to Kannada user text (audit / portal)."""
    if lang != 'kn' or not message:
        return message
    return _KN_HATHWAY_ERROR_KN.get((message or '').strip(), message)


def _tg_escape(s):
    if s is None:
        return ''
    return html.escape(str(s), quote=False)


def _plain_one_line(s):
    if s is None:
        return ''
    return str(s).replace('\r', ' ').replace('\n', ' | ').strip()


def format_audit_result_for_chat(chat_id, search_value, audit):
    lang = get_lang(chat_id) or 'en'
    if not audit.get('success'):
        if audit.get('provider') == 'hathway':
            reason_raw = audit.get('error', 'Unknown')
            reason_disp = translate_hathway_bot_error(lang, reason_raw)
            return _t(
                lang,
                'audit_fail_hathway',
                search=_plain_one_line(search_value),
                reason=_plain_one_line(reason_disp),
            )
        return (
            f'{_t(lang, "audit_fail_railtel_head", search=_tg_escape(search_value))}\n'
            f'{_t(lang, "audit_fail_railtel_reason", reason=_tg_escape(audit.get("error", "Unknown")))}'
        )

    if audit.get('provider') == 'hathway' and not audit.get('hathway_pack_management_only'):
        pack = _plain_one_line(audit.get('hathway_plan_name')) or _t(lang, 'na')
        valid_upto = _plain_one_line(audit.get('hathway_valid_upto') or audit.get('expiry')) or _t(lang, 'na')
        stb_st = _plain_one_line(audit.get('hathway_tv_status')) or _t(lang, 'na')
        lco = _plain_one_line(audit.get('hathway_bot_lco_display')) or _t(lang, 'na')
        return _t(lang, 'hathway_pack_lines', pack=pack, valid=valid_upto, stb=stb_st, lco=lco)

    if audit.get('hathway_pack_management_only'):
        ref = _plain_one_line(audit.get('matched_cid') or search_value)
        return _t(lang, 'hathway_pack_mgmt', ref=ref)

    matched_cid = _tg_escape(audit.get('matched_cid') or search_value)
    # Railtel (and any non-Hathway pack) audit: keep labels identical to English even in Kannada UI.
    label_lang = 'en' if audit.get('provider') != 'hathway' else lang
    status = _t(label_lang, 'status_active') if audit['is_online'] else _t(label_lang, 'status_inactive')
    session_days = audit.get('session_days', 0)
    downtime = _tg_escape(audit.get('downtime', _t(label_lang, 'na')))

    result_lines = [
        _t(label_lang, 'audit_result_head', matched=matched_cid),
        _t(label_lang, 'audit_search_input', search=_tg_escape(search_value)),
        _t(label_lang, 'audit_status', status=status),
        _t(label_lang, 'audit_session_days', days=session_days),
        _t(label_lang, 'audit_time_info', downtime=downtime),
    ]

    if audit.get('mac'):
        result_lines.append(_t(label_lang, 'audit_mac', mac=_tg_escape(audit.get('mac'))))

    if audit.get('expiry'):
        result_lines.append(_t(label_lang, 'audit_expiry', expiry=_tg_escape(audit.get('expiry'))))

    return '\n'.join(result_lines)


def format_clear_result_for_chat(chat_id, search_value, result):
    lang = get_lang(chat_id) or 'en'
    if result.get('success'):
        mc = _tg_escape(result.get('matched_cid') or search_value)
        msg = _tg_escape(result.get('message') or _t(lang, 'session_cleared_msg'))
        return f'{_t(lang, "clear_ok_head")}\n{_t(lang, "clear_ok_matched", mc=mc)}\n{msg}'
    err = _tg_escape(result.get('error', 'Unknown'))
    mc = result.get('matched_cid')
    lines = [
        _t(lang, 'clear_fail_head'),
        _t(lang, 'clear_fail_input', search=_tg_escape(search_value)),
        _t(lang, 'clear_fail_reason', err=err),
    ]
    if mc:
        lines.insert(2, _t(lang, 'clear_fail_matched_line', mc=_tg_escape(mc)))
    return '\n'.join(lines)


def login_fail_message(chat_id, portal):
    lang = get_lang(chat_id) or 'en'
    if portal == 'hathway':
        return _t(lang, 'login_fail_hathway')
    return _t(lang, 'login_fail_railtel')

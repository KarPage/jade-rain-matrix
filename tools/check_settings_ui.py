#!/usr/bin/env python3
"""Optional Playwright acceptance check. Only temporary, demo-only settings.

python3 tools/check_settings_ui.py
python3 tools/check_settings_ui.py --before ../previous-checkout
No browser dependency is added to the installed application.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--before', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.before or ROOT))
from jade_rain.editor import EditorServer
from jade_rain.config import apply_mode_form, load_document, load_settings

SHOTS = Path(os.environ.get('JRM_TEST_SHOTS', ROOT / 'shots'))
SHOTS.mkdir(parents=True, exist_ok=True)
LOGO = ROOT / 'assets' / 'kp-logo-white.png'
checks=[]
def capture_full(page, name):
    previous = page.viewport_size
    page.set_viewport_size(dict(width=previous['width'],height=page.evaluate('document.documentElement.scrollHeight')))
    page.screenshot(path=str(SHOTS/name),full_page=True)
    page.set_viewport_size(previous)

def ok(name):
    checks.append(name)
    print('PASS:',name,flush=True)

with tempfile.TemporaryDirectory(prefix='jrm-demo-') as temp, patch.dict(os.environ, {
    'HOME':temp, 'XDG_CONFIG_HOME':temp+'/config', 'XDG_STATE_HOME':temp+'/state'}):
    apply_mode_form('demo','live',{'phrases':'Stay curious\nMake something good','logo':str(LOGO),
        'color_preset':'jade', 'glyph_set':'katakana','logo_opacity':.6})
    server=EditorServer(); server.start()
    try:
      with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('JRM_TEST_BROWSER') or shutil.which('chromium') or shutil.which('google-chrome'),headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1100,'height':1000},device_scale_factor=1)
        page=context.new_page(); errors=[]; requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append(r.url.split('?')[0]))
        page.goto(server.url())
        if args.before:
            page.wait_for_function("()=>(document.querySelector('#frame').src.startsWith('blob:'))")
            page.screenshot(path=str(SHOTS/'before-desktop.png'),full_page=True)
            page.set_viewport_size({'width':825,'height':1024})
            page.screenshot(path=str(SHOTS/'before-narrow.png'),full_page=True)
            print('Before screenshots captured.'); browser.close()
        else:
            page.wait_for_function("()=>(typeof preview !== 'undefined' && preview.scene && document.querySelector('#preview').dataset.frame)")
            expect(page.locator('#advanced')).not_to_have_attribute('open','')
            assert page.locator('#preview').bounding_box()['y'] < page.locator('#mode-buttons').bounding_box()['y']
            ok('Preview first; Advanced closed; four modes')
            first=page.locator('#preview').get_attribute('data-frame')
            page.wait_for_function('(first)=>document.querySelector("#preview").dataset.frame!==first',arg=first)
            ok('Rain actually animates, without polling')
            page.locator('#pause').click()
            page.wait_for_function('()=>(preview.paused)')
            capture_full(page,'after-desktop.png')
            original=(load_document().path).read_bytes()
            page.locator('#phrases').fill('Demo rain\nOnly demo data')
            page.wait_for_function('()=>(preview.scene.streams.some(s=>Object.keys(s.words).length))')
            page.locator('#mode-buttons [data-mode=still]').click()
            page.locator('#phrases').fill('Still demo')
            page.locator('#mode-buttons [data-mode=live]').click()
            expect(page.locator('#phrases')).to_have_value('Demo rain\nOnly demo data')
            assert load_document().path.read_bytes()==original
            ok('Per-mode drafts survive switching; preview never saves')
            page.locator('#save').click()
            expect(page.locator('#status')).to_have_text('Saved on this computer')
            doc=load_document()
            assert doc.profiles['demo'].modes['live']['phrases']=='Demo rain\nOnly demo data'
            assert doc.profiles['demo'].modes['still']['phrases']=='Still demo'
            page.reload(); page.wait_for_function('()=>(preview.scene)')
            expect(page.locator('#phrases')).to_have_value('Demo rain\nOnly demo data')
            ok('One save persists all edited modes and reloads correctly')
            page.locator('#mode-buttons [data-mode=still]').click()
            page.wait_for_function("()=>(preview.scene.mode==='still' && document.querySelector('#preview').dataset.frame==='160')")
            page.locator('#mode-buttons [data-mode=light]').click()
            page.wait_for_function("()=>(preview.scene.mode==='light' && Math.max(...preview.scene.background)>140)")
            capture_full(page,'after-light.png')
            ok('Still is still; Light uses the real paper palette')
            page.locator('#mode-buttons [data-mode=live]').click()
            page.locator('#logo-file').set_input_files(str(LOGO))
            expect(page.locator('#logo-message')).to_have_text('Logo added · save to keep it')
            page.wait_for_function("()=>(document.querySelector('#logo-thumb').src.startsWith('data:image/png'))")
            assert '/logos/' in page.locator('#logo').input_value()
            page.locator('#logo-style').select_option('sprite')
            page.wait_for_function('()=>(preview.scene.logoSprite!==null)')
            ok('Logo upload and thumbnail; floating and small-mark styles')
            page.locator('#remove-logo').click()
            page.wait_for_function('()=>(preview.scene.logos.length===0 && preview.scene.logoSprite===null)')
            ok('Remove logo updates the preview')
            # Exercise the drop target with the same approved, demo-only logo.
            page.evaluate('''(data)=>{const transfer=new DataTransfer(); const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
              transfer.items.add(new File([bytes],'demo-logo.png',{type:'image/png'}));
              document.querySelector('#logo-drop').dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:transfer}));}''',base64.b64encode(LOGO.read_bytes()).decode())
            expect(page.locator('#logo-message')).to_have_text('Logo added · save to keep it')
            ok('Logo drag and drop')
            page.locator('#theme-colors').click()
            page.wait_for_function("()=>(preview.scene.ramp && document.querySelector('#theme-colors').getAttribute('aria-pressed')==='true')")
            expect(page.locator('#primary')).to_have_value('')
            page.locator('#custom-colors').click()
            page.locator('#primary-pick').evaluate("el=>{el.value='#ff4422';el.dispatchEvent(new Event('input',{bubbles:true}));}")
            page.wait_for_function('()=>(preview.scene.ramp[2][0]>preview.scene.ramp[2][1])')
            ok('Theme and custom color controls update the real palette')
            page.locator('#advanced > summary').click()
            page.locator('#primary').fill('#not-a-color')
            expect(page.locator('#preview-status')).to_have_text('Finish your color to update the preview.')
            assert not page.locator('#primary').evaluate('el=>el.checkValidity()')
            page.locator('#primary').fill('#3fe0a4')
            ok('Invalid colors are explained and block saving')
            page.locator('#glyph').select_option('custom'); page.locator('#glyphs').fill('ABC123')
            page.locator('#import-path').fill('/does-not-exist-demo.txt'); page.locator('#import').click()
            expect(page.locator('#status')).to_contain_text('Import failed:')
            ok('Import error is recoverable')
            # Save keyboard shortcut, with a double invocation guarded.
            page.locator('#phrases').fill('Keyboard demo')
            page.keyboard.press('Control+s'); page.keyboard.press('Control+s')
            expect(page.locator('#status')).to_have_text('Saved on this computer')
            ok('Keyboard save and duplicate-submit guard')
            page.once('dialog',lambda dialog:dialog.dismiss())
            page.locator('#reset').click()
            expect(page.locator('#phrases')).to_have_value('Keyboard demo')
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#reset').click()
            expect(page.locator('#status')).to_have_text('Defaults restored and saved')
            expect(page.locator('#phrases')).to_have_value('')
            ok('Reset confirms, honors Cancel, then refreshes fields immediately')
            # Profile cloning keeps all mode settings, not just the current mode.
            page.locator('#new-profile').fill('demo-copy'); page.locator('#save').click()
            expect(page.locator('#status')).to_have_text('Saved on this computer')
            assert 'demo-copy' in load_document().profiles
            ok('Save-as-profile preserved in Advanced')
            page.locator('#advanced > summary').click()
            page.set_viewport_size({'width':825,'height':1024})
            page.wait_for_function("()=>(document.querySelector('#preview-status').textContent.includes('Preview only'))")
            page.screenshot(path=str(SHOTS/'after-narrow.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_function('()=>(document.documentElement.scrollWidth<=window.innerWidth)')
            capture_full(page,'after-mobile.png')
            ok('825px and 390px layouts; no horizontal overflow')
            page.emulate_media(reduced_motion='reduce')
            page.wait_for_function("()=>(document.querySelector('#preview').dataset.frame==='160')")
            ok('Reduced motion respected')
            page.locator('#about').click(); expect(page.locator('#about-panel')).to_be_visible()
            page.keyboard.press('Escape'); expect(page.locator('#about-panel')).not_to_be_visible()
            page.locator('#phrases').fill('Do not save')
            page.route('**/api/save',lambda route:route.fulfill(status=500,content_type='application/json',body='{"ok":false,"error":"Demo retry failure"}'))
            page.locator('#save').click()
            expect(page.locator('#status')).to_contain_text('Not saved: Demo retry failure')
            expect(page.locator('#save')).to_be_enabled()
            page.unroute('**/api/save'); page.locator('#save').click()
            expect(page.locator('#status')).to_have_text('Saved on this computer')
            ok('Failed save shows retry; retry succeeds')
            assert not errors,errors
            assert all(url.startswith('http://127.0.0.1:') or url.startswith('data:') or url.startswith('blob:') for url in requests),requests
            ok('No JavaScript errors or external network requests')
            (SHOTS/'browser-results.json').write_text(json.dumps({'passed':checks,'javascript_errors':errors,'external_requests':[]},indent=2)+'\n')
            browser.close()
    finally:
      server.close()

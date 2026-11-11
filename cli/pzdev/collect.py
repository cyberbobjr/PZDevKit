"""pzdev scenario collect: archive actual game reports and acknowledge batch children (formerly
PZPuppeteer tools/collect_reports.py). Never controls game actions.

    python PZDevKit/pzdev.py scenario collect --output <Project>/tests/puppeteer/reports/runs [--user DIR] [--seconds S]
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import re
import os
import time

USER = Path(os.environ.get('USERPROFILE') or str(Path.home())) / 'Zomboid'
LUA_ERROR = re.compile(r'ERROR\s*:\s*Lua|KahluaThread\.flushErrorMessage|ExceptionLogger|stack trace|Artemis.*ERREUR', re.I)
TOKEN = re.compile(r'^\d+-\d+$')

def lua_errors(text):
    return [line for line in text.splitlines() if LUA_ERROR.search(line)]

def report_metadata(raw):
    text = raw.decode('utf-8', errors='replace')
    match = re.search(r'^(.+) : (passed|failed|cancelled)$', text, re.M)
    if not match:
        return None
    fields = dict(re.findall(r'^(Run token|Batch token|Batch index|Persistent report|Scenario path|Player index|Manual stop): (.+)$', text, re.M))
    return dict(name=match[1], status=match[2], fields=fields)

def acknowledge(metadata, raw, console, archive, user=USER):
    """Return False until ready; reject stale/incomplete receipts and any new batch Lua error."""
    fields = metadata['fields']
    token, batch = fields.get('Run token'), fields.get('Batch token')
    if not batch:
        return False
    if not token or not TOKEN.fullmatch(token) or not TOKEN.fullmatch(batch):
        raise ValueError('Invalid batch report token')
    relative = fields.get('Persistent report', '')
    if relative != f'PZPuppet/reports/{token}.txt':
        raise ValueError('Invalid persistent report path')
    request = f'[PZPuppet] Batch archive requested: {token} | report: {relative}'
    if request not in console:
        return False
    persistent = user / 'Lua' / relative
    if not persistent.exists() or persistent.read_bytes() != raw:
        return False
    start = console.find(f'[PZPuppet] Batch {batch} starting |')
    if start < 0:
        return False  # Do not approve a batch whose initial error baseline is unavailable.
    errors = lua_errors(console[start:])
    accepted = metadata['status'] == 'passed' and not errors
    reason = 'new Lua error in batch' if errors else 'scenario did not pass'
    line = f'PZPuppet ACK {token} ' + ('passed' if accepted else 'rejected ' + reason)
    receipt = dict(run_token=token, batch_token=batch, accepted=accepted,
                   errors=errors, persistent_report_verified=True)
    (archive / 'batch-ack.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    (archive / 'batch-errors.txt').write_text('\n'.join(errors), encoding='utf-8')
    result_file = archive / 'result.json'
    if result_file.exists():
        result = json.loads(result_file.read_text(encoding='utf-8'))
        result['batch_archive_accepted'] = accepted
        result['batch_errors'] = errors
        if not accepted:
            result['status'] = '\u00e9chou\u00e9' if result['status'] in ('r\u00e9ussi','\u00e9chou\u00e9') else 'failed'
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    target = user / 'Lua/PZPuppet/batch-ack.txt'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(line + '\n', encoding='utf-8')
    temporary.replace(target)
    return True

def main(argv=None):
    parser = argparse.ArgumentParser(prog='pzdev scenario collect', description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, required=True, help='Dedicated project reports/runs directory')
    parser.add_argument('--user', type=Path, default=USER)
    parser.add_argument('--seconds', type=float, default=0, help='0: watch until interrupted')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    console_file = args.user / 'console.txt'
    report_file = args.user / 'Lua/PZPuppet/last-report.txt'
    console = ''
    offset, signature = 0, None
    seen, pending = set(), None
    started = time.monotonic()
    print('Watching actual game reports; batch ACK requires complete archived evidence.', flush=True)
    while not args.seconds or time.monotonic() - started < args.seconds:
        if console_file.exists():
            with console_file.open('rb') as handle:
                head = handle.read(256)
                if signature is not None and (head != signature or console_file.stat().st_size < offset):
                    console, offset, pending = '', 0, None
                signature = head
                handle.seek(offset)
                addition = handle.read()
                offset += len(addition)
                console += addition.decode('utf-8', errors='replace').replace('\x00', '')
        if report_file.exists():
            raw = report_file.read_bytes()
            metadata = report_metadata(raw)
            if metadata:
                token = metadata['fields'].get('Run token')
                relative = metadata['fields'].get('Persistent report', '')
                if token and (not TOKEN.fullmatch(token) or relative != f'PZPuppet/reports/{token}.txt'):
                    raise ValueError('Invalid persistent report metadata')
                marker = f'[PZPuppet] Run token: {token} |'
                index = console.find(marker)
                persistent = args.user / 'Lua' / relative
                complete = (persistent.is_file() and persistent.read_bytes() == raw)
                batch = metadata['fields'].get('Batch token')
                if batch and metadata['status'] == 'passed':
                    complete = complete and f'[PZPuppet] Batch archive requested: {token} | report: PZPuppet/reports/{token}.txt' in console
                end = console.find(f'[PZPuppet] {metadata["name"]} : {metadata["status"]}', index)
                if token and TOKEN.fullmatch(token) and token not in seen and index >= 0 and end >= 0 and complete:
                    name = re.sub(r'[^A-Za-z0-9_-]', '_', metadata['name'])
                    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    out = args.output / f'{stamp}_{name}_{token}'
                    out.mkdir()
                    line_end = console.find('\n', end)
                    segment = console[index:] if line_end < 0 else console[index:line_end + 1]
                    (out / 'puppeteer.txt').write_bytes(raw)
                    (out / 'console.txt').write_text(segment, encoding='utf-8')
                    (out / 'before-scenario.txt').write_text(console[:index], encoding='utf-8')
                    errors = lua_errors(segment)
                    (out / 'errors.txt').write_text('\n'.join(errors), encoding='utf-8')
                    result = dict(metadata, new_errors=errors, engine_status=metadata['status'],
                                  status='passed' if metadata['status'] == 'passed' and not errors else 'failed',
                                  report_sha256=hashlib.sha256(raw).hexdigest())
                    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                    seen.add(token)
                    pending = (metadata, raw, out) if batch and metadata['status'] == 'passed' else None
                    print(f'{metadata["name"]}: {metadata["status"]} -> {out}', flush=True)
        if pending and acknowledge(*pending[:2], console, pending[2], args.user):
            print('Batch archive ACK: ' + pending[0]['fields']['Run token'], flush=True)
            pending = None
        time.sleep(0.25)
    return 0

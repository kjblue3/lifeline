"""Offline nonmedical llama-server diagnostics, not an inference provider.

No dependencies, model loading, retries, filtering, or remote destinations.
Full raw HTTP response bodies and request payloads are retained in JSONL.
Heuristics are triage signals ONLY; human review is required for every answer.
"""

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
from pathlib import Path
import re
import sys
import time


PROMPTS = (
    ('copy', 'Reply in English with exactly these three words: blue square orange', 'blue square orange'),
    ('arithmetic', 'In English, what is 7 plus 5? Answer in one short sentence.', '12 or twelve'),
    ('sort', 'Sort these words alphabetically: zebra, apple, moon. Answer in English.', 'apple, moon, zebra'),
    ('explain', 'In two short English sentences, explain why a compass is useful on a hike.',
     'Coherent compass/navigation explanation; not medical advice'),
    ('supplies', 'In English, name three ordinary nonmedical supplies to pack for a day hike.',
     'Three sensible supplies, coherent English; not medical advice'),
)

SIMPLE_SYSTEM = 'Respond concisely in English. Follow the requested format. These are nonmedical test questions.'
LONG_PROMPT = (
    'Read the following ordinary hiking-planning notes. They are background text, '
    'not medical information.\n\n'
    + '\n\n'.join(
        f'Planning note {i}: A group is considering a daytime walk on a marked trail. '
        'They want to check the route map, weather forecast, trail access and return time. '
        'They plan to carry drinking water, snacks, a rain jacket, a paper map and a compass. '
        'The group will stay together, keep the outing within daylight hours, and tell '
        'a responsible person the intended route. No one is injured or asking for treatment.'
        for i in range(1, 7)
    )
    + '\n\nIn two short English sentences, summarize the nonmedical planning priorities. '
    'Do not repeat the notes or provide medical treatment instructions.'
)


def request(port, method, path, timeout, payload=None):
    """Direct loopback TCP, bypassing proxy settings; never follows redirects."""
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    started = time.perf_counter()
    try:
        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        connection.request(method, path, body, {'Content-Type': 'application/json'})
        response = connection.getresponse()
        raw = response.read(4 * 1024 * 1024 + 1)
        elapsed = time.perf_counter() - started
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('Response exceeds diagnostic 4 MiB limit')
        utf8_error = False
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            utf8_error = True
            text = raw.decode('utf-8', errors='replace')
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        return {'http_status': response.status, 'latency_seconds': elapsed,
                'raw_response': text, 'raw_response_base64': base64.b64encode(raw).decode('ascii'),
                'utf8_decode_error': utf8_error, 'response': data}
    finally:
        connection.close()


def assess(text):
    """Diagnostic flags, not a language detector or a correctness/safety grade."""
    if not isinstance(text, str) or not text.strip():
        return {'flags': ['empty_or_nontext'], 'review': 'REQUIRED'}
    words = re.findall(r'\w+', text.lower())
    counts = Counter(words)
    flags = []
    if len(words) >= 12 and counts.most_common(1)[0][1] / len(words) > 0.45:
        flags.append('dominant_repeated_word')
    grams = Counter(tuple(words[i:i + 3]) for i in range(max(0, len(words) - 2)))
    if grams and grams.most_common(1)[0][1] >= 4:
        flags.append('repeated_three_word_sequence')
    letters = [char for char in text if char.isalpha()]
    non_ascii = sum(not char.isascii() for char in letters)
    if letters and non_ascii / len(letters) > 0.15:
        flags.append('many_non_ascii_letters_in_english_test')
    if '\ufffd' in text:
        flags.append('unicode_replacement_character')
    return {'flags': flags, 'review': 'REQUIRED', 'word_count': len(words),
            'non_ascii_letter_count': non_ascii}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--rounds', type=int, default=3, help='Repeat all prompts in the selected suite')
    parser.add_argument('--suite', choices=('basic', 'runtime'), default='basic',
                        help='runtime: short, long ordinary text, and long text with full LifeLine safety prompt')
    parser.add_argument('--max-tokens', type=int, default=160)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--cache', choices=('default', 'off', 'on'), default='default',
                        help='default omits cache controls, matching LifeLine; off/on pins slot 0')
    parser.add_argument('--system', choices=('simple', 'lifeline'), default='lifeline',
                        help='basic suite only; runtime deliberately tests both system prompts')
    parser.add_argument('--erase-between', action='store_true',
                        help='Requires --slot-save-path on b11680; use with --cache-ram 0')
    parser.add_argument('--label', required=True, help='Build/configuration identifier recorded verbatim')
    parser.add_argument('--output', type=Path, required=True, help='NEW JSONL path; never overwrites')
    parser.add_argument('--review', action='store_true', help='Prompt for manual judgment of each answer')
    args = parser.parse_args(argv)
    if (not 1 <= args.port <= 65535 or not 1 <= args.rounds <= 100 or
            not 1 <= args.max_tokens <= 512 or not math.isfinite(args.timeout) or args.timeout <= 0):
        parser.error('Invalid port, round count, token limit, or timeout')
    if args.suite == 'runtime' and args.system != 'lifeline':
        parser.error('runtime suite requires the unchanged LifeLine safety prompt; omit --system')
    system = SIMPLE_SYSTEM
    if args.system == 'lifeline':
        # Read only the literal constant: no application imports/dependencies or side effects.
        import ast
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'inference.py').read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == 'SYSTEM_INSTRUCTION'
                    for target in node.targets):
                system = ast.literal_eval(node.value)
                break
        else:
            parser.error('SYSTEM_INSTRUCTION literal not found; do not substitute a weaker prompt')
    cases = [(name, question, expected, system) for name, question, expected in PROMPTS]
    if args.suite == 'runtime':
        cases = [
            ('short', 'In English, name three ordinary nonmedical supplies for a day hike.',
             'Coherent English supplies; no repeated-token corruption', SIMPLE_SYSTEM),
            ('long-ordinary', LONG_PROMPT,
             'Coherent English summary of the long planning notes', SIMPLE_SYSTEM),
            ('full-lifeline-safety', LONG_PROMPT,
             'Coherent English with unchanged LifeLine safety instruction; no unsupported treatment', system),
        ]
    if not args.output.parent.is_dir():
        parser.error('Output parent directory must already exist')

    def emit(record):
        output.write(json.dumps(record, ensure_ascii=True) + '\n')
        output.flush()

    try:
        output = args.output.open('x', encoding='utf-8')
    except FileExistsError:
        parser.error('Output exists; choose a new filename')
    with output:
        emit({'event': 'metadata', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'arguments': dict(vars(args), output=str(args.output)),
              'python': sys.version, 'system_instruction': system,
              'system_sha256': hashlib.sha256(system.encode()).hexdigest(),
              'warning': 'NOT MEDICAL VALIDATION. No heuristic pass means nothing without human review.'})
        try:
            health = request(args.port, 'GET', '/health', min(5, args.timeout))
            emit(dict(health, event='health'))
            if (health['http_status'] != 200 or not isinstance(health['response'], dict)
                    or health['response'].get('status') != 'ok'):
                print('Server not healthy; inspect the recorded response. No prompts sent.')
                return 2
            for round_index in range(1, args.rounds + 1):
                for name, question, expected, case_system in cases:
                    if args.erase_between:
                        erased = request(args.port, 'POST', '/slots/0?action=erase', args.timeout, {})
                        emit(dict(erased, event='erase'))
                        result = erased['response']
                        if (erased['http_status'] != 200 or not isinstance(result, dict)
                                or result.get('id_slot') != 0
                                or not isinstance(result.get('n_erased'), int)):
                            print('Slot erase failed. Stopping without silently continuing.')
                            return 2
                    payload = {'model': 'lifeline-qwen', 'messages': [
                        {'role': 'system', 'content': case_system}, {'role': 'user', 'content': question}],
                        'temperature': 0, 'max_tokens': args.max_tokens, 'stream': False}
                    if args.cache != 'default':
                        payload.update(cache_prompt=args.cache == 'on', id_slot=0, n_cache_reuse=0)
                    record = {'event': 'completion', 'round': round_index, 'prompt_id': name,
                              'expected_for_human_review': expected, 'request': payload}
                    # Flush before sending so even interruption preserves the attempted payload.
                    emit(dict(record, event='request'))
                    result = request(args.port, 'POST', '/v1/chat/completions', args.timeout, payload)
                    record.update(result)
                    data = result['response']
                    try:
                        text = data['choices'][0]['message']['content']
                    except (KeyError, IndexError, TypeError):
                        text = None
                    record['answer'] = text
                    record['quality_triage'] = assess(text)
                    record['manual_quality'] = 'not_reviewed'
                    usage = data.get('usage', {}) if isinstance(data, dict) else {}
                    count = usage.get('completion_tokens') if isinstance(usage, dict) else None
                    record['completion_tokens'] = count
                    record['wall_output_tokens_per_second'] = (
                        count / result['latency_seconds'] if isinstance(count, int) and count >= 0 else None)
                    # Server usage/timings remain in full raw response; never fabricate missing counts.
                    print(f'\nRound {round_index} / {name}: HTTP {result["http_status"]}, '
                          f'{result["latency_seconds"]:.3f}s, output tokens={count}')
                    print(json.dumps(text, ensure_ascii=True))
                    print('Triage:', record['quality_triage'], '| Expected:', expected)
                    emit(record)
                    if args.review:
                        review = input('Human review [coherent / corrupted / unclear]: ').strip().lower()
                        emit({'event': 'review', 'round': round_index, 'prompt_id': name,
                              'manual_quality': review if review in (
                                  'coherent', 'corrupted', 'unclear') else 'unclear'})
                    if result['http_status'] != 200:
                        print('HTTP failure; stopping. No retries or queued requests.')
                        return 2
        except (OSError, http.client.HTTPException, ValueError) as exc:
            emit({'event': 'transport_error', 'error': str(exc), 'type': type(exc).__name__})
            print('Transport failed. Stop/restart server before another experiment; no retry was sent.')
            return 2
    print(f'\nSaved {args.rounds * len(cases)} full responses to {args.output}.')
    print('Exit 0 means collection completed, NOT that quality passed. Review every raw answer.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

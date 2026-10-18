"""Replay captured UI JSON against loopback llama-server, one-field A/B controls.

Diagnostics only: no production imports, tools executed, retries, or filtering.
Every response chunk is saved losslessly before parsing or human review.
"""

import argparse
import ast
import base64
import copy
import hashlib
import http.client
import json
import math
from pathlib import Path
import re
import time


ROOT = Path(__file__).resolve().parents[1]


def safety_instruction():
    tree = ast.parse((ROOT / 'inference.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'SYSTEM_INSTRUCTION' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Existing SYSTEM_INSTRUCTION literal not found')


def adapter_payload(question, max_tokens):
    """Extract the actual source dictionary without importing/running the app.

    This is source reconstruction, NOT a capture of the running Dell process.
    Reject nonliteral future code rather than evaluating arbitrary expressions.
    """
    tree = ast.parse((ROOT / 'offline_ai' / 'llama_adapter.py').read_text(encoding='utf-8'))

    class Substitute(ast.NodeTransformer):
        def visit_Name(self, node):
            values = {'question': question, 'SYSTEM_INSTRUCTION': safety_instruction()}
            return ast.Constant(values[node.id]) if node.id in values else node

        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == 'self' and node.attr == '_max_tokens':
                return ast.Constant(max_tokens)
            return node

    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == '_request' and len(node.args) == 3
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == '/v1/chat/completions'):
            return ast.literal_eval(Substitute().visit(node.args[2]))
    raise ValueError('Adapter request dictionary not found; inspect changed source')


def variants(ui, max_tokens=160):
    if not isinstance(ui, dict) or not isinstance(ui.get('messages'), list) or not ui['messages']:
        raise ValueError('Input must be the actual JSON request body with nonempty messages')
    if not all(isinstance(m, dict) and isinstance(m.get('role'), str) for m in ui['messages']):
        raise ValueError('Invalid messages')
    if ui.get('stream') is not True:
        raise ValueError('Captured working UI baseline must have stream:true')
    if ui['messages'][-1].get('role') != 'user' or not isinstance(ui['messages'][-1].get('content'), str):
        raise ValueError('Capture a text request ending with a user turn, before any tool execution')
    cases = {'ui': copy.deepcopy(ui)}

    def changed(name, key, value):
        payload = copy.deepcopy(ui)
        payload[key] = value
        cases[name] = payload

    changed('stream-off', 'stream', False)
    messages = [copy.deepcopy(m) for m in ui['messages'] if m['role'] != 'system']
    changed('system-lifeline', 'messages', [{'role': 'system', 'content': safety_instruction()}, *messages])
    changed('temperature-zero', 'temperature', 0)
    changed('max-tokens', 'max_tokens', max_tokens)
    retained = [copy.deepcopy(m) for m in ui['messages'] if m['role'] in ('system', 'developer')]
    changed('history-last', 'messages', retained + [copy.deepcopy(ui['messages'][-1])])
    for key in ('return_progress', 'sse_ping_interval', 'reasoning_format', 'reasoning_control',
                'backend_sampling', 'timings_per_token', 'tools'):
        payload = copy.deepcopy(ui)
        payload.pop(key, None)
        cases['omit-' + key.replace('_', '-')] = payload
    # Multi-variable endpoint control, deliberately NOT called a one-field A/B.
    cases['adapter'] = adapter_payload(ui['messages'][-1]['content'], max_tokens)
    return cases


class SSE:
    """Incremental SSE framing, independent of TCP chunks and UTF-8 boundaries."""
    def __init__(self):
        self.buffer = b''
        self.data = []
        self.event = ''

    def feed(self, chunk):
        self.buffer += chunk
        events = []
        while True:
            match = re.search(b'\r\n|\r(?!$)|\n', self.buffer)
            if not match:
                break
            line = self.buffer[:match.start()].decode('utf-8-sig', errors='strict')
            self.buffer = self.buffer[match.end():]
            if not line:
                if self.data:
                    events.append({'event': self.event or 'message', 'data': '\n'.join(self.data)})
                self.data, self.event = [], ''
            elif not line.startswith(':'):
                field, _, value = line.partition(':')
                value = value[1:] if value.startswith(' ') else value
                if field == 'data':
                    self.data.append(value)
                elif field == 'event':
                    self.event = value
        return events


def capture(port, payload, timeout, emit):
    """Collect text, reasoning and tool deltas separately; never execute tools."""
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    started = time.perf_counter()
    result = {'answer': '', 'reasoning': '', 'tool_call_deltas': [], 'finish_reasons': {},
              'usage': None, 'first_content_seconds': None, 'errors': [], 'done': False}
    parser = SSE()
    total = 0
    raw = []
    parse_failed = False

    def consume(event):
        emit({'event': 'sse', 'sse_event': event['event'], 'data': event['data'],
              'elapsed_seconds': time.perf_counter() - started})
        if event['data'] == '[DONE]':
            result['done'] = True
            return
        data = json.loads(event['data'])
        if not isinstance(data, dict):
            raise ValueError('SSE JSON is not an object')
        if 'error' in data:
            result['errors'].append(data['error'])
        if data.get('usage') is not None:
            result['usage'] = data['usage']
        choices = data.get('choices', [])
        if not isinstance(choices, list):
            raise ValueError('SSE choices is not a list')
        for choice in choices:
            if not isinstance(choice, dict):
                raise ValueError('SSE choice is not an object')
            index = choice.get('index', 0)
            if index != 0:
                raise ValueError('Multiple choices: inspect raw stream, not a merged answer')
            delta = choice.get('delta', {})
            if not isinstance(delta, dict):
                raise ValueError('SSE delta is not an object')
            for key, destination in (('content', 'answer'), ('reasoning_content', 'reasoning')):
                text = delta.get(key)
                if isinstance(text, str):
                    if key == 'content' and text and result['first_content_seconds'] is None:
                        result['first_content_seconds'] = time.perf_counter() - started
                    result[destination] += text
            if delta.get('tool_calls'):
                result['tool_call_deltas'].extend(delta['tool_calls'])
            if choice.get('finish_reason') is not None:
                result['finish_reasons'][str(index)] = choice['finish_reason']

    try:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        connection.request('POST', '/v1/chat/completions', body, {'Content-Type': 'application/json'})
        sock = connection.sock
        response = connection.getresponse()
        result['http_status'] = response.status
        mime = response.getheader('Content-Type', '')
        emit({'event': 'headers', 'status': response.status, 'headers': response.getheaders(),
              'elapsed_seconds': time.perf_counter() - started})
        streaming = 'text/event-stream' in mime.lower()
        if bool(payload.get('stream')) != streaming and response.status == 200:
            result['errors'].append('Response media type does not match requested streaming mode')
        while True:
            if time.perf_counter() - started > timeout:
                raise TimeoutError('Total capture deadline exceeded')
            if sock is not None:
                sock.settimeout(max(0.001, timeout - (time.perf_counter() - started)))
            chunk = response.read1(4096)
            if not chunk:
                break
            total += len(chunk)
            emit({'event': 'raw_chunk', 'base64': base64.b64encode(chunk).decode('ascii'),
                  'elapsed_seconds': time.perf_counter() - started})
            if total > 16 * 1024 * 1024:
                raise ValueError('Capture exceeded 16 MiB limit')
            if streaming:
                if not parse_failed:
                    try:
                        for event in parser.feed(chunk):
                            consume(event)
                    except (ValueError, TypeError, KeyError, IndexError) as exc:
                        result['errors'].append(f'Parse error; remaining bytes retained only: {exc}')
                        parse_failed = True
                if result['done']:
                    break
            else:
                raw.append(chunk)
        if streaming:
            if not result['done']:
                result['errors'].append('Premature EOF: no [DONE]; answer is incomplete')
        else:
            data = json.loads(b''.join(raw).decode('utf-8'))
            emit({'event': 'json_response', 'data': data})
            if not isinstance(data, dict):
                raise ValueError('Nonstream JSON is not an object')
            if 'error' in data:
                result['errors'].append(data['error'])
            choices = data.get('choices', [])
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise ValueError('Expected exactly one nonstream choice; inspect raw response')
            choice = choices[0]
            message = choice.get('message', {})
            if not isinstance(message, dict):
                raise ValueError('Nonstream message is not an object')
            result['answer'] = message.get('content') or ''
            result['reasoning'] = message.get('reasoning_content') or ''
            result['tool_call_deltas'] = message.get('tool_calls', [])
            result['finish_reasons']['0'] = choice.get('finish_reason')
            result['usage'] = data.get('usage')
            result['done'] = response.status == 200 and bool(choice.get('finish_reason'))
        if response.status != 200:
            result['errors'].append('Non-200 HTTP response')
    except (OSError, ValueError, TypeError, KeyError, IndexError, http.client.HTTPException) as exc:
        result['errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        connection.close()
        result['latency_seconds'] = time.perf_counter() - started
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui-request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='NEW JSONL file')
    parser.add_argument('--case', default='ui', help='One case per invocation; use --list to see names')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--max-tokens', type=int, default=160, help='Match LIFELINE_LLAMA_MAX_TOKENS')
    parser.add_argument('--timeout', type=float, default=180, help='Capture deadline/inactivity seconds')
    parser.add_argument('--review', action='store_true')
    args = parser.parse_args(argv)
    if (not 1 <= args.port <= 65535 or not 1 <= args.max_tokens <= 4096
            or not math.isfinite(args.timeout) or args.timeout <= 0):
        parser.error('Invalid numeric configuration')
    try:
        source = args.ui_request.read_bytes()
        ui = json.loads(source.decode('utf-8-sig'))
        cases = variants(ui, args.max_tokens)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.list:
        print('\n'.join(cases))
        return 0
    if args.case not in cases:
        parser.error('Unknown case; use --list')
    payload = cases[args.case]
    changed = [key for key in sorted(set(ui) | set(payload)) if (key in ui) != (key in payload)
               or ui.get(key) != payload.get(key)]
    try:
        output = args.output.open('x', encoding='utf-8')
    except OSError as exc:
        parser.error(str(exc))
    with output:
        def emit(record):
            output.write(json.dumps(record, ensure_ascii=True) + '\n')
            output.flush()

        emit({'event': 'request', 'case': args.case, 'changed_top_level_fields': changed,
              'payload': payload, 'ui_file_sha256': hashlib.sha256(source).hexdigest(),
              'adapter_source_sha256': hashlib.sha256(
                  (ROOT / 'offline_ai' / 'llama_adapter.py').read_bytes()).hexdigest(),
              'warning': 'Source reconstruction is not a live adapter capture. No tools will execute.'})
        print('Changed top-level fields:', changed)
        result = capture(args.port, payload, args.timeout, emit)
        emit(dict(result, event='result', human_quality='not_reviewed'))
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if args.review:
            value = input('Human quality [coherent/corrupted/unclear/tool_call_only]: ').strip().lower()
            emit({'event': 'review', 'human_quality': value if value in (
                'coherent', 'corrupted', 'unclear', 'tool_call_only') else 'unclear'})
    print('Collection only; no automatic quality or medical-safety pass.')
    return 0 if result['done'] and not result['errors'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

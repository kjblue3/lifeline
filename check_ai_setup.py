"""Read-only local AI preflight: no inference, downloads, or server startup.

Run in the working backend's Python environment. Exit 2 means prerequisites or
the running backend are not ready; an existing process is never reconfigured.
"""
import argparse
import http.client
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=os.environ.get('LIFELINE_GGUF_PATH', ''))
    parser.add_argument('--llama-port', type=int,
                        default=os.environ.get('LIFELINE_LLAMA_PORT', '8081'))
    parser.add_argument('--backend-port', type=int, default=8000)
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.llama_port, args.backend_port)):
        parser.error('Ports must be between 1 and 65535')
    model_exists = False
    gguf_header = False
    if args.model:
        path = Path(args.model).expanduser()
        model_exists = path.is_file()
        if model_exists and path.suffix.lower() == '.gguf':
            try:
                with path.open('rb') as source:
                    gguf_header = source.read(4) == b'GGUF'
            except OSError:
                pass
    result = {
        'platform': platform.system(), 'architecture': platform.machine(),
        'model_file_exists': model_exists, 'gguf_header_present': gguf_header,
        'llama_server_on_path': bool(shutil.which('llama-server')),
        'torch_installed': importlib.util.find_spec('torch') is not None,
        'transformers_installed': importlib.util.find_spec('transformers') is not None,
        'rag_requested_in_this_terminal': os.environ.get('LIFELINE_RAG') == '1',
    }
    for name, port, endpoint in (('llama', args.llama_port, '/health'),
                                 ('backend', args.backend_port, '/api/status')):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            # Numeric loopback only: no DNS, proxies, redirects, or remote host.
            connection.request('GET', endpoint)
            response = connection.getresponse()
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Oversized local status response')
            result[name] = {'port': port, 'http_status': response.status}
            if response.status == 200:
                result[name]['status'] = json.loads(raw)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            result[name] = {'port': port, 'error': type(exc).__name__}
        finally:
            connection.close()
    try:
        from medical_rag import MedicalLibrary
        library = MedicalLibrary()
        result['installed_reference_topics'] = library.count()
        result['ankle_search_titles'] = [row['title'] for row in library.search('twisted ankle')]
    except ImportError:
        result['installed_reference_topics'] = None
        result['reference_check_error'] = 'Run with the installed LifeLine backend environment.'
    llama_status = result['llama'].get('status')
    backend_status = result['backend'].get('status')
    llama_ok = isinstance(llama_status, dict) and llama_status.get('status') == 'ok'
    backend_data = backend_status.get('data', {}) if isinstance(backend_status, dict) else {}
    selected = isinstance(backend_data, dict) and backend_data.get('local', {}).get('model')
    result['ready_for_manual_inference_test'] = bool(model_exists and gguf_header and llama_ok and selected)
    result['inference_tested'] = False
    result['note'] = ('A local status response and GGUF header do not verify weights, '
                      'model identity, generation quality, ExecuTorch, or NPU execution.')
    print(json.dumps(result, indent=2))
    return 0 if result['ready_for_manual_inference_test'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

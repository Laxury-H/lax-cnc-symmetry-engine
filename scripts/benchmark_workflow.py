"""Run from the repository root: python scripts/benchmark_workflow.py."""
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.web.app import app, SESSIONS


def timed(action):
    started = perf_counter()
    response = action()
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.json, round(perf_counter() - started, 3)


if __name__ == '__main__':
    client = app.test_client()
    loaded, upload = timed(lambda: client.post('/api/load-sample', json={'sample_id': 'sample_no2'}))
    sid = loaded['session_id']
    try:
        result, candidates = timed(lambda: client.get('/api/candidates/' + sid))
        _, cached = timed(lambda: client.get('/api/candidates/' + sid))
        _, apply = timed(lambda: client.post('/api/repair', json={
            'session_id': sid, 'candidate_id': result['recommended_id']}))
        print(json.dumps({'sample': loaded['filename'], 'upload_seconds': upload,
                          'candidates_seconds': candidates, 'cached_seconds': cached,
                          'apply_seconds': apply, 'recommended_id': result['recommended_id'],
                          'candidates': [{k: c[k] for k in ('candidate_id', 'visual_quality',
                                         'change_ratio_percent', 'is_valid')} for c in result['candidates']]}, indent=2))
    finally:
        SESSIONS.pop(sid, None)

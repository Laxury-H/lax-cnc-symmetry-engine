import importlib
from unittest.mock import patch

import pytest

from src.web.app import app, SESSIONS
from src.repair.candidates import CandidateRepairGenerator


def test_candidate_cache_selection_and_invalidation(tmp_path, monkeypatch):
    monkeypatch.setattr(importlib.import_module('src.web.app'), 'OUTPUT_DIR', str(tmp_path))
    client = app.test_client()
    loaded = client.post('/api/load-sample', json={'sample_id': 'sample_no2'}).json
    sid = loaded['session_id']
    try:
        first = client.get('/api/candidates/' + sid).json
        assert not first['cached']
        assert first['recommended_id'] == 'candidate_a'
        with patch.object(CandidateRepairGenerator, 'generate_all', side_effect=AssertionError('Cache missed')):
            again = client.get('/api/candidates/' + sid).json
            assert again['cached']
            candidate = next(c for c in first['candidates'] if c['candidate_id'] == 'candidate_b')
            result = client.post('/api/repair', json={'session_id': sid, 'candidate_id': 'candidate_b'})
            assert result.status_code == 200
            assert result.json['repaired_geometry'] == candidate['geometry']
            assert result.json['metrics']['visual_quality_after'] == pytest.approx(candidate['visual_quality'], abs=.005)
            assert result.json['metrics']['total_loops'] == candidate['validation']['closed_loops']
            assert client.get(result.json['download_url']).status_code == 200
            assert client.post('/api/repair', json={'session_id': sid, 'candidate_id': 'unknown'}).status_code == 400
            SESSIONS[sid]['candidate_cache'][1][0].validation.is_valid = False
            assert client.post('/api/repair', json={'session_id': sid, 'candidate_id': 'candidate_a'}).status_code == 422
        changed = client.post('/api/update-model', json={'session_id': sid, 'lines': loaded['geometry']['lines']})
        assert changed.status_code == 200
        assert 'candidate_cache' not in SESSIONS[sid]
        assert 'repaired_dxf_path' not in SESSIONS[sid]
        assert client.get(result.json['download_url']).status_code == 404
    finally:
        SESSIONS.pop(sid, None)


def test_boundary_option_changes_cache_key():
    from src.web.app import session_candidates
    session = {'model': object()}
    with patch.object(CandidateRepairGenerator, 'generate_all', return_value=[]) as generate:
        assert session_candidates(session, True)[1] is False
        assert session_candidates(session, True)[1] is True
        assert session_candidates(session, False)[1] is False
        assert generate.call_count == 2

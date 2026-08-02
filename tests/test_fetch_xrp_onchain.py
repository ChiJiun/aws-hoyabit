"""Tests for fetch_xrp_onchain function."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))
from tools.onchain import fetch_xrp_onchain


def _make_ledger_response():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        'result': {
            'status': 'success',
            'ledger': {
                'ledger_index': '12345678',
                'close_time_human': '2024-Jan-01 12:00:00',
                'ledger_hash': 'ABC123DEF456',
                'transactions': ['tx1', 'tx2', 'tx3'],
                'total_coins': '99999999990000000',
                'close_time_resolution': 10,
            }
        }
    }
    return resp


def _make_fee_response():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        'result': {
            'status': 'success',
            'drops': {
                'open_ledger_fee': '12',
                'minimum_fee': '10',
                'median_fee': '15',
                'base_fee': '10',
            },
            'current_queue_size': '5',
            'expected_ledger_size': '100',
            'max_queue_size': '200',
            'current_ledger_size': '50',
        }
    }
    return resp


def _make_server_info_response():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        'result': {
            'status': 'success',
            'info': {
                'load_factor': 1,
                'server_state': 'full',
                'peers': 42,
                'uptime': 86400,
                'complete_ledgers': '32570-12345678',
                'validated_ledger': {
                    'reserve_base_xrp': 10,
                    'reserve_inc_xrp': 2,
                    'base_fee_xrp': 0.00001,
                    'seq': 12345678,
                }
            }
        }
    }
    return resp


def test_all_metrics_when_none():
    """Empty/None metrics should fetch all supported metrics."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.side_effect = [
            _make_ledger_response(),
            _make_fee_response(),
            _make_server_info_response(),
        ]

        result = fetch_xrp_onchain(None, 7)

        assert 'raw' in result
        assert 'source' in result
        assert 'content_reference' in result
        assert 'summary' in result
        assert 'ledger_info' in result['raw']
        assert 'tx_count' in result['raw']
        assert 'fee' in result['raw']
        assert 'reserve' in result['raw']
        assert 'validator_count' in result['raw']


def test_tx_count_metric():
    """Fetching tx_count returns transaction count from latest ledger."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.return_value = _make_ledger_response()

        result = fetch_xrp_onchain(['tx_count'], 7)

        assert 'raw' in result
        assert 'tx_count' in result['raw']
        assert result['raw']['tx_count']['tx_count_in_latest_ledger'] == 3
        assert result['raw']['tx_count']['latest_validated_ledger'] == '12345678'


def test_fee_metric():
    """Fetching fee returns fee information."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.return_value = _make_fee_response()

        result = fetch_xrp_onchain(['fee'], 7)

        assert 'raw' in result
        assert 'fee' in result['raw']
        assert result['raw']['fee']['open_ledger_fee'] == '12'
        assert result['raw']['fee']['minimum_fee'] == '10'
        assert result['raw']['fee']['median_fee'] == '15'


def test_reserve_metric():
    """Fetching reserve returns reserve and server info."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.return_value = _make_server_info_response()

        result = fetch_xrp_onchain(['reserve'], 7)

        assert 'raw' in result
        assert 'reserve' in result['raw']
        assert result['raw']['reserve']['reserve_base_xrp'] == 10
        assert result['raw']['reserve']['reserve_inc_xrp'] == 2
        assert result['raw']['reserve']['server_state'] == 'full'


def test_string_metrics_input():
    """Single string metric input should be handled correctly."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.return_value = _make_ledger_response()

        result = fetch_xrp_onchain('tx_count', 7)

        assert 'raw' in result
        assert 'tx_count' in result['raw']


def test_unsupported_metrics_fallback():
    """Unsupported metrics should fallback to all metrics."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.side_effect = [
            _make_ledger_response(),
            _make_fee_response(),
            _make_server_info_response(),
        ]

        result = fetch_xrp_onchain(['nonexistent_metric'], 7)

        assert 'raw' in result
        # Should have fetched all metrics since none matched
        assert len(result['raw']) == 5


def test_error_handling():
    """Network errors should return error dict, not raise."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.side_effect = Exception('Network timeout')

        result = fetch_xrp_onchain(['fee'], 7)

        assert 'error' in result
        assert 'fetch_xrp_onchain' in result['error']
        assert 'source' in result
        assert result['content_reference'] == {}


def test_content_reference_structure():
    """Content reference should include required fields."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.return_value = _make_fee_response()

        result = fetch_xrp_onchain(['fee'], 14)

        cr = result['content_reference']
        assert 'endpoints_called' in cr
        assert 'metrics_retrieved' in cr
        assert 'data_time_range' in cr
        assert 'fetched_at' in cr
        assert 'lookback_days=14' in cr['data_time_range']


def test_summary_in_chinese():
    """Summary should be a Chinese-language string."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.return_value = _make_fee_response()

        result = fetch_xrp_onchain(['fee'], 7)

        assert 'XRP' in result['summary']
        assert 'drops' in result['summary']
        assert '；' in result['summary']


def test_return_format_success():
    """Success result should have raw, source, content_reference, summary."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.return_value = _make_fee_response()

        result = fetch_xrp_onchain(['fee'], 7)

        assert set(result.keys()) == {'raw', 'source', 'content_reference', 'summary'}


def test_return_format_error():
    """Error result should have error, source, content_reference."""
    with patch('tools.onchain.requests.post') as mock_post:
        mock_post.side_effect = Exception('fail')

        result = fetch_xrp_onchain(['fee'], 7)

        assert set(result.keys()) == {'error', 'source', 'content_reference'}

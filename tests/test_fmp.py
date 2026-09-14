import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.data.fmp import (
    FmpAcquisitionError,
    FmpRequest,
    acquire_fmp_extracts,
)
from src.data.fmp_transform import FmpTransformError, transform_fmp_manifest
from src.data.trusted_historical import SecurityIdentityInterval


class FakeTransport:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls = 0

    def get_json(self, endpoint: str, parameters: object, token: str) -> object:
        assert token == self.token
        self.calls += 1
        return [{"endpoint": endpoint, "value": 1}]


class RealisticTransport:
    def get_json(self, endpoint: str, parameters: object, token: str) -> object:
        if endpoint == "historical-price-eod/full":
            return [
                {
                    "date": "2020-01-02",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10,
                    "volume": 100,
                }
            ]
        if endpoint == "dividends":
            return [{"date": "2020-01-02", "dividend": 0.2}]
        return [{"symbol": "AAA", "exchange": "NYSE", "delistedDate": "2020-01-02"}]


def _requests() -> tuple[FmpRequest, ...]:
    return (
        FmpRequest("historical-price-eod/full", "SEC", "AAA", date(2020, 1, 1), date(2020, 1, 2)),
        FmpRequest("dividends", "SEC", "AAA", date(2020, 1, 1), date(2020, 1, 2)),
        FmpRequest("delisted-companies", "GLOBAL", ""),
    )


def test_acquisition_is_immutable_resumable_and_secret_free(tmp_path: Path) -> None:
    token = "secret-fmp-token"
    transport = FakeTransport(token)
    arguments = dict(
        token=token,
        transport=transport,
        plan="Basic",
        api_version="stable",
        licence="FMP terms checked 2026-09-13",
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    first = acquire_fmp_extracts(_requests(), tmp_path, **arguments)  # type: ignore[arg-type]
    assert first.successful == 3
    assert token not in first.manifest_path.read_text()
    second = acquire_fmp_extracts(_requests(), tmp_path, **arguments)  # type: ignore[arg-type]
    assert second.resumed == 3
    assert transport.calls == 3


def test_required_endpoints_and_prior_manifest_binding_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(FmpAcquisitionError, match="all required"):
        acquire_fmp_extracts(
            _requests()[:1],
            tmp_path,
            token="token",
            transport=FakeTransport("token"),
            plan="Basic",
            api_version="stable",
            licence="terms",
        )


def test_complete_manifest_transforms_to_content_bound_observations(tmp_path: Path) -> None:
    result = acquire_fmp_extracts(
        _requests(),
        tmp_path,
        token="token",
        transport=RealisticTransport(),
        plan="Basic",
        api_version="stable",
        licence="terms checked",
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
        sleeper=lambda _: None,
    )
    transformed = transform_fmp_manifest(
        result.manifest_path,
        tmp_path,
        identities=(SecurityIdentityInterval("SEC", "AAA", date(2019, 1, 1), None),),
    )
    assert transformed.prices[0].close == 10
    assert transformed.dividends[0].cash_amount == 0.2
    assert transformed.delistings[0].security_id == "SEC"
    assert transformed.provenance.manifest_sha256

    manifest = json.loads(result.manifest_path.read_text())
    price_request = next(
        request
        for request in manifest["requests"]
        if request["endpoint"] == "historical-price-eod/full"
    )
    price_request["parameters"]["from"] = "2019-01-01"
    result.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(FmpTransformError, match="request ID"):
        transform_fmp_manifest(
            result.manifest_path,
            tmp_path,
            identities=(SecurityIdentityInterval("SEC", "AAA", date(2019, 1, 1), None),),
        )

    orphan = tmp_path / "orphan"
    (orphan / "raw").mkdir(parents=True)
    request = _requests()[0]
    from src.data import fmp

    (orphan / "raw" / f"{fmp.fmp_request_id(request)}.json").write_text('[{"value":1}]')
    with pytest.raises(FmpAcquisitionError, match="prior manifest"):
        acquire_fmp_extracts(
            _requests(),
            orphan,
            token="token",
            transport=FakeTransport("token"),
            plan="Basic",
            api_version="stable",
            licence="terms",
        )

import pytest

from tools.update_symbol_directory import parse_master


def row(code: str, name: str, group: str = "ST") -> bytes:
    return (
        (code.ljust(9) + "KR7005930003").encode("ascii")
        + name.encode("cp949").ljust(40)
        + group.encode("ascii")
    )


def test_master_preserves_preferred_names_and_filters_unsupported_codes() -> None:
    payload = b"\n".join(
        [
            row("005930", "삼성전자"),
            row("005935", "삼성전자우"),
            row("069500", "KODEX 200", "EF"),
            row("0001A0", "영문코드"),
            row("123456", "미지원", "EN"),
        ]
    )
    assert parse_master(payload, "KOSPI") == [
        ["005930", "삼성전자", "KOSPI", "주식"],
        ["005935", "삼성전자우", "KOSPI", "주식"],
        ["069500", "KODEX 200", "KOSPI", "ETF"],
    ]


def test_master_rejects_truncation_and_duplicate_identity() -> None:
    with pytest.raises(ValueError, match="TRUNCATED"):
        parse_master(b"bad", "KOSPI")
    with pytest.raises(ValueError, match="DUPLICATE"):
        parse_master(row("005930", "삼성전자") + b"\n" + row("005930", "중복"), "KOSPI")

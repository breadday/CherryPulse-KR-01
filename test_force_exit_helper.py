from __future__ import annotations

from typing import Iterable, Optional


def force_close_all_positions(engine, logger=None, reason: str = "TEST_FORCE_EXIT") -> int:
    """
    테스트 종료 시 남아 있는 포지션을 강제 청산한다.

    사용 예:
        from test_force_exit_helper import force_close_all_positions

        ...
        closed_count = force_close_all_positions(engine, logger=logger)
        logger.info(f"테스트 강제청산 완료 | closed_count={closed_count}")

    동작:
    - engine.portfolio.positions 를 순회
    - qty > 0 인 포지션만 매도 요청
    - engine._submit_auto_sell(symbol, qty, reason) 호출
    - DRY_RUN 환경에서는 on_fill 까지 이어지면 TRADE_CLOSE / CSV 저장으로 연결될 수 있다.

    주의:
    - TradingEngine 구현에 _submit_auto_sell(symbol, qty, reason) 이 있어야 한다.
    - 실제 CSV 저장은 엔진 내부의 fill 처리 및 거래 종료 기록 로직을 따라간다.
    """

    if engine is None:
        raise ValueError("engine is None")

    portfolio = getattr(engine, "portfolio", None)
    if portfolio is None:
        raise ValueError("engine.portfolio 가 없습니다.")

    positions = getattr(portfolio, "positions", {})
    if not isinstance(positions, dict):
        raise ValueError("engine.portfolio.positions 가 dict 형태가 아닙니다.")

    closed_count = 0

    for symbol, pos in list(positions.items()):
        try:
            qty = int(getattr(pos, "qty", 0) or 0)
            if qty <= 0:
                continue

            if logger:
                logger.info(
                    f"테스트 강제청산 요청 | symbol={symbol} qty={qty} reason={reason}"
                )

            engine._submit_auto_sell(symbol=symbol, qty=qty, reason=reason)
            closed_count += 1

        except Exception as e:
            if logger:
                logger.exception(f"테스트 강제청산 실패 | symbol={symbol} err={e}")
            else:
                print(f"[ERROR] 테스트 강제청산 실패 | symbol={symbol} err={e}")

    if logger:
        logger.info(f"테스트 강제청산 완료 | closed_count={closed_count}")

    return closed_count


def force_close_selected_positions(engine, symbols: Iterable[str], logger=None, reason: str = "TEST_FORCE_EXIT") -> int:
    """
    특정 종목만 강제 청산.
    """
    if engine is None:
        raise ValueError("engine is None")

    portfolio = getattr(engine, "portfolio", None)
    if portfolio is None:
        raise ValueError("engine.portfolio 가 없습니다.")

    closed_count = 0
    for symbol in symbols:
        try:
            pos = portfolio.get_position(symbol)
            qty = int(getattr(pos, "qty", 0) or 0)
            if qty <= 0:
                continue

            if logger:
                logger.info(
                    f"선택 강제청산 요청 | symbol={symbol} qty={qty} reason={reason}"
                )

            engine._submit_auto_sell(symbol=symbol, qty=qty, reason=reason)
            closed_count += 1

        except Exception as e:
            if logger:
                logger.exception(f"선택 강제청산 실패 | symbol={symbol} err={e}")
            else:
                print(f"[ERROR] 선택 강제청산 실패 | symbol={symbol} err={e}")

    if logger:
        logger.info(f"선택 강제청산 완료 | closed_count={closed_count}")

    return closed_count

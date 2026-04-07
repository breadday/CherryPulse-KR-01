# test_kiwoom_account.py

import sys
from PyQt5.QtWidgets import QApplication

from broker.kiwoom_broker import KiwoomBroker
from utils.logger import setup_logger


def main():
    app = QApplication(sys.argv)

    logger = setup_logger()
    broker = KiwoomBroker(logger=logger)

    broker.connect()

    print("\n[0] 계좌비밀번호 입력창 열기")
    broker.show_account_window()
    input("계좌비밀번호 저장/확인 후 Enter를 누르세요...")

    print("\n[1] 예수금 조회 시작")
    deposit = broker.get_deposit(password="")
    print(f"deposit = {deposit}")

    print("\n[2] 보유종목 조회 시작")
    positions = broker.get_positions(password="")
    print(f"positions count = {len(positions)}")

    for i, item in enumerate(positions, start=1):
        print(
            f"{i}. "
            f"symbol={item['symbol']} "
            f"name={item['name']} "
            f"qty={item['qty']} "
            f"available_qty={item['available_qty']} "
            f"avg_price={item['avg_price']} "
            f"current_price={item['current_price']} "
            f"eval_pnl={item['eval_pnl']} "
            f"return_pct={item['return_pct']}"
        )

    broker.shutdown()
    app.quit()


if __name__ == "__main__":
    main()
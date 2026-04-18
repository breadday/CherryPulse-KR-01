# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from broker.kiwoom_broker import KiwoomBroker
from utils.logger import setup_logger


OUTPUT_FILE = "condition_list_dump.json"


def main():
    app = QApplication(sys.argv)
    logger = setup_logger("dump_condition_list")
    broker = KiwoomBroker(logger=logger)
    output_path = Path(__file__).resolve().parent / OUTPUT_FILE

    try:
        broker.connect()
        condition_list = broker.load_condition_list()
        rows = [{"index": index, "name": name} for index, name in condition_list]
        output_path.write_text(
            json.dumps({"count": len(rows), "conditions": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"조건식 목록 저장 완료 | path={output_path} count={len(rows)}")
    finally:
        try:
            broker.shutdown()
        except Exception:
            pass
        app.quit()


if __name__ == "__main__":
    main()

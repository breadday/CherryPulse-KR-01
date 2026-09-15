# -*- coding: utf-8 -*-
# save_condition_snapshot.py
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from broker.kiwoom_broker import KiwoomBroker
from utils.logger import setup_logger

CONDITION_NAME = "주도주_스나이퍼"
SNAPSHOT_FILE = "condition_snapshot.json"
MAX_LOG_SYMBOLS = 50


def main():
    app = QApplication(sys.argv)
    logger = setup_logger("save_condition_snapshot")

    base_dir = Path(__file__).resolve().parent
    output_path = base_dir / SNAPSHOT_FILE

    broker = KiwoomBroker(logger=logger)

    try:
        logger.info(f"snapshot 저장 시작 | condition_name={CONDITION_NAME}")
        broker.connect()

        broker.load_condition_list()
        codes = broker.send_condition_by_name(CONDITION_NAME, search=0)

        rows = []
        for code in codes:
            clean_code = str(code).strip()
            if not clean_code:
                continue
            rows.append(
                {
                    "symbol": clean_code,
                    "name": broker.get_code_name(clean_code),
                }
            )

        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "condition_name": CONDITION_NAME,
            "count": len(rows),
            "codes": rows,
        }

        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        display = ", ".join(
            f"{item['symbol']}({item['name']})" for item in rows[:MAX_LOG_SYMBOLS]
        )

        logger.info(
            f"snapshot 저장 완료 | path={output_path} count={len(rows)} "
            f"codes={display if display else '(empty)'}"
        )
    except Exception as e:
        logger.exception(f"snapshot 저장 실패 | err={e}")
        raise
    finally:
        try:
            broker.stop_condition(CONDITION_NAME)
        except Exception:
            pass

        try:
            broker.shutdown()
        except Exception:
            pass

        app.quit()


if __name__ == "__main__":
    main()

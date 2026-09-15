# test_force_exit_helper.py

def force_close_all_positions(engine, logger=None, reason="TEST_FORCE_EXIT"):
    if logger:
        logger.info(
            f"force_close_all_positions 더미 호출 | reason={reason} | closed_count=0"
        )
    return 0
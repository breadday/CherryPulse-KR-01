# config.py

USE_TEST_CONFIG = True   # 👉 True: 테스트 / False: 실전

if USE_TEST_CONFIG:
    from config_test import *
else:
    from config_live import *
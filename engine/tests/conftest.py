"""测试环境统一隔离：绝不允许测试写进用户的真实数据目录。
坑：`engine.app.main` 在 import 时就固定了 DATA_DIR，
所以单独运行某个测试文件时，如果没有先设 MANGJU_DATA_DIR，
就会直接往 `engine/data/mangju.db`（用户真实项目库）里写数据。
之前就踩过：测试夹具清空真实库。现在统一在 conftest 里兜住 ——
本文件一定早于各测试模块被导入，所以这里的设置对所有测试生效。
"""
from __future__ import annotations
import os
import shutil
import tempfile
# 必须在 import engine.app.* 之前设置
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="mangju-test-")
os.environ["MANGJU_DATA_DIR"] = _TEST_DATA_DIR
def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """测试结束后清掉临时目录，别留一堆垃圾在系统临时区。"""
    try:
        shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
    except OSError:
        pass

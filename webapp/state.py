"""
서버 런타임 상태 (프로세스 메모리)
"""
from datetime import datetime

# 오라클 서버 자동매매 봇 상태 (향후 무중단 자동매매용)
AUTOTRADE_STATE = {
    "enabled": False,
    "last_run": None,
    "next_run": "미국 장전 (22:30 KST) / 장마감 (05:00 KST)",
    "status": "IDLE (대기중)",
    "logs": [
        {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "msg": "오라클 웹 서버 엔진 초기화 완료"}
    ],
}

#!/usr/bin/env python3
import asyncio
import aiohttp
from aiohttp import ClientTimeout
from typing import Dict, List, Any, Deque, Set
from collections import deque
import argparse
import json
import os
import signal
import sys
import time

banktrackerurl = "https://api.abc.com/" # Tùy vào tracker của bạn.

should_stop = False

def handle_sigint(*args): # Khi bạn sử dụng Ctrl + C, sẽ đổi flag should_stop = True, tránh gây lỗi kém chính xác khi thoát script đột ngột.
    global should_stop
    should_stop = True
signal.signal(signal.SIGINT, handle_sigint)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, handle_sigint)

def parse_int_amount(s: str) -> int: # Quy đổi amount lấy từ API thành chuỗi số nguyên (int), tránh sai định dạng.
    try:
        return int(str(s or "0").replace(",", "").strip())
    except Exception:
        return 0

async def fetch_banktracker(session: aiohttp.ClientSession, banktrackerurl: str) -> Any: # Fetch API status.
    try:
        async with session.get(banktrackerurl) as resp:
            print(f"[AutoBuy] API status: {resp.status}")
            if resp.status != 200:
                msg = f"Non-200 status: {resp.status}"
                print("[AutoBuy]", msg)
                return {"ok": False, "error": msg}
            try:
                data = await resp.json(content_type=None)
                return {"ok": True, "data": data}
            except Exception as je:
                preview = (await resp.text())[:300]
                msg = f"JSON decode failed: {je}"
                print("[AutoBuy]", msg)
                print("[AutoBuy] Response preview:", preview)
                return {"ok": False, "error": msg, "preview": preview}
    except asyncio.TimeoutError:
        msg = "Bank tracker request timed out"
        print("[AutoBuy]", msg)
        return {"ok": False, "error": msg}
    except aiohttp.ClientError as ce:
        msg = f"Bank tracker client error: {ce}"
        print("[AutoBuy]", msg)
        return {"ok": False, "error": msg}
    except Exception as e:
        msg = f"Fetch error: {e}"
        print("[AutoBuy]", msg)
        return {"ok": False, "error": msg}

async def check_autobuy_once(banktrackerurl: str, expected: Dict[str, int]) -> List[dict]: # Hàm này chỉ check một lần duy nhất nếu bạn seperate out of script.
    timeout = ClientTimeout(total=15, connect=5, sock_read=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        res = await fetch_banktracker(session, banktrackerurl)
    if not res.get("ok"):
        return [res]
    data = res.get("data", {})
    if not isinstance(data, dict) or not data.get("status"):
        print("[AutoBuy] API trả status false hoặc lỗi bất định..")
        return [{"ok": False, "error": "invalid_payload"}]

    txs = data.get("data") or []
    print(f"[AutoBuy] Đã fetch {len(txs)} giao dịch.")

    results = []
    for tx in txs:
        try:
            ref_no = (tx or {}).get("refNo")
            if not ref_no:
                print("[AutoBuy] Skip tx không có refNo")
                results.append({"ok": False, "reason": "no_refno", "tx": tx})
                continue

            debit = parse_int_amount(tx.get("debitAmount"))
            credit = parse_int_amount(tx.get("creditAmount"))
            if debit != 0 or credit <= 0:
                print(f"[AutoBuy] Not an inbound credit tx: refNo={ref_no}, debit={debit}, credit={credit}")
                results.append({"ok": False, "reason": "not_inbound_credit", "refNo": ref_no, "debit": debit, "credit": credit})
                continue

            add_desc = str((tx.get("addDescription") or "")).strip().upper()
            words = add_desc.split()
            if "VNDEV" not in words:
                print(f"[AutoBuy] Thiếu token (Thực tế là nội dung chuyển khoản) 'VNDEV': refNo={ref_no}, desc={add_desc!r}")
                results.append({"ok": False, "reason": "missing_vndev_token", "refNo": ref_no, "desc": add_desc})
                continue

            idx = words.index("VNDEV")
            code = words[idx + 1] if idx + 1 < len(words) else None
            if not (code and len(code) == 6 and code.isalnum()):
                print(f"[AutoBuy] Nội dung chuyển khoản thiếu code static sau token: refNo={ref_no}, code={code!r}")
                results.append({"ok": False, "reason": "invalid_code", "refNo": ref_no, "code": code})
                continue

            expected_amount = int(expected.get(code, 0))
            if expected_amount <= 0:
                print(f"[AutoBuy] Code not in expected map: refNo={ref_no}, code={code}, credit={credit}")
                results.append({"ok": False, "reason": "code_not_expected", "refNo": ref_no, "code": code, "credit": credit})
                continue

            if credit == expected_amount:
                print("Đã thanh toán")
                results.append({"ok": True, "status": "paid", "refNo": ref_no, "code": code, "amount": credit})
            else:
                print(f"[AutoBuy] Giao dịch lệch tiền: refNo={ref_no}, code={code}, expected={expected_amount}, actual={credit}")
                results.append({"ok": False, "reason": "amount_mismatch", "refNo": ref_no, "code": code, "expected": expected_amount, "actual": credit})

        except Exception as ex:
            print(f"[AutoBuy] Error while processing tx item: {ex}")
            results.append({"ok": False, "reason": "exception", "error": str(ex), "tx": tx})
    return results

async def loop_check(banktrackerurl: str, expected: Dict[str, int], interval: int = 10, dedup_size: int = 2000):
    """
    Loop check liên tục, sẽ loại trùng theo refNo.
    - interval: số giây giữa mỗi lần check (poll).
    - dedup_size: max amount refNo được logged để tránh print lặp lại cùng một giao dịch.
    """
    seen: Deque[str] = deque(maxlen=dedup_size)
    timeout = ClientTimeout(total=15, connect=5, sock_read=10)
    print(f"[AutoBuy] Start loop check every {interval}s (dedup last {dedup_size} refNos). Press Ctrl+C to stop.")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while not should_stop:
            t0 = time.time()
            res = await fetch_banktracker(session, banktrackerurl)
            if res.get("ok"):
                data = res.get("data", {})
                if isinstance(data, dict) and data.get("status"):
                    txs = data.get("data") or []
                    print(f"[AutoBuy] Đã track {len(txs)} giao dịch.")
                    for r in await check_autobuy_once(banktrackerurl, expected):
                        # hàm check_autobuy_once đã tự in thông báo rồi, nên ở đây chỉ thực hiện loại trùng các giao dịch "đã thanh toán" dựa trên refNo.
                        ref_no = r.get("refNo")
                        if r.get("ok") and r.get("status") == "paid" and ref_no:
                            if ref_no in seen:
                                # bỏ qua, không print "Đã thanh toán" cho cùng một refNo đã được xử lý trước đó.
                                pass
                            else:
                                seen.append(ref_no)
                else:
                    print("[AutoBuy] API trả status lỗi hoặc lỗi bất định.")
            else:
                pass

            # tạm dừng cho đến lần check tiếp theo, có tính đến time đã pass trong vòng lặp hiện tại.
            elapsed = time.time() - t0
            to_sleep = max(0.0, interval - elapsed)
            await asyncio.sleep(to_sleep)

    print("[AutoBuy] Tạm biệt.")

def load_expected(path: str) -> Dict[str, int]:
    expected = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                expected = json.load(f) or {}
            if not isinstance(expected, dict):
                print("[AutoBuy] expected.json không phải dict, sẽ sử dụng dict rỗng thay thế.")
                expected = {}
        except Exception as e:
            print(f"[AutoBuy] Lỗi khi đọc expected.json: {e}")
    return {str(k).upper(): int(v) for k, v in expected.items() if str(k).strip()}

def main():
    parser = argparse.ArgumentParser(description="Bank tracker autobuy checker.")
    parser.add_argument("--url", default=os.environ.get("banktrackerurl", banktrackerurl), help="Bank tracker history API URL")
    parser.add_argument("--expected", default=os.environ.get("EXPECTED_JSON", "expected.json"), help="Đường dẫn expected.json")
    parser.add_argument("--loop", type=int, default=10, help="Khoảng thời gian giữa các lần kiểm tra (tính bằng giây); nếu đặt <= 0 thì chỉ chạy một lần rồi thoát")
    parser.add_argument("--dedup", type=int, default=2000, help="Ghi nhớ N mã refNo gần nhất để tránh print trùng dòng 'Đã thanh toán' cho cùng một giao dịch nhiều lần")
    args = parser.parse_args()
    # ^ các bạn có thể sử dụng python (scriptname).py --(flag) như script đã hỗ trợ.
    expected = load_expected(args.expected)

    if args.loop and args.loop > 0:
        asyncio.run(loop_check(args.url, expected, interval=args.loop, dedup_size=args.dedup))
    else:
        asyncio.run(check_autobuy_once(args.url, expected))

if __name__ == "__main__":
    main()

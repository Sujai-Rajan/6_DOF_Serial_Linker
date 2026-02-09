#!/usr/bin/env python3
import argparse
import sys

import requests


def depanel_only(op_id, serial_code, url):
    payload = {"op_id": op_id, "sernum": serial_code}
    try:
        r = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if r.status_code >= 400:
            try:
                resp = r.json()
                print(f"Full response: {resp}")
                err = resp.get("error", r.text)
                details = resp.get("details")
                if details:
                    if isinstance(details, list):
                        detail_str = "; ".join(str(d) for d in details if d is not None)
                    else:
                        detail_str = str(details)
                    if detail_str:
                        err = f"{err} | {detail_str}"
            except Exception:
                print(f"Raw response: {r.text}")
                err = r.text
            return False, f"HTTP {r.status_code}: {err}"

        try:
            resp = r.json()
            print(f"Full response: {resp}")
        except Exception:
            print(f"Raw response: {r.text}")
            return False, "Invalid response from server"

        # Error response
        if "error" in resp:
            details = resp.get("details")
            if details:
                if isinstance(details, list):
                    detail_str = "; ".join(str(d) for d in details if d is not None)
                else:
                    detail_str = str(details)
                if detail_str:
                    return False, f"{resp['error']} | {detail_str}"
            return False, str(resp["error"])

        # Success/fail response
        if "linked" in resp:
            ok = bool(resp["linked"])
            msg = resp.get("info") or ""
            details = resp.get("details")
            if details and not ok:
                if isinstance(details, list):
                    detail_str = "; ".join(str(d) for d in details if d is not None)
                else:
                    detail_str = str(details)
                if detail_str:
                    msg = f"{msg} | {detail_str}" if msg else detail_str
            if not msg:
                msg = "Depanel successful" if ok else "Depanel failed"
            return ok, msg

        return False, "Unknown response from server"
    except requests.exceptions.Timeout:
        return False, "Request timed out"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Test depanel-only API")
    parser.add_argument("--op-id", default="TEST_OP", help="Operator ID")
    parser.add_argument(
        "--sernum",
        default="1026054858",
        help="Serial number (left side code)",
    )
    parser.add_argument(
        "--url",
        default="https://web.futaba.com/api/v1/sernums/depanel",
        help="Depanel API URL",
    )
    args = parser.parse_args()


    ok, msg = depanel_only(args.op_id, args.sernum, args.url)
    print(f"ok={ok} msg={msg}")
    return 0 if ok else 1




if __name__ == "__main__":
    sys.exit(main())

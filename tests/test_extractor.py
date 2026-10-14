import unittest
from datetime import datetime

from coolmemo_app.extractor import Message, build_ics, extract_candidates


class ExtractorTests(unittest.TestCase):
    def message(self, body, title="연수 안내"):
        return Message("tbl_recv", 10, "받은 메모", "2026/10/14 09:20:00 (수)", title, "유향기", body)

    def test_extracts_korean_date_time_and_place(self):
        items = extract_candidates(self.message("10월 23일(금) 16:30 국어과 협의회\n장소: 회의실"))
        self.assertEqual(1, len(items))
        self.assertEqual("2026-10-23", items[0]["date"])
        self.assertEqual("16:30", items[0]["time"])
        self.assertEqual("회의실", items[0]["location"])

    def test_extracts_deadline_as_all_day(self):
        items = extract_candidates(self.message("11/2까지 보고서를 제출해 주세요."))
        self.assertEqual("2026-11-02", items[0]["date"])
        self.assertTrue(items[0]["all_day"])

    def test_quoted_history_is_not_duplicated(self):
        body = "확인했습니다.\n홍길동(123)님이 보낸글 >>2026/09/15 19:06:03 (화)\n9/20까지 신청"
        self.assertEqual([], extract_candidates(self.message(body, title="확인했습니다")))

    def test_list_number_is_not_read_as_date(self):
        body = "3. 9/23(수)까지 보고서 제출\n4. 9/24(목) 회의"
        items = extract_candidates(self.message(body))
        self.assertEqual(["2026-09-23", "2026-09-24"], [item["date"] for item in items])

    def test_class_number_is_not_read_as_date(self):
        body = "10월 26일(3-9 홍길동)과 11월 2일(3-9) 감독 변경 신청"
        items = extract_candidates(self.message(body))
        self.assertEqual(["2026-10-26", "2026-11-02"], [item["date"] for item in items])

    def test_ics_contains_timezone_event(self):
        content = build_ics([{
            "uid": "test@local", "title": "협의회", "date": "2026-10-23", "time": "16:30",
            "end_time": "17:30", "all_day": False, "location": "회의실", "description": "담당자: 홍길동",
        }])
        self.assertIn("DTSTART;TZID=Asia/Seoul:20261023T163000", content)
        self.assertIn("LOCATION:회의실", content)


if __name__ == "__main__":
    unittest.main()

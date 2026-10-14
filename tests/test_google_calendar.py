import unittest

from coolmemo_app.google_calendar import event_payload


class GoogleCalendarTests(unittest.TestCase):
    def event(self, **overrides):
        value = {
            "title": "협의회",
            "date": "2026-10-23",
            "time": "",
            "all_day": True,
            "source_table": "tbl_recv",
            "source_key": 10,
            "occurrence_key": "2026-10-23-all-day",
        }
        value.update(overrides)
        return value

    def test_default_reminder_is_none(self):
        payload = event_payload(self.event())
        self.assertEqual({"useDefault": False, "overrides": []}, payload["reminders"])

    def test_calendar_default_reminder_is_preserved_as_option(self):
        payload = event_payload(self.event(reminder_minutes=-1))
        self.assertEqual({"useDefault": True}, payload["reminders"])


if __name__ == "__main__":
    unittest.main()

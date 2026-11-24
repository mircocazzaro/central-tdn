"""First-start administrator registration, manager password and research notice."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

NOTICE = ("Research prototype of the HEREDITARY project. Not a medical device "
          "and not for clinical use. Do not enter personal or patient data.")
GOOD = "correct-horse-7"


class FirstStartTests(TestCase):
    def test_no_user_login_leads_to_setup(self):
        r = Client().get("/login/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].endswith("/setup/"))

    def test_setup_creates_the_administrator_and_signs_in(self):
        c = Client()
        r = c.post("/setup/", {"username": "admin", "password1": GOOD, "password2": GOOD})
        self.assertEqual(r.status_code, 302)
        user = get_user_model().objects.get(username="admin")
        self.assertTrue(user.is_superuser)
        self.assertEqual(c.get("/catalog/").status_code, 200)

    def test_setup_is_closed_once_a_user_exists(self):
        get_user_model().objects.create_user("ana", password=GOOD)
        r = Client().post("/setup/", {"username": "intruder", "password1": GOOD, "password2": GOOD})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(username="intruder").exists())

    def test_setup_checks_the_password(self):
        for p1, p2 in (("short", "short"), (GOOD, "other-one-99"), ("password123", "password123")):
            Client().post("/setup/", {"username": "admin", "password1": p1, "password2": p2})
        self.assertFalse(get_user_model().objects.exists())

    def test_notice_on_login_and_setup_pages(self):
        self.assertContains(Client().get("/setup/"), NOTICE)
        get_user_model().objects.create_user("ana", password=GOOD)
        self.assertContains(Client().get("/login/"), NOTICE)


class ManagerPasswordTests(TestCase):
    def test_manager_is_closed_when_no_password_is_configured(self):
        with override_settings(ENDPOINT_MANAGER_PASSWORD=""):
            r = Client().post("/catalog/manager/", {"manager_password": ""})
        self.assertEqual(r.status_code, 503)

    def test_manager_opens_only_with_the_configured_password(self):
        with override_settings(ENDPOINT_MANAGER_PASSWORD="from-env-123"):
            c = Client()
            bad = c.post("/catalog/manager/", {"manager_password": "supersecret"})
            self.assertContains(bad, "Incorrect password")
            ok = c.post("/catalog/manager/", {"manager_password": "from-env-123"})
            self.assertEqual(ok.status_code, 302)

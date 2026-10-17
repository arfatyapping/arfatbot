import os, tempfile, unittest
from app import app, init_db

class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        os.environ["DATABASE_PATH"] = self.tmp.name
        # app.DB_PATH is read at import time, so this smoke test targets the default instance DB
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        try: os.unlink(self.tmp.name)
        except OSError: pass

    def test_login_page_loads(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sign in", response.data)

if __name__ == "__main__":
    unittest.main()

# Add unit tests
import unittest
from app import app

class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
    
    def test_root_route(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), 'Hello, World! This is your Fly.io server with Postgres!')
    
    def test_gemini_request(self):
        # Test valid request
        response = self.app.post('/gemini_request', 
                                json={'user_input': 'Test message'})
        self.assertEqual(response.status_code, 200) 
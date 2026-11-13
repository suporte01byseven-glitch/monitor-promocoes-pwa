import unittest

import server


class ServerLogicTests(unittest.TestCase):
    def test_clean_url_accepts_http_and_https(self):
        self.assertEqual(server.clean_url('https://example.com/deal'), 'https://example.com/deal')
        self.assertEqual(server.clean_url('http://example.com/deal'), 'http://example.com/deal')

    def test_clean_url_rejects_unsafe_or_malformed_urls(self):
        self.assertEqual(server.clean_url('javascript:alert(1)'), '')
        self.assertEqual(server.clean_url('file:///etc/passwd'), '')
        self.assertEqual(server.clean_url('https://user:pass@example.com/'), '')
        self.assertEqual(server.clean_url('not a url'), '')
        self.assertEqual(server.clean_url('https://example.com/' + 'x' * 2100), '')

    def test_frequency_values(self):
        self.assertEqual(server.frequency_seconds('A cada 15 min'), 900)
        self.assertEqual(server.frequency_seconds('A cada hora'), 3600)
        self.assertEqual(server.frequency_seconds('A cada 6 horas'), 21600)
        self.assertEqual(server.frequency_seconds('Uma vez por dia'), 86400)

    def test_price_rule_only_compares_brl(self):
        item = {'target_price': 100.0, 'min_discount': None}
        self.assertTrue(server.qualifies(item, {'currency': 'BRL', 'price': 99.0, 'discount': 0}))
        self.assertFalse(server.qualifies(item, {'currency': 'USD', 'price': 1.0, 'discount': 0}))

    def test_discount_rule_is_independent(self):
        item = {'target_price': None, 'min_discount': 40.0}
        self.assertTrue(server.qualifies(item, {'currency': 'USD', 'price': 50.0, 'discount': 45.0}))
        self.assertFalse(server.qualifies(item, {'currency': 'USD', 'price': 50.0, 'discount': 20.0}))


if __name__ == '__main__':
    unittest.main()

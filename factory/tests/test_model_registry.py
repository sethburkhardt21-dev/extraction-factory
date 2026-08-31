import unittest
from hermes_factory.model_registry import certification_key, get_status, is_certified

class RegistryAuthorityTests(unittest.TestCase):
    def test_absent_registry_entry_is_unbenchmarked(self):
        reg={"benchmark_version":"B1","certifications":{}}
        key=certification_key("P","M","PRIMARY","W2","S1","B1")
        self.assertEqual(get_status(reg,key),"UNBENCHMARKED")
        self.assertFalse(is_certified(reg,key))

    def test_only_registry_status_controls_certification(self):
        key=certification_key("P","M","PRIMARY","W2","S1","B1")
        reg={"certifications":{key:{"status":"CERTIFIED"}}}
        self.assertTrue(is_certified(reg,key))

if __name__=='__main__': unittest.main()

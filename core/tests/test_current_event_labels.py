"""Every persisted event can be shown without exposing an untranslated key."""
from unittest import TestCase

from verantyx.domain.events import ACTORS
from verantyx.i18n import LANGUAGES, catalog


class CurrentEventLabels(TestCase):
    def test_all_current_events_have_nonempty_labels_in_each_locale(self):
        for locale in LANGUAGES:
            labels = catalog(locale)
            for event in ACTORS:
                with self.subTest(locale=locale, event=event):
                    key = "event." + event
                    self.assertIn(key, labels)
                    self.assertIsInstance(labels[key], str)
                    self.assertTrue(labels[key].strip())
                    self.assertNotEqual(labels[key], key)

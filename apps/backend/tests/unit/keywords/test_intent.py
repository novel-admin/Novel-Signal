from novel_signal.modules.keywords.intent import classify_keyword_intent
from novel_signal.modules.keywords.models import IntentCluster


def classify(text: str) -> IntentCluster:
    return classify_keyword_intent(
        text,
        owned_brands=("Novel",),
        competitor_brands=("Acme",),
        categories=("Baby Wipes", "Diapers"),
    )


def test_intent_classifier_uses_configured_catalogue_vocabulary() -> None:
    assert classify("Novel baby wipes") is IntentCluster.OWN_BRAND
    assert classify("Acme baby wipes") is IntentCluster.COMPETITOR_BRAND
    assert classify("baby wipes") is IntentCluster.GENERIC_CATEGORY
    assert classify("sensitive baby wipes") is IntentCluster.PROBLEM_BENEFIT
    assert classify("unrelated discovery phrase") is IntentCluster.UNCLASSIFIED
